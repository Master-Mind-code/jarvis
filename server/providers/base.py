"""
Interface commune aux providers LLM (Anthropic, Gemini, ...).

Format pivot interne (= format Anthropic) :
  message:
    {"role": "user"|"assistant", "content": str | [block]}
  block:
    {"type": "text", "text": str}
    {"type": "tool_use", "id": str, "name": str, "input": dict}
    {"type": "tool_result", "tool_use_id": str, "content": str}

Chaque provider convertit ce format pivot vers/depuis son format natif.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ProviderResponse:
    """Réponse normalisée d'un appel LLM."""
    content: list   # liste de blocks dict ({"type": "text", ...} | {"type": "tool_use", ...})
    stop_reason: str   # "end_turn" | "tool_use" | "max_tokens"


class Provider(ABC):
    name: str = "abstract"
    model: str = ""

    @abstractmethod
    def call(self, system: str, tools: list, messages: list, max_tokens: int = 4096) -> ProviderResponse:
        ...
