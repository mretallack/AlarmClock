# AlarmClock — Task Breakdown

Actionable task list for building the HA-integrated Internet radio alarm clock
on the Waveshare **ESP32-S3-Touch-LCD-1.54**.

- Companion docs: [`design.md`](./design.md) (design), [`README.md`](./README.md)
- Legend: `[ ]` todo · `[~]` in progress · `[x]` done · `[!]` blocked
- Each phase maps to a milestone in `design.md` §17 (M0–M7).
- "AC" = acceptance criteria (definition of done).

---

## Phase 0 — Decisions & repo prep (pre-M0)

- [ ] **D1. Choose firmware approach** (ESPHome vs ESP-IDF vs Arduino) — design.md §7, §18 Q8. *Recommendation: ESPHome.*
- [ ] **D2. Accept the `media_player` approach** — MQTT primitives + built-in Universal Media Player (design.md §6.5, §18 Q1 resolved).
- [ ] **D3. Confirm alarm modelling** — `switch`+`time`+`select` vs `alarm_control_panel`; one alarm or many (design.md §18 Q2).
- [ ] **D4. Choose MQTT broker** — HA Mosquitto add-on (recommended) vs external (design.md §5).
- [ ] **D5. Confirm board RTC** — discrete I²C chip vs ESP32 internal (design.md §3.1, §18 Q3).
- [ ] **D6. Confirm speaker/amp** — onboard speaker behind grille? external connector + rating (design.md §3.3, §18 Q4).
- [ ] **D7. Station policy** — which stations; HTTP vs HTTPS endpoints; licensing/geo (design.md §18 Q5).
- [ ] **D8. Missed-alarm policy after power loss** (design.md §18 Q7).
- [ ] Repo hygiene: add `.gitignore`, `LICENSE` (Apache-2.0?), `secrets.example.yaml`.
- [ ] Create `alarmclock.yaml` (ESPHome) or `firmware/` (IDF) skeleton + `ha/` snippets dir.

**Phase AC:** decisions D1–D8 recorded (update design.md §18); repo scaffolding in place.

---

## Phase 1 — Hardware bring-up (design.md M0)

- [ ] Unbox; photograph board + case; confirm SKU/case cut-outs (speaker grille, USB-C, touch).
- [ ] Confirm the **pin map** (design.md §3.2) against the official schematic PDF.
- [ ] Power via USB-C; confirm it enumerates as `/dev/ttyACM*`; practise **BOOT** download mode.
- [ ] Flash the **vendor factory firmware** and exercise it (display, touch, Wi-Fi, audio).
- [ ] Confirm **audio out** works (speaker tones) and note `PA_CTRL` behaviour (GPIO 7).
- [ ] Confirm **display** driver (ST7789V2) and **touch** (CST816T) respond.
- [ ] Note device **MAC/hostname**; save the factory `.bin` for recovery.

**Phase AC:** display, touch and audio all verified working; pin map confirmed or corrected in design.md; factory image archived.

---

## Phase 2 — Dev environment & "hello clock" (design.md M1)

- [ ] Install toolchain (ESPHome via pipx, and/or ESP-IDF v5.5+).
- [ ] Configure build for **16 MB flash + Octal PSRAM**; confirm enough headroom.
- [ ] Bring up: Wi-Fi connection + NTP time (POSIX TZ) + a **clock face** on screen.
- [ ] Capture first successful `esphome run` (USB) then an **OTA** update.
- [ ] Add logging + a firmware-version constant.

**Phase AC:** device boots, joins Wi-Fi, shows correct local time, and accepts an OTA flash.

---

## Phase 3 — MQTT plumbing (design.md M2)

- [ ] Add `mqtt:` config with broker host/port/user/pass via `secrets.yaml` (never commit secrets).
- [ ] Publish **availability** + LWT (`online`/`offline`) on a status topic.
- [ ] Publish **discovery** for one dummy `switch`; confirm entity auto-appears in HA.
- [ ] Implement the **device block** (`dev`/identifiers/manufacturer/model) shared by all entities.
- [ ] Verify: HA restart, broker restart, device reboot → entity state persists/recovers.

**Phase AC:** a test switch is created in HA purely via MQTT discovery and round-trips on/off.

---

## Phase 4 — Radio (design.md M3)

