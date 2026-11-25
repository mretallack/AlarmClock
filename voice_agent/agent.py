"""PC-side dumb voice agent — phase 1: make the alarm clock speak.

Usage:
    python3 -m voice_agent.agent chime          # generate a chime and play it
    python3 -m voice_agent.agent serve          # just serve ./out for manual tests
    python3 -m voice_agent.agent play <url>     # send a PLAY command for a URL

Nothing here talks to Home Assistant, and no LLM is involved.
"""

from __future__ import annotations

import argparse
import socket
import sys
import threading
import time
import tomllib
from pathlib import Path

from . import audio, ha, protocol, server, stt, tts, uplink

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.toml"
OUT_DIR = ROOT / "out"


def load_config(path: Path = CONFIG_PATH) -> dict:
    with path.open("rb") as fh:
        return tomllib.load(fh)


def send_command(cfg: dict, cmd: protocol.Command, *, timeout: float = 2.0) -> None:
    host = cfg["device"]["host"]
    port = int(cfg["device"]["command_port"])
    payload = cmd.encode()
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        sock.sendto(payload, (host, port))
    print(f"[udp] -> {host}:{port} {payload.decode().strip()!r}", flush=True)


def transcribe_heard(path: Path, args: argparse.Namespace) -> str:
    """Transcribe a captured utterance, tolerating a missing/broken STT setup."""
    if getattr(args, "no_stt", False):
        return ""
    try:
        text = stt.transcribe(path, model_name=args.stt_model)
    except Exception as exc:  # keep the dumb loop alive if STT is unavailable
        print(f"[stt] failed: {exc}", flush=True)
        return ""
    print(f"[stt] {text!r}", flush=True)
    return text


def answer_utterance(cfg: dict, text: str, args: argparse.Namespace) -> tuple[Path, float]:
    """Turn a transcript into a spoken reply file. Returns (path, seconds).

    With HA enabled the text goes to HA Assist and its speech is spoken by
    Piper. Otherwise, or on any failure, fall back to the local chime.
    """
    reply_rate = int(cfg["audio"]["sample_rate"])
    reply = OUT_DIR / "reply.wav"
    if text and not getattr(args, "no_ha", False):
        try:
            result = ha.ask(text, agent_id=getattr(args, "agent_id", None))
            speech = result.get("speech") or ""
            print(f"[ha] {result.get('response_type')}: {speech!r}", flush=True)
            if speech:
                tts.speak(speech, reply, sample_rate=reply_rate)
                return reply, tts.duration_seconds(reply)
        except Exception as exc:
            print(f"[ha] failed: {exc}", flush=True)
    audio.generate_chime(reply, sample_rate=reply_rate, volume=getattr(args, "volume", 0.35))
    return reply, audio.duration_seconds(reply)


def cmd_chime(cfg: dict, args: argparse.Namespace) -> int:
    wav = audio.generate_chime(
        OUT_DIR / "reply.wav",
        sample_rate=int(cfg["audio"]["sample_rate"]),
        volume=args.volume,
    )
    seconds = audio.duration_seconds(wav)
    public_host = cfg["server"]["public_host"]
    port = int(cfg["server"]["port"])
    url = f"http://{public_host}:{port}/{wav.name}"

    print(f"[chime] {wav} ({seconds:.2f}s) -> {url}", flush=True)
    with server.AudioServer(OUT_DIR, cfg["server"]["bind"], port):
        send_command(cfg, protocol.play(url))
        # Give the device time to fetch + play. No ACK in phase 1.
        time.sleep(seconds + args.margin)
    return 0


def cmd_play(cfg: dict, args: argparse.Namespace) -> int:
    send_command(cfg, protocol.play(args.url))
    return 0


def cmd_serve(cfg: dict, args: argparse.Namespace) -> int:
    port = int(cfg["server"]["port"])
    public_host = cfg["server"]["public_host"]
    print(f"[http] serving {OUT_DIR} on http://{public_host}:{port}/", flush=True)
    srv = server.AudioServer(OUT_DIR, cfg["server"]["bind"], port).start()
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass
    finally:
        srv.stop()
    return 0


