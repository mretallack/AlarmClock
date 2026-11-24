# voice_agent — dumb voice agent, phase 1

A tiny PC-side agent that makes the alarm clock speak. **No Home Assistant, no
LLM.** Phase 1 is one direction only: PC → device audio. The microphone /
uplink comes in phase 2.

## How it works

```
PC                                   Alarm clock (ESPHome)
──────────────────────────────       ─────────────────────────────
python3 -m voice_agent.agent chime
  ├─ generate out/reply.wav
  ├─ serve http://10.0.0.78:8000/
  └─ UDP "PLAY <url>" ─────────────►  udp: on_receive
                                       └─ media_player.play_media(announcement)
                                            └─ HTTP GET /reply.wav
                                            └─ speaker (ES8311 + PA)
```

The device is expected to be at `10.0.0.97`, the PC at `10.0.0.78`. Change both
in `config.toml` if your LAN differs.

## Run

```bash
# from the repo root
python3 -m voice_agent.agent chime
```

That generates a short three-note chime, serves it over HTTP, sends the PLAY
command, and waits for the device to fetch and play it.

Other commands:

```bash
python3 -m voice_agent.agent serve              # keep the HTTP server running
python3 -m voice_agent.agent play <url>         # send PLAY for an existing URL
```

## Protocol

One UTF-8 command per UDP datagram, port **5006**:

| Command | Meaning |
|---|---|
| `PLAY <http-url>` | play the URL as a media announcement |
| `STOP` | stop playback |
| `PING` | liveness probe (logged by the device) |

No framing, no JSON — easy to test with `nc`/`tcpdump`.

## Firmware requirement

The device needs a `udp:` block that listens on 5006 and calls
`media_player.play_media` with `announcement: true` for a `PLAY` command. See
`firmware/alarmclock.yaml`.

## Tests

```bash
python3 -m pytest voice_agent/tests
```

## Not in phase 1

- Microphone uplink (device → PC)
- Wake word
- VAD / conversation state
- TTS (the chime is a placeholder; espeak/piper can be added later)
