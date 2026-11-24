"""UDP PCM receiver: record the device microphone to a WAV file.

The device sends raw 16-bit mono PCM at 48 kHz to UDP port 5005. This module
binds that port, writes the frames to a WAV, and prints a rough level meter so
you can tell whether the mic is actually hearing anything.
"""

from __future__ import annotations

import socket
import time
import wave
from pathlib import Path

import math
import struct


def _rms(frame: bytes) -> float:
    if len(frame) < 2:
        return 0.0
    count = len(frame) // 2
    total = 0.0
    for (sample,) in struct.iter_unpack("<h", frame[: count * 2]):
        total += sample * sample
    return math.sqrt(total / count)


def capture_utterance(
    *,
    port: int = 5005,
    bind: str = "0.0.0.0",
    threshold: float = 300.0,
    silence_ms: int = 700,
    max_seconds: float = 8.0,
    pre_roll_ms: int = 250,
    verbose: bool = True,
) -> tuple[bytes, float]:
    """Wait for one burst of speech and return its PCM plus peak RMS.

    The gate is deliberately dumb: a packet is "speech" when its RMS is above
    *threshold*. An utterance starts at the first loud packet (with a short
    pre-roll) and ends after *silence_ms* of quiet, or *max_seconds* total.
    Returns ``(b"", 0.0)`` if nothing is heard before the caller gives up.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((bind, port))
    sock.settimeout(0.5)

    started = time.monotonic()
    peak = 0.0
    speaking = False
    last_voice = 0.0
    pre_roll: list[bytes] = []
    frames: list[bytes] = []

    try:
        while True:
            now = time.monotonic()
            if now - started > max_seconds:
                break
            try:
                data, _addr = sock.recvfrom(65535)
            except socket.timeout:
                if speaking and (now - last_voice) * 1000 >= silence_ms:
                    break
                if not speaking and now - started > max_seconds:
                    break
                continue
            if not data:
                continue

            level = _rms(data)
            if level >= threshold:
                if not speaking:
                    speaking = True
                    frames.extend(pre_roll)
                    pre_roll.clear()
                last_voice = now
                peak = max(peak, level)
                frames.append(data)
                if verbose:
                    print(f"[gate] {level:6.0f} speech", flush=True)
            else:
                if speaking:
                    frames.append(data)
                    if (now - last_voice) * 1000 >= silence_ms:
                        break
                else:
                    pre_roll.append(data)
                    keep = max(1, int(pre_roll_ms / 1000 * 20))
                    if len(pre_roll) > keep:
                        pre_roll.pop(0)
    finally:
        sock.close()

    return b"".join(frames), peak


def record(
    path: str | Path,
    *,
    port: int = 5005,
    sample_rate: int = 48000,
    seconds: float = 5.0,
    bind: str = "0.0.0.0",
    verbose: bool = True,
) -> dict:
    """Record PCM from *port* into *path* for *seconds* (0 = until Ctrl-C)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((bind, port))
    sock.settimeout(0.5)

    started = time.monotonic()
    packets = 0
    frames = 0
    peak = 0.0
    last_print = 0.0
    stop_at = started + seconds if seconds else None

    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        try:
            while True:
                now = time.monotonic()
                if stop_at is not None and now >= stop_at:
                    break
                try:
                    data, _addr = sock.recvfrom(65535)
                except socket.timeout:
                    continue
                if not data:
                    continue
                wav.writeframesraw(data)
                packets += 1
                frames += len(data) // 2
                level = _rms(data)
                peak = max(peak, level)
                if verbose and now - last_print >= 0.5:
                    last_print = now
                    bar = "#" * min(40, int(level / 200))
                    print(f"[mic] {level:6.0f} {bar}", flush=True)
        except KeyboardInterrupt:
            print("\n[mic] stopped by user", flush=True)
        finally:
            sock.close()

    duration = time.monotonic() - started
    return {
        "path": str(path),
        "packets": packets,
        "frames": frames,
        "seconds": round(duration, 2),
        "peak_rms": round(peak, 1),
    }
