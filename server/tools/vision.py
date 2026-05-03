"""
Orion Tool — Vision : analyse d'images via Claude / Gemini.

Modèles supportés :
  - Anthropic Claude (Sonnet/Opus 3.5+)  : vision native, best quality
  - Google Gemini 2.0+                   : vision native, fast & free
  - Ollama avec llava / llama3.2-vision  : local, qualité variable

Utilisation typique : "regarde C:\\screenshot.png et dis-moi ce qui ne va pas",
"décris cette photo", "lis le texte sur l'image", etc.
"""
from __future__ import annotations

import base64
import os
from pathlib import Path

SUPPORTED_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
MIME_BY_EXT = {
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png":  "image/png",
    ".gif":  "image/gif",
    ".webp": "image/webp",
    ".bmp":  "image/bmp",
}
MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB raw — au-delà, on rejette


def _load_image(path: str) -> tuple[bytes, str]:
    """Charge une image, valide son extension, retourne (bytes, mime_type)."""
    p = Path(path).expanduser()
    if not p.exists():
        raise FileNotFoundError(f"Image introuvable : {p}")
    if not p.is_file():
        raise ValueError(f"Pas un fichier : {p}")
    ext = p.suffix.lower()
    if ext not in SUPPORTED_EXTS:
        raise ValueError(
            f"Extension non supportée : {ext}. Formats acceptés : "
            f"{', '.join(sorted(SUPPORTED_EXTS))}"
        )
    raw = p.read_bytes()
    if len(raw) > MAX_IMAGE_BYTES:
        raise ValueError(
            f"Image trop grosse ({len(raw) // 1024} KB > {MAX_IMAGE_BYTES // 1024} KB). "
            f"Compresse d'abord."
        )
    return raw, MIME_BY_EXT[ext]


def _analyze_anthropic(raw: bytes, mime: str, prompt: str, model: str | None) -> str:
    from anthropic import Anthropic
    client = Anthropic()
    msg = client.messages.create(
        model=model or os.getenv("ORION_VISION_MODEL")
              or os.getenv("JARVIS_ANTHROPIC_MODEL")
              or os.getenv("ORION_ANTHROPIC_MODEL")
              or "claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": mime,
                        "data": base64.standard_b64encode(raw).decode("ascii"),
                    },
                },
                {"type": "text", "text": prompt},
            ],
        }],
    )
    text_parts = [b.text for b in msg.content if b.type == "text"]
    return "\n".join(text_parts).strip()


def _analyze_gemini(raw: bytes, mime: str, prompt: str, model: str | None) -> str:
    from google import genai
    from google.genai import types
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY manquant pour la vision Gemini")
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model or os.getenv("ORION_VISION_MODEL")
              or os.getenv("JARVIS_GEMINI_MODEL")
              or os.getenv("ORION_GEMINI_MODEL")
              or "gemini-2.0-flash",
        contents=[
            types.Part.from_bytes(data=raw, mime_type=mime),
            prompt,
        ],
    )
    return (response.text or "").strip()


def _analyze_ollama(raw: bytes, mime: str, prompt: str, model: str | None) -> str:
    """Ollama supporte la vision avec llava, llama3.2-vision, qwen2-vl, etc."""
    import httpx
    host = (os.environ.get("ORION_OLLAMA_HOST")
            or os.environ.get("OLLAMA_HOST")
            or "http://localhost:11434").rstrip("/")
    chosen = (model or os.getenv("ORION_VISION_MODEL")
              or os.getenv("ORION_OLLAMA_MODEL")
              or "llama3.2-vision")
    payload = {
        "model": chosen,
        "messages": [{
            "role": "user",
            "content": prompt,
            "images": [base64.standard_b64encode(raw).decode("ascii")],
        }],
        "stream": False,
    }
    resp = httpx.post(f"{host}/api/chat", json=payload, timeout=300.0)
    resp.raise_for_status()
    data = resp.json()
    return (data.get("message", {}).get("content") or "").strip()


def analyze_image(
    path: str,
    prompt: str = "Décris cette image en détail.",
    provider: str | None = None,
    model: str | None = None,
) -> dict:
    """Analyse une image et retourne sa description.

    provider : 'anthropic' | 'gemini' | 'ollama' | None (=provider Orion par défaut)
    model    : override du modèle (sinon ORION_VISION_MODEL ou défaut du provider)
    """
    try:
        raw, mime = _load_image(path)
    except (FileNotFoundError, ValueError) as exc:
        return {"success": False, "error": str(exc)}

    chosen_provider = (
        provider
        or os.getenv("ORION_VISION_PROVIDER")
        or os.getenv("ORION_PROVIDER")
        or os.getenv("JARVIS_PROVIDER")
        or "anthropic"
    ).strip().lower()

    try:
        if chosen_provider == "anthropic":
            description = _analyze_anthropic(raw, mime, prompt, model)
        elif chosen_provider == "gemini":
            description = _analyze_gemini(raw, mime, prompt, model)
        elif chosen_provider == "ollama":
            description = _analyze_ollama(raw, mime, prompt, model)
        else:
            return {"success": False, "error": f"Provider vision inconnu : {chosen_provider}"}
    except ImportError as exc:
        return {"success": False, "error": f"Dépendance manquante : {exc}"}
    except Exception as exc:
        return {"success": False, "error": f"{type(exc).__name__}: {exc}"}

    if not description:
        return {"success": False, "error": "Réponse vision vide (image bloquée par filtres ?)"}

    return {
        "success": True,
        "path": path,
        "provider": chosen_provider,
        "image_size_kb": len(raw) // 1024,
        "description": description,
    }


HANDLERS = {
    "analyze_image": lambda p: analyze_image(**p),
}
