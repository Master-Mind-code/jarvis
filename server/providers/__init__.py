"""
Sélecteur de provider LLM.

Configuration :
  ORION_PROVIDER=anthropic   (défaut, payant, qualité top)
  ORION_PROVIDER=gemini      (gratuit jusqu'à 1M tokens/jour)
  ORION_PROVIDER=ollama      (100% local, offline, pas de clé API)
  ORION_PROVIDER=fallback    (chaîne avec bascule auto sur erreur)
                             ORION_FALLBACK_CHAIN=anthropic,gemini,ollama (défaut)

Modèles par défaut :
  Anthropic : claude-sonnet-4-6           (override via ORION_ANTHROPIC_MODEL)
  Gemini    : gemini-2.0-flash            (override via ORION_GEMINI_MODEL)
  Ollama    : llama3.1:8b                 (override via ORION_OLLAMA_MODEL)
"""
import os
from .base import Provider, ProviderResponse
from branding import get_env


def get_provider(name: str = None) -> Provider:
    name = (name or get_env("PROVIDER", "anthropic")).strip().lower()

    if name == "anthropic":
        from .anthropic_provider import AnthropicProvider
        model = get_env("ANTHROPIC_MODEL", "claude-sonnet-4-6")
        return AnthropicProvider(model=model)

    if name == "gemini":
        from .gemini_provider import GeminiProvider
        model = get_env("GEMINI_MODEL", "gemini-2.0-flash")
        return GeminiProvider(model=model)

    if name == "ollama":
        from .ollama_provider import OllamaProvider
        model = get_env("OLLAMA_MODEL", "llama3.1:8b")
        return OllamaProvider(model=model)

    if name == "fallback":
        from .fallback_provider import build_fallback_chain
        return build_fallback_chain()

    raise ValueError(
        f"Provider inconnu : '{name}'. Choisis 'anthropic', 'gemini', 'ollama' ou 'fallback'."
    )


__all__ = ["Provider", "ProviderResponse", "get_provider"]
