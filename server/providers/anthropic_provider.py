"""Provider Anthropic Claude (avec prompt caching)."""
import os
from anthropic import Anthropic
from .base import Provider, ProviderResponse


class AnthropicProvider(Provider):
    name = "anthropic"

    def __init__(self, model: str = "claude-sonnet-4-6"):
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError("ANTHROPIC_API_KEY manquante dans .env")
        self.model = model
        self.client = Anthropic()

    def call(self, system: str, tools: list, messages: list, max_tokens: int = 4096) -> ProviderResponse:
        # Cache control sur system + dernier tool (économise tokens en boucle agentic)
        cached_system = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
        cached_tools = [*tools[:-1], {**tools[-1], "cache_control": {"type": "ephemeral"}}] if tools else []

        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=cached_system,
            tools=cached_tools,
            messages=messages,
        )

        # Normalise en dicts purs (l'historique stocke des dicts, pas des objets SDK)
        content = []
        for b in response.content:
            if b.type == "text":
                content.append({"type": "text", "text": b.text})
            elif b.type == "tool_use":
                content.append({
                    "type": "tool_use",
                    "id": b.id,
                    "name": b.name,
                    "input": dict(b.input) if b.input else {},
                })

        return ProviderResponse(content=content, stop_reason=response.stop_reason or "end_turn")
