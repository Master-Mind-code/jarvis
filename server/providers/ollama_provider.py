"""
Provider Ollama (LLM 100% local — fallback offline / sans clé API).

Active avec :
    ORION_PROVIDER=ollama
    ORION_OLLAMA_MODEL=llama3.3:70b-instruct-q2_K   (ou autre tag installé)
    ORION_OLLAMA_HOST=http://localhost:11434         (défaut)

Prérequis :
    1. Installer Ollama : https://ollama.com/download
    2. Démarrer le service : ollama serve
    3. Télécharger un modèle qui supporte le tool calling :
        ollama pull llama3.3:70b-instruct-q2_K       (~26 GB, qualité moyenne)
        ollama pull llama3.1:8b                      (~5 GB, plus rapide, tool calling OK)
        ollama pull qwen2.5:14b                      (~9 GB, excellent tool calling)
        ollama pull mistral-nemo                     (~7 GB, rapide, tool calling fiable)

Notes performance :
    - 70B en CPU sans GPU : ~1 token/s, donc une réponse complète peut prendre
      30-90 secondes. Recommandé seulement avec GPU NVIDIA 24+ GB VRAM ou
      Mac M-series unified memory ≥ 32 GB.
    - Quantisation Q2_K = qualité dégradée vs Q4_K_M ou Q5_K_M.
      Si tu as la VRAM, télécharge plutôt llama3.3:70b-instruct-q4_K_M.
    - Tool calling Llama 3.3 fonctionne mais est moins fiable que Claude/Gemini :
      le modèle peut halluciner des tools ou en oublier dans des chaînes longues.

Conversion format pivot Anthropic ↔ format Ollama (compatible OpenAI) :
    role 'assistant' avec tool_use → message {role:'assistant', tool_calls:[...]}
    block 'tool_result'            → message {role:'tool', tool_call_id, content}
    tools schema Anthropic         → tools schema OpenAI ({type:'function', function:{...}})
"""
from __future__ import annotations

import json
import os
import uuid

import httpx

from .base import Provider, ProviderResponse


DEFAULT_HOST = "http://localhost:11434"
DEFAULT_MODEL = "llama3.1:8b"
# Timeout généreux : un 70B en CPU peut prendre plusieurs minutes par réponse.
DEFAULT_TIMEOUT = 300.0


