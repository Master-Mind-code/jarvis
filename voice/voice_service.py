"""
Orchestration du service voix d'Orion.

Pipeline :
    1. Capture micro (vad.MicCapture, frames 30 ms 16 kHz)
    2. Détection wake word (mode passif)
    3. Enregistrement de la commande (silence adaptatif)
    4. STT (faster-whisper)
    5. Envoi au serveur Orion via WebSocket controller
    6. Réception réponse + chunks TTS streamés vers SeamlessPlayer
    7. Retour mode wake word après silence prolongé

États : idle / listening / thinking / speaking
"""
from __future__ import annotations

import asyncio
import re
import sys
import threading
import time
from dataclasses import dataclass

import numpy as np

from .config import VoiceConfig
from .orion_client import OrionClient
from .player import SeamlessPlayer
from .stt import SpeechToText
from .tts import TextToSpeech
from .vad import MicCapture
from .wake_word import WakeWordDetector


SENTENCE_BOUNDARY = re.compile(r"([.!?…]+)\s+")
CLAUSE_BOUNDARY = re.compile(r"([,;:])\s+")
MARKDOWN_NOISE = re.compile(r"[*_`#>\[\]\(\)]")

# Emojis et symboles unicode non vocalisables. Couvre les blocs principaux :
#   - Emoticons (1F600-1F64F)        - Symboles & pictogrammes (1F300-1F5FF)
#   - Transports & cartes (1F680-1F6FF) - Symboles supplémentaires (1F900-1F9FF)
#   - Symboles divers (2600-26FF)    - Dingbats (2700-27BF)
#   - Variation selectors (FE0F)     - Zero-width joiner (200D)
#   - Drapeaux (1F1E6-1F1FF)         - Symboles & flèches (2190-21FF, 2B00-2BFF)
EMOJI_REGEX = re.compile(
    "["
    "\U0001F600-\U0001F64F"
    "\U0001F300-\U0001F5FF"
    "\U0001F680-\U0001F6FF"
    "\U0001F700-\U0001F77F"
    "\U0001F780-\U0001F7FF"
    "\U0001F800-\U0001F8FF"
    "\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FA6F"
    "\U0001FA70-\U0001FAFF"
    "\U00002600-\U000026FF"
    "\U00002700-\U000027BF"
    "\U0001F1E6-\U0001F1FF"
    "\U00002B00-\U00002BFF"
    "\U00002190-\U000021FF"
    "\U0000FE00-\U0000FE0F"
    "\U0000200D"
    "]+",
    flags=re.UNICODE,
)


@dataclass
class State:
    name: str = "idle"  # idle | listening | thinking | speaking | wake


def _clean_text_for_tts(text: str) -> str:
    """Retire les éléments non vocalisables : emojis, markdown, code, URLs."""
    # Supprime les blocs de code triple backtick complets
    text = re.sub(r"```[\s\S]*?```", " ", text)
    # Supprime emojis et symboles unicode décoratifs
    text = EMOJI_REGEX.sub("", text)
    # Supprime markdown léger (* _ ` # > [ ] ( ))
    text = MARKDOWN_NOISE.sub("", text)
    # URLs longues : on dit juste "lien"
    text = re.sub(r"https?://\S+", "lien", text)
    # Normalise les espaces (collapse + strip)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def split_sentences(text: str, max_chars: int = 280) -> list[str]:
    """Découpe un texte en phrases vocalisables, sans dépasser max_chars par phrase."""
    text = _clean_text_for_tts(text)
    if not text:
        return []

    # Première passe : split sur frontières de phrase
    pieces: list[str] = []
    last = 0
    for match in SENTENCE_BOUNDARY.finditer(text):
        end = match.end()
        chunk = text[last:end].strip()
        if chunk:
            pieces.append(chunk)
        last = end
    tail = text[last:].strip()
    if tail:
        pieces.append(tail)

    # Deuxième passe : si une pièce est trop longue, on coupe sur clauses
    out: list[str] = []
    for piece in pieces:
        if len(piece) <= max_chars:
            out.append(piece)
            continue
        sub_last = 0
        for match in CLAUSE_BOUNDARY.finditer(piece):
            end = match.end()
            chunk = piece[sub_last:end].strip()
            if chunk:
                out.append(chunk)
            sub_last = end
        sub_tail = piece[sub_last:].strip()
        if sub_tail:
            out.append(sub_tail)
    return [p for p in out if p]


