"""
Transcription audio côté serveur (utilisée par l'UI navigateur).

Lazy-load de faster-whisper au premier appel — évite d'occuper ~1 GB de RAM
si l'utilisateur n'utilise jamais le micro de l'UI.

Le module est totalement indépendant du service `python start.py voice` :
celui-ci tourne dans un autre process avec son propre Whisper. Si les deux
sont actifs en même temps, ~2 GB RAM Whisper. C'est OK.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from branding import get_env

_model = None


def _get_model():
    """Charge le modèle Whisper au premier appel (lazy)."""
    global _model
    if _model is not None:
        return _model

    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise ImportError(
            "faster-whisper n'est pas installé côté serveur. Installe avec :\n"
            "    pip install -r requirements-voice.txt"
        ) from exc

    model_size = get_env("VOICE_STT_MODEL", "small") or "small"
    device = get_env("VOICE_STT_DEVICE", "cpu") or "cpu"
    compute_type = get_env("VOICE_STT_COMPUTE", "int8") or "int8"
    print(f"[transcribe] Chargement faster-whisper '{model_size}' ({device}, {compute_type})...")
    _model = WhisperModel(model_size, device=device, compute_type=compute_type)
    print("[transcribe] Modèle prêt.")
    return _model


def transcribe_blob(blob: bytes, language: str | None = None, suffix: str = ".webm") -> str:
    """Transcrit un blob audio (WebM, MP3, WAV, OGG, FLAC, M4A).

    faster-whisper appelle ffmpeg en interne pour décoder. Le format est
    auto-détecté ; `suffix` n'est qu'une indication.
    """
    if not blob:
        return ""
    model = _get_model()
    lang = language or get_env("VOICE_STT_LANG", "fr") or "fr"

    # faster-whisper veut un chemin de fichier, pas un bytes
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(blob)
        tmp_path = Path(tmp.name)
    try:
        segments, _info = model.transcribe(
            str(tmp_path),
            language=lang,
            beam_size=5,
            temperature=0.0,
            condition_on_previous_text=False,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 300, "speech_pad_ms": 200},
        )
        text = " ".join(seg.text.strip() for seg in segments).strip()
        return text
    finally:
        try:
            tmp_path.unlink()
        except OSError:
            pass
