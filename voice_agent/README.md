# voice_agent — dumb voice agent, phase 2

A tiny PC-side agent for the alarm clock. **No Home Assistant, no LLM.** It can
make the clock speak, and it can record the clock's microphone.

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

python3 -m voice_agent.agent listen
  └─ UDP "LISTEN" ─────────────────►  stop radio, start mic
  ◄────────────── raw PCM :5005 ────  microphone (ES8311 ADC, I2S)
  └─ write out/mic.wav
  └─ UDP "STOP" ───────────────────►  stop mic
```

The mic and speaker share one I2S bus. They cannot run at the same time. The PC
drives the handover: `LISTEN` stops the radio and starts the mic; `PLAY` stops
the mic and plays the reply.

The device is expected at `10.0.0.97`, the PC at `10.0.0.78`. Change both in
`config.toml` if your LAN differs.

## Run

```bash
# from the repo root
python3 -m voice_agent.agent chime              # play a chime on the clock
python3 -m voice_agent.agent listen --seconds 5 # record 5s of mic audio
python3 -m voice_agent.agent stop               # stop the mic
python3 -m voice_agent.agent serve              # keep the HTTP server running
python3 -m voice_agent.agent run                # continuous listen -> answer loop
```

`listen` writes `voice_agent/out/mic.wav` and prints a level meter. If the meter
stays at 0, the mic is not hearing anything (check the bus handover and the
ES8311 ADC).

## Protocol

One UTF-8 command per UDP datagram, port **5006**:

| Command | Meaning |
|---|---|
| `LISTEN` | stop the radio and start the mic |
| `PLAY <http-url>` | stop the mic and play the URL as an announcement |
| `STOP` | stop the mic |
| `PING` | liveness probe (logged by the device) |

Audio uplink: raw PCM, 48 kHz, 16-bit, mono, UDP port **5005**.

## Firmware requirement

The device needs:

- a `udp:` control block on port 5006,
- a second `udp:` block on port 5005 for the PCM uplink,
- an `i2s_audio` microphone on the shared `i2s_out` bus (`i2s_din_pin: GPIO11`),
- a `Voice Agent` switch that stops the radio and captures the mic.

See `firmware/alarmclock.yaml`.

## Tests

```bash
python3 -m pytest voice_agent/tests
```

## Calibrating with a cue (`calibrate`)

If you can't tell when to talk, use `calibrate`. It waits `--delay` seconds,
plays a chime on the clock as the "start talking" cue, then records a fixed
window and reports room noise vs speech with a suggested gate:

```bash
python3 -m voice_agent.agent calibrate --delay 20 --seconds 40
```

You don't need to stop on cue — the report picks out your speech from the room
noise by percentile. Walk to the room during the delay, talk when you hear the
chime, then stop whenever.

## The dumb loop (`run`)

`run` is the actual agent: it arms the mic, waits for a burst of speech above an
RMS gate, records the utterance to `out/heard.wav`, then answers with a chime
played through the clock. No wake word, no LLM, no Home Assistant — it reacts to
any sufficiently loud sound.

```bash
python3 -m voice_agent.agent run --threshold 300 --silence-ms 700 --max-seconds 8
```

The gate is calibrated in raw 16-bit RMS units. Measured on this board: a quiet
room sits around 14–25, speech peaks around 180–240. The default threshold of 60
sits between them. Raise it if background noise triggers it; lower it if your
voice never does.

## Not yet

- Wake word
- Real speech recognition / replies beyond a chime
- Conversation state machine
