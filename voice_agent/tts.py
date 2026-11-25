"""Piper text-to-speech for the PC-side voice agent.

Piper lives in its own venv (``.venv-piper``) because its deps are heavy; this
module shells out to it and resamples the result to the device's 48 kHz mono
pipeline with ffmpeg.
"""

from __future__ import annotations

import shutil
import subprocess
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PIPER_PY = ROOT / ".venv-piper" / "bin" / "python"
VOICE_MODEL = ROOT / "voices" / "en_GB-northern_english_male-medium.onnx"
DEVICE_RATE = 48000


def _check() -> None:
    if not PIPER_PY.exists():
        raise RuntimeError(
            f"piper venv missing at {PIPER_PY}; create it and `pip install piper-tts`"
        )
    if not VOICE_MODEL.exists():
        raise RuntimeError(
            f"voice model missing at {VOICE_MODEL}; download with "
            "`python -m piper.download_voices en_GB-northern_english_male-medium --data-dir voices`"
        )


def speak(
    text: str,
    path: str | Path,
    *,
    model: str | Path = VOICE_MODEL,
    sample_rate: int = DEVICE_RATE,
) -> Path:
    """Synthesise *text* to *path* as 16-bit mono WAV at *sample_rate*."""
    _check()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = path.with_suffix(".piper.wav")

    subprocess.run(
        [
            str(PIPER_PY),
            "-m",
            "piper",
            "-m",
            str(model),
            "-f",
            str(raw),
            "--",
            text,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    with wave.open(str(raw), "rb") as wav:
        src_rate = wav.getframerate()
    if src_rate == sample_rate:
        shutil.move(str(raw), str(path))
    else:
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw),
             "-ar", str(sample_rate), "-ac", "1", str(path)],
            check=True,
        )
        raw.unlink(missing_ok=True)
    return path


def duration_seconds(path: str | Path) -> float:
    with wave.open(str(path), "rb") as wav:
        return wav.getnframes() / float(wav.getframerate())