def cmd_listen(cfg: dict, args: argparse.Namespace) -> int:
    """Tell the device to open its mic, record the PCM, then stop the mic."""
    audio_port = int(cfg["device"].get("audio_port", 5005))
    sample_rate = int(cfg["audio"].get("uplink_sample_rate", 16000))
    path = OUT_DIR / "mic.wav"

    send_command(cfg, protocol.listen())
    # Let the device stop the radio and start the mic before we bind.
    time.sleep(0.4)
    try:
        stats = uplink.record(
            path,
            port=audio_port,
            sample_rate=sample_rate,
            seconds=args.seconds,
            verbose=not args.quiet,
        )
    finally:
        send_command(cfg, protocol.stop())

    print(
        f"[mic] saved {stats['path']}  "
        f"{stats['seconds']}s  {stats['packets']} packets  "
        f"peak RMS {stats['peak_rms']}",
        flush=True,
    )
    return 0


def cmd_run(cfg: dict, args: argparse.Namespace) -> int:
    """Continuous dumb loop: listen, gate on speech, answer with a chime.

    No LLM, no Home Assistant. The device and speaker share one I2S bus, so the
    loop hands the bus back and forth: LISTEN -> capture -> STOP -> PLAY.
    """
    audio_port = int(cfg["device"].get("audio_port", 5005))
    sample_rate = int(cfg["audio"].get("uplink_sample_rate", 16000))
    reply_rate = int(cfg["audio"]["sample_rate"])
    public_host = cfg["server"]["public_host"]
    port = int(cfg["server"]["port"])
    url = f"http://{public_host}:{port}/reply.wav"

    srv = server.AudioServer(OUT_DIR, cfg["server"]["bind"], port).start()
    print(f"[run] listening on UDP {audio_port}, threshold {args.threshold:.0f}", flush=True)
    try:
        while True:
            send_command(cfg, protocol.listen())
            time.sleep(0.4)
            pcm, peak = uplink.capture_utterance(
                port=audio_port,
                threshold=args.threshold,
                silence_ms=args.silence_ms,
                max_seconds=args.max_seconds,
                min_seconds=args.min_seconds,
                sample_rate=sample_rate,
                verbose=not args.quiet,
            )
            send_command(cfg, protocol.stop())

            if not pcm:
                print("[run] nothing heard; re-arming", flush=True)
                continue

            wav = OUT_DIR / "heard.wav"
            audio.write_pcm_wav(wav, pcm, sample_rate=sample_rate)
            print(
                f"[run] heard {len(pcm) // 2 / sample_rate:.2f}s  peak RMS {peak:.0f}"
                f"  -> {wav}",
                flush=True,
            )
            text = transcribe_heard(wav, args)

            reply, seconds = answer_utterance(cfg, text, args)
            send_command(cfg, protocol.play(url))
            # Cooldown: let the reply finish and its echo die before re-arming,
            # otherwise the mic hears the chime and answers itself.
            time.sleep(seconds + args.margin + 1.0)
    except KeyboardInterrupt:
        print("\n[run] stopped by user", flush=True)
    finally:
        try:
            send_command(cfg, protocol.stop())
        except OSError:
            pass
        srv.stop()
    return 0


def cmd_calibrate(cfg: dict, args: argparse.Namespace) -> int:
    """Cue the human with a chime, then record and recommend a gate.

    The clock plays a chime as the "start talking" cue, then the mic records a
    fixed window. No precise stop is needed: the report separates room noise
    from speech by percentile, so any amount of talking in the window works.
    """
    public_host = cfg["server"]["public_host"]
    http_port = int(cfg["server"]["port"])
    url = f"http://{public_host}:{http_port}/reply.wav"
    cal_path = OUT_DIR / "calibration.wav"

    audio.generate_chime(OUT_DIR / "reply.wav", sample_rate=48000, volume=1.0)
    srv = server.AudioServer(OUT_DIR, cfg["server"]["bind"], http_port).start()
    try:
        print(f"[cal] cue in {args.delay:.0f}s — chime = start talking", flush=True)
        time.sleep(args.delay)
        send_command(cfg, protocol.play(url))
        time.sleep(1.8)
    finally:
        srv.stop()

    send_command(cfg, protocol.listen())
    time.sleep(0.4)
    try:
        uplink.record(
            cal_path,
            seconds=args.seconds,
            sample_rate=int(cfg["audio"].get("uplink_sample_rate", 16000)),
            verbose=not args.quiet,
        )
    finally:
        send_command(cfg, protocol.stop())

    report = uplink.analyse(cal_path)
    print("\n[cal] === calibration report ===", flush=True)
    for key, value in report.items():
        print(f"[cal] {key}: {value}", flush=True)
    return 0


