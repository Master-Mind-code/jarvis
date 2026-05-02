"""
Lecteur audio zero-gap pour le streaming TTS.

Pattern repris de Jarvis Local Voice (chatbot_speech_to_speech.py:88).
Un thread sounddevice consomme un buffer numpy continu — les chunks TTS sont
concaténés et lus sans micro-coupure entre les phrases.
"""
from __future__ import annotations

import threading
from typing import Callable

import numpy as np

try:
    import sounddevice as sd
except ImportError as exc:  # pragma: no cover
    raise ImportError("sounddevice n'est pas installé.") from exc


class SeamlessPlayer:
    """Lecteur audio float32 mono qui accepte des chunks et les joue en continu."""

    def __init__(self, sample_rate: int = 24000, blocksize: int = 1024):
        self.sample_rate = sample_rate
        self.blocksize = blocksize
        self._lock = threading.Lock()
        self._buffer = np.zeros(0, dtype=np.float32)
        self._stream: sd.OutputStream | None = None
        self._on_idle_callbacks: list[Callable[[], None]] = []
        self._was_playing = False

    def start(self):
        if self._stream is not None:
            return

        def callback(outdata, frames, time_info, status):
            with self._lock:
                available = len(self._buffer)
                if available >= frames:
                    outdata[:, 0] = self._buffer[:frames]
                    self._buffer = self._buffer[frames:]
                    self._was_playing = True
                else:
                    if available > 0:
                        outdata[:available, 0] = self._buffer
                        outdata[available:, 0] = 0
                        self._buffer = np.zeros(0, dtype=np.float32)
                    else:
                        outdata[:, 0] = 0
                    if self._was_playing:
                        self._was_playing = False
                        for cb in self._on_idle_callbacks:
                            try:
                                cb()
                            except Exception:
                                pass

        self._stream = sd.OutputStream(
            samplerate=self.sample_rate,
            blocksize=self.blocksize,
            channels=1,
            dtype="float32",
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

    def enqueue(self, chunk: np.ndarray):
        """Ajoute un chunk audio float32 [-1,1] mono à lire."""
        if chunk is None or len(chunk) == 0:
            return
        chunk = np.asarray(chunk, dtype=np.float32).flatten()
        with self._lock:
            self._buffer = np.concatenate([self._buffer, chunk])

    def clear(self):
        """Vide immédiatement le buffer (interruption de la lecture)."""
        with self._lock:
            self._buffer = np.zeros(0, dtype=np.float32)

    def is_playing(self) -> bool:
        with self._lock:
            return len(self._buffer) > 0 or self._was_playing

    def wait_until_done(self, poll_interval: float = 0.05):
        """Bloque jusqu'à ce que le buffer soit vidé."""
        import time
        while self.is_playing():
            time.sleep(poll_interval)

    def on_idle(self, callback: Callable[[], None]):
        """Enregistre un callback appelé quand le buffer devient vide après lecture."""
        self._on_idle_callbacks.append(callback)
