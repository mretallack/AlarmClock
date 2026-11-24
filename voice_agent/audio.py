"""Generate the reply audio the device will play.

Phase 1 has no TTS, so the default reply is a short, friendly chime. The file is
plain 16-bit PCM WAV at the device's pipeline rate (48 kHz mono).
"""

from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

# A rising three-note "hello" — deliberately simple and synthetic.
DEFAULT_NOTES = ((523.25, 0.16), (659.25, 0.16), (783.99, 0.30))
FADE = 0.01


def _sine(freq: float, seconds: float, sample_rate: int, volume: float) -> list[float]:
    n = int(seconds * sample_rate)
    fade_n = max(1, int(FADE * sample_rate))
    out: list[float] = []
    for i in range(n):
        # short attack/release so the notes do not click
        env = 1.0
        if i < fade_n:
            env = i / fade_n
        elif i > n - fade_n:
            env = max(0.0, (n - i) / fade_n)
        out.append(volume * env * math.sin(2 * math.pi * freq * i / sample_rate))
    return out


def generate_chime(
    path: str | Path,
    sample_rate: int = 48000,
    notes: tuple[tuple[float, float], ...] = DEFAULT_NOTES,
    volume: float = 0.35,
    gap: float = 0.04,
) -> Path:
    """Write a WAV chime to *path* and return it."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    samples: list[float] = []
    for freq, seconds in notes:
        samples.extend(_sine(freq, seconds, sample_rate, volume))
        samples.extend([0.0] * int(gap * sample_rate))

    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(
            b"".join(struct.pack("<h", int(max(-1.0, min(1.0, s)) * 32767)) for s in samples)
        )
    return path


def duration_seconds(path: str | Path) -> float:
    with wave.open(str(path), "rb") as wav:
        return wav.getnframes() / float(wav.getframerate())
