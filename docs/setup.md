# Setup guide

How to get a deployed alarm clock talking to Home Assistant. See
[`design.md`](../design.md) and [`docs/mqtt-interface.md`](mqtt-interface.md).

## 1. Home Assistant prerequisites

- **MQTT integration** + the **Mosquitto broker** add-on
  (Settings → Devices & Services → Add Integration → MQTT).
- **Discovery prefix:** `homeassistant` (HA default).
- Note the broker **host/port and a username/password** for the device.

## 2. Build & flash the firmware

```bash
cp secrets.example.yaml secrets.yaml     # fill in Wi-Fi + MQTT creds
esphome run firmware/alarmclock.yaml     # USB first time
```

First-time Wi-Fi: use **Improv via serial** from the ESPHome Dashboard (or the
web installer) — no app needed. If it can't connect it raises a fallback hotspot
(captive portal at http://192.168.4.1).

## 3. Confirm in Home Assistant

On connect, the device publishes MQTT discovery; entities appear automatically
(one HA device per clock, named `alarmclock-<device_id>`). Expect a `switch`,
`time`, `select`, several `number`/`button`/`sensor` entities, plus the
diagnostic entities (see `docs/mqtt-interface.md` §3).

## 4. Add the media_player façade (optional)

Include the Universal Media Player so the radio shows as a real `media_player`:

```yaml
# configuration.yaml
media_player: !include ha/universal_media_player.yaml
```

Duplicate the entry per device (replace the id). See `ha/universal_media_player.yaml`.

## 5. Using it

- **Alarm:** `switch.alarmclock_<id>_alarm_enabled`, `time...._alarm_time`,
  `select...._alarm_days`; snooze/dismiss via the buttons.
- **Radio:** `switch...._radio`, `select...._station`, `number...._volume`;
  now-playing on the sensor.
- The alarm **fires on-device even if HA/broker are offline**.

## Testing without hardware

Run the simulator (see `tools/mqtt_sim.py`) to exercise the whole HA side:

```bash
pip install paho-mqtt pyyaml
python3 tools/mqtt_sim.py --host <broker> --device-id b8d61f --name Bedroom
```
