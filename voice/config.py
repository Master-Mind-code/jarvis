"""
Configuration du service voix, lue depuis l'environnement.

Toutes les variables sont préfixées ORION_VOICE_*. Compatibilité legacy JARVIS_VOICE_*
gérée via branding.get_env (qui essaie les deux préfixes).
"""
from __future__ import annotations

import platform
from dataclasses import dataclass, field
from pathlib import Path

from branding import get_env


def _env_bool(name: str, default: bool) -> bool:
    raw = get_env(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on", "oui")


def _env_int(name: str, default: int) -> int:
    raw = get_env(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = get_env(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_list(name: str, default: list[str]) -> list[str]:
    raw = get_env(name)
    if not raw:
        return default
    return [item.strip().lower() for item in raw.split(",") if item.strip()]


@dataclass
class VoiceConfig:
    # Connexion au serveur Orion
    server_url: str = "ws://localhost:8765"
    secret_token: str = ""
    device_id: str = "voice"

    # STT
    stt_backend: str = "faster-whisper"    # voir voice/registry.py SpeechRegistry.list()
    stt_model_size: str = "small"          # tiny | base | small | medium | large-v3
    stt_device: str = "cpu"                # cpu | cuda
    stt_compute_type: str = "int8"         # int8 | int8_float16 | float16 | float32
    stt_language: str = "fr"               # langue par défaut

    # TTS
    tts_backend: str = "kokoro"            # voir voice/registry.py TTSRegistry.list()
    tts_voice: str = "ff_siwis"            # voix française féminine (seule FR Kokoro v1)
    tts_speed: float = 1.0
    tts_lang: str = "fr-fr"
    tts_model_dir: Path = field(default_factory=lambda: Path("data/kokoro"))
    tts_model_url: str = (
        "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
        "kokoro-v1.0.onnx"
    )
    tts_voices_url: str = (
        "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
        "voices-v1.0.bin"
    )

    # VAD / capture micro
    sample_rate: int = 16000
    vad_aggressiveness: int = 3            # 0-3, 3 = plus agressif
    silence_short_ms: int = 520            # silence court (commande brève)
    silence_long_ms: int = 950             # silence long (après 2.5s de parole continue)
    silence_long_after_ms: int = 2500      # bascule vers silence_long_ms après ce délai
    max_record_seconds: int = 30           # protection : coupe l'enregistrement après N s

    # Wake word
    wake_words: list[str] = field(default_factory=lambda: ["hey orion", "orion", "hey o"])
    wake_clip_seconds: float = 3.0         # durée max d'un clip wake word
    wake_idle_timeout: int = 120           # secondes d'inactivité avant retour en mode wake word
    wake_enabled: bool = True              # False = écoute toujours active sans wake word
    # Fenêtre follow-up : après une réponse, on écoute la suite sans wake word
    # pendant N secondes (style Alexa/Siri). 0 = désactivé.
    followup_window_sec: int = 15
    # Mots qui déverrouillent l'UI navigateur via WebSocket (court-circuite le LLM)
    unlock_words: list[str] = field(default_factory=lambda: [
        "ouverture", "ouvre toi", "deverrouille", "orion ouverture", "orion ouvre",
    ])

    # Pipeline
    history_max_turns: int = 0             # 0 = laissé au serveur Orion (qui garde l'historique)
    print_user_transcription: bool = True

    @classmethod
    def from_env(cls) -> "VoiceConfig":
        default_device = f"voice-{platform.node().lower()}"
        return cls(
            server_url=get_env("SERVER_URL", "ws://localhost:8765") or "ws://localhost:8765",
            secret_token=get_env("SECRET_TOKEN", "") or "",
            device_id=get_env("VOICE_DEVICE_ID", default_device) or default_device,
            stt_backend=get_env("VOICE_STT_BACKEND", "faster-whisper") or "faster-whisper",
            stt_model_size=get_env("VOICE_STT_MODEL", "small") or "small",
            stt_device=get_env("VOICE_STT_DEVICE", "cpu") or "cpu",
            stt_compute_type=get_env("VOICE_STT_COMPUTE", "int8") or "int8",
            stt_language=get_env("VOICE_STT_LANG", "fr") or "fr",
            tts_backend=get_env("VOICE_TTS_BACKEND", "kokoro") or "kokoro",
            tts_voice=get_env("VOICE_TTS_VOICE", "ff_siwis") or "ff_siwis",
            tts_speed=_env_float("VOICE_TTS_SPEED", 1.0),
            tts_lang=get_env("VOICE_TTS_LANG", "fr-fr") or "fr-fr",
            tts_model_dir=Path(get_env("VOICE_KOKORO_DIR", "data/kokoro") or "data/kokoro"),
            sample_rate=_env_int("VOICE_SAMPLE_RATE", 16000),
            vad_aggressiveness=_env_int("VOICE_VAD_LEVEL", 3),
            silence_short_ms=_env_int("VOICE_SILENCE_SHORT_MS", 520),
            silence_long_ms=_env_int("VOICE_SILENCE_LONG_MS", 950),
            silence_long_after_ms=_env_int("VOICE_SILENCE_SWITCH_MS", 2500),
            max_record_seconds=_env_int("VOICE_MAX_RECORD_SEC", 30),
            wake_words=_env_list("VOICE_WAKE_WORDS", ["hey orion", "orion", "hey o"]),
            wake_clip_seconds=_env_float("VOICE_WAKE_CLIP_SEC", 3.0),
            wake_idle_timeout=_env_int("VOICE_WAKE_TIMEOUT", 120),
            wake_enabled=_env_bool("VOICE_WAKE_ENABLED", True),
            followup_window_sec=_env_int("VOICE_FOLLOWUP_SEC", 15),
            unlock_words=_env_list("VOICE_UNLOCK_WORDS", [
                "ouverture", "ouvre toi", "deverrouille", "orion ouverture", "orion ouvre",
            ]),
            print_user_transcription=_env_bool("VOICE_PRINT_TRANSCRIPT", True),
        )

    def kokoro_model_path(self) -> Path:
        return self.tts_model_dir / "kokoro-v1.0.onnx"

    def kokoro_voices_path(self) -> Path:
        return self.tts_model_dir / "voices-v1.0.bin"
