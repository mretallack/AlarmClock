# Firmware backups

Local archives of device flash images. **Not** committed to git
(`*.bin` is git-ignored) — this README records what exists and how to restore.

## Unit: `48e620` (first alarm clock)

| Field | Value |
|---|---|
| `device_id` | `48e620` |
| Chip | ESP32-S3 (QFN56, rev v0.2), 8 MB PSRAM, 16 MB flash |
| Port | USB-Serial/JTAG (`/dev/ttyACM0`) |
| File | `factory-48e620.bin` (full 16 MB dump, offset `0x0`) |
| Size | 16 777 216 bytes |
| SHA-256 | `7aac67a6cb06ecab5ac4b4d4ad9209abe772e5e946c6d2951b8848e90dafc300` |
| Taken | 2026-11-20 |

> Full MAC address is deliberately not recorded here; see the private inventory.

### Restore the factory firmware

```bash
esptool --port /dev/ttyACM0 write_flash 0x0 backups/factory-48e620.bin
```

Or overwrite just the application (vendor demo) once we have our own build:

```bash
esphome run firmware/alarmclock.yaml
```

### Verify a backup

```bash
sha256sum backups/factory-48e620.bin   # must match the hash above
```

### If a flash goes wrong

The ESP32-S3 ROM bootloader is in mask ROM and cannot be overwritten, so the
board is effectively unbrickable:

1. Enter download mode — normally automatic over USB; if not, hold **BOOT**,
   tap **RESET**, release **BOOT**.
2. `esptool --port /dev/ttyACM0 erase_flash`
3. Re-flash our firmware or the factory image above.

(Do **not** burn eFuses for secure boot / flash encryption / disabling USB-JTAG —
those are irreversible; we don't use them.)
