"""
Backends Speech-to-Text d'Orion.

Backend par défaut : faster-whisper (local, multilingue, modèle small int8).
Pour ajouter un nouveau backend (Deepgram, OpenAI Whisper API, Vosk…),
décorer la classe avec @SpeechRegistry.register("nom") et hériter de
SpeechBackend.
"""
from __future__ import annotations

import numpy as np

from .registry import SpeechBackend, SpeechRegistry


@SpeechRegistry.register("faster-whisper")
class FasterWhisperBackend(SpeechBackend):
    """Local STT via faster-whisper (CTranslate2). Wheel Windows prêt à l'emploi."""

    def __init__(
        self,
        model_size: str = "small",
        device: str = "cpu",
        compute_type: str = "int8",
        language: str = "fr",
    ):
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise ImportError(
                "faster-whisper n'est pas installé. Installe avec :\n"
                "    pip install -r requirements-voice.txt"
            ) from exc

        self.language = language
        print(
            f"[stt] Chargement faster-whisper '{model_size}' "
            f"({device}, {compute_type})..."
        )
        self.model = WhisperModel(model_size, device=device, compute_type=compute_type)
        print("[stt] Modèle prêt.")

    def transcribe(
        self, audio_int16: bytes | np.ndarray, language: str | None = None
    ) -> str:
        if isinstance(audio_int16, (bytes, bytearray)):
            audio = np.frombuffer(audio_int16, dtype=np.int16)
        else:
            audio = np.asarray(audio_int16, dtype=np.int16)

        if audio.size == 0:
            return ""

        audio_f32 = audio.astype(np.float32) / 32768.0

        segments, _info = self.model.transcribe(
            audio_f32,
            language=language or self.language,
            beam_size=5,
            temperature=0.0,
            condition_on_previous_text=False,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 300, "speech_pad_ms": 200},
        )
        return " ".join(seg.text.strip() for seg in segments).strip()


# ─── Façade pour conserver l'ancienne API ────────────────────────────────
class SpeechToText:
    """Wrapper qui instancie le bon backend selon `backend_id`.

    Utilisation classique : `SpeechToText(model_size="small", language="fr")`
    Backend personnalisé   : `SpeechToText(backend="faster-whisper", model_size="...")`
    """

    def __init__(self, backend: str = "faster-whisper", **kwargs):
        self.backend = SpeechRegistry.create(backend, **kwargs)

    def transcribe(
        self, audio_int16: bytes | np.ndarray, language: str | None = None
    ) -> str:
        return self.backend.transcribe(audio_int16, language=language)
