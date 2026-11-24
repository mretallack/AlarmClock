"""Speech-to-text for the PC-side voice agent.

Uses faster-whisper (CTranslate2) on CPU. The model is loaded lazily once and
reused, so the first call pays the load cost and later utterances are fast.

The device uplink is 16 kHz mono 16-bit PCM, which is exactly what Whisper
wants, so no resampling is needed.
"""

from __future__ import annotations

from pathlib import Path

# base.en is a good speed/accuracy trade for short commands on a CPU.
DEFAULT_MODEL = "base.en"
DEFAULT_COMPUTE_TYPE = "int8"

_model = None
_model_key: tuple[str, str, str] | None = None


def _get_model(model_name: str, device: str, compute_type: str):
    global _model, _model_key
    key = (model_name, device, compute_type)
    if _model is None or _model_key != key:
        from faster_whisper import WhisperModel

        _model = WhisperModel(model_name, device=device, compute_type=compute_type)
        _model_key = key
    return _model


def transcribe(
    path: str | Path,
    *,
    model_name: str = DEFAULT_MODEL,
    device: str = "cpu",
    compute_type: str = DEFAULT_COMPUTE_TYPE,
    language: str = "en",
    beam_size: int = 5,
) -> str:
    """Return the transcript of a WAV/audio file as one stripped string."""
    model = _get_model(model_name, device, compute_type)
    segments, _info = model.transcribe(
        str(path), language=language, beam_size=beam_size, vad_filter=False
    )
    return " ".join(seg.text.strip() for seg in segments).strip()
