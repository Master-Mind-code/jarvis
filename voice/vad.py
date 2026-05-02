"""
Capture micro avec Voice Activity Detection (webrtcvad).

Le silence de fin d'enregistrement est adaptatif : court si l'utilisateur a parlé
brièvement, plus long après une phrase prolongée (évite de couper en plein milieu).
"""
from __future__ import annotations

import collections
import queue
from typing import Callable

import numpy as np

try:
    import sounddevice as sd
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "sounddevice n'est pas installé. Sous Windows il fournit son propre PortAudio.\n"
        "Installe avec : pip install -r requirements-voice.txt"
    ) from exc

try:
    import webrtcvad
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "webrtcvad-wheels n'est pas installé. Installe avec :\n"
        "    pip install -r requirements-voice.txt"
    ) from exc


FRAME_DURATION_MS = 30  # webrtcvad accepte 10/20/30 ms uniquement


class MicCapture:
    """Capture le micro et retourne un buffer audio quand l'utilisateur a fini de parler.

    Sous le capot : un thread sounddevice remplit une queue de frames de 30 ms.
    `record_until_silence()` consomme les frames, détecte le début de la parole
    (premier frame non-silence), puis arrête après un silence soutenu.
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        aggressiveness: int = 3,
        silence_short_ms: int = 520,
        silence_long_ms: int = 950,
        silence_long_after_ms: int = 2500,
        max_record_seconds: int = 30,
    ):
        self.sample_rate = sample_rate
        self.frame_samples = int(sample_rate * FRAME_DURATION_MS / 1000)
        self.frame_bytes = self.frame_samples * 2  # int16
        self.vad = webrtcvad.Vad(aggressiveness)

        self.silence_short_frames = max(1, silence_short_ms // FRAME_DURATION_MS)
        self.silence_long_frames = max(1, silence_long_ms // FRAME_DURATION_MS)
        self.silence_switch_frames = max(1, silence_long_after_ms // FRAME_DURATION_MS)
        self.max_record_frames = max(1, (max_record_seconds * 1000) // FRAME_DURATION_MS)

        self._audio_q: queue.Queue[bytes] = queue.Queue()
        self._stream: sd.RawInputStream | None = None

    def start(self):
        """Démarre la capture micro en arrière-plan."""
        if self._stream is not None:
            return

        def callback(indata, frames, time_info, status):
            if status:
                # Underflow / overflow possible — on ignore, ce n'est pas critique
                pass
            self._audio_q.put(bytes(indata))

        self._stream = sd.RawInputStream(
            samplerate=self.sample_rate,
            blocksize=self.frame_samples,
            dtype="int16",
            channels=1,
            callback=callback,
        )
        self._stream.start()

    def stop(self):
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.stop()

    def _drain(self):
        """Vide la queue audio (utile entre deux enregistrements)."""
        while not self._audio_q.empty():
            try:
                self._audio_q.get_nowait()
            except queue.Empty:
                break

    def read_frame(self, timeout: float = 1.0) -> bytes | None:
        """Lit une frame audio brute (30 ms, 16 kHz, int16)."""
        try:
            return self._audio_q.get(timeout=timeout)
        except queue.Empty:
            return None

    def is_speech(self, frame: bytes) -> bool:
        if len(frame) != self.frame_bytes:
            return False
        return self.vad.is_speech(frame, self.sample_rate)

    def record_until_silence(
        self,
        on_speech_start: Callable[[], None] | None = None,
        initial_silence_timeout_sec: float | None = None,
    ) -> bytes:
        """Bloquant : enregistre jusqu'à détecter un silence durable après la parole.

        Si `initial_silence_timeout_sec` est défini : retourne b"" si rien n'a
        été détecté dans ce délai (utile pour follow-up window).

        Retourne le buffer audio brut (int16, mono, 16 kHz) ou b"" si rien capté.
        """
        import time
        self._drain()
        ring: collections.deque[bytes] = collections.deque(maxlen=10)  # ~300 ms de pré-buffer
        recorded: list[bytes] = []
        speaking = False
        silence_count = 0
        speech_frames = 0
        notified = False
        wait_start = time.monotonic()

        for _ in range(self.max_record_frames):
            frame = self.read_frame(timeout=2.0)
            if frame is None:
                if speaking:
                    break
                # Pas encore de parole : on vérifie le timeout d'attente initiale
                if (initial_silence_timeout_sec is not None
                        and time.monotonic() - wait_start >= initial_silence_timeout_sec):
                    return b""
                continue

            # Timeout initial actif et toujours pas de parole détectée
            if (not speaking
                    and initial_silence_timeout_sec is not None
                    and time.monotonic() - wait_start >= initial_silence_timeout_sec):
                return b""

            speech = self.is_speech(frame)

            if not speaking:
                ring.append(frame)
                if speech:
                    speaking = True
                    speech_frames = 1
                    silence_count = 0
                    recorded.extend(ring)
                    ring.clear()
                    if on_speech_start and not notified:
                        on_speech_start()
                        notified = True
            else:
                recorded.append(frame)
                if speech:
                    speech_frames += 1
                    silence_count = 0
                else:
                    silence_count += 1
                    threshold = (
                        self.silence_long_frames
                        if speech_frames >= self.silence_switch_frames
                        else self.silence_short_frames
                    )
                    if silence_count >= threshold:
                        break

        if not recorded:
            return b""
        return b"".join(recorded)

    def record_fixed(self, seconds: float) -> bytes:
        """Enregistre un clip de durée fixe (utilisé pour le wake word)."""
        self._drain()
        n_frames = max(1, int(seconds * 1000 // FRAME_DURATION_MS))
        chunks: list[bytes] = []
        for _ in range(n_frames):
            frame = self.read_frame(timeout=2.0)
            if frame is None:
                break
            chunks.append(frame)
        return b"".join(chunks)


def to_int16_array(raw: bytes) -> np.ndarray:
    return np.frombuffer(raw, dtype=np.int16)
