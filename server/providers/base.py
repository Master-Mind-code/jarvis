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

Streaming :
  stream(...) yield des dicts du type :
    {"type": "text_delta", "text": "..."}        # fragment de texte
    {"type": "done", "response": ProviderResponse}  # fin du tour
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Iterator


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

    def stream(self, system: str, tools: list, messages: list,
               max_tokens: int = 4096) -> Iterator[dict]:
        """Version streamée. Default : appelle call() puis yield tout en un seul chunk.
        Les providers qui supportent le streaming réel (Anthropic, Gemini, Ollama)
        surchargent cette méthode."""
        response = self.call(system, tools, messages, max_tokens)
        # Yield le texte d'un seul coup pour les providers non-streaming
        for block in response.content:
            if block.get("type") == "text":
                yield {"type": "text_delta", "text": block["text"]}
        yield {"type": "done", "response": response}
