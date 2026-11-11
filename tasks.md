# AlarmClock — Task Breakdown

Actionable task list for building the HA-integrated Internet radio alarm clock
on the Waveshare **ESP32-S3-Touch-LCD-1.54**.

- Companion docs: [`design.md`](./design.md) (design), [`README.md`](./README.md)
- Legend: `[ ]` todo · `[~]` in progress · `[x]` done · `[!]` blocked
- Tags: **`[SW]` = doable with no hardware** (laptop only) · **`[HW]` = needs the
  physical board**
- The board is **not yet in hand**, so the list is split into **Track A (start
  now)** and **Track B (once hardware arrives)**.

---

## TL;DR — what we can do today

We can build and **fully test the Home Assistant side plus the complete device
configuration** before the hardware lands, by writing the firmware config,
the MQTT interface, and a small **device simulator** that impersonates the board
over MQTT. Then Track B becomes mostly *flash, verify, calibrate*.

```
TRACK A (no hardware)                         TRACK B (hardware)
─────────────────────                         ──────────────────
A1 decisions          ─┐                       B1 unbox + pin verify
A2 firmware config     │                       B2 flash + bring-up
A3 MQTT interface      ├─► device simulator ──► B3 radio validate
A4 station list        │        (A6)            B4 alarm validate
A5 HA integration      │                        B5 screen/UI validate
A6 simulator          ─┘                        B6 hardening/OTA/soak
A7 CI, A8 docs
```

---

# TRACK A — No hardware required (start immediately) `[SW]`

## A1. Decisions & repo prep  *(design.md Phase 0)*

- [ ] **D1. Firmware approach** (ESPHome vs ESP-IDF vs Arduino) — design.md §7, §18 Q8.
- [ ] **D2. `media_player` approach** — MQTT primitives + Universal Media Player (design.md §6.5, Q1).
- [ ] **D3. Alarm modelling** — `switch`+`time`+`select` vs `alarm_control_panel`; one vs many (Q2).
- [ ] **D4. MQTT broker** — HA Mosquitto add-on vs external (design.md §5).
- [ ] **D5. Station policy** — which stations; HTTP vs HTTPS; licensing/geo (Q5).
- [ ] **D6. Missed-alarm policy after power loss** (Q7).
- [x] **D7. `device_id` scheme — DECIDED: MAC-derived** (unique, invisible, stable); optional friendly slug is a future enhancement (design.md §9.1, §9.4).
- [ ] **D8. Wi-Fi onboarding method** — Improv-serial (+ captive-portal fallback) vs on-device setup UI; confirm **no WPS** (design.md §14.1).
- [x] **D9. `device_id` provisioning — DECIDED: MAC default, no runtime provisioning for v1.** Device reports its own id; a **physical label** maps unit ↔ id (design.md §14.2).
- [ ] Repo scaffolding: `.gitignore`, `LICENSE`, `secrets.example.yaml`, `ha/`, `firmware/`, `tools/` dirs.
- [ ] Record all decisions back into design.md §18.

## A2. Author the full firmware config  *(design.md M1/M3/M4/M5, without flashing)*

- [ ] Write the complete `alarmclock.yaml` (ESPHome) — or equivalent IDF skeleton.
- [ ] Implement **per-device `device_id`**: config override with MAC-derived
      default, **persisted in NVS** and stable across reboots/OTA (design.md §9.4).
- [ ] Add **Wi-Fi onboarding**: `improv_serial` (first setup) + `captive_portal`
      fallback; support `wifi: networks:` + static IP (design.md §14.1).
- [ ] Implement **`device_id` = MAC-derived** (D7/D9): derive it at boot, use it
      for all topic/unique_id namespacing; no runtime id entry in v1 (design.md §14.2).
- [ ] Implement a **`sensor` exposing the device id/short-MAC** so HA can show/confirm it.
- [ ] Include all components up front: display, touch, audio/speaker, time/NTP,
      Wi-Fi, MQTT, `switch`/`select`/`number`/`time`/`button`/`sensor`, alarm automations.
- [ ] Set build flags for **16 MB flash + Octal PSRAM** (design.md §3.1/§13).
- [ ] Validate the config schema: `esphome config alarmclock.yaml`.
- [ ] **Compile the firmware without a device**: `esphome compile alarmclock.yaml`
      (proves it builds; the `.bin` is ready to flash later).
- [ ] Add a firmware-version constant + changelog entry.

## A3. Design the MQTT interface  *(design.md M2, §9)*

