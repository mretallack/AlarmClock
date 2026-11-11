#!/usr/bin/env python3
"""
Alarm-clock firmware SIMULATOR.

Impersonates a real ESP32-S3-Touch-LCD-1.54 alarm clock over MQTT so the entire
Home Assistant integration can be built and tested **before the hardware exists**
(design.md §9, tasks.md A6).

It implements the contract in docs/mqtt-interface.md: publishes MQTT discovery,
availability (with LWT), and state; subscribes to command topics and reacts.

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
import threading
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
            if v:
                cur[k.strip()] = int(v) if v.isdigit() else v
        return stations


# --------------------------------------------------------------------------- #
# Simulator
# --------------------------------------------------------------------------- #
class Sim:
    def __init__(self, args):
        self.device_id = args.device_id.lower()
        self.name = args.name or f"Alarm Clock {self.device_id}"
        self.fw = args.firmware
        self.stations = load_stations(args.stations)
        self.station_names = [s["name"] for s in self.stations]
        self.base = f"alarmclock/{self.device_id}"
        self.avail = f"{self.base}/status"
        self.node = f"alarmclock_{self.device_id}"

        self.state = {
            "alarm_enabled": "OFF",
            "alarm_time": "07:00:00",
            "alarm_days": "daily",
            "alarm_snooze_minutes": 10,
            "alarm_state": "disabled",
            "alarm_next": "",
            "radio": "OFF",
            "station": self.station_names[0],
            "volume": 30,
            "now_playing": "",
        }

        self.client = mqtt.Client(client_id=self.node)
        if args.username:
            self.client.username_pw_set(args.username, args.password)
        # Last Will -> HA marks us offline if we vanish
        self.client.will_set(self.avail, "offline", retain=True)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.connect(args.host, args.port, keepalive=30)

    # -- helpers ----------------------------------------------------------- #
    def pub(self, topic: str, payload, retain=True):
        self.client.publish(topic, str(payload), retain=retain)

    def dev_block(self) -> dict:
        return {
            "ids": f"alarmclock-{self.device_id}",
            "name": self.name,
            "mf": "Custom",
            "mdl": "ESP32-S3-Touch-LCD-1.54",
            "sw": self.fw,
        }

    def discovery(self) -> list[tuple[str, str, dict]]:
        d, nid = self.dev_block(), self.node
        avail = {"avty_t": self.avail, "dev": d}
        uid = lambda role: f"{self.node}_{role}"  # noqa: E731
        t = lambda role: f"{self.base}/{role}"  # noqa: E731
        out = [
            ("switch", "alarm_enabled", {
                "name": "Alarm enabled", "uniq_id": uid("alarm_enabled"),
                "cmd_t": t("alarm/enabled/set"), "stat_t": t("alarm/enabled/state"),
                "ic": "mdi:alarm", **avail}),
            ("time", "alarm_time", {
                "name": "Alarm time", "uniq_id": uid("alarm_time"),
                "cmd_t": t("alarm/time/set"), "stat_t": t("alarm/time/state"),
                "ic": "mdi:clock-outline", **avail}),
            ("select", "alarm_days", {
                "name": "Alarm repeat", "uniq_id": uid("alarm_days"),
                "cmd_t": t("alarm/days/set"), "stat_t": t("alarm/days/state"),
                "options": DAYS, "ic": "mdi:calendar-week", **avail}),
            ("number", "alarm_snooze_minutes", {
                "name": "Snooze (min)", "uniq_id": uid("alarm_snooze_minutes"),
                "cmd_t": t("alarm/snooze_minutes/set"),
                "stat_t": t("alarm/snooze_minutes/state"),
                "min": 1, "max": 60, "step": 1, "unit_of_meas": "min",
                "ic": "mdi:timer-snooze", **avail}),
            ("button", "alarm_snooze", {
                "name": "Snooze", "uniq_id": uid("alarm_snooze"),
                "cmd_t": t("alarm/snooze/cmd"), "ic": "mdi:sleep", **avail}),
            ("button", "alarm_dismiss", {
                "name": "Dismiss", "uniq_id": uid("alarm_dismiss"),
                "cmd_t": t("alarm/dismiss/cmd"), "ic": "mdi:alarm-off", **avail}),
            ("sensor", "alarm_state", {
                "name": "Alarm state", "uniq_id": uid("alarm_state"),
                "stat_t": t("alarm/state"), "ic": "mdi:alarm-bell", **avail}),
            ("sensor", "alarm_next", {
                "name": "Next alarm", "uniq_id": uid("alarm_next"),
                "stat_t": t("alarm/next"), "dev_cla": "timestamp",
                "ic": "mdi:clock-check", **avail}),
            ("switch", "radio", {
                "name": "Radio", "uniq_id": uid("radio"),
                "cmd_t": t("radio/power/set"), "stat_t": t("radio/power/state"),
                "ic": "mdi:radio", **avail}),
            ("select", "station", {
                "name": "Station", "uniq_id": uid("station"),
                "cmd_t": t("radio/station/set"), "stat_t": t("radio/station/state"),
                "options": self.station_names, "ic": "mdi:radio-tower", **avail}),
            ("number", "volume", {
                "name": "Volume", "uniq_id": uid("volume"),
                "cmd_t": t("radio/volume/set"), "stat_t": t("radio/volume/state"),
                "min": 0, "max": 100, "step": 1, "unit_of_meas": "%",
                "ic": "mdi:volume-high", **avail}),
            ("button", "next_station", {
                "name": "Next station", "uniq_id": uid("next_station"),
                "cmd_t": t("radio/next/cmd"), "ic": "mdi:skip-next", **avail}),
            ("button", "prev_station", {
                "name": "Previous station", "uniq_id": uid("prev_station"),
                "cmd_t": t("radio/prev/cmd"), "ic": "mdi:skip-previous", **avail}),
            ("sensor", "now_playing", {
                "name": "Now playing", "uniq_id": uid("now_playing"),
                "stat_t": t("radio/now_playing"), "ic": "mdi:music-note", **avail}),
            ("sensor", "ip", {
                "name": "IP", "uniq_id": uid("ip"), "stat_t": t("device/ip"),
                "ic": "mdi:ip", **avail}),
            ("sensor", "rssi", {
                "name": "Wi-Fi signal", "uniq_id": uid("rssi"),
                "stat_t": t("device/rssi"), "unit_of_meas": "dBm",
                "dev_cla": "signal_strength", "ent_cat": "diagnostic",
                "ic": "mdi:wifi", **avail}),
            ("sensor", "firmware", {
                "name": "Firmware", "uniq_id": uid("firmware"),
                "stat_t": t("device/firmware"), "ent_cat": "diagnostic",
                "ic": "mdi:chip", **avail}),
            ("sensor", "device_id", {
                "name": "Device id", "uniq_id": uid("device_id"),
                "stat_t": t("device/id"), "ent_cat": "diagnostic",
                "ic": "mdi:identifier", **avail}),
            ("binary_sensor", "mqtt", {
                "name": "MQTT", "uniq_id": uid("mqtt"), "stat_t": t("device/mqtt"),
                "dev_cla": "connectivity", "ent_cat": "diagnostic",
                "ic": "mdi:server-network", **avail}),
            ("button", "reboot", {
                "name": "Reboot", "uniq_id": uid("reboot"),
                "cmd_t": t("device/reboot/cmd"), "ent_cat": "config",
                "ic": "mdi:restart", **avail}),
        ]
        return out

    # -- publish helpers --------------------------------------------------- #
    def publish_all_state(self):
        s = self.state
        self.pub(f"{self.base}/alarm/enabled/state", s["alarm_enabled"])
        self.pub(f"{self.base}/alarm/time/state", s["alarm_time"])
        self.pub(f"{self.base}/alarm/days/state", s["alarm_days"])
        self.pub(f"{self.base}/alarm/snooze_minutes/state", s["alarm_snooze_minutes"])
        self.pub(f"{self.base}/alarm/state", s["alarm_state"])
        self.pub(f"{self.base}/alarm/next", s["alarm_next"])
        self.pub(f"{self.base}/radio/power/state", s["radio"])
        self.pub(f"{self.base}/radio/station/state", s["station"])
        self.pub(f"{self.base}/radio/volume/state", s["volume"])
        self.pub(f"{self.base}/radio/now_playing", s["now_playing"])
        self.pub(f"{self.base}/device/ip", "192.168.0.50")
        self.pub(f"{self.base}/device/rssi", -55)
        self.pub(f"{self.base}/device/firmware", self.fw)
        self.pub(f"{self.base}/device/id", self.device_id)
        self.pub(f"{self.base}/device/mqtt", "online")

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
        for sub in (f"{self.base}/alarm/+/set", f"{self.base}/alarm/+/cmd",
                    f"{self.base}/radio/+/set", f"{self.base}/radio/+/cmd",
                    f"{self.base}/device/+/cmd"):
            client.subscribe(sub)

    def on_message(self, client, userdata, msg):
        topic = msg.topic
        payload = msg.payload.decode().strip()
        print(f"[cmd] {topic} = {payload}")
        s = self.state
        if topic.endswith("alarm/enabled/set"):
            s["alarm_enabled"] = payload
            s["alarm_state"] = "idle" if payload == "ON" else "disabled"
            self.pub(f"{self.base}/alarm/state", s["alarm_state"])
        elif topic.endswith("alarm/time/set"):
            s["alarm_time"] = payload
        elif topic.endswith("alarm/days/set"):
            s["alarm_days"] = payload
        elif topic.endswith("alarm/snooze_minutes/set"):
            s["alarm_snooze_minutes"] = int(payload)
        elif topic.endswith("alarm/snooze/cmd"):
            s["alarm_state"] = "snoozed"
            self.pub(f"{self.base}/alarm/state", "snoozed")
        elif topic.endswith("alarm/dismiss/cmd"):
            s["alarm_state"] = "idle" if s["alarm_enabled"] == "ON" else "disabled"
            self.pub(f"{self.base}/alarm/state", s["alarm_state"])
        elif topic.endswith("radio/power/set"):
            s["radio"] = payload
            s["now_playing"] = s["station"] if payload == "ON" else ""
            self.pub(f"{self.base}/radio/power/state", s["radio"])
            self.pub(f"{self.base}/radio/now_playing", s["now_playing"])
        elif topic.endswith("radio/station/set"):
            s["station"] = payload
            if s["radio"] == "ON":
                s["now_playing"] = payload
                self.pub(f"{self.base}/radio/now_playing", payload)
        elif topic.endswith("radio/volume/set"):
            s["volume"] = int(payload)
        elif topic.endswith("radio/next/cmd") or topic.endswith("radio/prev/cmd"):
            i = self.station_names.index(s["station"])
            step = 1 if topic.endswith("next/cmd") else -1
            s["station"] = self.station_names[(i + step) % len(self.station_names)]
            self.pub(f"{self.base}/radio/station/state", s["station"])
            if s["radio"] == "ON":
                s["now_playing"] = s["station"]
                self.pub(f"{self.base}/radio/now_playing", s["station"])
        elif topic.endswith("device/reboot/cmd"):
            print("[sim] reboot requested (simulated)")
        # reflect the changed value back on its /state topic
        self.publish_all_state()

    # -- alarm scheduling -------------------------------------------------- #
    def tick(self):
        if self.state["alarm_enabled"] != "ON":
            return
        now = dt.datetime.now()
        if (self.state["alarm_state"] == "idle"
                and now.strftime("%H:%M:00") == self.state["alarm_time"]):
            self.state["alarm_state"] = "ringing"
            self.pub(f"{self.base}/alarm/state", "ringing")
            print("[sim] ALARM RINGING")
        nxt = now.replace(hour=int(self.state["alarm_time"][:2]),
                          minute=int(self.state["alarm_time"][3:5]),
                          second=0, microsecond=0)
        if nxt <= now:
            nxt += dt.timedelta(days=1)
        self.pub(f"{self.base}/alarm/next", nxt.isoformat())

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
