# MQTT Interface Specification

Canonical contract between the alarm-clock firmware and Home Assistant.

**Decision (2026-11-20):** we **accept ESPHome's native MQTT scheme** as the wire
format (option (a) — see `tasks.md` A3). ESPHome generates the topics,
`unique_id`s and discovery payloads; we document the result here so the
simulator (`tools/mqtt_sim.py`) and the HA snippets (`ha/`) match what the
device actually publishes.

See `design.md` §5, §6, §9, §9.4 for background.

---

## 1. Device identity

| Concept | Value |
|---------|-------|
| `device_id` | **last 6 hex of the Wi-Fi station MAC**, lowercase — e.g. `48e620` |
| MQTT node name | `alarmclock-<device_id>` (hyphen) |
| Discovery prefix | `homeassistant` |
| Availability topic | `alarmclock-<device_id>/status` |
| HA device identifier (`dev.ids`) | the **12-hex MAC without separators**, e.g. `7c0c5f48e620` |

`device_id` is derived at boot from the MAC (design.md §9.1, §14.2) — unique,
invisible, no provisioning. A physical label carries the short id.
ESPHome derives the node name from the `device_id` substitution at build time.

---

## 2. Topic scheme

ESPHome namespaces **every** topic by node name, and includes the component in
the path:

```
# availability (retained + LWT)
alarmclock-<device_id>/status                              online | offline

# per entity  (<component> ∈ switch|time|select|number|button|sensor|binary_sensor)
alarmclock-<device_id>/<component>/<object_id>/state       <value>   (retained)
alarmclock-<device_id>/<component>/<object_id>/command     <cmd>     (subscribe)

# discovery (retained)
homeassistant/<component>/alarmclock-<device_id>/<object_id>/config   <json>
```

- `<object_id>` is ESPHome's slugified entity name (see §3).
- State values are ESPHome-formatted: `switch`→`ON`/`OFF`,
  `number`→float text (`"40.000000"`), `select`→the option text,
  `time`→JSON `{"hour":H,"minute":M,"second":S}`.
- `uniq_id` = `ESP<component><object_id>` (e.g. `ESPswitchalarm_enabled`).

---

## 3. Entities

| component | object_id | HA name | command payload |
|-----------|-----------|---------|-----------------|
| switch | `alarm_enabled` | Alarm enabled | `ON` / `OFF` |
| time | `alarm_time` | Alarm time | `{"hour":7,"minute":30,"second":0}` |
| select | `alarm_repeat` | Alarm repeat | `off`\|`once`\|`daily`\|`weekdays`\|`weekends`\|`custom` |
| number | `snooze__min_` | Snooze (min) | `1`..`60` |
| number | `volume` | Volume | `0`..`100` |
| button | `snooze` | Snooze | any |
| button | `dismiss` | Dismiss | any |
| button | `next_station` | Next station | any |
| button | `previous_station` | Previous station | any |
| sensor | `alarm_state` | Alarm state | _(read-only)_ |
| sensor | `now_playing` | Now playing | _(read-only)_ |
| sensor | `firmware` | Firmware | _(read-only)_ |
| sensor | `device_id` | Device id | _(read-only)_ |
| sensor | `wi-fi_signal` | Wi-Fi signal | _(read-only)_ |
| binary_sensor | `mqtt` | MQTT | _(read-only)_ |

> **Planned (Track B3, once audio is wired):** `switch radio`, `select station`,
> `button reboot` — same scheme (`alarmclock-<id>/switch/radio/command`, …).
> The simulator already emits these so the HA side can be built ahead of the
> hardware audio work.

---

## 4. Discovery payloads (as published)

Shared device block (every entity):
```json
"dev": {
  "ids": "7c0c5f48e620",
  "name": "Alarm Clock",
  "mf": "Espressif",
  "mdl": "esp32-s3-devkitc-1",
  "sw": "2026.10.2 (config hash 0x00ab48ba)",
  "cns": [["mac", "7c0c5f48e620"]]
}
```
Availability on entities: `"avty_t": "alarmclock-<device_id>/status"`.

