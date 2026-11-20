# Task brief: bedside stand for the alarm clock

Handoff for a new agent. Design a **stand** for the alarm clock that **lifts the
device off the surface** and **routes the USB-C power cable with a bend so it
exits out the back** (the connector faces straight down out of the case bottom).

## The device

- **SKU:** Waveshare **ESP32-S3-Touch-LCD-1.54-EN** (Amazon UK `B0GS9CW66Z`).
- **Form factor:** square white plastic case, shipped enclosed (the `-EN`
  variant). Flat back. Front is a 1.54" 240×240 **capacitive touch** LCD.
  Photo in repo: `docs/images/alarmclock-case.jpg` (also in `README.md`).
- **Orientation:** the **USB-C port is on the bottom edge** and points straight
  down, so the cable exits downward and out along the tabletop — the problem
  this stand solves.
- **Other case features to preserve access to:** speaker grille (top/back),
  a side slot (microSD/reset — vertical slot visible on the left edge in the
  photo), and the full touchscreen face.
- Source of truth for the hardware: `design.md` §3.1 (board), §3.2 (pins),
  `docs/devices.md`.

## Goal & constraints

1. **Lift** the device up so the down-facing USB-C plug isn't pinched against
   the tabletop.
2. **Bend the cable:** the cable enters at the bottom and must **exit the back**
   of the stand — shape an internal channel/lip that holds a smooth ≥ 90° bend
   and relieves strain on the connector.
3. Stable on a **bedside table**; cable pull must not topple it.
4. **Do not obstruct** the screen (touch), speaker grille, or the side slot.
5. Bedside aesthetic; v1 is allowed to be simple (3D-printable or folded).
6. Not a permanent mod to the device — no gluing to the case; friction/ledge fit.

## Measurements the agent must gather FIRST (not yet recorded)

`design.md` only says to *confirm case dimensions during bring-up* — they are
**not documented**. Get these with calipers and add them to this file:

- [ ] Case **width × height × depth** (mm).
- [ ] **USB-C port**: distance from each side edge, port width/height, and how
      far the plug body protrudes below the case bottom.
- [ ] Mass of the device (g) — for stability/centre-of-gravity.
- [ ] Bottom-face geometry: is it flat? any feet, seams, or recesses?
- [ ] Speaker-grille and side-slot locations (so the stand clears them).
- [ ] Angled viewing preference: flat-upright vs ~10–20° back tilt.

## Open questions for the user (confirm before building)

- Output format: **parametric CAD / 3D-print STL** (e.g. OpenSCAD), or a
  printable 2D template, or a purchased stand to adapt?
- Print material / printer constraints, if 3D printing.
- Desired tilt angle and how high it should lift.
- Cable style/plug: right-angle vs straight USB-C connector.

## Where to record the result

- New design section (or `docs/stand.md`) + measured dimensions above.
- Keep `design.md` §3.1 / §17 M0 "case fit" items consistent with findings.
