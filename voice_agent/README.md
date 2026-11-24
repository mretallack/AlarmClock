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
  ◄────────────── raw PCM :5005 ────  microphone (ES7210 ADC, I2S)
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
stays at 0, the mic is not hearing anything — check the bus handover and that the
`es7210` `audio_adc` block is present (without it the ADC stays powered down and
drives silence on I2S DIN).

## Protocol

One UTF-8 command per UDP datagram, port **5006**:

| Command | Meaning |
|---|---|
| `LISTEN` | stop the radio and start the mic |
| `PLAY <http-url>` | stop the mic and play the URL as an announcement |
| `STOP` | stop the mic |
| `PING` | liveness probe (logged by the device) |

Audio uplink: raw PCM, **16 kHz**, 16-bit, mono, UDP port **5005**.

The 16 kHz rate is not cosmetic: the on-device wake word requires it, and the
ES7210 ADC must be configured to the same rate (`audio_adc: sample_rate: 16000`).
A 48 kHz ADC read as 16 kHz produces noise, not voice.

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
room sits around 14–32, speech peaks around 166–358. The default threshold of 90
sits between them. Raise it if background noise triggers it; lower it if your
voice never does.

## Status: where we got to

Working end-to-end:

- **PC → clock speaker.** `chime` / `PLAY <url>` generates a WAV, serves it over
  HTTP and plays it on the clock as an announcement. Verified.
- **Clock mic → PC.** `listen` arms the mic over UDP and records real PCM to
  `out/mic.wav`. Verified: 498 packets, all non-zero, peak 471 RMS.
- **Speech is now actually audible.** After the ES7210 fixes the capture shows
  real dynamics (10 % of 20 ms windows above RMS 60, peak 823) instead of the
  flat ~1 kHz hum we started with. `calibrate` suggests a gate of ~99.
- **The dumb loop** (`run`) does listen → RMS gate → chime reply, no LLM and no
  Home Assistant. See "The dumb loop" above.

## The blocker: on-device wake word never fires

The on-device `micro_wake_word` engine (`hey_jarvis`, 16 kHz) is configured and
reported as loaded — `[micro_wake_word] Wake Word: Hey Jarvis, cutoff 0.97` — but
it has **never** produced a detection. The device never sends `WAKE`, so
`python3 -m voice_agent.agent wake` waits forever.

Three bugs were found and fixed on the way; one is still open:

1. **Mic was never initialised.** The firmware configured the ES8311 (the DAC)
   but never the ES7210 (the 4-channel ADC that actually owns the mic array), so
   the ADC stayed powered down and drove zeros. Fixed with an `audio_adc:
   platform: es7210` block. This was the "all-zero PCM" bug.
2. **Sample-rate mismatch.** The ES7210 was configured for 48 kHz while the
   microphone was read at 16 kHz, which yields noise-like data. Fixed by setting
   the ADC to 16 kHz.
3. **The wake-word engine was never re-armed.** `STOP` stopped the engine and
   nothing restarted it, so after any PC capture "hey jarvis" was dead until a
   reboot. Fixed: `STOP` now re-arms the engine when the radio is off.

Still open — the engine is armed but does not detect. Remaining suspects, in
order:

- **The shared I2S bus.** `micro_wake_word` and the speaker both hang off
  `i2s_out`; the handover is driven by the PC over UDP. If the bus is left in the
  speaker's 48 kHz format when the engine arms, the engine sees the wrong rate.
- **Signal level.** The mic is quiet even at 30 dB gain (peak 823 of 32767 with
  someone talking). The model may simply not have enough SNR.
- **Model/threshold.** `hey_jarvis` at cutoff 0.97 is strict; a lower cutoff or a
  different model may be needed.
- **ES7210 channel mapping.** The ADC is 4-channel non-TDM; only one slot is
  read. If the wrong slot is selected the engine gets a near-silent channel.

Diagnostic that was in place when we stopped: `logger: logs: micro_wake_word:
DEBUG` (the engine's state changes and probabilities are DEBUG-only; at INFO it
logs nothing at all, which is why the first tests looked like the engine was
missing).

Next step if we pick this up: run the engine with DEBUG logging while saying
"hey jarvis", and check whether the state is `DETECTING_WAKE_WORD` and what
probability the model reports.

## Not yet

- Wake word (blocked, see above)
- Real speech recognition / replies beyond a chime
- Conversation state machine
