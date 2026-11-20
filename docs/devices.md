# Device inventory

Map each physical alarm clock to its MQTT `device_id`, HA device and label
(design.md §14.2). Update as units are built.

| Label (on case) | `device_id` (last 6 MAC hex) | MAC | HA device name | Location | Notes |
|-----------------|------------------------------|-----|----------------|----------|-------|
| `48e620`        | `48e620`                     | _private_ | Alarm Clock 48e620 | Bedroom | first unit; factory fw backed up (`backups/`) |
|                 |                              |     |                |          | |

> The `device_id` is derived from the Wi-Fi MAC at boot; the physical label
> carries the short id so you can tell units apart. Keep full MACs out of public
> repos/screenshots.
