"""
Orion Tool — Génération d'images via Google Gemini Imagen.

Utilise google-genai (déjà dans requirements.txt). Clé requise : GEMINI_API_KEY.

Modèles Imagen disponibles (mai 2026) :
  - imagen-3.0-generate-002      (qualité photoréaliste)
  - imagen-3.0-fast-generate-001 (plus rapide, plus économique)

Ratios d'aspect : "1:1" (1024x1024), "3:4", "4:3", "9:16", "16:9".
"""
from __future__ import annotations

import base64
import os
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DIR = ROOT / "data" / "images"


def generate_image(
    prompt: str,
    output_path: str | None = None,
    aspect_ratio: str = "1:1",
    n: int = 1,
    model: str | None = None,
) -> dict:
    """Génère une ou plusieurs images depuis un prompt texte."""
    prompt = (prompt or "").strip()
    if not prompt:
        return {"success": False, "error": "prompt vide"}

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return {
            "success": False,
            "error": "GEMINI_API_KEY manquant dans .env. "
                     "Récupère une clé sur https://aistudio.google.com/apikey",
        }

    try:
        from google import genai
        from google.genai import types
    except ImportError:
        return {
            "success": False,
            "error": "google-genai n'est pas installé (devrait être dans requirements.txt)",
        }

    n = max(1, min(int(n or 1), 4))
    aspect = aspect_ratio if aspect_ratio in ("1:1", "3:4", "4:3", "9:16", "16:9") else "1:1"
    model_id = (model or os.getenv("ORION_IMAGE_MODEL")
                or "imagen-3.0-fast-generate-001")

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_images(
            model=model_id,
            prompt=prompt,
            config=types.GenerateImagesConfig(
                number_of_images=n,
                aspect_ratio=aspect,
            ),
        )
    except Exception as exc:
        return {"success": False, "error": f"{type(exc).__name__}: {exc}"}

    if not response or not getattr(response, "generated_images", None):
        return {"success": False, "error": "Aucune image générée (filtre de sécurité ?)"}

    DEFAULT_DIR.mkdir(parents=True, exist_ok=True)
    saved: list[str] = []
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    for i, gen in enumerate(response.generated_images):
        img_bytes = gen.image.image_bytes
        if output_path and n == 1:
            out = Path(output_path).expanduser()
            out.parent.mkdir(parents=True, exist_ok=True)
        else:
            suffix = "" if n == 1 else f"_{i + 1}"
            out = DEFAULT_DIR / f"orion_{timestamp}{suffix}.png"
        out.write_bytes(img_bytes)
        saved.append(str(out))

    return {
        "success": True,
        "model": model_id,
        "aspect_ratio": aspect,
        "count": len(saved),
        "paths": saved,
        "prompt": prompt,
    }


HANDLERS = {
    "generate_image": lambda p: generate_image(**p),
}