class VoiceService:
    def __init__(self, config: VoiceConfig):
        self.config = config
        self.state = State("idle")
        self._state_lock = threading.Lock()
        self._stop_event = threading.Event()

        # Lazy-init pour montrer la progression à l'écran
        self.mic: MicCapture | None = None
        self.stt: SpeechToText | None = None
        self.tts: TextToSpeech | None = None
        self.player: SeamlessPlayer | None = None
        self.wake: WakeWordDetector | None = None
        self._client: OrionClient | None = None
        self._main_loop: asyncio.AbstractEventLoop | None = None

    # ─── Init ────────────────────────────────────────────────────────────
    def _init_components(self):
        cfg = self.config
        print("─" * 60)
        print(f"  ORION VOIX  ·  device='{cfg.device_id}'  ·  langue={cfg.stt_language}")
        print("─" * 60)
        self.stt = SpeechToText(
            backend=cfg.stt_backend,
            model_size=cfg.stt_model_size,
            device=cfg.stt_device,
            compute_type=cfg.stt_compute_type,
            language=cfg.stt_language,
        )
        if cfg.tts_backend == "kokoro":
            tts_kwargs = dict(
                model_path=cfg.kokoro_model_path(),
                voices_path=cfg.kokoro_voices_path(),
                voice=cfg.tts_voice,
                speed=cfg.tts_speed,
                lang=cfg.tts_lang,
                download_urls=(cfg.tts_model_url, cfg.tts_voices_url),
            )
        else:
            tts_kwargs = dict(voice=cfg.tts_voice, speed=cfg.tts_speed, lang=cfg.tts_lang)
        self.tts = TextToSpeech(backend=cfg.tts_backend, **tts_kwargs)
        self.mic = MicCapture(
            sample_rate=cfg.sample_rate,
            aggressiveness=cfg.vad_aggressiveness,
            silence_short_ms=cfg.silence_short_ms,
            silence_long_ms=cfg.silence_long_ms,
            silence_long_after_ms=cfg.silence_long_after_ms,
            max_record_seconds=cfg.max_record_seconds,
        )
        self.player = SeamlessPlayer(sample_rate=self.tts.sample_rate)
        self.wake = WakeWordDetector(cfg.wake_words)
        # Variantes normalisées des unlock words pour matching rapide
        from .wake_word import _normalize
        self._unlock_variants = [_normalize(w) for w in cfg.unlock_words if w.strip()]

    # ─── État ────────────────────────────────────────────────────────────
    def _set_state(self, name: str):
        changed = False
        with self._state_lock:
            if self.state.name != name:
                self.state.name = name
                changed = True
                print(f"[état] → {name}")
        if changed and self._client is not None and self._main_loop is not None:
            # Best-effort : envoie l'état au serveur depuis n'importe quel thread
            asyncio.run_coroutine_threadsafe(
                self._client.send_voice_state(name), self._main_loop
            )

    # ─── Helpers ─────────────────────────────────────────────────────────
    def _speak(self, text: str):
        """Synthétise et joue un texte de bout en bout (bloquant jusqu'à la fin)."""
        sentences = split_sentences(text)
        if not sentences:
            return
        self._set_state("speaking")
        self.player.start()
        for sentence in sentences:
            if self._stop_event.is_set():
                break
            try:
                audio = self.tts.synthesize(sentence)
                if len(audio) > 0:
                    self.player.enqueue(audio)
            except Exception as exc:
                print(f"[tts!] {exc}")
        self.player.wait_until_done()

    def _transcribe_recorded(self, audio: bytes) -> str:
        if not audio:
            return ""
        try:
            return self.stt.transcribe(audio)
        except Exception as exc:
            print(f"[stt!] {exc}")
            return ""

    # ─── Détection unlock (court-circuite le LLM) ───────────────────────
    def _is_unlock_command(self, text: str) -> bool:
        """True si la transcription contient un mot d'unlock UI."""
        from .wake_word import _normalize
        if not text or not self._unlock_variants:
            return False
        norm = _normalize(text)
        return any(variant in norm for variant in self._unlock_variants)

    async def _try_unlock(self, client: OrionClient, text: str) -> bool:
        """Si la commande matche un unlock word, déverrouille les UI et retourne True."""
        if not self._is_unlock_command(text):
            return False
        await client.send_unlock_request()
        print(f"[unlock] envoi vers serveur (déclenché par : {text!r})")
        await asyncio.to_thread(self._speak, "Système ouvert.")
        return True

    # ─── Boucle conversationnelle ────────────────────────────────────────
    async def _converse(self, client: OrionClient, user_text: str):
        """Envoie une commande à Orion et joue la réponse."""
        self._set_state("thinking")
        try:
            await client.send_message(user_text)
        except Exception as exc:
            self._speak(f"Erreur d'envoi au serveur : {exc}")
            return

        async for msg in client.receive_response(timeout=180.0):
            t = msg.get("type")
            if t == "tool_action":
                ok = "✓" if msg.get("result", {}).get("success", True) else "✗"
                print(f"  [{ok} {msg.get('tool')}]")
            elif t == "info":
                print(f"  [i] {msg.get('message', '')}")
            elif t == "response":
                content = (msg.get("content") or "").strip()
                print(f"\nOrion : {content}\n")
                if content:
                    await asyncio.to_thread(self._speak, content)
            elif t == "error":
                err = msg.get("content") or "erreur inconnue"
                print(f"  [!] {err}")
                await asyncio.to_thread(self._speak, "Désolé, une erreur est survenue.")

    # ─── Boucle principale ───────────────────────────────────────────────
    async def run(self):
        self._init_components()

        client = OrionClient(
            self.config.server_url,
            self.config.device_id,
            self.config.secret_token,
        )
        try:
            await client.connect()
        except Exception as exc:
            print(f"[!] Impossible de se connecter au serveur Orion : {exc}")
            print(f"    Vérifie que le serveur tourne sur {self.config.server_url}")
            return

        # Mémorise client + loop pour que _set_state puisse broadcaster l'état
        self._client = client
        self._main_loop = asyncio.get_running_loop()

        with self.mic, self.player:
            try:
                await self._run_loop(client)
            finally:
                # Annonce l'arrêt avant de fermer
                try:
                    await client.send_voice_state("offline")
                except Exception:
                    pass
                await client.close()
                self._client = None
                self._main_loop = None

    async def _run_loop(self, client: OrionClient):
        cfg = self.config
        wake_active = cfg.wake_enabled
        last_interaction = time.time()

        if wake_active:
            print(f"\n[wake] En attente de '{cfg.wake_words[0]}'... (Ctrl+C pour quitter)")
            self._set_state("wake")
        else:
            print("\n[ouvert] Écoute active permanente (pas de wake word)")
            self._set_state("listening")

        while not self._stop_event.is_set():
            # ── Mode wake word ──
            if wake_active:
                clip = await asyncio.to_thread(
                    self.mic.record_until_silence,
                    None,
                )
                if not clip:
                    continue
                # Transcription rapide pour matcher le wake word
                text = await asyncio.to_thread(self._transcribe_recorded, clip)
                if not text:
                    continue
                if not self.wake.matches(text):
                    # On peut afficher discrètement ce qu'on a entendu pour debug
                    if cfg.print_user_transcription:
                        print(f"  [wake?] entendu : {text!r}")
                    continue

                # Wake word détecté — l'utilisateur a peut-être déjà énoncé sa demande
                # dans le même clip. Si oui, on l'utilise directement.
                self._set_state("listening")
                # Retire le wake word de la transcription
                cleaned = self._strip_wake_word(text)
                if len(cleaned.split()) >= 2:
                    print(f"\nVous : {cleaned}")
                    if not await self._try_unlock(client, cleaned):
                        await self._converse(client, cleaned)
                    last_interaction = time.time()
                else:
                    self._beep_or_print("J'écoute.")
                    await asyncio.sleep(0.05)
                    user_audio = await asyncio.to_thread(
                        self.mic.record_until_silence,
                        lambda: self._set_state("listening"),
                    )
                    user_text = await asyncio.to_thread(
                        self._transcribe_recorded, user_audio
                    )
                    if user_text:
                        print(f"\nVous : {user_text}")
                        if not await self._try_unlock(client, user_text):
                            await self._converse(client, user_text)
                        last_interaction = time.time()

                # ── Follow-up window : suite de conversation sans wake word ──
                if cfg.followup_window_sec > 0:
                    await self._followup_loop(client)

                self._set_state("wake")
                print(f"\n[wake] En attente de '{cfg.wake_words[0]}'...")
                continue

            # ── Mode toujours actif (pas de wake word) ──
            user_audio = await asyncio.to_thread(
                self.mic.record_until_silence,
                lambda: self._set_state("listening"),
            )
            user_text = await asyncio.to_thread(self._transcribe_recorded, user_audio)
            if not user_text:
                self._set_state("listening")
                continue
            print(f"\nVous : {user_text}")
            await self._converse(client, user_text)
            last_interaction = time.time()
            self._set_state("listening")

            # Bascule vers wake word après inactivité prolongée
            if cfg.wake_enabled and time.time() - last_interaction > cfg.wake_idle_timeout:
                wake_active = True
                self._set_state("wake")
                print(f"\n[wake] Inactif {cfg.wake_idle_timeout}s, retour en attente de wake word.")

    # ─── Follow-up : suite de conversation sans wake word ──────────────
    async def _followup_loop(self, client: OrionClient):
        """Après une réponse, écoute pendant N secondes les commandes suivantes
        sans exiger le wake word. Reset à chaque interaction réussie."""
        cfg = self.config
        window = cfg.followup_window_sec
        print(f"  [follow-up] J'écoute {window}s pour une suite (sans wake word)...")
        self._set_state("listening")

        while not self._stop_event.is_set():
            user_audio = await asyncio.to_thread(
                self.mic.record_until_silence,
                None,
                float(window),  # initial_silence_timeout_sec
            )
            if not user_audio:
                # Pas de parole dans la fenêtre → fin du follow-up
                return
            user_text = await asyncio.to_thread(self._transcribe_recorded, user_audio)
            if not user_text:
                continue
            # Sécurité : si l'utilisateur dit à nouveau "hey orion" pendant le follow-up,
            # on retire le préfixe pour ne pas le faire entendre dans la commande
            user_text = self._strip_wake_word(user_text) or user_text
            print(f"\nVous : {user_text}")
            if not await self._try_unlock(client, user_text):
                await self._converse(client, user_text)
            self._set_state("listening")
            print(f"  [follow-up] J'écoute {window}s de plus...")

    # ─── Utilitaires ────────────────────────────────────────────────────
    def _strip_wake_word(self, text: str) -> str:
        """Retire la première occurrence du wake word de la transcription."""
        from .wake_word import _normalize
        norm = _normalize(text)
        for variant in self.wake.variants:
            idx = norm.find(variant)
            if idx == -1:
                continue
            # On coupe au-delà du variant + un éventuel ", " ou " et"
            # En s'appuyant sur la longueur dans la version normalisée
            cleaned_len = len(variant)
            # Approx : on cherche dans l'original la même structure
            # (c'est inexact à cause des accents, mais suffisant)
            tail = text[idx + cleaned_len :]
            tail = tail.lstrip(" ,.;:!?-").strip()
            if tail:
                return tail
            return ""
        return text.strip()

    def _beep_or_print(self, msg: str):
        # Future : court son d'acquittement. Pour l'instant juste un print.
        print(f"[orion] {msg}")
        sys.stdout.flush()

    def stop(self):
        self._stop_event.set()


def run_from_env():
    """Point d'entrée appelé par start.py."""
    # Sous Windows, on évite ProactorEventLoop qui crashe en __del__ après
    # Ctrl+C (bug connu Python 3.11+, https://bugs.python.org/issue39232).
    # SelectorEventLoop supporte websockets sans problème pour notre charge.
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    config = VoiceConfig.from_env()
    if not config.secret_token:
        print("[!] ORION_SECRET_TOKEN manquant dans .env")
        sys.exit(1)
    service = VoiceService(config)
    try:
        asyncio.run(service.run())
    except KeyboardInterrupt:
        print("\nArrêt demandé.")
        service.stop()


if __name__ == "__main__":
    run_from_env()
