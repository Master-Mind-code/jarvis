"""
Détection de mot de réveil ("hey orion") par transcription Whisper de clips courts.

Approche du projet Jarvis Local Voice : on enregistre un clip audio court
(~3 s) dès qu'on détecte de la parole, on le transcrit avec Whisper, et on
match contre une liste de variantes du wake word.

Pas optimal en CPU continu (Whisper est lourd même en small int8) mais
zéro setup. Pour de la production, envisager OpenWakeWord ou Picovoice
Porcupine.
"""
from __future__ import annotations

import re
import unicodedata


def _normalize(text: str) -> str:
    """Minuscule, sans accents, sans ponctuation, espaces collapsés."""
    text = text.lower().strip()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


class WakeWordDetector:
    def __init__(self, wake_words: list[str]):
        self.variants = [_normalize(w) for w in wake_words if w.strip()]
        if not self.variants:
            self.variants = ["orion"]

    def matches(self, transcription: str) -> bool:
        """True si la transcription contient une des variantes du wake word."""
        if not transcription:
            return False
        norm = _normalize(transcription)
        if not norm:
            return False
        for variant in self.variants:
            if variant in norm:
                return True
            # Tolérance : tokens du variant tous présents dans l'ordre
            tokens = variant.split()
            if all(t in norm for t in tokens):
                idx = -1
                ok = True
                for t in tokens:
                    new_idx = norm.find(t, idx + 1)
                    if new_idx == -1:
                        ok = False
                        break
                    idx = new_idx
                if ok:
                    return True
        return False
