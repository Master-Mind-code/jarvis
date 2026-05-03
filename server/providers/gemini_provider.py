"""
Provider Google Gemini 2.0 Flash.

Convertit le format pivot Anthropic vers le format natif Gemini :
  - role 'assistant' → 'model'
  - blocks 'tool_use' → Part.function_call
  - blocks 'tool_result' → Part.function_response (nécessite de retracer le name via tool_use_id)
  - tools schema → list[Tool(function_declarations=...)]
"""
import os
import json
import uuid
from .base import Provider, ProviderResponse


def _to_jsonable(obj):
    """Convertit récursivement les structures proto/MapComposite en types Python natifs."""
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(v) for v in obj]
    # MapComposite, RepeatedComposite, etc.
    try:
        return dict(obj)
    except Exception:
        try:
            return list(obj)
        except Exception:
            return str(obj)


class GeminiProvider(Provider):
    name = "gemini"

    def __init__(self, model: str = "gemini-2.0-flash"):
        if not os.environ.get("GEMINI_API_KEY") and not os.environ.get("GOOGLE_API_KEY"):
            raise RuntimeError("GEMINI_API_KEY (ou GOOGLE_API_KEY) manquante dans .env")
        # Import paresseux : permet aux utilisateurs Anthropic-only de ne pas installer google-genai
        from google import genai
        from google.genai import types
        self._genai = genai
        self._types = types
        self.model = model
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        self.client = genai.Client(api_key=api_key)

    def _convert_tools(self, tools: list) -> list:
        types = self._types
        decls = []
        for t in tools:
            schema = t.get("input_schema", {"type": "object", "properties": {}})
            decls.append(types.FunctionDeclaration(
                name=t["name"],
                description=t.get("description", ""),
                parameters=schema,
            ))
        return [types.Tool(function_declarations=decls)] if decls else []

    def _convert_messages(self, messages: list) -> list:
        types = self._types
        # Mapping tool_use_id → tool_name (Gemini exige le name dans function_response)
        id_to_name: dict[str, str] = {}
        contents = []

        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            gemini_role = "user" if role == "user" else "model"

            if isinstance(content, str):
                contents.append(types.Content(role=gemini_role, parts=[types.Part(text=content)]))
                continue

            parts = []
            for block in content:
                # Supporte dicts (notre pivot) et objets SDK Anthropic (au cas où)
                btype = block.get("type") if isinstance(block, dict) else getattr(block, "type", None)

                if btype == "text":
                    text = block["text"] if isinstance(block, dict) else block.text
                    if text:
                        parts.append(types.Part(text=text))

                elif btype == "tool_use":
                    bid = block["id"] if isinstance(block, dict) else block.id
                    bname = block["name"] if isinstance(block, dict) else block.name
                    binput = block["input"] if isinstance(block, dict) else block.input
                    id_to_name[bid] = bname
                    parts.append(types.Part(function_call=types.FunctionCall(
                        name=bname, args=binput or {},
                    )))

                elif btype == "tool_result":
                    bid = block["tool_use_id"] if isinstance(block, dict) else block.tool_use_id
                    bcontent = block["content"] if isinstance(block, dict) else block.content
                    name = id_to_name.get(bid, "unknown")
                    # Le content est une string JSON depuis execute_tool ; on la décompose
                    try:
                        parsed = json.loads(bcontent) if isinstance(bcontent, str) else bcontent
                    except Exception:
                        parsed = {"result": bcontent}
                    if not isinstance(parsed, dict):
                        parsed = {"result": parsed}
                    parts.append(types.Part(function_response=types.FunctionResponse(
                        name=name, response=parsed,
                    )))

            if parts:
                contents.append(types.Content(role=gemini_role, parts=parts))

        return contents

    def _build_config(self, system: str, tools: list, max_tokens: int):
        types = self._types
        return types.GenerateContentConfig(
            system_instruction=system,
            tools=self._convert_tools(tools),
            max_output_tokens=max_tokens,
            temperature=0.7,
        )

    def call(self, system: str, tools: list, messages: list, max_tokens: int = 4096) -> ProviderResponse:
        gemini_messages = self._convert_messages(messages)
        config = self._build_config(system, tools, max_tokens)

        response = self.client.models.generate_content(
            model=self.model,
            contents=gemini_messages,
            config=config,
        )

        content = []
        if response.candidates:
            cand_parts = response.candidates[0].content.parts or []
            for part in cand_parts:
                if getattr(part, "text", None):
                    content.append({"type": "text", "text": part.text})
                fc = getattr(part, "function_call", None)
                if fc and getattr(fc, "name", None):
                    args = _to_jsonable(fc.args) if fc.args else {}
                    content.append({
                        "type": "tool_use",
                        "id": f"toolu_{uuid.uuid4().hex[:12]}",
                        "name": fc.name,
                        "input": args if isinstance(args, dict) else {"value": args},
                    })

        has_tool_use = any(b["type"] == "tool_use" for b in content)
        stop_reason = "tool_use" if has_tool_use else "end_turn"
        return ProviderResponse(content=content, stop_reason=stop_reason)

    def stream(self, system: str, tools: list, messages: list, max_tokens: int = 4096):
        """Streaming Gemini via generate_content_stream."""
        gemini_messages = self._convert_messages(messages)
        config = self._build_config(system, tools, max_tokens)

        accumulated_text: list[str] = []
        tool_calls: list[dict] = []

        for chunk in self.client.models.generate_content_stream(
            model=self.model,
            contents=gemini_messages,
            config=config,
        ):
            if not chunk.candidates:
                continue
            parts = chunk.candidates[0].content.parts or []
            for part in parts:
                if getattr(part, "text", None):
                    accumulated_text.append(part.text)
                    yield {"type": "text_delta", "text": part.text}
                fc = getattr(part, "function_call", None)
                if fc and getattr(fc, "name", None):
                    args = _to_jsonable(fc.args) if fc.args else {}
                    tool_calls.append({
                        "type": "tool_use",
                        "id": f"toolu_{uuid.uuid4().hex[:12]}",
                        "name": fc.name,
                        "input": args if isinstance(args, dict) else {"value": args},
                    })

        content = []
        full_text = "".join(accumulated_text).strip()
        if full_text:
            content.append({"type": "text", "text": full_text})
        content.extend(tool_calls)

        stop_reason = "tool_use" if tool_calls else "end_turn"
        yield {"type": "done", "response": ProviderResponse(content=content, stop_reason=stop_reason)}