- [ ] Choose audio stack (ESPHome speaker vs ESP32-audioI2S) and prove a single stream → speaker.
- [ ] Build the **station list** (name → URL, codec, bitrate); prefer MP3/HTTP for reliability.
- [ ] Implement **play / stop** radio (drive `PA_CTRL`, handle buffering in PSRAM).
- [ ] Implement **volume** control + gentle **wake ramp**.
- [ ] Implement **station select** and **next/prev**.
- [ ] Report **now-playing** (station name / ICY title) to a sensor.
- [ ] Expose over MQTT discovery: `switch.radio`, `select.station`, `number.volume`, `button.next/prev`, `sensor.now_playing` (design.md §6.2, §9).
- [ ] Test 5–10 stations incl. one HTTPS-only + overnight soak (design.md §16).

**Phase AC:** HA can turn radio on/off, pick a station and set volume; now-playing reflects reality; streams survive an overnight soak.

---

## Phase 5 — Alarm engine (design.md M4)

- [ ] Implement on-device scheduling: time + days-of-week + enabled, persisted to NVS/flash.
- [ ] Fire independently of HA/broker; recompute next trigger on TZ/DST change.
- [ ] On fire: wake ramp + play radio (or tone) + show ringing screen.
- [ ] Snooze (configurable minutes) and dismiss.
- [ ] Report state: `sensor.next_alarm`, `sensor.alarm_state`.
- [ ] Expose over MQTT discovery: `switch.alarm_enabled`, `time.alarm_time`, `select.alarm_days`, `number.snooze`, `button.snooze/dismiss`, alarm sensors (design.md §6.1, §9).
- [ ] **Critical test:** alarm fires with HA and broker powered off (design.md §16).
- [ ] Test DST transition + reboot persistence.

**Phase AC:** alarm rings at the set time/day even when HA/broker are down; snooze/dismiss/enable work from HA.

---

## Phase 6 — UI / UX (design.md M5)

- [ ] LVGL screens: clock, radio, alarm-set, ringing, settings (design.md §12).
- [ ] Touch interactions: play/pause, next/prev, snooze/stop, screen brightness.
- [ ] Status indicators: alarm on/off, next alarm, Wi-Fi, radio state.
- [ ] Idle/dim behaviour (e.g. dim at night), and pulsing on ring.

**Phase AC:** the clock is usable entirely on-device without HA.

---

## Phase 7 — Hardening, OTA & docs (design.md M6)

- [ ] Watchdog + reconnect/backoff for Wi-Fi & MQTT.
- [ ] Availability (LWT) correctly flips offline on power cut.
- [ ] 72-hour soak with periodic Wi-Fi drop/restore (design.md §16).
- [ ] OTA update path + **safe rollback** (keep factory/golden image).
- [ ] Add the **HA Universal Media Player** snippet as `ha/universal_media_player.yaml` (design.md §6.5) and test.
- [ ] Write user docs: setup, Wi-Fi/MQTT provisioning, changing stations, HA usage.
- [ ] Secrets handling review (gitignore, `secrets.example.yaml`).

**Phase AC:** device runs 72 h unattended; OTA works; docs let a fresh user set it up.

---

## Phase 8 — Nice-to-haves (design.md M7)

- [ ] Gentle multi-stage wake ramp / easing.
- [ ] Album art / station logos on screen.
- [ ] Editable station list from HA (config topic) — design.md §6.4.
- [ ] Radio-Browser API search integration.
- [ ] Multiple alarms (weekday/weekend sets).
- [ ] Sleep timer / "off in N minutes".
- [ ] Optional ESPHome **native-API `media_player`** alongside MQTT (design.md §6.5 option 2).

---

## Cross-cutting / ongoing

- [ ] Keep `design.md` §18 open questions updated as decisions land.
- [ ] Add `docs/images/` photos as hardware arrives.
- [ ] CI: GitHub Actions building `esphome compile` / `idf.py build`; publish release `.bin` (design.md §13.5).
- [ ] Define versioning + changelog.

---

## Critical path & dependencies

```
Phase 0 (decisions)
   └── Phase 1 (hardware bring-up)
          └── Phase 2 (hello clock) ──► Phase 3 (MQTT plumbing)
                                             ├── Phase 4 (radio)
                                             └── Phase 5 (alarm engine)
                                                     └── Phase 6 (UI)
                                                            └── Phase 7 (hardening/OTA/docs)
                                                                   └── Phase 8 (nice-to-haves)
```

- **Phase 1 blocks everything** — verify hardware/pins first.
- **Phase 3 blocks Phases 4–5** — the MQTT/discovery plumbing is shared.
- **Phase 5 (alarm) is the highest-risk item** — allocate extra soak/edge-case time.

---

## Immediate next actions

1. Start **Phase 0** — lock D1–D4 (they gate the repo layout).
2. Begin **Phase 1** — unbox, verify pin map, flash the vendor demo.
3. Then scaffold the chosen toolchain (ESPHome `alarmclock.yaml`) and go for the "hello clock" in Phase 2.
