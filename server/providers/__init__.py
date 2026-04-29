"""
Sélecteur de provider LLM.

Configuration :
  JARVIS_PROVIDER=anthropic   (défaut)
  JARVIS_PROVIDER=gemini

Modèles par défaut :
  Anthropic : claude-sonnet-4-6   (override via JARVIS_ANTHROPIC_MODEL)
  Gemini    : gemini-2.0-flash    (override via JARVIS_GEMINI_MODEL)
"""
import os
from .base import Provider, ProviderResponse


def get_provider(name: str = None) -> Provider:
    name = (name or os.getenv("JARVIS_PROVIDER", "anthropic")).strip().lower()

    if name == "anthropic":
        from .anthropic_provider import AnthropicProvider
        model = os.getenv("JARVIS_ANTHROPIC_MODEL", "claude-sonnet-4-6")
        return AnthropicProvider(model=model)

    if name == "gemini":
        from .gemini_provider import GeminiProvider
        model = os.getenv("JARVIS_GEMINI_MODEL", "gemini-2.0-flash")
        return GeminiProvider(model=model)

    raise ValueError(f"Provider inconnu : '{name}'. Choisis 'anthropic' ou 'gemini'.")


__all__ = ["Provider", "ProviderResponse", "get_provider"]