- [ ] Finalise topic scheme + node id + `unique_id`s for every entity (design.md §9.1).
- [ ] Namespace **all** topics/`unique_id`s/`dev.ids` by the per-device id so
      **multiple clocks** coexist (design.md §9.1, §9.4). `device_id` **= MAC**
      (short/long form) — define the exact derivation + resulting patterns.
- [ ] Ensure each clock groups as its own HA device (shared `dev` block) and add a
      friendly device `name`.
- [ ] Evaluate **device-based discovery** (`homeassistant/device/<device_id>/config`,
      one message per device) vs per-entity config messages (design.md §9.4).
- [ ] Write the exact **discovery payloads** (JSON) for every entity (design.md §9.2, §6).
- [ ] Define all `*/state` topics → command mapping and availability/LWT (design.md §9.3).
- [ ] Document the contract in a `docs/mqtt-interface.md` (this is the firmware↔HA spec).

## A4. Station list  *(design.md M3, §10.4)*

- [ ] Curate the initial station list (name → URL, codec, bitrate).
- [ ] Verify each URL resolves and is a supported codec (MP3/HTTP preferred).
- [ ] Store as `data/stations.yaml` (or JSON) usable by firmware + simulator.

## A5. Home Assistant integration  *(design.md M3/M4, §6.5)*

- [ ] Write the **Universal Media Player** snippet → `ha/universal_media_player.yaml` (design.md §6.5) — templated/written **one per device**.
- [ ] Write any HA packages/automations (alarm dashboards, notifications).
- [ ] Write a **mock HA entities** file (temporary `mqtt:` YAML or helpers) to
      exercise the UI before the device exists.
- [ ] Optionally stand up a **local Mosquitto + HA** in Docker to test discovery.

## A6. Device simulator  *(enables end-to-end testing pre-hardware)*

- [ ] Write `tools/mqtt_sim.py` (Python `paho-mqtt`) that **impersonates the device**:
  - takes a `--device-id` (a simulated MAC-like id) + optional `--name` so
    **two+ simulators can run simultaneously** to prove multi-clock support (design.md §9.4),
  - publishes the same discovery payloads (A3),
  - publishes availability + state,
  - subscribes to command topics and updates state accordingly,
  - simulates alarm firing / radio state / now-playing.
- [ ] Use it to verify HA entities appear, command round-trips, availability on/off,
      and the Universal Media Player façade — **all without the board**.
- [ ] Run **two simulators at once** (different `device_id`s) to prove both clocks
      appear as separate HA devices with no topic clashes (design.md §9.4).
- [ ] Reuse the same payloads verbatim in the firmware (single source of truth).

## A7. CI  *(design.md §13.5)*

- [ ] GitHub Actions: run `esphome config` + `esphome compile` on push (works with no hardware).
- [ ] Optionally lint `tools/` and validate `data/stations.*` against a schema.
- [ ] On tag: publish release `.bin` + a web-installer manifest.

## A8. Docs, hardware prep & ordering

- [ ] Read the official **schematic PDF** and pre-verify the pin map (design.md §3.2) — no board needed.
- [ ] Resolve **RTC** (Q3) and **speaker/amp** (Q4) from docs/listing before/at unboxing.
- [ ] Order/confirm accessories (speaker if needed, USB-C PSU, microSD) (design.md §3.3).
- [ ] Write user docs: setup, Wi-Fi/MQTT provisioning, changing stations, HA usage.
- [ ] Note the **factory `.bin` recovery** procedure (design.md §13.6).
- [ ] Design the **physical device label** (short id = last 6 MAC hex, optional
      name/QR) and create a `docs/devices.md` inventory (unit ↔ id ↔ HA name) (design.md §14.2).

**Track A AC:** firmware compiles; MQTT interface + discovery payloads are frozen;
HA shows all entities (against the simulator); Universal Media Player works;
CI green; pin map pre-verified. → *Everything left is hardware validation.*

---

# TRACK B — Hardware required `[HW]`

## B1. Unbox & bring-up  *(design.md M0, Phase 1)*

- [ ] Unbox; photograph board + case; confirm case cut-outs (speaker grille, USB-C, touch).
- [ ] **Confirm the pin map** against the board/schematic; correct design.md §3.2 if needed.
- [ ] Power via USB-C; confirm `/dev/ttyACM*`; practise **BOOT** download mode.
- [ ] Flash the **vendor factory firmware**; exercise display, touch, Wi-Fi, audio.
- [ ] Confirm **audio out** (tones) and `PA_CTRL` (GPIO 7); confirm **display** (ST7789V2) + **touch** (CST816T).
- [ ] Note MAC/hostname; archive the factory `.bin`.
- [ ] Capture the vendor **MAC/QR sticker** on the board (before fitting the case);
      record it in `docs/devices.md` and apply our own underside label (design.md §14.2).

