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
    the CST816T touch block is in and **verified** (tap-to-cancel); remaining
    is confirming the panel's rotation/offsets (tasks.md B5).
  - **Codecs:** a top-level `audio: codecs:` block is required. ESPHome only
    compiles the codecs listed there (default: FLAC only), so **MP3 streams fail
    with `ESP_ERR_NOT_SUPPORTED` unless `mp3` is listed**. See `design.md` §10.2.
  - **Setup ordering (I²C):** at equal setup priority ESPHome initialises
    components in the order they appear in the config. The CST816T touch
    controller (which resets and can hold SCL during bring-up) must be declared
    **after** the audio stack, otherwise `es8311.audio_dac` fails to probe
    (`… was marked as failed`). Keep the `touchscreen:` block last.
  - **Cold-boot ES8311 self-heal (2026-11-20):** ordering is **not sufficient
    on a cold power-up** — the codec can still fail to probe (I²C/power race),
    and it `mark_failed()`s with no retry, so there is **no audio path for the
    whole boot** and a ringing alarm is **silent**. Warm (software) reboots
    always re-init the codec. Mitigation: an `esphome: on_boot:` at
    `priority: -100` (`setup_priority::LATE`, i.e. after every component has
    set up) checks `id(es8311_dac).is_failed()` and, if so, does **one** guarded
    warm reboot via `App.safe_reboot()`. The persisted global `g_boot_retries`
    caps it at 2 reboots so a *permanently* dead codec can't reboot-loop; the
    `Audio ok` diagnostic binary_sensor exposes the state to HA. Cold-cycle
    failure rate not yet sized (see `tasks.md` B4).

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
(ES8311/I2S; `Radio` switch + `Station` select + `Volume`), and the **CST816T
touch screen** dismisses a ringing alarm / stops the radio (HA-independent:
tap-to-cancel verified — alarm rings, tap dismisses it and stops playback).
