"""
Sélecteur de provider LLM.

Configuration :
  ORION_PROVIDER=anthropic   (défaut)
  ORION_PROVIDER=gemini

Modèles par défaut :
  Anthropic : claude-sonnet-4-6   (override via ORION_ANTHROPIC_MODEL)
  Gemini    : gemini-2.0-flash    (override via ORION_GEMINI_MODEL)
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

    raise ValueError(f"Provider inconnu : '{name}'. Choisis 'anthropic' ou 'gemini'.")


__all__ = ["Provider", "ProviderResponse", "get_provider"]
