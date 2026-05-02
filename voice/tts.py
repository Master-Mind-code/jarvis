"""
Backends Text-to-Speech d'Orion.

Backend par défaut : kokoro-onnx (local, multilingue, voix française ff_siwis).
Pour ajouter un backend (Piper, ElevenLabs, OpenAI TTS…), décorer la classe
avec @TTSRegistry.register("nom") et hériter de TTSBackend.
"""
from __future__ import annotations

import urllib.request
from pathlib import Path

import numpy as np

from .registry import TTSBackend, TTSRegistry


def _download(url: str, dest: Path):
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"[tts] Téléchargement de {dest.name} depuis {url}")
    print(f"      → {dest}")

    def _progress(blocknum, blocksize, total):
        if total <= 0:
            return
        downloaded = blocknum * blocksize
        pct = min(100, downloaded * 100 / total)
        if blocknum % 200 == 0 or downloaded >= total:
            mb = downloaded / 1024 / 1024
            total_mb = total / 1024 / 1024
            print(f"      {pct:5.1f}%  ({mb:.1f}/{total_mb:.1f} MB)")

    tmp = dest.with_suffix(dest.suffix + ".part")
    urllib.request.urlretrieve(url, tmp, reporthook=_progress)
    tmp.replace(dest)
    print(f"[tts] {dest.name} prêt.")


def ensure_models(
    model_path: Path,
    voices_path: Path,
    model_url: str,
    voices_url: str,
):
    if not model_path.exists():
        _download(model_url, model_path)
    if not voices_path.exists():
        _download(voices_url, voices_path)


@TTSRegistry.register("kokoro")
class KokoroBackend(TTSBackend):
    """Local TTS via kokoro-onnx (~300 MB, multilingue, voix française ff_siwis)."""

    def __init__(
        self,
        model_path: Path,
        voices_path: Path,
        voice: str = "ff_siwis",
        speed: float = 1.0,
        lang: str = "fr-fr",
        download_urls: tuple[str, str] | None = None,
    ):
        try:
            from kokoro_onnx import Kokoro
        except ImportError as exc:
            raise ImportError(
                "kokoro-onnx n'est pas installé. Installe avec :\n"
                "    pip install -r requirements-voice.txt"
            ) from exc

        if not model_path.exists() or not voices_path.exists():
            if download_urls is None:
                raise FileNotFoundError(
                    f"Modèles Kokoro absents : {model_path}, {voices_path}"
                )
            ensure_models(model_path, voices_path, *download_urls)

        print(f"[tts] Chargement Kokoro (voix={voice}, lang={lang})...")
        self.kokoro = Kokoro(str(model_path), str(voices_path))
        self.voice = voice
        self.speed = speed
        self.lang = lang
        self.sample_rate = 24000  # ajusté à la première synthèse si différent
        print("[tts] Modèle prêt.")

    def synthesize(self, text: str) -> np.ndarray:
        text = text.strip()
        if not text:
            return np.zeros(0, dtype=np.float32)
        audio, sr = self.kokoro.create(
            text, voice=self.voice, speed=self.speed, lang=self.lang
        )
        if sr != self.sample_rate:
            self.sample_rate = sr
        return np.asarray(audio, dtype=np.float32)


# ─── Façade pour conserver l'ancienne API ────────────────────────────────
class TextToSpeech:
    """Wrapper qui instancie le bon backend TTS.

    Compatible avec l'ancien constructeur (backend par défaut = "kokoro").
    """

    def __init__(self, backend: str = "kokoro", **kwargs):
        self.backend_obj = TTSRegistry.create(backend, **kwargs)

    @property
    def sample_rate(self) -> int:
        return self.backend_obj.sample_rate

    def synthesize(self, text: str) -> np.ndarray:
        return self.backend_obj.synthesize(text)
