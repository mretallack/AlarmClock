# MQTT Interface Specification

Canonical contract between the alarm-clock firmware and Home Assistant.
This is the **single source of truth** — the firmware (`firmware/`), the
simulator (`tools/mqtt_sim.py`) and the HA snippets (`ha/`) all implement this.

See `design.md` §5, §6, §9, §9.4 for background.

---

## 1. Device identity

| Concept | Value |
|---------|-------|
| `device_id` | **last 6 hex of the Wi-Fi station MAC**, lowercase — e.g. `b8d61f` |
| MQTT node id | `alarmclock_<device_id>` |
| unique_id prefix | `alarmclock_<device_id>_` |
| HA device identifier | `alarmclock-<device_id>` |
| Availability topic | `alarmclock/<device_id>/status` |
| Discovery prefix | `homeassistant` |

`device_id` is derived at boot from the MAC (design.md §9.1, §14.2) — unique,
invisible, no provisioning. A physical label carries the short id.

---

## 2. Topic scheme

```
alarmclock/<device_id>/status                       online | offline   (retained + LWT)
alarmclock/<device_id>/alarm/enabled/{set,state}     ON | OFF
alarmclock/<device_id>/alarm/time/{set,state}        HH:MM:SS
alarmclock/<device_id>/alarm/days/{set,state}        off|once|daily|weekdays|weekends|custom
alarmclock/<device_id>/alarm/snooze_minutes/{set,state}  1..60
alarmclock/<device_id>/alarm/snooze/cmd              PRESS
alarmclock/<device_id>/alarm/dismiss/cmd             PRESS
alarmclock/<device_id>/alarm/state                   idle|ringing|snoozed|disabled
alarmclock/<device_id>/alarm/next                    ISO-8601 timestamp (retained)
alarmclock/<device_id>/radio/power/{set,state}       ON | OFF
alarmclock/<device_id>/radio/station/{set,state}     <station name>
alarmclock/<device_id>/radio/volume/{set,state}      0..100
alarmclock/<device_id>/radio/next/cmd                PRESS
alarmclock/<device_id>/radio/prev/cmd                PRESS
alarmclock/<device_id>/radio/now_playing             <text>   (retained)
alarmclock/<device_id>/device/ip                     <ip>     (retained)
alarmclock/<device_id>/device/rssi                   <dBm>    (retained)
alarmclock/<device_id>/device/firmware               <ver>    (retained)
alarmclock/<device_id>/device/id                     <device_id> (retained)
alarmclock/<device_id>/device/mqtt                   online|offline (retained)
alarmclock/<device_id>/device/reboot/cmd             PRESS
```

- `{set,state}`: firmware **subscribes** to `.../set` and **publishes** `.../state`
  (retained). Commands are also reflected back on `.../state` (optimistic + confirm).
- Homie-style `.../cmd` topics are **buttons** (payload `PRESS`).
- All `.../state` and `.../status` messages are **retained** so HA recovers after
  a restart.

---

## 3. Discovery topics

Component discovery: `homeassistant/<component>/alarmclock_<device_id>/<object_id>/config`

| object_id | component | HA entity |
|-----------|-----------|-----------|
| `alarm_enabled` | switch | Alarm enabled |
| `alarm_time` | time | Alarm time |
| `alarm_days` | select | Alarm repeat |
| `alarm_snooze_minutes` | number | Snooze (min) |
| `alarm_snooze` | button | Snooze |
| `alarm_dismiss` | button | Dismiss |
| `alarm_state` | sensor | Alarm state |
| `alarm_next` | sensor | Next alarm |
| `radio` | switch | Radio |
| `station` | select | Station |
| `volume` | number | Volume |
| `next_station` | button | Next station |
| `prev_station` | button | Previous station |
| `now_playing` | sensor | Now playing |
| `ip` | sensor | IP |
| `rssi` | sensor | Wi-Fi signal |
| `firmware` | sensor | Firmware |
| `device_id` | sensor | Device id |
| `mqtt` | binary_sensor | MQTT |
| `reboot` | button | Reboot |