def cmd_wake(cfg: dict, args: argparse.Namespace) -> int:
    """Wait for the device's on-device wake word, then capture and answer.

    The device runs the wake word while the radio is off. On detection it sends
    WAKE and starts streaming PCM; this loop records the command and plays a
    reply. The device re-arms the wake word itself when the reply finishes.
    """
    audio_port = int(cfg["device"].get("audio_port", 5005))
    sample_rate = int(cfg["audio"].get("uplink_sample_rate", 16000))
    reply_rate = int(cfg["audio"]["sample_rate"])
    public_host = cfg["server"]["public_host"]
    port = int(cfg["server"]["port"])
    url = f"http://{public_host}:{port}/reply.wav"

    srv = server.AudioServer(OUT_DIR, cfg["server"]["bind"], port).start()
    # Load the STT model in the background while we wait, so the first real
    # command does not pay the multi-second load cost.
    if not getattr(args, "no_stt", False):
        threading.Thread(
            target=lambda: stt.prewarm(args.stt_model), daemon=True
        ).start()
    print(f"[wake] waiting for the wake word on UDP {audio_port}", flush=True)
    # One socket for the whole loop: the device sends WAKE and the PCM that
    # follows on the same port, so binding once avoids dropping the first
    # frames of the command.
    sock = uplink.open_socket(audio_port, cfg["server"]["bind"])
    try:
        while True:
            lead = uplink.wait_for_wake(timeout=args.timeout, sock=sock)
            if lead is None:
                print("[wake] no wake word; exiting", flush=True)
                return 0
            print("[wake] detected — recording the command", flush=True)
            t0 = time.monotonic()
            pcm, peak = uplink.capture_utterance(
                port=audio_port,
                sock=sock,
                threshold=args.threshold,
                silence_ms=args.silence_ms,
                max_seconds=args.max_seconds,
                min_seconds=args.min_seconds,
                sample_rate=sample_rate,
                verbose=not args.quiet,
                seed=lead,
            )
            if not pcm:
                print("[wake] nothing captured; re-arming", flush=True)
                continue

            wav = OUT_DIR / "heard.wav"
            audio.write_pcm_wav(wav, pcm, sample_rate=sample_rate)
            print(
                f"[wake] heard {len(pcm) // 2 / sample_rate:.2f}s peak RMS {peak:.0f}"
                f" -> {wav}",
                flush=True,
            )
            t_cap = time.monotonic()
            text = transcribe_heard(wav, args)
            t_stt = time.monotonic()
            reply, seconds = answer_utterance(cfg, text, args)
            t_tts = time.monotonic()
            send_command(cfg, protocol.play(url))
            print(
                f"[latency] capture {(t_cap - t0) * 1000:.0f} ms"
                f" | stt {(t_stt - t_cap) * 1000:.0f} ms"
                f" | ha+tts {(t_tts - t_stt) * 1000:.0f} ms"
                f" | total {(time.monotonic() - t0) * 1000:.0f} ms",
                flush=True,
            )
            time.sleep(seconds + args.margin + 1.0)
    except KeyboardInterrupt:
        print("\n[wake] stopped by user", flush=True)
    finally:
        sock.close()
        srv.stop()
    return 0


def cmd_stop(cfg: dict, args: argparse.Namespace) -> int:
    send_command(cfg, protocol.stop())
    return 0


def cmd_transcribe(cfg: dict, args: argparse.Namespace) -> int:
    path = Path(args.path)
    if not path.exists():
        print(f"[stt] no such file: {path}", flush=True)
        return 2
    text = stt.transcribe(path, model_name=args.stt_model)
    print(text, flush=True)
    return 0