class OllamaProvider(Provider):
    name = "ollama"

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        host: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        self.model = model
        self.host = (host or os.environ.get("ORION_OLLAMA_HOST")
                     or os.environ.get("OLLAMA_HOST")
                     or DEFAULT_HOST).rstrip("/")
        self.timeout = timeout
        # Vérification basique : Ollama est-il joignable ?
        try:
            r = httpx.get(f"{self.host}/api/tags", timeout=3.0)
            r.raise_for_status()
            tags = [m["name"] for m in r.json().get("models", [])]
            if model not in tags and not any(t.startswith(model.split(":")[0]) for t in tags):
                print(f"[ollama] ⚠ Modèle '{model}' non trouvé. Modèles installés : "
                      f"{', '.join(tags) if tags else '(aucun)'}.\n"
                      f"           Télécharge avec : ollama pull {model}")
        except Exception as exc:
            raise RuntimeError(
                f"Ollama injoignable sur {self.host}. Démarre le service avec "
                f"`ollama serve` puis vérifie qu'il répond sur cette URL.\n"
                f"Erreur : {exc}"
            )

    # ─── Conversion : pivot Anthropic → format OpenAI/Ollama ─────────────
    @staticmethod
    def _convert_tools(tools: list) -> list:
        out = []
        for t in tools:
            schema = t.get("input_schema") or {"type": "object", "properties": {}}
            out.append({
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": schema,
                },
            })
        return out

    @staticmethod
    def _convert_messages(system: str, messages: list) -> list:
        """Format pivot → format Ollama (compatible OpenAI chat)."""
        out: list[dict] = []
        if system:
            out.append({"role": "system", "content": system})

        for msg in messages:
            role = msg["role"]
            content = msg["content"]

            if isinstance(content, str):
                out.append({"role": role, "content": content})
                continue

            # content est une liste de blocks (text, tool_use, tool_result)
            text_parts = []
            tool_calls = []
            tool_results = []

            for block in content:
                btype = block.get("type") if isinstance(block, dict) else getattr(block, "type", None)

                if btype == "text":
                    text = block["text"] if isinstance(block, dict) else block.text
                    if text:
                        text_parts.append(text)

                elif btype == "tool_use":
                    bid = block["id"] if isinstance(block, dict) else block.id
                    bname = block["name"] if isinstance(block, dict) else block.name
                    binput = block["input"] if isinstance(block, dict) else block.input
                    tool_calls.append({
                        "id": bid,
                        "type": "function",
                        "function": {
                            "name": bname,
                            # Ollama veut des arguments en JSON string ou en dict selon
                            # la version. On envoie un dict (formats récents).
                            "arguments": binput or {},
                        },
                    })

                elif btype == "tool_result":
                    bid = block["tool_use_id"] if isinstance(block, dict) else block.tool_use_id
                    bcontent = block["content"] if isinstance(block, dict) else block.content
                    if not isinstance(bcontent, str):
                        bcontent = json.dumps(bcontent, ensure_ascii=False)
                    tool_results.append({
                        "role": "tool",
                        "tool_call_id": bid,
                        "content": bcontent,
                    })

            # On émet le message assistant (text + tool_calls) si applicable
            if role == "assistant":
                msg_out = {"role": "assistant", "content": "\n".join(text_parts)}
                if tool_calls:
                    msg_out["tool_calls"] = tool_calls
                out.append(msg_out)
            else:
                # role == "user" : peut contenir des tool_results (ce que fait le pivot)
                if tool_results:
                    out.extend(tool_results)
                if text_parts:
                    out.append({"role": "user", "content": "\n".join(text_parts)})

        return out

    # ─── Appel ───────────────────────────────────────────────────────────
    def call(self, system: str, tools: list, messages: list, max_tokens: int = 4096) -> ProviderResponse:
        payload = {
            "model": self.model,
            "messages": self._convert_messages(system, messages),
            "stream": False,
            "options": {
                "num_predict": max_tokens,
                "temperature": 0.7,
            },
        }
        ollama_tools = self._convert_tools(tools)
        if ollama_tools:
            payload["tools"] = ollama_tools

        try:
            resp = httpx.post(
                f"{self.host}/api/chat",
                json=payload,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Erreur Ollama ({self.host}) : {exc}")

        message = data.get("message", {}) or {}
        text = (message.get("content") or "").strip()
        tool_calls = message.get("tool_calls") or []

        content_blocks: list[dict] = []
        if text:
            content_blocks.append({"type": "text", "text": text})

        for tc in tool_calls:
            fn = tc.get("function", {}) or {}
            name = fn.get("name")
            args = fn.get("arguments")
            # Ollama renvoie soit un dict, soit une string JSON. Normalise.
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {"raw": args}
            if not isinstance(args, dict):
                args = {"value": args}
            if not name:
                continue
            content_blocks.append({
                "type": "tool_use",
                "id": tc.get("id") or f"toolu_{uuid.uuid4().hex[:12]}",
                "name": name,
                "input": args,
            })

        has_tool_use = any(b["type"] == "tool_use" for b in content_blocks)
        stop_reason = "tool_use" if has_tool_use else "end_turn"
        return ProviderResponse(content=content_blocks, stop_reason=stop_reason)

    def stream(self, system: str, tools: list, messages: list, max_tokens: int = 4096):
        """Streaming Ollama via /api/chat avec stream=true (NDJSON)."""
        payload = {
            "model": self.model,
            "messages": self._convert_messages(system, messages),
            "stream": True,
            "options": {"num_predict": max_tokens, "temperature": 0.7},
        }
        ollama_tools = self._convert_tools(tools)
        if ollama_tools:
            payload["tools"] = ollama_tools

        accumulated_text = []
        tool_calls_collected: list[dict] = []

        with httpx.stream(
            "POST", f"{self.host}/api/chat", json=payload, timeout=self.timeout,
        ) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                msg = data.get("message", {}) or {}
                # Texte streamé chunk par chunk
                txt = msg.get("content", "")
                if txt:
                    accumulated_text.append(txt)
                    yield {"type": "text_delta", "text": txt}
                # Tool calls : Ollama les envoie souvent en bloc à la fin
                tcs = msg.get("tool_calls") or []
                for tc in tcs:
                    fn = tc.get("function", {}) or {}
                    name = fn.get("name")
                    args = fn.get("arguments")
                    if isinstance(args, str):
                        try: args = json.loads(args)
                        except Exception: args = {"raw": args}
                    if not isinstance(args, dict):
                        args = {"value": args}
                    if name:
                        tool_calls_collected.append({
                            "type": "tool_use",
                            "id": tc.get("id") or f"toolu_{uuid.uuid4().hex[:12]}",
                            "name": name,
                            "input": args,
                        })
                if data.get("done"):
                    break

        content_blocks = []
        full_text = "".join(accumulated_text).strip()
        if full_text:
            content_blocks.append({"type": "text", "text": full_text})
        content_blocks.extend(tool_calls_collected)
        stop_reason = "tool_use" if tool_calls_collected else "end_turn"
        yield {"type": "done", "response": ProviderResponse(content=content_blocks, stop_reason=stop_reason)}
