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
import time
import tomllib
from pathlib import Path

from . import audio, protocol, server, uplink

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
    sample_rate = int(cfg["audio"]["sample_rate"])
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


def cmd_stop(cfg: dict, args: argparse.Namespace) -> int:
    send_command(cfg, protocol.stop())
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

    stop = sub.add_parser("stop", help="stop the device mic")
    stop.set_defaults(func=cmd_stop)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cfg = load_config()
    return args.func(cfg, args)


if __name__ == "__main__":
    sys.exit(main())
