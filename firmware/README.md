# Firmware

ESPHome firmware for the alarm clock. See [`design.md`](../design.md) §7/§13 and
[`tasks.md`](../tasks.md).

## Files

- `alarmclock.yaml` — the ESPHome device configuration.
  - **Track A (now):** Wi-Fi/MQTT/time plumbing + alarm & radio entities + the
    on-device alarm engine. Validates and compiles without hardware.
  - **Track B (bring-up):** the display/touch/audio block at the bottom
    (`# TODO(hardware)`), wired to the pins in `design.md` §3.2.

## Build / flash

```bash
esphome config  firmware/alarmclock.yaml     # validate schema (no hardware)
esphome compile firmware/alarmclock.yaml    # build the .bin (no hardware)
esphome run     firmware/alarmclock.yaml    # build + flash over USB
esphome run     firmware/alarmclock.yaml --device alarmclock-<id>.local  # OTA
```

Copy `secrets.example.yaml` → `secrets.yaml` and fill it in first.

## `device_id` and topic naming

The design (design.md §9.1) derives `device_id` from the **MAC at runtime**.
ESPHome names the *node* at **compile time**, so `alarmclock.yaml` uses a
`device_id` substitution for now (one build per unit) and ESPHome namespaces all
of its MQTT topics by the node name (`alarmclock-<id>`), which keeps multiple
clocks collision-free.

`docs/mqtt-interface.md` is the **canonical MQTT contract** implemented by the
simulator (`tools/mqtt_sim.py`) and intended for any hand-written (ESP-IDF)
implementation. ESPHome's auto-generated topics are functionally equivalent,
namespaced per device but **cosmetically different**.

> **Follow-up (design decision needed):** either (a) accept ESPHome's native MQTT
> topic naming as the firmware's wire format, or (b) implement manual discovery
> via `mqtt.publish_json` lambdas to match `docs/mqtt-interface.md` exactly.
> Tracked in `tasks.md` (A2/A3).

## Status

Track A **complete and verified without hardware**:

- `esphome config` → *Configuration is valid!*
- `esphome compile` → **builds clean**: 12.2 % flash used, 88 % of the app
  partition free (ESP-IDF 5.5, esp32s3).

Alarm + radio entity logic, the on-device alarm engine, Wi-Fi onboarding, the
MQTT layer and the `Device id`/`Firmware` sensors are implemented. The
display/touch/audio block is stubbed (`# TODO(hardware)`) and is wired up in
Track B (B1/B2).
