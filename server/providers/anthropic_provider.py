"""Provider Anthropic Claude (avec prompt caching + streaming)."""
import json
import os
from typing import Iterator

from anthropic import Anthropic

from .base import Provider, ProviderResponse


class AnthropicProvider(Provider):
    name = "anthropic"

    def __init__(self, model: str = "claude-sonnet-4-6"):
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError("ANTHROPIC_API_KEY manquante dans .env")
        self.model = model
        self.client = Anthropic()

    def _cached_payload(self, system: str, tools: list):
        cached_system = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
        cached_tools = [*tools[:-1], {**tools[-1], "cache_control": {"type": "ephemeral"}}] if tools else []
        return cached_system, cached_tools

    def call(self, system: str, tools: list, messages: list, max_tokens: int = 4096) -> ProviderResponse:
        cached_system, cached_tools = self._cached_payload(system, tools)
        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=cached_system,
            tools=cached_tools,
            messages=messages,
        )

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

    def stream(self, system: str, tools: list, messages: list,
               max_tokens: int = 4096) -> Iterator[dict]:
        """Streaming SSE Anthropic : yield les text_delta puis le response final."""
        cached_system, cached_tools = self._cached_payload(system, tools)

        # Accumulateurs reconstruits depuis les events
        content_blocks: list[dict] = []
        current_block: dict | None = None
        current_tool_args_buf: str = ""
        stop_reason = "end_turn"

        with self.client.messages.stream(
            model=self.model,
            max_tokens=max_tokens,
            system=cached_system,
            tools=cached_tools,
            messages=messages,
        ) as stream:
            for event in stream:
                etype = getattr(event, "type", None)

                if etype == "content_block_start":
                    block = event.content_block
                    if block.type == "text":
                        current_block = {"type": "text", "text": ""}
                    elif block.type == "tool_use":
                        current_block = {
                            "type": "tool_use",
                            "id": block.id,
                            "name": block.name,
                            "input": {},
                        }
                        current_tool_args_buf = ""

                elif etype == "content_block_delta":
                    delta = event.delta
                    dtype = getattr(delta, "type", None)
                    if dtype == "text_delta":
                        if current_block and current_block["type"] == "text":
                            current_block["text"] += delta.text
                        yield {"type": "text_delta", "text": delta.text}
                    elif dtype == "input_json_delta":
                        # Args du tool (JSON partiel cumulatif)
                        current_tool_args_buf += delta.partial_json

                elif etype == "content_block_stop":
                    if current_block:
                        if current_block["type"] == "tool_use" and current_tool_args_buf:
                            try:
                                current_block["input"] = json.loads(current_tool_args_buf)
                            except json.JSONDecodeError:
                                current_block["input"] = {"raw": current_tool_args_buf}
                        content_blocks.append(current_block)
                        current_block = None
                        current_tool_args_buf = ""

                elif etype == "message_delta":
                    if hasattr(event, "delta") and getattr(event.delta, "stop_reason", None):
                        stop_reason = event.delta.stop_reason

        response = ProviderResponse(content=content_blocks, stop_reason=stop_reason)
        yield {"type": "done", "response": response}
