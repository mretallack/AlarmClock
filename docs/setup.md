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
under a device named **"Alarm Clock"** (with the `Device id` sensor showing the
MAC-derived id, e.g. `48e620`). Expect a `switch`, `time`, `select`, several
`number`/`button`/`sensor` entities, plus the diagnostic entities (see
`docs/mqtt-interface.md` §3). HA derives entity_ids from the entity **name**, so
they look like `switch.alarm_enabled`, `time.alarm_time`, `select.alarm_repeat`
— confirm exact ids under Developer Tools → States.

## 4. Add the media_player façade (optional)

Include the Universal Media Player so the radio shows as a real `media_player`:

```yaml
# configuration.yaml
media_player: !include ha/universal_media_player.yaml
```

Duplicate the entry per device and confirm the entity ids. See
`ha/universal_media_player.yaml`. (Requires the radio entities — Track B3.)

## 5. Using it

- **Alarm:** `switch.alarm_enabled`, `time.alarm_time`, `select.alarm_repeat`;
  snooze/dismiss via `button.snooze` / `button.dismiss`.
- **Radio (once available):** `switch.radio`, `select.station`, `number.volume`;
  now-playing on `sensor.now_playing`.
- The alarm **fires on-device even if HA/broker are offline**.

## Testing without hardware

Run the simulator (see `tools/mqtt_sim.py`) to exercise the whole HA side:

```bash
pip install paho-mqtt pyyaml
python3 tools/mqtt_sim.py --host <broker> --device-id b8d61f --name Bedroom
```
