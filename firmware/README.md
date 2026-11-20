# Firmware

ESPHome firmware for the alarm clock. See [`design.md`](../design.md) §7/§13 and
[`tasks.md`](../tasks.md).

## Files

- `alarmclock.yaml` — the ESPHome device configuration.
  - **Track A (now):** Wi-Fi/MQTT/time plumbing + alarm & radio entities + the
    on-device alarm engine + the **on-screen clock** (ST7789V, design.md §12.1).
    Validates and compiles without hardware.
  - **Track B (bring-up):** the touch/audio block at the bottom
    (`# TODO(hardware)`), wired to the pins in `design.md` §3.2, plus confirming
    the panel's rotation/offsets.

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

Track A **complete and verified without hardware**:

- `esphome config` → *Configuration is valid!*
- `esphome compile` → **builds clean**: 13.1 % flash used, 87 % of the app
  partition free (ESP-IDF 5.5, esp32s3).

Alarm + radio entity logic, the on-device alarm engine, Wi-Fi onboarding, the
MQTT layer, the `Device id`/`Firmware` sensors and the **on-screen clock**
(ST7789V: time + date + alarm status) are implemented. The touch/audio block is
stubbed (`# TODO(hardware)`) and is wired up in Track B (B1/B2/B5).
