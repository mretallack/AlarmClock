# Firmware

ESPHome firmware for the alarm clock. See [`design.md`](../design.md) §7/§13 and
[`tasks.md`](../tasks.md).

## Files

- `alarmclock.yaml` — the ESPHome device configuration.
  - **Track A (now):** Wi-Fi/MQTT/time plumbing + alarm & radio entities + the
    on-device alarm engine + the **on-screen clock** (ST7789V, design.md §12.1).
    Validates and compiles without hardware.
  - **Track B (bring-up):** the audio stack (ES8311 + I2S + `media_player`, pins
    per `design.md` §3.2) is wired up and **plays internet radio on hardware**;
    remaining items are the CST816T touch block and confirming the panel's
    rotation/offsets.
  - **Codecs:** a top-level `audio: codecs:` block is required. ESPHome only
    compiles the codecs listed there (default: FLAC only), so **MP3 streams fail
    with `ESP_ERR_NOT_SUPPORTED` unless `mp3` is listed**. See `design.md` §10.2.

## Build / flash

```bash
esphome config  firmware/alarmclock.yaml     # validate schema (no hardware)
esphome compile firmware/alarmclock.yaml    # build the .bin (no hardware)
esphome run     firmware/alarmclock.yaml    # build + flash over USB
esphome run     firmware/alarmclock.yaml --device alarmclock-<id>.local  # OTA
```

Copy `secrets.example.yaml` → `secrets.yaml` and fill it in first.

## `device_id` and topic naming

`device_id` = **last 6 hex of the MAC**, set as a substitution per unit
(this unit: `48e620`). ESPHome names the node `alarmclock-<device_id>` and
namespaces **all** MQTT topics/`unique_id`s by it, so multiple clocks never
collide; it also publishes its own device id on `sensor/device_id/state`.

**Decided (2026-11-20): we use ESPHome's native MQTT scheme as the wire format**
(option (a) in `tasks.md` A3). `docs/mqtt-interface.md` documents exactly what
the device publishes, and `tools/mqtt_sim.py` emits the same scheme. (The
alternative — hand-rolled discovery via `mqtt.publish_json` to match the old
`alarmclock/<id>/...` draft — was dropped.)

## Status

Track A **complete and verified without hardware**; Track B bring-up **in
progress on the first unit** (`48e620`).

- `esphome config` → *Configuration is valid!*
- `esphome compile` → **builds clean**: 15.5 % flash used, 85 % of the app
  partition free (ESP-IDF 5.5, esp32s3) — display + full audio stack.

Alarm + radio entity logic, the on-device alarm engine, Wi-Fi onboarding, the
MQTT layer, the `Device id`/`Firmware` sensors and the **on-screen clock**
(ST7789V: time + date + alarm status) are implemented. On hardware: Wi-Fi/MQTT
up, discovery + command round-trips verified, **internet radio plays**
(ES8311/I2S; `Radio` switch + `Station` select + `Volume`). Touch (CST816T) is
the remaining stubbed block.