def cmd_ask(cfg: dict, args: argparse.Namespace) -> int:
    """Send text to HA Assist and speak the reply locally (no device needed)."""
    result = ha.ask(args.text, agent_id=args.agent_id)
    print(f"[ha] {result['response_type']}: {result['speech']!r}", flush=True)
    if args.speak and result["speech"]:
        out = OUT_DIR / "reply.wav"
        tts.speak(result["speech"], out, sample_rate=int(cfg["audio"]["sample_rate"]))
        print(f"[tts] {out} ({tts.duration_seconds(out):.2f}s)", flush=True)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)

    chime = sub.add_parser("chime", help="generate a chime and play it on the clock")
    chime.add_argument("--volume", type=float, default=0.35, help="0.0-1.0 (default 0.35)")
    chime.add_argument(
        "--margin", type=float, default=2.0, help="extra seconds to wait after playback"
    )
    chime.set_defaults(func=cmd_chime)

    play = sub.add_parser("play", help="send a PLAY command for an existing URL")
    play.add_argument("url")
    play.set_defaults(func=cmd_play)

    serve = sub.add_parser("serve", help="serve ./out over HTTP for manual testing")
    serve.set_defaults(func=cmd_serve)

    listen = sub.add_parser("listen", help="record the device mic to out/mic.wav")
    listen.add_argument("--seconds", type=float, default=5.0, help="0 = until Ctrl-C")
    listen.add_argument("--quiet", action="store_true", help="hide the level meter")
    listen.set_defaults(func=cmd_listen)

    run = sub.add_parser("run", help="continuous listen -> answer loop (no LLM)")
    run.add_argument(
        "--threshold", type=float, default=120.0, help="RMS gate for speech (default 120)"
    )
    run.add_argument(
        "--silence-ms", type=int, default=400, help="quiet time that ends an utterance"
    )
    run.add_argument(
        "--max-seconds", type=float, default=8.0, help="max length of one utterance"
    )
    run.add_argument(
        "--min-seconds", type=float, default=0.8, help="ignore utterances shorter than this"
    )
    run.add_argument("--volume", type=float, default=0.35, help="reply volume 0.0-1.0")
    run.add_argument("--margin", type=float, default=1.0, help="seconds to wait after playback")
    run.add_argument("--quiet", action="store_true", help="hide the gate meter")
    run.add_argument("--stt-model", default="base.en", help="faster-whisper model (default base.en)")
    run.add_argument("--no-stt", action="store_true", help="skip speech-to-text")
    run.add_argument("--no-ha", action="store_true", help="skip Home Assistant; chime instead")
    run.add_argument("--agent-id", default=None, help="HA conversation agent id (optional)")
    run.set_defaults(func=cmd_run)

    cal = sub.add_parser(
        "calibrate", help="chime as a cue, record, and suggest a speech gate"
    )
    cal.add_argument(
        "--delay", type=float, default=20.0, help="seconds between command and chime cue"
    )
    cal.add_argument("--seconds", type=float, default=40.0, help="recording window")
    cal.add_argument("--quiet", action="store_true", help="hide the level meter")
    cal.set_defaults(func=cmd_calibrate)

    wake = sub.add_parser("wake", help="wait for the on-device wake word, then answer")
    wake.add_argument("--threshold", type=float, default=120.0, help="RMS gate for speech")
    wake.add_argument("--silence-ms", type=int, default=400)
    wake.add_argument("--max-seconds", type=float, default=8.0)
    wake.add_argument("--min-seconds", type=float, default=0.8)
    wake.add_argument("--timeout", type=float, default=3600.0, help="give up after N seconds")
    wake.add_argument("--volume", type=float, default=0.35)
    wake.add_argument("--margin", type=float, default=1.0)
    wake.add_argument("--quiet", action="store_true")
    wake.add_argument("--stt-model", default="base.en", help="faster-whisper model (default base.en)")
    wake.add_argument("--no-stt", action="store_true", help="skip speech-to-text")
    wake.add_argument("--no-ha", action="store_true", help="skip Home Assistant; chime instead")
    wake.add_argument("--agent-id", default=None, help="HA conversation agent id (optional)")
    wake.set_defaults(func=cmd_wake)

    stop = sub.add_parser("stop", help="stop the device mic")
    stop.set_defaults(func=cmd_stop)

    tr = sub.add_parser("transcribe", help="transcribe a WAV file with faster-whisper")
    tr.add_argument("path")
    tr.add_argument("--stt-model", default="base.en", help="faster-whisper model (default base.en)")
    tr.set_defaults(func=cmd_transcribe)

    ask = sub.add_parser("ask", help="send text to HA Assist and speak the reply")
    ask.add_argument("text")
    ask.add_argument("--agent-id", default=None, help="HA conversation agent id (optional)")
    ask.add_argument("--speak", action="store_true", help="render the reply with Piper")
    ask.set_defaults(func=cmd_ask)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cfg = load_config()
    return args.func(cfg, args)


if __name__ == "__main__":
    sys.exit(main())