**switch / alarm_enabled**
```json
{"name":"Alarm enabled",
 "stat_t":"alarmclock-48e620/switch/alarm_enabled/state",
 "cmd_t":"alarmclock-48e620/switch/alarm_enabled/command",
 "avty_t":"alarmclock-48e620/status","uniq_id":"ESPswitchalarm_enabled","dev":{...}}
```

**time / alarm_time**
```json
{"name":"Alarm time",
 "stat_t":"alarmclock-48e620/time/alarm_time/state",
 "cmd_t":"alarmclock-48e620/time/alarm_time/command",
 "avty_t":"alarmclock-48e620/status","uniq_id":"ESPtimealarm_time","dev":{...}}
```

**select / alarm_repeat**
```json
{"name":"Alarm repeat",
 "ops":["off","once","daily","weekdays","weekends","custom"],
 "stat_t":"alarmclock-48e620/select/alarm_repeat/state",
 "cmd_t":"alarmclock-48e620/select/alarm_repeat/command",
 "avty_t":"alarmclock-48e620/status","uniq_id":"ESPselectalarm_repeat","dev":{...}}
```

**number / volume**
```json
{"name":"Volume","min":0,"max":100,"step":1,
 "stat_t":"alarmclock-48e620/number/volume/state",
 "cmd_t":"alarmclock-48e620/number/volume/command",
 "avty_t":"alarmclock-48e620/status","uniq_id":"ESPnumbervolume","dev":{...}}
```

**button / snooze**
```json
{"name":"Snooze",
 "cmd_t":"alarmclock-48e620/button/snooze/command",
 "avty_t":"alarmclock-48e620/status","uniq_id":"ESPbuttonsnooze","dev":{...}}
```

**sensor / alarm_state**
```json
{"name":"Alarm state",
 "stat_t":"alarmclock-48e620/sensor/alarm_state/state",
 "avty_t":"alarmclock-48e620/status","uniq_id":"ESPsensoralarm_state","dev":{...}}
```

> The executable form of this contract is `tools/mqtt_sim.py`
> (`Sim.discovery()`); keep the two in sync. The live topics were also
> verified against the real device (unit `48e620`).

---

## 5. Command semantics (verified on hardware)

| Command topic | Payload | Effect |
|---------------|---------|--------|
| `…/switch/alarm_enabled/command` | `ON`/`OFF` | Enable/disable alarm → `alarm_state` `idle`/`disabled` |
| `…/time/alarm_time/command` | `{"hour":7,"minute":30,"second":0}` | Set alarm time; echoed on `…/state` |
| `…/select/alarm_repeat/command` | option text | Set repeat |
| `…/number/snooze__min_/command` | `1`..`60` | Snooze duration |
| `…/number/volume/command` | `0`..`100` | Volume |
| `…/button/snooze/command` | any | Snooze the ringing alarm |
| `…/button/dismiss/command` | any | Stop the ringing alarm |
| `…/button/next_station/command` / `previous_station` | any | Change station |

HA tolerates any payload on `button`/`command` topics (it just triggers).

---

## 6. State machine (alarm)

```
disabled ──enable──► idle ──time reached──► ringing ──snooze──► snoozed
                       ▲                        │                 │
                       └────────dismiss─────────┘◄────trigger─────┘
```

- `sensor/alarm_state` mirrors this (`disabled`/`idle`/`ringing`/`snoozed`).
- The alarm **fires on-device** even if HA/MQTT is down (design.md §11).

---

## 7. Availability / LWT

On connect the firmware publishes `alarmclock-<device_id>/status = "online"`
(retained) and registers an MQTT **Last Will** of `"offline"` on the same topic.
HA marks the device unavailable if it drops. (`binary_sensor/<id>/mqtt` mirrors it.)

---

## 8. Multi-device

Every topic and `unique_id` embeds the node name `alarmclock-<device_id>`, and
each clock's discovery groups under its own HA device, so N clocks share one
broker with no collisions (design.md §9.4). Run two simulators with different
ids to verify.

---

## 9. Note on HA entity ids

Home Assistant derives each `entity_id` from the entity **name**
(e.g. `switch.alarm_enabled`, `time.alarm_time`) — it is **not** prefixed with
the device id. With several clocks sharing a broker, HA appends a suffix
(`switch.alarm_enabled_2`) or you can rename in the UI. Keep this in mind when
writing automations; the `ha/universal_media_player.yaml` snippet notes the same.
