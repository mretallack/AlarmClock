#!/usr/bin/env python3
"""
Alarm-clock firmware SIMULATOR.

Impersonates a real ESP32-S3-Touch-LCD-1.54 alarm clock over MQTT so the Home
Assistant integration can be built/tested without the board (design.md §9,
tasks.md A6). It implements the SAME wire format the ESPHome firmware actually
publishes (docs/mqtt-interface.md, option (a)):

    discovery : homeassistant/<component>/alarmclock-<id>/<object_id>/config
    state     : alarmclock-<id>/<component>/<object_id>/state
    command   : alarmclock-<id>/<component>/<object_id>/command
    availability: alarmclock-<id>/status   (retained + LWT)

It additionally emits the planned radio entities (switch radio / select station
/ button reboot) so the HA side can be built ahead of the hardware audio work.

Run two instances with different --device-id to prove multi-device support.

Usage:
    pip install paho-mqtt pyyaml
    python3 tools/mqtt_sim.py --host localhost --device-id b8d61f --name Bedroom
    python3 tools/mqtt_sim.py --host localhost --device-id a1c2e3 --name Kitchen
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import signal
import sys
import time

try:
    import paho.mqtt.client as mqtt
except ImportError:  # pragma: no cover
    sys.exit("Missing dependency: pip install paho-mqtt")

from pathlib import Path

DISCOVERY_PREFIX = "homeassistant"
DAYS = ["off", "once", "daily", "weekdays", "weekends", "custom"]


# --------------------------------------------------------------------------- #
# Station loading (tiny YAML subset parser, falls back to pyyaml if present)
# --------------------------------------------------------------------------- #
def load_stations(path: str) -> list[dict]:
    text = Path(path).read_text()
    try:
        import yaml  # type: ignore

        return yaml.safe_load(text)["stations"]
    except ImportError:
        stations, cur = [], None
        for line in text.splitlines():
            s = line.strip()
            if s.startswith("- "):
                cur = {}
                stations.append(cur)
                s = s[2:]
            if not cur or ":" not in s:
                continue
            k, _, v = s.partition(":")
            v = v.strip().strip('"')
            cur[k.strip()] = v
        return stations


# --------------------------------------------------------------------------- #
# Simulator
# --------------------------------------------------------------------------- #
class Sim:
    def __init__(self, args):
        self.device_id = args.device_id.lower()
        self.name = args.name or "Alarm Clock"
        self.fw = args.firmware
        self.stations = load_stations(args.stations)
        self.station_names = [s["name"] for s in self.stations]
        # ESPHome uses node name `alarmclock-<id>` and a 12-hex MAC as dev.ids.
        self.node = f"alarmclock-{self.device_id}"
        self.base = self.node
        self.avail = f"{self.base}/status"
        self.mac = f"000000{self.device_id}"   # 12 hex; last 6 = device_id

        self.state = {
            "alarm_enabled": "OFF",
            "alarm_time": "07:00:00",
            "alarm_days": "daily",
            "alarm_snooze_minutes": 10,
            "alarm_state": "disabled",
            "radio": "OFF",
            "station": self.station_names[0],
            "volume": 30,
            "now_playing": "",
        }

        self.client = mqtt.Client(client_id=self.node)
        if args.username:
            self.client.username_pw_set(args.username, args.password)
        self.client.will_set(self.avail, "offline", retain=True)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.connect(args.host, args.port, keepalive=30)

    # -- helpers ----------------------------------------------------------- #
    def pub(self, topic: str, payload, retain=True):
        self.client.publish(topic, str(payload), retain=retain)

    def state_topic(self, comp: str, obj: str) -> str:
        return f"{self.base}/{comp}/{obj}/state"

    def dev_block(self) -> dict:
        return {
            "ids": self.mac,
            "name": self.name,
            "mf": "Simulator",
            "mdl": "ESP32-S3-Touch-LCD-1.54",
            "sw": self.fw,
            "cns": [["mac", self.mac]],
        }

    def entities(self) -> list[tuple[str, str, dict]]:
        """(component, object_id, extra discovery keys) — mirrors the firmware."""
        return [
            ("switch", "alarm_enabled", {"name": "Alarm enabled"}),
            ("time", "alarm_time", {"name": "Alarm time"}),
            ("select", "alarm_repeat", {"name": "Alarm repeat", "ops": DAYS}),
            ("number", "snooze__min_", {"name": "Snooze (min)", "min": 1, "max": 60, "step": 1}),
            ("number", "volume", {"name": "Volume", "min": 0, "max": 100, "step": 1}),
            ("button", "snooze", {"name": "Snooze"}),
            ("button", "dismiss", {"name": "Dismiss"}),
            ("button", "next_station", {"name": "Next station"}),
            ("button", "previous_station", {"name": "Previous station"}),
            ("sensor", "alarm_state", {"name": "Alarm state"}),
            ("sensor", "now_playing", {"name": "Now playing"}),
            ("sensor", "firmware", {"name": "Firmware", "ent_cat": "diagnostic"}),
            ("sensor", "device_id", {"name": "Device id", "ent_cat": "diagnostic"}),
            ("sensor", "wi-fi_signal", {"name": "Wi-Fi signal", "unit": "dBm",
                                        "dev_cla": "signal_strength", "ent_cat": "diagnostic"}),
            ("binary_sensor", "mqtt", {"name": "MQTT", "dev_cla": "connectivity",
                                       "ent_cat": "diagnostic"}),
            # --- planned (Track B3) — not yet in the firmware ---
            ("switch", "radio", {"name": "Radio"}),
            ("select", "station", {"name": "Station", "ops": self.station_names}),
            ("button", "reboot", {"name": "Reboot", "ent_cat": "config"}),
        ]

    def discovery(self) -> list[tuple[str, str, dict]]:
        """Full discovery payloads: (component, object_id, payload)."""
        dev = self.dev_block()
        avail = {"avty_t": self.avail, "dev": dev}
        out = []
        for comp, obj, extra in self.entities():
            payload = {"uniq_id": f"ESP{comp}{obj}", **avail}
            if comp != "button":
                payload["stat_t"] = self.state_topic(comp, obj)
            if comp in ("switch", "time", "select", "number", "button"):
                payload["cmd_t"] = f"{self.base}/{comp}/{obj}/command"
            # spread extra keys, mapping our short aliases to discovery keys
            for k, v in extra.items():
                payload[{"ops": "ops", "unit": "unit_of_meas",
                         "dev_cla": "dev_cla", "ent_cat": "ent_cat"}.get(k, k)] = v
            out.append((comp, obj, payload))
        return out

    # -- publish helpers --------------------------------------------------- #
    def publish_all_state(self):
        s = self.state
        self.pub(self.state_topic("switch", "alarm_enabled"), s["alarm_enabled"])
        h, m, sec = (int(x) for x in s["alarm_time"].split(":"))
        self.pub(self.state_topic("time", "alarm_time"),
                 json.dumps({"hour": h, "minute": m, "second": sec}))
        self.pub(self.state_topic("select", "alarm_repeat"), s["alarm_days"])
        self.pub(self.state_topic("number", "snooze__min_"),
                 f"{float(s['alarm_snooze_minutes']):.6f}")
        self.pub(self.state_topic("number", "volume"), f"{float(s['volume']):.6f}")
        self.pub(self.state_topic("sensor", "alarm_state"), s["alarm_state"])
        self.pub(self.state_topic("sensor", "now_playing"), s["now_playing"] or "(null)")
        self.pub(self.state_topic("sensor", "firmware"), self.fw)
        self.pub(self.state_topic("sensor", "device_id"), self.device_id)
        self.pub(self.state_topic("sensor", "wi-fi_signal"), -55)
        self.pub(self.state_topic("binary_sensor", "mqtt"), "ON")
        self.pub(self.state_topic("switch", "radio"), s["radio"])
        self.pub(self.state_topic("select", "station"), s["station"])

    def publish_discovery(self):
        for comp, obj, payload in self.discovery():
            topic = f"{DISCOVERY_PREFIX}/{comp}/{self.node}/{obj}/config"
            self.pub(topic, json.dumps(payload))
            print(f"[discovery] {topic}")

    # -- MQTT callbacks ---------------------------------------------------- #
    def on_connect(self, client, userdata, flags, rc):
        print(f"[mqtt] connected rc={rc} as {self.node}")
        self.pub(self.avail, "online")
        self.publish_discovery()
        self.publish_all_state()
        client.subscribe(f"{self.base}/+/+/command")

    def _num(self, payload):
        try:
            return int(float(payload))
        except ValueError:
            return None

    def on_message(self, client, userdata, msg):
        parts = msg.topic.split("/")
        if len(parts) < 4 or not msg.topic.endswith("/command"):
            return
        comp, obj = parts[-3], parts[-2]
        payload = msg.payload.decode().strip()
        print(f"[cmd] {comp}/{obj} = {payload}")
        s = self.state

        if (comp, obj) == ("switch", "alarm_enabled"):
            s["alarm_enabled"] = payload
            s["alarm_state"] = "idle" if payload == "ON" else "disabled"
        elif (comp, obj) == ("time", "alarm_time"):
            try:
                d = json.loads(payload)
                s["alarm_time"] = f"{int(d['hour']):02d}:{int(d['minute']):02d}:{int(d.get('second', 0)):02d}"
            except (ValueError, KeyError):
                return
        elif (comp, obj) == ("select", "alarm_repeat"):
            s["alarm_days"] = payload
        elif (comp, obj) == ("number", "snooze__min_"):
            v = self._num(payload)
            if v is not None:
                s["alarm_snooze_minutes"] = v
        elif (comp, obj) == ("number", "volume"):
            v = self._num(payload)
            if v is not None:
                s["volume"] = v
        elif (comp, obj) == ("button", "snooze"):
            s["alarm_state"] = "snoozed"
        elif (comp, obj) == ("button", "dismiss"):
            s["alarm_state"] = "idle" if s["alarm_enabled"] == "ON" else "disabled"
        elif (comp, obj) == ("switch", "radio"):
            s["radio"] = payload
            s["now_playing"] = s["station"] if payload == "ON" else ""
        elif (comp, obj) == ("select", "station"):
            s["station"] = payload
            if s["radio"] == "ON":
                s["now_playing"] = payload
        elif (comp, obj) in (("button", "next_station"), ("button", "previous_station")):
            step = 1 if obj == "next_station" else -1
            i = self.station_names.index(s["station"])
            s["station"] = self.station_names[(i + step) % len(self.station_names)]
            if s["radio"] == "ON":
                s["now_playing"] = s["station"]
        elif (comp, obj) == ("button", "reboot"):
            print("[sim] reboot requested (simulated)")

        self.publish_all_state()

    # -- alarm scheduling -------------------------------------------------- #
    def tick(self):
        if self.state["alarm_enabled"] != "ON":
            return
        now = dt.datetime.now()
        if (self.state["alarm_state"] == "idle"
                and now.strftime("%H:%M:00") == self.state["alarm_time"]):
            self.state["alarm_state"] = "ringing"
            self.pub(self.state_topic("sensor", "alarm_state"), "ringing")
            print("[sim] ALARM RINGING")

    def run(self):
        self.client.loop_start()
        try:
            while True:
                self.tick()
                time.sleep(1)
        finally:
            self.client.loop_stop()


def main():
    p = argparse.ArgumentParser(description="Alarm clock MQTT simulator")
    p.add_argument("--host", default="localhost")
    p.add_argument("--port", type=int, default=1883)
    p.add_argument("--device-id", required=True,
                   help="short id, e.g. last 6 hex of MAC (b8d61f)")
    p.add_argument("--name", default=None, help="friendly device name")
    p.add_argument("--firmware", default="sim-0.1.0")
    p.add_argument("--stations", default=str(Path(__file__).parent.parent / "data/stations.yaml"))
    p.add_argument("--username", default=None)
    p.add_argument("--password", default=None)
    args = p.parse_args()

    sim = Sim(args)
    signal.signal(signal.SIGINT, lambda *_: sys.exit(0))
    sim.run()


if __name__ == "__main__":
    main()
