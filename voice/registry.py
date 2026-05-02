"""
Registries multi-backend pour STT et TTS.

Chaque backend s'enregistre via un décorateur :

    @SpeechRegistry.register("faster-whisper")
    class FasterWhisperBackend(SpeechBackend):
        ...

Permet de basculer entre Whisper / Deepgram / OpenAI / etc. via une seule
variable d'environnement (ORION_VOICE_STT_BACKEND, ORION_VOICE_TTS_BACKEND)
sans modifier le code du pipeline.

Pattern repris de OpenJarvis (Stanford SAIL / Hazy Research, Apache 2.0).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, Type, TypeVar

import numpy as np


# ─── Interfaces abstraites ────────────────────────────────────────────────
class SpeechBackend(ABC):
    """Backend STT (Speech-to-Text)."""

    backend_id: str = ""

    @abstractmethod
    def transcribe(
        self, audio_int16: bytes | np.ndarray, language: str | None = None
    ) -> str:
        """Retourne le texte transcrit."""


class TTSBackend(ABC):
    """Backend TTS (Text-to-Speech)."""

    backend_id: str = ""
    sample_rate: int = 24000

    @abstractmethod
    def synthesize(self, text: str) -> np.ndarray:
        """Retourne un buffer float32 mono à la fréquence `sample_rate`."""


# ─── Registry générique ───────────────────────────────────────────────────
T = TypeVar("T")


class _Registry:
    def __init__(self, kind: str):
        self.kind = kind
        self._backends: Dict[str, Type[Any]] = {}

    def register(self, name: str) -> Callable[[Type[T]], Type[T]]:
        def decorator(cls: Type[T]) -> Type[T]:
            cls.backend_id = name  # type: ignore[attr-defined]
            self._backends[name] = cls
            return cls

        return decorator

    def get(self, name: str) -> Type[Any]:
        if name not in self._backends:
            available = ", ".join(sorted(self._backends.keys())) or "(aucun)"
            raise KeyError(
                f"Backend {self.kind} '{name}' inconnu. Disponibles : {available}"
            )
        return self._backends[name]

    def list(self) -> list[str]:
        return sorted(self._backends.keys())

    def create(self, name: str, **kwargs: Any) -> Any:
        return self.get(name)(**kwargs)


# Singletons exportés
SpeechRegistry = _Registry("STT")
TTSRegistry = _Registry("TTS")
