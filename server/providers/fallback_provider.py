"""
Provider FallbackChain : enchaîne plusieurs providers et bascule auto sur erreur.

Utilité :
  - Anthropic rate-limited / hors quota → bascule auto sur Gemini
  - Internet down → bascule auto sur Ollama
  - Plus jamais de "API down" qui bloque Orion

Activation :
    ORION_PROVIDER=fallback
    ORION_FALLBACK_CHAIN=anthropic,gemini,ollama   (défaut)

Le premier provider qui répond sans lever d'exception gagne. Si tous
échouent, l'erreur du dernier est remontée.
"""
from __future__ import annotations

import os
from typing import Iterable

from .base import Provider, ProviderResponse


# Erreurs qui doivent déclencher la bascule immédiate (pas de retry inutile)
TRANSIENT_ERROR_HINTS = (
    "rate limit",
    "rate_limit",
    "quota",
    "overloaded",
    "503",
    "502",
    "504",
    "timeout",
    "connection",
    "name resolution",
    "credit balance",
    "insufficient",
    "unauthorized",
    "401",
)


def _is_transient(exc: Exception) -> bool:
    """Détecte les erreurs où ça vaut le coup de basculer sur le provider suivant."""
    msg = str(exc).lower()
    return any(hint in msg for hint in TRANSIENT_ERROR_HINTS)


class FallbackProvider(Provider):
    name = "fallback"

    def __init__(self, chain: list[Provider]):
        if not chain:
            raise ValueError("FallbackProvider exige au moins un provider dans la chaîne.")
        self.chain = chain
        self.model = " → ".join(f"{p.name}({p.model})" for p in chain)
        self._active_idx = 0  # provider actuellement préféré

    def _try_provider(self, idx: int, *args, **kwargs) -> ProviderResponse:
        provider = self.chain[idx]
        return provider.call(*args, **kwargs)

    def call(self, system: str, tools: list, messages: list, max_tokens: int = 4096) -> ProviderResponse:
        last_error: Exception | None = None

        # On commence par le provider actuellement actif (sticky)
        order = list(range(len(self.chain)))
        order = order[self._active_idx:] + order[:self._active_idx]

        for idx in order:
            provider = self.chain[idx]
            try:
                response = self._try_provider(idx, system, tools, messages, max_tokens)
                if idx != self._active_idx:
                    print(f"[fallback] ✓ Bascule sur '{provider.name}' (sticky)")
                self._active_idx = idx  # devient le préféré pour les prochains appels
                return response
            except Exception as exc:
                last_error = exc
                if _is_transient(exc) or len(self.chain) > 1:
                    next_idx = (order[order.index(idx) + 1] if order.index(idx) + 1 < len(order) else None)
                    if next_idx is not None:
                        next_name = self.chain[next_idx].name
                        print(f"[fallback] ⚠ '{provider.name}' a échoué ({exc}). "
                              f"Bascule sur '{next_name}'...")
                        continue
                raise

        # Tous les providers ont échoué
        raise RuntimeError(
            f"Tous les providers de la chaîne ont échoué. "
            f"Dernière erreur : {last_error}"
        )


def build_fallback_chain(spec: str | None = None) -> "FallbackProvider":
    """Construit une FallbackChain depuis une string CSV ('anthropic,gemini,ollama')."""
    from . import get_provider as _get_provider  # éviter cycle d'import

    raw = (spec
           or os.environ.get("ORION_FALLBACK_CHAIN")
           or os.environ.get("JARVIS_FALLBACK_CHAIN")
           or "anthropic,gemini,ollama")
    names = [n.strip().lower() for n in raw.split(",") if n.strip()]

    chain = []
    for name in names:
        if name == "fallback":
            continue  # évite récursion
        try:
            provider = _get_provider(name)
            chain.append(provider)
            print(f"[fallback] + {name} ({provider.model})")
        except Exception as exc:
            # Provider non disponible (clé manquante, Ollama down…) : on l'ignore
            print(f"[fallback] - {name} ignoré : {exc}")

    if not chain:
        raise RuntimeError(
            "Aucun provider disponible dans la chaîne fallback. "
            "Vérifie tes clés API et qu'Ollama tourne."
        )
    return FallbackProvider(chain)
