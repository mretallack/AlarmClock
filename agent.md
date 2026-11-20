# agent.md — working notes for AI/dev agents

Orientation for an autonomous agent (or a new human) picking up this repo. Read
this first, then `design.md`, `tasks.md`, and `docs/mqtt-interface.md`.

## What this project is

A **bedside Internet-radio alarm clock** built on a Waveshare
**ESP32-S3-Touch-LCD-1.54-EN** (1.54" 240×240 capacitive-touch LCD, square white
molded case, USB-C on the bottom edge). It runs **ESPHome** firmware that:

- streams Internet radio (ES8311 codec + I2S amp),
- runs an **on-device alarm engine** (schedules, wake ramp) that works **without
  Home Assistant**,
- shows an on-screen clock, and
- integrates with **Home Assistant** over **MQTT** (native ESPHome MQTT scheme).

The design rationale lives in [`design.md`](./design.md); the actionable list is
[`tasks.md`](./tasks.md) (Track A = no hardware, Track B = hardware).

## How to access the device (first unit, `device_id` = `48e620`)

The board is flashed, on Wi-Fi, and publishes MQTT. It is **fully reachable over
the network — no USB cable needed.**

| | |
|---|---|
| **mDNS name** | `alarmclock-48e620.local` |
| **LAN IP** | `10.0.0.97` (DHCP — prefer the `.local` name over the IP) |
| **OTA port** | `3232` (ESPHome `ota:` platform, password in `firmware/secrets.yaml`) |
| **API** | ESPHome native API, encryption key in `secrets.yaml` |
| **MQTT broker** | HA Mosquitto add-on at `10.0.0.10:1883` (creds in `secrets.yaml`) |
| **Node / topic prefix** | `alarmclock-48e620` |

Credentials live in **`firmware/secrets.yaml`** (git-ignored). Copy from
[`secrets.example.yaml`](./secrets.example.yaml). **Never commit real secrets.**

### Common commands (run from `firmware/`)

```bash
esphome config  alarmclock.yaml                     # validate schema
esphome compile alarmclock.yaml                     # build .bin (no hardware)
esphome logs    alarmclock.yaml --device alarmclock-48e620.local   # live logs
esphome run     alarmclock.yaml --device alarmclock-48e620.local   # build + OTA flash
esphome run     alarmclock.yaml                     # USB flash (first time only)
```

OTA is verified (~10 s, compressed/deflate, "OTA successful"). Prefer it; only
use USB for the very first flash or if the app is bricked.

Connectivity check:

```bash
avahi-resolve -a alarmclock-48e620.local            # → 10.0.0.97
python3 -c "import socket;s=socket.socket();s.settimeout(2);s.connect(('10.0.0.97',3232));print('OTA port open')"
```

## Repository layout

```
firmware/    alarmclock.yaml (ESPHome config) + README + secrets.yaml (untracked)
docs/        mqtt-interface.md (firmware↔HA wire contract), setup.md,
             devices.md (unit ↔ id ↔ label inventory), stand-handoff.md, images/
ha/          Home Assistant snippets (Universal Media Player)
data/        stations.yaml — Internet radio station list
tools/       mqtt_sim.py — device simulator (test the HA side without hardware)
backups/     factory firmware .bin dumps (recovery)
.github/     CI — validates + compiles the firmware with no device
design.md    full design doc (hardware, architecture, MQTT, UI, roadmap)
tasks.md     Track A / Track B task breakdown
```

## Current status

**Track A complete** (built + verified without hardware). **Track B in progress
on the first unit:**

- ✅ Flashed, on Wi-Fi, in MQTT; discovery + command round-trips verified.
- ✅ Internet radio plays (ES8311/I2S) — `Radio` switch, `Station` select, `Volume`.
- ✅ CST816T touch dismisses a ringing alarm / stops the radio (HA-independent).
- ✅ On-screen clock (ST7789V) implemented.
- ✅ OTA verified.

**Still open (see `tasks.md` for the live list):** alarm reliability with HA
**offline** + NVS/DST persistence + RTC across power loss (highest risk),
on-device station soak, LVGL/idle UI, watchdog/backoff, OTA safe rollback,
72 h soak. Decisions still open: **D6** (missed-alarm policy after power loss).

## Gotchas learned on hardware (don't regress these)

- **Audio codecs:** ESPHome only compiles codecs listed under a top-level
  `audio: codecs:` block (default FLAC only). **MP3 streams fail with
  `ESP_ERR_NOT_SUPPORTED`** unless `mp3` is listed. → `design.md` §10.2.
- **I²C setup ordering:** the `touchscreen:` (CST816T) block **must be declared
  after** the audio stack, or `es8311.audio_dac` fails to probe. Keep it last.
- **MQTT DNS stall:** ESPHome's MQTT client does its first DNS lookup before
  Wi-Fi/DNS is ready → ~25 s stall per boot. **Point `mqtt_broker` at the broker's
  LAN IP**, not a hostname.
- **HA alarm time format:** ESPHome's `time` entity uses JSON; HA's `time`
  platform uses ISO `HH:MM:SS`. Handled with a custom ISO-format entity (see
  `docs/mqtt-interface.md` §3).

## Conventions

- `device_id` = **last 6 hex of the Wi-Fi MAC**, set as an ESPHome substitution
  per unit (this unit `48e620`). ESPHome names the node `alarmclock-<device_id>`
  and namespaces **all** MQTT topics/`unique_id`s by it, so multiple clocks never
  collide. Record new units in `docs/devices.md`.
- **Wire format = ESPHome's native MQTT scheme** (decided 2026-11-20).
  `docs/mqtt-interface.md` is the contract; `tools/mqtt_sim.py` and `ha/` match it.
- Keep full MAC addresses out of public commits/screenshots.
- TODO: rotate the placeholder `ota_password`/`api_key` before this device leaves
  a trusted LAN (see README TODO).

## Safety

- OTA reflashing is quick and idempotent; the same config is safe to re-upload.
- `backups/` holds the vendor factory `.bin` for recovery — don't delete it.
- Secrets stay local; never commit `firmware/secrets.yaml`.
