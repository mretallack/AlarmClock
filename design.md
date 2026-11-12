# AlarmClock — Design Document

**A Home Assistant–integrated Internet radio alarm clock on the Waveshare
ESP32-S3-Touch-LCD-1.54**

- Status: **Design / discovery — no implementation started**
- Target hardware: Waveshare ESP32-S3-Touch-LCD-1.54 (ESP32-S3R8)
- Integration: Home Assistant via **MQTT** using **MQTT discovery**
- Author: Mark Retallack
- Last updated: 2026-11-11

---

## 1. Table of contents

1. [Goal & scope](#2-goal--scope)
2. [Hardware](#3-hardware)
3. [Existing solutions — does a firmware already exist?](#4-existing-solutions--does-a-firmware-already-exist)
4. [The MQTT / Home Assistant integration model](#5-the-mqtt--home-assistant-integration-model)
5. [Feature / entity model](#6-feature--entity-model)
6. [Architecture options](#7-architecture-options)
7. [Recommended architecture](#8-recommended-architecture)
8. [MQTT topic & discovery design](#9-mqtt-topic--discovery-design)
9. [Audio / Internet radio design](#10-audio--internet-radio-design)
10. [Time, alarms & scheduling](#11-time-alarms--scheduling)
11. [UI / UX (display + touch)](#12-ui--ux-display--touch)
12. [Toolchain, build & flashing](#13-toolchain-build--flashing)
13. [Provisioning & OTA updates](#14-provisioning--ota-updates)
14. [Risks & mitigations](#15-risks--mitigations)
15. [Testing plan](#16-testing-plan)
16. [Roadmap / milestones](#17-roadmap--milestones)
17. [Open questions](#18-open-questions)
18. [References](#19-references)

---

## 2. Goal & scope

Build custom firmware for the Waveshare ESP32-S3-Touch-LCD-1.54 board that turns
it into a **radio alarm clock** fully controllable from Home Assistant over MQTT
with MQTT discovery.

### In scope

- Wake-to-radio alarm clock with on-device display and touch controls.
- Home Assistant can: set alarm time(s), enable/disable the alarm, choose days
  of week, control the radio (on/off, station, volume), snooze/dismiss.
- Streaming Internet radio from a curated, user-defined station list.
- Local time via NTP; alarm logic robust to reboots / network loss.
- Discovered and configured in HA purely by MQTT discovery (no manual YAML
  required for core entities).

### Out of scope (for v1)

- Spotify / media-library playback (only Internet radio streams).
- Voice assistant / wake word.
- Multi-room / synchronised audio.
- Battery-powered portable operation (board variant ordered is "No Battery";
  mains USB-C power is assumed and is the right choice for a bedside clock).

### Non-functional requirements

- **Reliability is paramount** — an alarm clock that fails to ring is useless.
  Must survive Wi-Fi blips, broker restarts, brown-outs and OTA reboots.
- Boot-to-ready (clock visible) within a few seconds.
- Alarm must fire even if Home Assistant / the broker is offline (local alarm
  scheduling on-device, not dependent on HA to "send the ring command").
- Reasonable audio quality from the onboard ES8311 DAC + small speaker.

---

## 3. Hardware

### 3.1 Board overview

The **ESP32-S3-Touch-LCD-1.54** is a compact Waveshare dev board. The ordered
SKU (Amazon UK `B0GS9CW66Z`) is described as:

> "Waveshare ESP32-S3-Touch-LCD-1.54-EN, ESP32-S3 1.54inch LCD Display
> Development Board, 240 x 240 Resolution, 262K Color, Supports Dual
> Microphones, 2.4GHz Wi-Fi And BLE 5, **No Battery**"

| Part | Detail |
|------|--------|
| MCU | ESP32-S3R8 — dual-core Xtensa LX7 @ 240 MHz |
| Memory | 8 MB PSRAM (Octal), 16 MB Flash |
| Wireless | 2.4 GHz Wi-Fi (b/g/n), Bluetooth 5 LE |
| Display | 1.54" 240×240 capacitive touch LCD |
| Display driver | **ST7789V2** (SPI) |
| Touch controller | **CST816T** (I²C) |
| Audio codec (out) | **ES8311** mono DAC/codec (I²C + I²S) |
| Audio codec (in) | **ES7210** 4-ch ADC (dual/quad mic array) |
| Speaker amp enable | `PA_CTRL` GPIO 7 |
| IMU | **QMI8658** 6-axis (accel + gyro), I²C |
| RTC | Onboard RTC (investigate exact part — see Open Questions) |
| Storage | microSD (TF) card slot |
| Power | USB-C; LiPo battery connector + charger (battery not included) |
| Case | **Custom-molded square plastic case (included in the `-EN` variant)** — device arrives enclosed and bedside-ready |

> ✅ The ordered variant **includes a square plastic case**, so the device is
> already enclosed (no separate enclosure needed for v1). Confirm the case's
> cut-outs (speaker grille, USB-C, touch access) during bring-up (§17 M0), and
> confirm whether an onboard speaker is fitted behind the grille (§3.3, §18).
> A photo of the case is stored in the repo at `docs/images/` and shown in the
> [README](README.md).

> ⚠️ The GitHub README lists "an RTC". It is **not yet confirmed** whether this
> is a discrete I²C RTC chip (e.g. PCF85063) or simply the ESP32-S3 internal
> RTC domain. This matters for keeping time across power loss — see §11 and §18.

### 3.2 Pin map (from Waveshare ESP-IDF BSP + Arduino examples)

Source: `examples/.../ESP-IDF-5.5.1/01_factory/components/esp_bsp/*` and
`examples/.../Arduino-3.2.0/examples/01_i2s_audio/*` in the
[Waveshare repo](https://github.com/waveshareteam/ESP32-S3-Touch-LCD-1.54).

**Display — ST7789V2 over SPI**

| Signal | GPIO |
|--------|------|
| SPI MOSI | 39 |
| SPI SCLK | 38 |
| LCD CS | 21 |
| LCD DC | 45 |
| LCD RST | 40 |
| LCD Backlight (BL) | 46 |

**Shared I²C bus** (touch + codecs + IMU)

| Signal | GPIO |
|--------|------|
| I²C SDA | 42 |
| I²C SCL | 41 |

**Touch — CST816T**

| Signal | GPIO |
|--------|------|
| Touch INT | 48 |
| Touch RST | 47 |

**Audio — ES8311 (out) / ES7210 (in) over I²S**

| Signal | GPIO |
|--------|------|
| I²S MCLK | 8 |
| I²S BCLK | 9 |
| I²S LRCK/WS | 10 |
| I²S DOUT (ESP → codec) | 12 |
| I²S DIN (codec → ESP, mic) | 11 |
| PA_CTRL (speaker amp enable) | 7 |

I²C addresses: **ES8311 = 0x18** (CE low) / 0x19; ES7210 = 0x40 (typical).

> These values are taken from vendor example code and **must be verified
> against the official schematic**
> (`ESP32-S3-Touch-LCD-1.54.pdf`, linked from the Waveshare docs "Resources and
> Documents" page) before we commit to them. See §18.

### 3.3 Accessories to budget for

| Item | Why | Notes |
|------|-----|-------|
| microSD card | Optional; station list, tones, album art on-device | Small (≤32 GB, FAT32) |
| Speaker (8Ω, ~2–3 W) | Board has a codec+DAC but the amp output/speaker may need adding | Confirm onboard speaker vs. header |
| LiPo battery | Optional; not required for a bedside clock | Ordered variant has no battery |
| USB-C power supply | Mains power for a bedside clock | 5 V, ≥1 A |
| ~~Enclosure~~ | **Not needed** — the `-EN` variant ships in a square plastic case (§3.1) | Only if a custom/bespoke enclosure is later wanted |

> Confirm whether the ordered board includes an onboard speaker and the exact
> connector for an external one — the Amazon listing mentions dual microphones
> but not a speaker.

---

## 4. Existing solutions — does a firmware already exist?

**Short answer: no ready-made, MQTT-native radio-alarm-clock firmware exists for
this exact board.** There are, however, several closely-related building blocks
worth reusing. Findings:

### 4.1 Vendor firmware / examples (Waveshare)

- The vendor repo ships a factory demo (`Brookesia`) with apps: Settings,
  Photo Album, **Music Player** (MP3 from SD), Video Player, Spectrum Analyzer,
  AI voice, etc. It is a general demo — **not** an alarm clock and **not**
  HA-integrated.
- Example code includes a working **ES8311 I²S audio out** demo and an
  **ESP32-audioI2S** library copy — directly reusable for radio playback.
  - Repo: https://github.com/waveshareteam/ESP32-S3-Touch-LCD-1.54

### 4.2 ESPHome community configs for this board (closest thing that exists)

- HA Community: *"Waveshare ESP32 S3 Touch LCD 1.54 working configuration"* —
  a full ESPHome config for this board (SKU 33869).
  https://community.home-assistant.io/t/waveshare-esp32-s3-touch-lcd-1-54-working-configuration/1013907
- HA Community: *"Waveshare ESP32-S3-(Touch-)ePaper-1.54: working ESPHome Voice
  Assistant config (analog ES8311 mic gotcha — I2S bus deadlock)"* — documents
  the ES8311/I²S pitfalls on this board family.
  https://community.home-assistant.io/t/waveshare-esp32-s3-touch-epaper-1-54-working-esphome-voice-assistant-config-analog-es8311-mic-gotcha-i2s-bus-deadlock/1023975

  → These confirm ESPHome **works on this board** (display, touch, ES8311
  audio), but they are display/voice demos — **not** alarm clocks, and they use
  the **native API**, not MQTT.

### 4.3 Generic ESP32 web-radio projects (reusable audio core)

- **ESP32-audioI2S** (Schatzmann) — the de-facto library for HTTP MP3/AAC/OGG
  radio streams on ESP32; supports playlists (.m3u/.pls), metadata/ICY.
  https://github.com/schreibfaul1/ESP32-audioI2S
  (Bundled copy in the Waveshare repo as `ESP32-audioI2S-master`.)
- **pschatzmann/esp32_radio** — web radio player with a web UI and station
  browser (Radio-Browser API). https://github.com/pschatzmann/esp32_radio
- **yellobyte/ESP32-Webradio-PlusDLNA** — web radio + DLNA.
  https://github.com/yellobyte/ESP32-Webradio-PlusDLNA

  → Great audio/streaming foundations, but **no MQTT/Home Assistant alarm
  model**.

### 4.4 ESPHome Media Player project (jtenniswood)

- Builds a HA **touchscreen media controller** (`media_player`) with album art.
  https://github.com/jtenniswood/esphome-media-player
  https://jtenniswood.github.io/esphome-media-player/

  → This *controls* HA media players; it is **not** a standalone radio and not
  an alarm clock. Useful only as UI/inspiration.

### 4.5 Conclusion

We will **build custom firmware**, reusing:
- the vendor ES8311/BSP + display/touch pin knowledge and examples,
- an Internet-radio audio core (ESP32-audioI2S or ESPHome's speaker pipeline),
- and implement the **alarm logic + MQTT discovery layer ourselves**.

---

## 5. The MQTT / Home Assistant integration model

### 5.1 How MQTT discovery works

Home Assistant's MQTT integration listens on discovery topics and
auto-creates entities from retained config payloads:

- Component discovery:
  `homeassistant/<component>/<node_id>/<object_id>/config`
  e.g. `homeassistant/switch/bedroom/alarm_enabled/config`
- Device discovery (one message describes a whole device + its components):
  `homeassistant/device/<node_id>/config` with a `components` map.
- Payloads are JSON, **retained**, and use short aliases (`~` = base topic,
  `cmd_t`, `stat_t`, `uniq_id`, `dev`, `avty_t` …).

> `<node_id>` is the **per-device id** (see §9.4). It must be unique per clock so
> multiple alarm clocks coexist on one broker without collisions.

References:
- https://www.home-assistant.io/integrations/mqtt/#mqtt-discovery
- https://www.home-assistant.io/integrations/mqtt/#device-discovery-payload
- Availability + birth/LWT: the device must publish availability (e.g.
  `.../availability` = `online`/`offline`) and use the MQTT `LWT` (last will)
  so HA marks it unavailable when it drops.

### 5.2 ⚠️ Critical constraint: MQTT discovery has **no `media_player`**

HA MQTT discovery supports `alarm_control_panel`, `sensor`, `binary_sensor`,
`switch`, `number`, `select`, `button`, `text`, `time`, `date`, `sensor`,
`siren`, `light`, etc. — **but there is no `media_player` platform** (neither in
YAML nor discovery). See the support table:

- https://www.home-assistant.io/integrations/mqtt/

Likewise, **ESPHome's `media_player` does not work over MQTT** (it is native-API
only):

- https://github.com/esphome/issues/issues/4882

**Implications for our design (important):**

- A true `media_player` entity with play/stop/volume/now-playing **cannot** be
  produced by MQTT discovery alone.
- We therefore model the radio as **MQTT-native primitives** that *are* fully
  supported:

  | Want | MQTT-native representation |
  |------|-----------------------------|
  | Radio on/off / play-pause | `switch` |
  | Station selection | `select` |
  | Volume | `number` |
  | Now playing / status | `sensor` (text) |
  | Snooze / Dismiss / Next station | `button` |

- If a real `media_player` entity is desired in HA, options are:
  1. **Wrap** the above entities using HA's **Universal Media Player** (or a
     small `template`), giving a single `media_player` façade; or
  2. Use **ESPHome's native API** for the media player *and* MQTT for the
     alarm/controls (hybrid — see §7).

This constraint should be validated early (§16) and confirmed with the user as
an accepted trade-off.

---

## 6. Feature / entity model

Proposed HA entities (all via MQTT discovery unless noted). Entity object-ids
below are shown with the `alarmclock_` prefix for one example device; in the real
system they are namespaced **per device** as `alarmclock_<device_id>_<role>`
(e.g. `alarmclock_bedroom_alarm_enabled`, `alarmclock_kitchen_volume`) and each
clock is a **separate HA device** — see §9.4.

### 6.1 Alarm

| Entity | HA type | Direction | Purpose |
|--------|---------|-----------|---------|
| `switch.alarmclock_alarm_enabled` | switch | HA → dev | Master enable/disable |
| `time.alarmclock_alarm_time` | time | HA → dev | Alarm time (HH:MM) |
| `select.alarmclock_alarm_days` | select | HA → dev | Repeat pattern (e.g. `daily`, `weekdays`, `weekends`, `mon,wed,fri`, `once`) |
| `number.alarmclock_snooze_minutes` | number | HA → dev | Snooze duration |
| `sensor.alarmclock_next_alarm` | sensor | dev → HA | Next scheduled alarm (timestamp) |
| `sensor.alarmclock_alarm_state` | sensor | dev → HA | `idle` / `ringing` / `snoozed` / `disabled` |
| `button.alarmclock_snooze` | button | HA → dev | Snooze now |
| `button.alarmclock_dismiss` | button | HA → dev | Stop/dismiss ringing alarm |
| `switch.alarmclock_alarm_ring` *(optional)* | switch | HA → dev | Force ring (test) |

> A richer alternative is `alarm_control_panel` (supported by MQTT discovery)
> to model arm/disarm semantics, but a plain `switch` + `time` + `select` set is
> simpler and clearer for an alarm clock. Decide in §18.

### 6.2 Radio

| Entity | HA type | Direction | Purpose |
|--------|---------|-----------|---------|
| `switch.alarmclock_radio` | switch | HA → dev | Radio power / begin-stop playback |
| `select.alarmclock_station` | select | HA → dev | Choose station from list |
| `number.alarmclock_volume` | number | HA → dev | Volume 0–100 |
| `sensor.alarmclock_now_playing` | sensor | dev → HA | Current station name / ICY title |
| `button.alarmclock_next_station` | button | HA → dev | Next station |
| `button.alarmclock_prev_station` | button | HA → dev | Previous station |

### 6.3 Device / diagnostics

| Entity | HA type | Purpose |
|--------|---------|---------|
| `sensor.alarmclock_ip` | sensor | Device IP |
| `sensor.alarmclock_wifi_rssi` | sensor (dBm) | Wi-Fi signal |
| `sensor.alarmclock_firmware` | sensor | Firmware version |
| `binary_sensor.alarmclock_mqtt` | binary_sensor | MQTT connectivity |
| `button.alarmclock_reboot` | button | Reboot device |

### 6.4 Station list management

"Feed only radio stations" → the station set should be **configurable**:

- v1: a curated list compiled into firmware / stored on-device, exposed as the
  `select` options.
- v2: allow HA to push the station list (e.g. a `text` entity with JSON, or a
  dedicated config topic) — but a select's option list is set by the discovery
  payload, so changes mean re-publishing discovery. Design carefully (§18).

### 6.5 Exposing a real `media_player` (no custom component)

Because HA's built-in MQTT integration has **no `media_player` platform** (§5.2),
we surface a proper `media_player` entity **per clock** (e.g.
`media_player.bedroom_alarm_clock`) in three ways, none of which
require writing a custom component:

1. **Universal Media Player (recommended, core integration) — works with our
   MQTT entities.** Wraps the MQTT-discovered `switch`/`select`/`number`/`sensor`
   into a single media player with power, volume, mute, source selection and
   now-playing. It is configured in `configuration.yaml` (not via discovery), but
   it is a **built-in HA integration**, not a custom component.
   Docs: https://www.home-assistant.io/integrations/universal/
2. **ESPHome native API** (if we build on ESPHome): the `speaker`/`media_player`
   component is exposed to HA directly — a genuine `media_player`, zero config,
   but over the native API rather than MQTT (§7).
3. **Hybrid**: MQTT entities **and** an ESPHome native-API `media_player`
   simultaneously.

#### Example Universal Media Player config (wraps the MQTT entities)

```yaml
# configuration.yaml — one entry PER alarm clock (repeat & rename per device)
media_player:
  - platform: universal
    name: "Bedroom Alarm Clock"
    unique_id: alarmclock_bedroom_media_player
    device_class: speaker
    # Underlying MQTT-discovered entities created via discovery (§9)
    children:
      - switch.alarmclock_bedroom_radio
    commands:
      turn_on:
        service: switch.turn_on
        target: { entity_id: switch.alarmclock_bedroom_radio }
      turn_off:
        service: switch.turn_off
        target: { entity_id: switch.alarmclock_bedroom_radio }
      volume_set:
        service: number.set_value
        target: { entity_id: number.alarmclock_bedroom_volume }
        data: { value: "{{ (volume_level * 100) | round(0) | int }}" }
      volume_up:
        service: number.set_value
        target: { entity_id: number.alarmclock_bedroom_volume }
        data: { value: "{{ (state_attr('number.alarmclock_bedroom_volume','value') | float(0) + 5) | int }}" }
      volume_down:
        service: number.set_value
        target: { entity_id: number.alarmclock_bedroom_volume }
        data: { value: "{{ (state_attr('number.alarmclock_bedroom_volume','value') | float(0) - 5) | int }}" }
      select_source:
        service: select.select_option
        target: { entity_id: select.alarmclock_bedroom_station }
        data: { option: "{{ source }}" }
    attributes:
      state: "{{ 'playing' if is_state('switch.alarmclock_bedroom_radio','on') else 'idle' }}"
      source: "{{ states('select.alarmclock_bedroom_station') }}"
      source_list: "{{ state_attr('select.alarmclock_bedroom_station','options') }}"
      volume_level: "{{ (states('number.alarmclock_bedroom_volume') | float(0) / 100) | round(2) }}"
      media_title: "{{ states('sensor.alarmclock_bedroom_now_playing') }}"
```

> Notes:
> - `volume_level` is 0.0–1.0 in HA; the `number` entity is 0–100, hence
>   `×100` / `÷100`.
> - Add `media_play`/`media_pause`/`media_stop`/`media_next_track`/
>   `media_previous_track` commands mapped to the corresponding
>   `switch`/`button` entities if you want transport controls.
> - This YAML is the *only* manual config step; all underlying entities remain
>   MQTT-discovered. Keep it in the repo as a HA package/snippet (e.g.
>   `ha/universal_media_player.yaml`) so it's version-controlled.
> - **Multi-device:** add one `media_player:` entry **per clock**, each with its
>   own `name`/`unique_id` and its own `alarmclock_<device_id>_*` entity refs
>   (§9.4). The file can be templated/duplicated per device id.

---

## 7. Architecture options

### Option A — ESPHome (with MQTT)

Use ESPHome YAML to define the device: display (LVGL), touch, ES8311 audio,
`media_player`/`speaker`, `switch`, `select`, `number`, `time`, automations for
the alarm; enable the `mqtt:` component so supported entities get MQTT
discovery automatically.

- ✅ Fastest path; mature components for ST7789, CST816, ES8311, LVGL.
- ✅ Built-in HA integration (native API) *and* MQTT.
- ✅ OTA, web server, captive-portal Wi-Fi provisioning built in.
- ❌ `media_player` is **not available over MQTT** (native API only).
- ❌ Alarm-time entity options: ESPHome's `time`/`datetime` components map to HA
  entities; over MQTT, verify which map to MQTT discovery.
- ❌ Less control over bespoke alarm/streaming behaviour than hand-written code.

### Option B — Custom ESP-IDF firmware (+ `esp-mqtt`)

Hand-written C firmware using ESP-IDF v5.5+, `esp-mqtt` client, and a manual
MQTT-discovery publisher. Audio via the `esp_codec`/ES8311 drivers or the
Schatzmann audio component ported in.

- ✅ Full control over alarm logic, streaming, discovery payloads, topics.
- ✅ Best reliability/robustness for a critical device.
- ✅ Can implement a "media_player-shaped" experience via MQTT primitives.
- ❌ Most work: display/touch/LVGL, audio, networking, OTA all hand-rolled.
- ❌ More expertise required; longer time-to-first-ring.

### Option C — Arduino-IDE custom firmware

Use the Arduino ESP32 core 3.2.0 with `ESP32-audioI2S`, LVGL/GFX, and a
`PubSubClient`-based MQTT layer + manual discovery.

- ✅ Easiest audio/radio path (`ESP32-audioI2S` is Arduino-first).
- ✅ Vendor example libraries are Arduino-oriented.
- ❌ Manual MQTT discovery + alarm logic (same effort as B, less robust tooling).
- ❌ Arduino core less suited to long-running reliability tuning.

### Option D — Hybrid (recommended)

**ESPHome for the device + native API for the rich `media_player`, plus a
custom MQTT discovery layer for the alarm/radio primitives.** Discussed next.

---

## 8. Recommended architecture

**Start with Option A (ESPHome), structured so we can graduate to B if we hit
limits — and add an explicit MQTT layer for the entities MQTT discovery
supports.**

Rationale:

1. ESPHome gets display, touch, audio and OTA working quickly, and is proven on
   this exact board by the community configs (§4.2).
2. MQTT discovery cleanly covers **everything except `media_player`**:
   `switch` (radio + alarm enable), `select` (station), `number` (volume,
   snooze), `time` (alarm time), `sensor`/`binary_sensor` (status, RSSI),
   `button` (snooze/dismiss/next/prev). That satisfies the stated requirements
   ("set the alarm, disable/enable, set the radio and control the radio, feed
   only radio stations").
3. For a first-class `media_player` experience, keep the ESPHome **native API**
   connection as well (HA supports both), *or* assemble a **Universal Media
   Player** façade from the MQTT entities.
4. The alarm is scheduled **on-device** (ESPHome `time` + automations, or a
   custom component), so it rings even if HA/broker is down.

If ESPHome proves unable to meet reliability/audio requirements, fall back to
**Option B (ESP-IDF)** reusing the vendor BSP and the Schatzmann audio
component.

### Firmware stack (recommended)

```
┌──────────────────────────────────────────────────────────┐
│ Home Assistant                                            │
│  • MQTT integration (Mosquitto add-on)                    │
│  • MQTT discovery → switch/select/number/time/sensor/...  │
│  • (optional) ESPHome native API → media_player           │
│  • (optional) Universal Media Player façade               │
└───────────────▲───────────────────────┬──────────────────┘
                │ MQTT (1883)            │ native API (6053)
┌───────────────┴───────────────────────▼──────────────────┐
│ ESP32-S3-Touch-LCD-1.54 firmware                           │
│  • ESPHome: LVGL UI, touch, ES8311 speaker, time, OTA      │
│  • Alarm engine (on-device scheduling, snooze)             │
│  • Radio engine (station list → stream URLs)               │
│  • MQTT discovery publisher (entities in §6)               │
└──────────────────────────────────────────────────────────┘
```

---

## 9. MQTT topic & discovery design

### 9.1 Base topics (per device)

Every clock uses a **unique `device_id`** so multiple alarm clocks can share one
MQTT broker without collisions.

**`device_id` source — v1 decision:** derived from the **ESP32 MAC**
(e.g. `a4cf12b8d61f`, or shortened to its last 6 hex like `12b8d61f`). This is
unique by construction, invisible to users, stable across reboots/OTA, and needs
**no provisioning**. A physical label on the case maps each unit to its id
(§14.2).

> Future/optional: an explicit friendly slug (e.g. `bedroom`) could override the
> MAC for nicer topic names, but v1 keys everything on the MAC.

**Namespacing derived from `device_id`:**

| Thing | Pattern | Example (`device_id = bedroom`) |
|-------|---------|---------------------------------|
| Base topic root | `alarmclock/<device_id>/` | `alarmclock/bedroom/` |
| Discovery topic | `homeassistant/<component>/<device_id>/<object>/config` | `homeassistant/switch/bedroom/alarm_enabled/config` |
| `unique_id` | `alarmclock_<device_id>_<role>` | `alarmclock_bedroom_alarm_enabled` |
| Availability topic | `alarmclock/<device_id>/status` | `alarmclock/bedroom/status` |
| HA device identifier | `alarmclock-<device_id>` | `alarmclock-bedroom` |
| Discovery prefix | `homeassistant` (HA default) | — |

Availability is `online` (retained) + LWT `offline`.

### 9.2 Example discovery payloads

All examples below use `device_id = bedroom`. Substitute each device's own id.

**Switch — alarm enabled**

Topic: `homeassistant/switch/bedroom/alarm_enabled/config`

```json
{
  "name": "Alarm Enabled",
  "uniq_id": "alarmclock_bedroom_alarm_enabled",
  "cmd_t": "alarmclock/bedroom/alarm/enabled/set",
  "stat_t": "alarmclock/bedroom/alarm/enabled/state",
  "avty_t": "alarmclock/bedroom/status",
  "dev": { "ids": "alarmclock-bedroom", "name": "Bedroom Alarm Clock",
           "mf": "waveshare", "mdl": "ESP32-S3-Touch-LCD-1.54" }
}
```

**Time — alarm time**

Topic: `homeassistant/time/bedroom/alarm_time/config`

```json
{
  "name": "Alarm Time",
  "uniq_id": "alarmclock_bedroom_alarm_time",
  "cmd_t": "alarmclock/bedroom/alarm/time/set",
  "stat_t": "alarmclock/bedroom/alarm/time/state",
  "avty_t": "alarmclock/bedroom/status",
  "dev": { "ids": "alarmclock-bedroom" }
}
```

**Select — station**

Topic: `homeassistant/select/bedroom/station/config`

```json
{
  "name": "Station",
  "uniq_id": "alarmclock_bedroom_station",
  "cmd_t": "alarmclock/bedroom/radio/station/set",
  "stat_t": "alarmclock/bedroom/radio/station/state",
  "options": ["BBC Radio 4", "BBC Radio 6 Music", "Classic FM", "Absolute Radio"],
  "avty_t": "alarmclock/bedroom/status",
  "dev": { "ids": "alarmclock-bedroom" }
}
```

**Number — volume**

Topic: `homeassistant/number/bedroom/volume/config`

```json
{
  "name": "Volume",
  "uniq_id": "alarmclock_bedroom_volume",
  "cmd_t": "alarmclock/bedroom/radio/volume/set",
  "stat_t": "alarmclock/bedroom/radio/volume/state",
  "min": 0, "max": 100, "step": 1, "unit_of_meas": "%",
  "avty_t": "alarmclock/bedroom/status",
  "dev": { "ids": "alarmclock-bedroom" }
}
```

(Also: `switch` for radio, `button`s for snooze/dismiss/next/prev, `sensor`s for
next alarm / now playing / RSSI — each namespaced with the same `device_id`.)

### 9.3 State reporting

- Device publishes its own state on `*/state` topics (retained) so HA reflects
  reality and survives restarts.
- Device republishes discovery payloads on connect (retained) for idempotence.

### 9.4 Multi-device (multiple alarm clocks)

The design **must support several clocks on one broker**, each appearing as its
own HA device. This is achieved purely by namespacing on `device_id` (§9.1):

- **Isolation:** every topic, `unique_id` and HA `dev.ids` is namespaced by
  `device_id`, so N clocks never collide.
- **HA grouping:** all entities for one clock share the same `dev` block
  (`ids: alarmclock-<device_id>`, plus `name`/`mf`/`mdl`), so HA groups them
  under one device card per clock.
- **Naming:** set a friendly `name` (e.g. *Bedroom Alarm Clock*) via the config
  value for `device_id` (or an explicit device name); the `device_id` slug should
  be uniqueness-safe (lowercase, `[a-z0-9-]`, no spaces).
- **`device_id` stability:** it is resolved once and **persisted in NVS**, so it
  never changes across reboots or OTA. A MAC-derived default guarantees
  uniqueness out of the box; a friendly slug is opt-in.
- **Provisioning:** each unit is flashed with its `device_id`/name (build-time
  substitution or first-boot config). See §14.
- **HA side:** one **Universal Media Player** entry per device (§6.5); dashboards
  can be generated per device id.
- **Option — device-based discovery:** instead of one retained config message per
  entity, publish a single `homeassistant/device/<device_id>/config` message
  listing all components (`cmps`). Cleaner for many entities and naturally
  per-device; consider adopting this (§9, §5.1).
- **Backwards-compat:** a single device without an explicit id still works
  (MAC-derived id); the scheme is uniform.

**Example: two clocks**

| device_id | HA device | media_player | discovery topic root |
|-----------|-----------|--------------|----------------------|
| `bedroom` | Bedroom Alarm Clock | `media_player.bedroom_alarm_clock` | `homeassistant/.../bedroom/...` |
| `kitchen` | Kitchen Alarm Clock | `media_player.kitchen_alarm_clock` | `homeassistant/.../kitchen/...` |

> *Illustrative only:* v1 uses **MAC-derived** ids (e.g. `a4cf12b8`), not the
> friendly slugs shown above — the friendly names are set by renaming the HA
> device (§14.2). The namespacing mechanics are identical.

---

## 10. Audio / Internet radio design

### 10.1 Signal path

`HTTP/ICY stream → decode (MP3/AAC/OGG) → I²S → ES8311 DAC → PA_CTRL amp → speaker`

- PSRAM (8 MB) is essential for buffering/decoding — enable Octal PSRAM in the
  build config.
- `PA_CTRL` (GPIO 7) must be driven high to enable the speaker amplifier.

### 10.2 Codecs & transport

- **MP3** (Icecast/Shoutcast) and **AAC** streams are the realistic targets;
  most stations also offer MP3.
- **HTTPS/TLS streams**: an ESP32 can do TLS but it is costly in RAM/CPU and
  handshake time. **Prefer HTTP (or plain Icecast) endpoints** where legal; if
  only HTTPS is available the connection may be slow/fragile. Validate per
  station.
- Playlists: support `.m3u`/`.pls` and ICY metadata (artist/title) where cheap.

### 10.3 Library choice

- **ESPHome speaker/media_player** (ESP-IDF, has PSRAM performance notes,
  supports MP3/AAC/FLAC/OPUS/WAV via HTTP and HA-proxied media) — fits Option A.
  - https://esphome.io/components/media_player/speaker.html
  - https://esphome.io/components/audio_dac/es8311.html
- **ESP32-audioI2S** (Schatzmann) — proven Arduino radio library; fits Options
  C/B.
  - https://github.com/schreibfaul1/ESP32-audioI2S

### 10.4 Station catalogue

- Ship a small curated list (name → stream URL, codec, bitrate).
- Consider the **Radio-Browser** API for discovery in a v2 admin UI.
- The HA `select` only offers "approved" stations — matching the requirement to
  "feed only radio stations".

### 10.5 Volume & ducking

- Software volume via codec/DAC + amp enable line.
- "Wake gently" behaviour: ramp volume up over N seconds when the alarm fires
  (ESPHome speaker supports volume ramps/ducking; a custom ramp otherwise).

---

## 11. Time, alarms & scheduling

- **Time source:** NTP (SNTP) on boot + periodic resync; timezone/DST handled
  via POSIX TZ string (ESPHome `time: platform: sntp` with `timezone:`), or
  HA-supplied time.
- **Internal RTC:** use the ESP32-S3 internal RTC and, if the board has a
  discrete RTC chip, prefer it to survive brief power loss (investigate — §3.1).
- **Alarm engine (on-device):**
  - Stores one (or more) alarm(s): time, days-of-week, enabled, snooze.
  - Persists to NVS/flash so it survives reboots.
  - Evaluates each minute; fires independently of HA/broker.
  - On fire: ramp volume, play "alarm" (radio station or a tone), display
    prompt, offer snooze (default N minutes) / dismiss.
  - Reports state changes to HA.
- **DST/clock changes:** recompute next trigger on time change; avoid double-
  firing across DST.
- **Snooze:** re-arms for now + snooze-minutes; optional repeat limit.
- **Missed-alarm safety:** if device was off at the alarm time, do not fire on
  boot unless a "fire if within X minutes" policy is configured. Decide (§18).

---

## 12. UI / UX (display + touch)

240×240 touch LVGL UI:

- **Clock face:** large time, date, small status (alarm on/off, next alarm,
  Wi-Fi, radio playing).
- **Radio screen:** station name, now-playing, play/pause, prev/next, volume.
- **Alarm screen:** set time, toggle days, enable/disable, set snooze.
- **Ringing screen:** big Snooze / Stop buttons + brightness pulse.
- **Settings:** Wi-Fi status, MQTT status, brightness, reboot, firmware version.
- Touch gestures: tap; maybe swipe between clock/radio/alarm.

### 12.1 On-screen clock (time display)

The board is a **clock first**, so showing the time on the 1.54″ panel is core
functionality, not decoration. It is delivered in two stages:

**Stage 1 — plain on-screen clock (Track A, no hardware).** A minimal
ESPHome `display` renders the current time (from `sntp_time`) on the ST7789V
panel. This is pure software and **compiles/validates without the board**
(only the pixels are confirmed at bring-up).

- **Component:** ESPHome [`display`](https://esphome.io/components/display/)
  using the ST7789V driver (240×240, SPI).
- **Pins:** MOSI 39, SCLK 38, CS 21, DC 45, RST 40, Backlight 46 (§3.2).
- **Backlight:** driven high on boot (dimming = later).
- **Time source:** the existing `sntp_time` component — the *same* clock that
  drives the alarm engine, so screen and alarm can never disagree.
- **Rendering:** a `lambda` formats `HH:MM` via `strftime`, drawn with a large
  `.ttf` font; redraw every second. Small date line beneath.
- **Failure mode:** if NTP has not synced, show placeholders (`--:--`) instead
  of a bogus time.

**Stage 2 — LVGL UI (Track B5).** The full `LVGL` UI above (clock face +
radio / alarm / ringing / settings screens, touch) replaces the plain clock,
reusing the same display + time plumbing. The plain clock is the fallback if
LVGL bring-up slips.

> Stage 1 lives in `firmware/alarmclock.yaml`; Stage 2 is tracked as milestone
> **M5** and task **B5**.

---

## 13. Toolchain, build & flashing

### 13.1 Recommended (ESPHome)

- **ESPHome** (Dashboard or CLI) — define the device in YAML; build & flash.
  - Install: https://esphome.io/guides/installing_esphome/
  - Web installer / "Ready-Made Projects": https://esphome.io/projects/
- Compiles to a `.bin`; flashes over USB or OTA.

### 13.2 Alternative (ESP-IDF for custom firmware)

- **ESP-IDF v5.5.0+** (vendor requirement for this board) — via
  VS Code + **ESP-IDF extension** or the CLI (`idf.py`).
  - https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/
- Build: `idf.py set-target esp32s3 && idf.py build`
  (enable Octal PSRAM + 16 MB flash in menuconfig).
- Flash: `idf.py -p <PORT> flash monitor`.

### 13.3 Alternative (Arduino IDE)

- **Arduino IDE 2.x** + **ESP32 core by Espressif 3.2.0**.
  - Board: **ESP32S3 Dev Module**; Flash: **16 MB**; enable **USB CDC On Boot**
    for `Serial`, appropriate partition scheme.
  - Libraries (from vendor example package / Library Manager):
    LVGL (v8.4/9.3), GFX_Library_for_Arduino, U8g2, SensorLib,
    **ESP32-audioI2S**, OneButton.

### 13.4 Flashing the board (important)

- Board uses the **native USB** interface (not USB-UART).
- If the port isn't recognised, enter **download/boot mode**:
  1. Hold **BOOT**;
  2. plug in USB;
  3. release **BOOT**.
- Flash with the Espressif **Flash Download Tool** (GUI), `esptool.py`, or
  `idf.py`/ESPHome.
  - Vendor firmware flash address: **0x00**.
  - Tool: https://www.espressif.com/en/support/download/other-tools
  - `esptool`: https://github.com/espressif/esptool
- After flashing: power-cycle to run.
- To **erase**: use the tool's ERASE, or `esptool.py erase_flash`.

### 13.5 CI (later)

- GitHub Actions build matrix: `esphome compile` and/or `idf.py build`; publish
  release `.bin` + a web-installer manifest.

### 13.6 Flashing quickstart (cheat-sheet)

**One-time setup**

```bash
# Linux: add yourself to the dialout group for serial access, then re-login
sudo usermod -aG dialout "$USER"

# ESPHome (recommended path)
pipx install esphome            # or: pip install esphome
# ESP-IDF (alternative)
#   install v5.5+ via https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/
#   then: . $IDF_PATH/export.sh
```

**Find the serial port**

```bash
ls /dev/ttyACM* /dev/ttyUSB* 2>/dev/null   # native USB → usually /dev/ttyACM0
```

**Build + flash**

```bash
# --- ESPHome (recommended) ---
esphome compile alarmclock.yaml                 # build only
esphome run     alarmclock.yaml                 # build + flash via USB (auto-detects port)
esphome run     alarmclock.yaml --device /dev/ttyACM0
esphome run     alarmclock.yaml --device alarmclock.local   # OTA over Wi-Fi (later)

# --- ESP-IDF (custom firmware) ---
idf.py set-target esp32s3
idf.py build
idf.py -p /dev/ttyACM0 flash monitor            # flash + open serial monitor

# --- Arduino IDE ---
#   Board: "ESP32S3 Dev Module", Flash: 16MB, PSRAM: OPI/Octal, USB CDC On Boot: Enabled
#   Tools ▸ Port ▸ /dev/ttyACM0 ▸ click Upload
```

**Raw flashing with esptool (any toolchain, cross-platform)**

```bash
pip install esptool
esptool.py --chip esp32s3 --port /dev/ttyACM0 chip_id        # sanity-check the link
esptool.py --chip esp32s3 --port /dev/ttyACM0 erase_flash    # wipe (optional)
# ESPHome/IDF users normally let the tool above handle this; for a single image:
esptool.py --chip esp32s3 --port /dev/ttyACM0 write_flash 0x0 firmware.bin
```

**If the port isn't detected → manual download mode**

1. Hold **BOOT**
2. Plug in the USB-C cable
3. Release **BOOT**
4. Re-run the flash command.

**Erase / recover**

```bash
esptool.py --chip esp32s3 --port /dev/ttyACM0 erase_flash     # full wipe
# then re-flash the factory or your image at 0x0
```

**Windows GUI alternative:** Espressif **Flash Download Tool** — select
*ESP32-S3* + *USB*, pick the `.bin`, set address (`0x00` for vendor images),
tick the checkbox, click **START**.
https://www.espressif.com/en/support/download/other-tools

**After first flash → OTA (no cable):**

```bash
esphome run alarmclock.yaml --device alarmclock.local    # ESPHome wireless update
# ESP-IDF: esp_https_ota; Arduino: ArduinoOTA
```

> Keep a copy of the factory/vendor `.bin` for recovery, and note the board's
> MAC/hostname so you can find it on the network after OTA.

---

## 14. Provisioning & OTA updates

### 14.1 Getting the device onto Wi-Fi

Options (all ESP32-S3; ESPHome component names in brackets):

| Method | How it works | Pros | Cons | Verdict |
|--------|--------------|------|------|---------|
| **Compile-time credentials** (`wifi:`) | SSID/password baked into the YAML (via `secrets`) and flashed | Dead simple; works fully offline | Rebuild + reflash per network; secrets in build | Fine for a fixed home; poor for gifting |
| **Improv via Serial** (`improv_serial`) | Configure Wi-Fi from a browser (ESPHome Dashboard / web installer) over the USB-C serial — no app | Zero-config first flash; no app; works before Wi-Fi exists | Needs a USB cable + Chrome/Edge | ✅ **Recommended for first setup** |
| **Improv via BLE** (`improv_ble`, formerly `esp32_improv`) | Configure over Bluetooth LE from the ESPHome Dashboard / HA app | No cable after flashing | BLE stack uses **lots of RAM** — ESPHome explicitly warns against combining with audio components (which we have) | Optional; only if RAM budget allows |
| **Captive portal / fallback AP** (`captive_portal` + `ap:`) | After ~1 min of failed Wi-Fi, device raises a hotspot; you set credentials at `http://192.168.4.1` | Excellent recovery & re-provisioning; no cable | Device must boot; creds can be overwritten by a later serial upload | ✅ **Recommended as ongoing fallback** |
| **On-device setup UI** (our touchscreen) | Screen lists SSIDs; touch to enter password + set device name | Fully self-contained; uses the hardware we have | Extra LVGL UI work | ✅ Attractive; target for v2 |
| **Wi-Fi Easy Connect (DPP) / QR** (`wifi_provisioning`) | ESP-IDF DPP provisioning via QR code scan | No typing | More complex; niche tooling | Not recommended |
| **WPS** | ESP-IDF WPS push-button APIs | No password typing | **Insecure, widely deprecated, unsupported by ESPHome/HA**, absent on many APs | ❌ **Avoid** |

**Recommendation:** first boot → **Improv via Serial** (flash + hand it the Wi-Fi
from the ESPHome Dashboard / web installer); keep the **captive portal** as the
always-available fallback for re-provisioning. **Do not use WPS.**

Additional Wi-Fi notes:
- Support **multiple SSIDs** (`wifi: networks:`) and prefer a **static IP** —
  ESPHome recommends a static IP as it greatly improves reconnect time.
- Credentials persist in NVS.

### 14.2 Setting the `device_id` on the device

Follows the namespacing rules in §9.1/§9.4. Ways to *set* it:

| Method | Persistence | Notes |
|--------|-------------|-------|
| **MAC-derived default (no provisioning)** | computed at boot | Zero-config; topics guaranteed unique. ✅ **Default** |
| **Build-time substitution** (`device_id`/name in YAML; per-unit build) | firmware | Simple; one build per known unit; fine for a small fleet |
| **Runtime → NVS** (set once) — via: | NVS | Better for a single "any-unit" build |
| ↳ captive-portal **custom field** | NVS | Extend the portal page with an id/name box |
| ↳ HA **`text` entity** (set name/id, persist) | NVS | Configure from HA once on the network |
| ↳ **microSD `config.json`** | card | No rebuild; edit the card to rename |
| ↳ **serial console** | NVS | Bench/dev convenience |
| ↳ **first-boot AP form** | NVS | Like the captive portal |
| ↳ MQTT **command topic** | NVS | ⚠️ Renaming changes topics — use carefully |

**Decision (v1): MAC-derived `device_id` — no runtime provisioning needed.**

1. **`device_id` = the ESP32 MAC** (or a shortened form, e.g. last 6 hex) → unique
   by construction, **invisible** to users, and stable across reboots/OTA. This is
   the chosen approach for v1; no first-boot id entry required.
2. The device **reports its own id** (an MQTT `sensor`/discovery field, and on the
   settings screen) so it's always discoverable without a cable.
3. A friendly name is optional/later: rename in HA the normal way; if we later
   want a runtime slug, persist it in NVS without changing the topic key.

> 💡 **Decouple "topic id" from "human name":** HA lets you rename the device and
> entities in the UI independently of `unique_id`. Keep topics keyed on the
> (MAC) id, rename for humans in HA — no firmware change needed.

#### Physical labelling (identify which physical clock is which)

Because the id is invisible, put a **label on the device** so you can map a
physical clock → its HA device → its MQTT topics:

- Print a label with the **short id (last 6 hex of the MAC)** and optionally the
  HA friendly name; attach it to the **underside/back of the case** (the supplied
  square case has a flat back).
- The vendor may already print a MAC/QR sticker on the board — capture it before
  assembling into the case.
- Optionally generate a QR that deep-links to the HA device page.
- Add the label ↔ id mapping to a small `docs/devices.md` inventory table and to
  the HA device name, so "Bedroom" unambiguously maps to one unit.

> Keep the raw MAC off any public surface; the short id is enough for humans.

### 14.3 MQTT credentials

- Broker host/port/user/pass + discovery prefix, configured via ESPHome `mqtt:` /
  build-time secrets or a runtime provision. **Never commit secrets** (use
  `secrets.yaml` / env; keep `secrets.example.yaml` in the repo).

### 14.4 OTA

- **ESPHome OTA**, ESP-IDF `esp_https_ota`, or ArduinoOTA.
- Provide a firmware-version sensor and a HA "update available" indication.

### 14.5 Safe rollback

- Keep a golden/factory image and document re-flashing it (design.md §13.6).

---

## 15. Risks & mitigations

| # | Risk | Impact | Mitigation |
|---|------|--------|-----------|
| R1 | **MQTT has no `media_player`** | Can't expose a real media_player via discovery | Model radio as switch+select+number; wrap with Universal Media Player OR use ESPHome native API |
| R2 | ESPHome `media_player` unsupported over MQTT (issue #4882) | Same as R1 | As R1 |
| R3 | **Alarm reliability** (crash/reboot/Wi-Fi loss at ring time) | Missed alarm — unacceptable | On-device scheduling, NVS persistence, watchdog, tried-and-tested ESP-IDF/ESPHome runtime; fail-safe default ring |
| R4 | **HTTPS-only streams** cost RAM/CPU, slow handshake | Stutter / fail | Prefer HTTP/Icecast endpoints; verify each station; generous buffering in PSRAM |
| R5 | **Codec support** (AAC/HE-AAC/OGG) uneven | Some stations silent | Prefer MP3; test each station; document supported codecs |
| R6 | **Audio + Wi-Fi/BLE resource contention** on S3 | Instability/crashes | Don't enable BT/BLE; disable unused components; PSRAM; measure heap |
| R7 | **Board docs sparse / pin map unverified** | Wrong pins → no display/audio | Verify against official schematic PDF; prototype each peripheral first |
| R8 | **RTC across power loss** unclear | Time wrong after outage | NTP resync on boot; add/confirm RTC chip; alarm recompute policy |
| R9 | Onboard **speaker/amp presence unclear** | No sound | Confirm hardware; add external speaker if needed; drive PA_CTRL |
| R10 | **Stream URL licensing/geo/change** | Streams break/legal issues | Use official broadcaster HTTP endpoints; make list user-editable |
| R11 | **Secrets in repo** | Credential leak | Use `secrets.yaml`/env; gitignore; document |
| R12 | **OTA bricking** | Dead bedside clock | Keep factory image; verify OTA; optional dual-bank/rollback |
| R13 | **DST/timezone bugs** | Wrong ring time | POSIX TZ handling; test DST transitions |
| R14 | **Broker unreachable at boot** | No HA control (alarm still works) | Local alarm engine independent of MQTT; availability/LWT reporting |
| R15 | **Thermal/long-run stability** | Random freezes | Long soak tests; watchdog; minimal peripheral set |

---

## 16. Testing plan

- **Per-peripheral bring-up:** display, touch, ES8311 audio out, speaker amp.
- **Streams:** 5–10 representative stations (varied codecs/bitrates), including
  one HTTPS-only, overnight soak.
- **Alarm:** fires at set time; snooze; dismiss; disable; day-of-week
  correctness; DST transitions; reboot persistence; **alarm fires with HA and
  broker powered off**.
- **MQTT:** discovery creates all entities; command round-trips; availability
  (LWT) flips offline on power cut; reconnect after broker restart; retained
  state after device reboot.
- **HA UX:** entity naming/grouping; Universal Media Player façade (if used).
- **Reliability:** 72-hour soak with periodic Wi-Fi drop/restore.

---

## 17. Roadmap / milestones

1. **M0 — Bring-up:** flash vendor demo; confirm USB/Boot mode; verify display,
   touch, audio, amp. (Validate pin map.)
2. **M1 — Dev environment:** ESPHome (or ESP-IDF) builds & flashes a "hello"
   app with Wi-Fi, NTP, and a visible clock. *(Plain on-screen clock delivered
   in Track A — design §12.1; flashed/confirmed here.)*
3. **M2 — MQTT plumbing:** connect to broker; publish availability + discovery
   for one dummy `switch`; confirm entity appears in HA.
4. **M3 — Radio:** pick station → stream → speaker; volume; now-playing sensor;
   expose radio switch/select/number via discovery.
5. **M4 — Alarm engine:** on-device time + scheduling; snooze/dismiss;
   persistence; discovery for alarm entities; verify rings with HA offline.
6. **M5 — UI:** LVGL clock/radio/alarm/ringing screens; touch controls.
7. **M6 — Hardening:** OTA, watchdog, soak test, doc pin map, secrets handling.
8. **M7 — Nice-to-haves:** Universal Media Player façade, station-list editing,
   gentle wake ramp, album art, Radio-Browser search.

---

## 18. Open questions

1. **`media_player` — RESOLVED:** use MQTT discovery for all primitive entities
   (switch/select/number/sensor/button/time) **plus a built-in Universal Media
   Player** (§6.5) to expose a real `media_player` **per clock** (e.g.
   `media_player.bedroom_alarm_clock`) **without any
   custom HA component**. If we build on ESPHome we *additionally* get a native
   media_player via its API at no extra cost (optional). No custom integration
   required. Each clock is a separate HA device namespaced by `device_id` (§9.4).
2. **Alarm modelling:** simple `switch`+`time`+`select`, or use the
   `alarm_control_panel` MQTT component? One alarm or multiple?
3. **Board RTC:** is there a discrete I²C RTC chip, and which (PCF85063?)?
4. **Speaker:** is there an onboard speaker, and what is the external speaker
   connector/power rating?
5. **Stream legality:** which stations, and are HTTP (non-TLS) endpoints
   acceptable?
6. **Station list source:** shipped/curated vs. user-editable vs.
   Radio-Browser API?
7. **Missed-alarm policy** after power loss (fire on boot if late?).
8. **Firmware approach:** ESPHome vs ESP-IDF vs Arduino — final decision.
9. **Placement & case fit:** confirm the case cut-outs (speaker grille, USB-C,
   touch access) and where the clock sits bedside; only design a custom
   enclosure if the included case proves unsuitable.
10. ~~**Licence** for this repo?~~ **DECIDED: MIT** (see `LICENSE`).

---

## 19. References

### Hardware / vendor
- Waveshare board repo: https://github.com/waveshareteam/ESP32-S3-Touch-LCD-1.54
- Waveshare docs: https://docs.waveshare.com/ESP32-S3-Touch-LCD-1.54
- Waveshare wiki: https://www.waveshare.com/wiki/ESP32-S3-Touch-LCD-1.54
- Amazon UK listing: https://www.amazon.co.uk/gp/product/B0GS9CW66Z/ref=sw_img_1?smid=&psc=1
- ESP32-S3 (Espressif): https://www.espressif.com/en/products/socs/esp32-s3

### Home Assistant / MQTT
- MQTT integration: https://www.home-assistant.io/integrations/mqtt/
- MQTT discovery: https://www.home-assistant.io/integrations/mqtt/#mqtt-discovery
- Mosquitto broker add-on: https://www.home-assistant.io/integrations/mqtt/#setting-up-a-broker
- Universal Media Player: https://www.home-assistant.io/integrations/universal/

### ESPHome
- ESPHome: https://esphome.io/
- MQTT Client component: https://esphome.io/components/mqtt/
- Speaker media player: https://esphome.io/components/media_player/speaker.html
- ES8311 audio DAC: https://esphome.io/components/audio_dac/es8311.html
- ES7210 audio ADC: https://esphome.io/components/audio_adc/es7210.html
- Time / SNTP: https://esphome.io/components/time/sntp.html
- Media player over MQTT limitation: https://github.com/esphome/issues/issues/4882

### Provisioning / Wi-Fi onboarding
- Improv standard (open Wi-Fi setup): https://www.improv-wifi.com/
- Improv via Serial (ESPHome): https://esphome.io/components/improv_serial/
- Improv via BLE (ESPHome): https://esphome.io/components/improv_ble/
- Wi-Fi component (ESPHome): https://esphome.io/components/wifi/
- Captive portal / fallback AP (ESPHome): https://esphome.io/components/captive_portal/
- ESP Web Tools (browser flasher): https://esphome.github.io/esp-web-tools/
- ESP-IDF Wi-Fi provisioning (SoftAP/BLE): https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-reference/provisioning/wifi_provisioning.html

### Audio libraries / radio projects
- ESP32-audioI2S: https://github.com/schreibfaul1/ESP32-audioI2S
- pschatzmann/esp32_radio: https://github.com/pschatzmann/esp32_radio
- yellobyte/ESP32-Webradio-PlusDLNA: https://github.com/yellobyte/ESP32-Webradio-PlusDLNA
- jtenniswood ESPHome Media Player: https://github.com/jtenniswood/esphome-media-player
- Radio-Browser API: https://api.radio-browser.info/

### Tooling
- ESP-IDF: https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/
- Arduino ESP32 core: https://github.com/espressif/arduino-esp32
- esptool: https://github.com/espressif/esptool
- Espressif Flash Download Tool: https://www.espressif.com/en/support/download/other-tools
- LVGL: https://lvgl.io/

### Community configs for this board
- HA config thread: https://community.home-assistant.io/t/waveshare-esp32-s3-touch-lcd-1-54-working-configuration/1013907
- HA ES8311/I²S gotcha thread: https://community.home-assistant.io/t/waveshare-esp32-s3-touch-epaper-1-54-working-esphome-voice-assistant-config-analog-es8311-mic-gotcha-i2s-bus-deadlock/1023975
