# AlarmClock

A self-built **Internet radio alarm clock** based on the
**Waveshare ESP32-S3-Touch-LCD-1.54** development board, integrated with
**Home Assistant** over **MQTT (with MQTT discovery)**.

Home Assistant will be able to:

- Set / change the alarm time
- Enable / disable the alarm (per day-of-week)
- Turn the radio on/off and select a station
- Control volume
- (Ideally) expose the radio as a `media_player` entity

The device itself provides an on-screen clock, touch controls, a local
speaker, and snooze/dismiss buttons.

> 📄 **See [`design.md`](./design.md) for the full design, research, tools,
> firmware/flashing strategy, risks and roadmap.** No implementation has been
> started yet.

## Hardware

- **Board:** Waveshare ESP32-S3-Touch-LCD-1.54
  - https://github.com/waveshareteam/ESP32-S3-Touch-LCD-1.54
  - https://www.amazon.co.uk/gp/product/B0GS9CW66Z/ref=sw_img_1?smid=&psc=1

## Links

- Board source repo (Waveshare): https://github.com/waveshareteam/ESP32-S3-Touch-LCD-1.54
- Purchase (Amazon UK): https://www.amazon.co.uk/gp/product/B0GS9CW66Z/ref=sw_img_1?smid=&psc=1

## Status

🟡 **Design phase** — design documented, implementation not started.

## License

TBD (Apache-2.0 to match the Waveshare vendor code is a sensible default).