All payloads share the device block:

```json
"dev": {
  "ids": "alarmclock-<device_id>",
  "name": "Alarm Clock <device_id>",
  "mf": "Custom",
  "mdl": "ESP32-S3-Touch-LCD-1.54",
  "sw": "<firmware version>"
}
```
and reference availability:
```json
"avty_t": "alarmclock/<device_id>/status"
```

### 3.1 Example payloads

**switch / alarm_enabled**
```json
{
  "name": "Alarm enabled",
  "uniq_id": "alarmclock_<device_id>_alarm_enabled",
  "cmd_t": "alarmclock/<device_id>/alarm/enabled/set",
  "stat_t": "alarmclock/<device_id>/alarm/enabled/state",
  "avty_t": "alarmclock/<device_id>/status",
  "dev": { "ids": "alarmclock-<device_id>" }
}
```

**time / alarm_time**
```json
{
  "name": "Alarm time",
  "uniq_id": "alarmclock_<device_id>_alarm_time",
  "cmd_t": "alarmclock/<device_id>/alarm/time/set",
  "stat_t": "alarmclock/<device_id>/alarm/time/state",
  "avty_t": "alarmclock/<device_id>/status",
  "dev": { "ids": "alarmclock-<device_id>" }
}
```

**select / station**
```json
{
  "name": "Station",
  "uniq_id": "alarmclock_<device_id>_station",
  "cmd_t": "alarmclock/<device_id>/radio/station/set",
  "stat_t": "alarmclock/<device_id>/radio/station/state",
  "options": ["BBC Radio 4", "BBC Radio 6 Music", "Classic FM", "Absolute Radio"],
  "avty_t": "alarmclock/<device_id>/status",
  "dev": { "ids": "alarmclock-<device_id>" }
}
```

> The exact, complete payloads are generated by `tools/mqtt_sim.py`
> (see `build_discovery()`), which is the executable form of this table.
> Keep the two in sync.

---

## 4. Command semantics

| Command | Payload | Effect |
|---------|---------|--------|
| `alarm/enabled/set` | `ON`/`OFF` | Enable/disable alarm |
| `alarm/time/set` | `HH:MM:SS` | Set alarm time |
| `alarm/days/set` | one of the day options | Set repeat |
| `alarm/snooze_minutes/set` | `1`..`60` | Snooze duration |
| `alarm/snooze/cmd` | `PRESS` | Snooze the ringing alarm |
| `alarm/dismiss/cmd` | `PRESS` | Stop the ringing alarm |
| `radio/power/set` | `ON`/`OFF` | Start/stop playback |
| `radio/station/set` | station name | Select + play station |
| `radio/volume/set` | `0`..`100` | Set volume |
| `radio/next/cmd` / `prev/cmd` | `PRESS` | Change station |
| `device/reboot/cmd` | `PRESS` | Reboot |

---

## 5. State machine (alarm)

```
disabled ──enable──► idle ──time reached──► ringing ──snooze──► snoozed
                       ▲                        │                 │
                       └────────dismiss─────────┘◄────trigger─────┘
```

- `alarm/state` mirrors this; `alarm/next` carries the next fire timestamp
  (empty if disabled).
- The alarm **fires on-device** even if HA/MQTT is down (design.md §11).

---

## 6. Availability / LWT

On connect the firmware publishes `alarmclock/<device_id>/status = "online"`
(retained) and registers an MQTT **Last Will** of `"offline"` on the same topic.
HA marks the device unavailable if it drops.

---

## 7. Multi-device

Every topic, `unique_id` and `dev.ids` embeds `<device_id>`, so N clocks share
one broker with no collisions and each appears as its own HA device
(design.md §9.4). Run two simulators with different ids to verify.