## B2. Flash our firmware & iterate  *(design.md M1)*

- [ ] `esphome run alarmclock.yaml` over USB (first flash; Boot-mode trick if needed).
- [ ] Bring up Wi-Fi + NTP + on-screen clock on real hardware.
- [ ] Confirm OTA works; confirm PSRAM is detected.
- [ ] Reconcile any config that assumed hardware (pins, timing) — feed back into A2.
- [ ] Provision a real **`device_id`**/friendly name; confirm it persists across
      reboot/OTA and that the clock appears as its own HA device (design.md §9.4).
- [ ] Test **Wi-Fi onboarding** end-to-end: Improv-serial first setup + captive
      portal fallback; confirm creds persist (design.md §14.1).

## B3. Radio validation  *(design.md M3)*

- [ ] Prove a real stream → speaker; tune buffering.
- [ ] Validate the curated stations on-device (incl. one HTTPS-only) + overnight soak.
- [ ] Confirm volume + gentle wake ramp behave on real amp.
- [ ] Verify now-playing/ICY metadata appears on the sensor.

## B4. Alarm validation  *(design.md M4)*

- [ ] Verify on-device scheduling, NVS persistence across reboot, DST transition.
- [ ] **Critical:** alarm fires with HA and broker powered off.
- [ ] Snooze/dismiss/enable-from-HA on real device.
- [ ] Confirm RTC behaviour across power loss (Q3).

## B5. Screen / UI validation  *(design.md M5)*

- [ ] LVGL screens render correctly on the 240×240 panel; touch targets usable.
- [ ] Idle/dim behaviour; ring pulse visible.

## B6. Hardening, OTA & docs  *(design.md M6)*

- [ ] Watchdog + Wi-Fi/MQTT reconnect/backoff.
- [ ] Availability (LWT) flips offline on power cut — on real hardware.
- [ ] 72-hour soak with periodic Wi-Fi drop/restore.
- [ ] OTA + safe rollback (golden/factory image).
- [ ] Finalise user docs with real screenshots/photos.

**Track B AC:** device runs 72 h unattended; alarm reliable with HA offline; OTA works;
a fresh user can set it up from the docs.

---

## Later / nice-to-haves  *(design.md M7)*

- [ ] `[HW]` Multi-stage wake ramp / easing.
- [ ] `[SW]` Editable station list from HA (config topic) — design.md §6.4.
- [ ] `[SW]` Radio-Browser API search integration.
- [ ] `[SW]` Multiple alarms (weekday/weekend sets).
- [ ] `[SW]` Sleep timer / "off in N minutes".
- [ ] `[HW]` Optional ESPHome native-API `media_player` alongside MQTT (design.md §6.5 option 2).

---

## Critical path & dependencies

```
TRACK A (now, no hardware)                       TRACK B (board in hand)
──────────────────────────                       ───────────────────────
A1 decisions ──► A2 firmware config ─┐
A1 ──► A3 MQTT interface ────────────┼──► A6 simulator ──► (HA verified)
A1 ──► A5 HA integration ────────────┘         │
A4 station list ───────────────────────────────┤
A7 CI · A8 docs/schematic ─────────────────────┘
                                               │
                                               ▼
                        B1 bring-up ─► B2 flash/iterate ─┬─► B3 radio
                                                          ├─► B4 alarm  (highest risk)
                                                          └─► B5 UI
                                                                 └─► B6 hardening/OTA/soak
```

- **Track A is fully unblocked** — start now.
- **A3 (MQTT interface) + A6 (simulator)** are the keystone: they let us build and
  test the entire HA integration before hardware.
- **Track B mostly validates** what Track A produced; expect small config back-ports.

---

## Immediate next actions

1. `[SW]` Do **A1** — lock D1–D4 (they gate repo layout and everything else).
2. `[SW]` Do **A3** — freeze the MQTT interface (blocks A5/A6 and firmware).
3. `[SW]` Scaffold **A2** (ESPHome `alarmclock.yaml`) and get `esphome compile` green in **A7**.
4. `[SW]` Build **A6** simulator, then wire **A5** and confirm entities appear in HA.
5. `[HW]` When the board arrives, jump to **B1**.
