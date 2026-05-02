"""
Embeddings via sentence-transformers.

Modèle par défaut : paraphrase-multilingual-MiniLM-L12-v2 (~118 MB, 50+ langues
dont le français, vecteurs 384-dim, qualité correcte sur CPU).

Premier appel : DL automatique du modèle (~2 min en réseau correct).
"""
from __future__ import annotations

import os

import numpy as np

DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


class Embedder:
    _instance: "Embedder | None" = None

    def __init__(self, model_name: str | None = None, device: str = "cpu"):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise ImportError(
                "sentence-transformers n'est pas installé. Installe avec :\n"
                "    pip install -r requirements-rag.txt"
            ) from exc

        self.model_name = model_name or os.getenv(
            "ORION_MEMORY_MODEL", DEFAULT_MODEL
        )
        print(f"[memory] Chargement embeddings '{self.model_name}' ({device})...")
        self.model = SentenceTransformer(self.model_name, device=device)
        # API a été renommée get_sentence_embedding_dimension → get_embedding_dimension
        if hasattr(self.model, "get_embedding_dimension"):
            self.dim = self.model.get_embedding_dimension()
        else:
            self.dim = self.model.get_sentence_embedding_dimension()
        print(f"[memory] Modèle prêt (dim={self.dim}).")

    def embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        vectors = self.model.encode(
            texts,
            batch_size=32,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return np.asarray(vectors, dtype=np.float32)

    def embed_one(self, text: str) -> np.ndarray:
        return self.embed([text])[0]


def get_embedder() -> Embedder:
    """Singleton paresseux : on ne charge le modèle qu'au premier appel d'un tool memory."""
    if Embedder._instance is None:
        Embedder._instance = Embedder()
    return Embedder._instance
