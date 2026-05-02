"""
Vector store minimaliste : numpy + JSON, recherche cosinus exhaustive.

Suffisant jusqu'à ~50 000 entrées (recherche < 100 ms). Au-delà, basculer sur
ChromaDB / LanceDB / FAISS. Pour un usage personnel, c'est largement assez et
on évite des deps lourdes (ONNX Runtime, sqlite, etc.).

Format de persistance :
  data/memory/{namespace}/vectors.npy   — float32 (N, dim), normalisés
  data/memory/{namespace}/meta.jsonl    — un objet JSON par ligne :
      {id, text, source, tags, created_at}
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from threading import RLock

import numpy as np


@dataclass
class MemoryItem:
    id: str
    text: str
    source: str = "manual"
    tags: list[str] = field(default_factory=list)
    created_at: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


class VectorStore:
    """Index vectoriel minimal persisté sur disque, par namespace."""

    def __init__(self, root: Path, namespace: str = "default", dim: int = 384):
        self.namespace = namespace
        self.dir = root / namespace
        self.dir.mkdir(parents=True, exist_ok=True)
        self.vectors_path = self.dir / "vectors.npy"
        self.meta_path = self.dir / "meta.jsonl"
        self.dim = dim
        self._lock = RLock()
        self._load()

    def _load(self):
        if self.vectors_path.exists():
            self._vectors = np.load(str(self.vectors_path))
            if self._vectors.shape[1] != self.dim:
                # Dimension changée (changement de modèle) → on repart à zéro
                print(f"[memory!] dim mismatch (was {self._vectors.shape[1]}, now {self.dim}). "
                      f"Reset namespace '{self.namespace}'.")
                self._vectors = np.zeros((0, self.dim), dtype=np.float32)
                self._meta: list[MemoryItem] = []
                return
        else:
            self._vectors = np.zeros((0, self.dim), dtype=np.float32)

        self._meta = []
        if self.meta_path.exists():
            for line in self.meta_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    self._meta.append(MemoryItem(**obj))
                except Exception:
                    continue

        if len(self._meta) != len(self._vectors):
            print(f"[memory!] désynchro meta({len(self._meta)}) / vectors({len(self._vectors)})."
                  f" Tronque au minimum.")
            n = min(len(self._meta), len(self._vectors))
            self._meta = self._meta[:n]
            self._vectors = self._vectors[:n]

    def _persist(self):
        np.save(str(self.vectors_path), self._vectors)
        with self.meta_path.open("w", encoding="utf-8") as f:
            for item in self._meta:
                f.write(json.dumps(item.to_dict(), ensure_ascii=False) + "\n")

    def add(
        self,
        text: str,
        vector: np.ndarray,
        source: str = "manual",
        tags: list[str] | None = None,
    ) -> MemoryItem:
        with self._lock:
            item = MemoryItem(
                id=uuid.uuid4().hex[:12],
                text=text,
                source=source,
                tags=tags or [],
                created_at=time.time(),
            )
            self._meta.append(item)
            vec = np.asarray(vector, dtype=np.float32).reshape(1, -1)
            if self._vectors.size == 0:
                self._vectors = vec
            else:
                self._vectors = np.concatenate([self._vectors, vec], axis=0)
            self._persist()
            return item

    def add_batch(
        self,
        texts: list[str],
        vectors: np.ndarray,
        source: str = "batch",
        tags: list[str] | None = None,
    ) -> int:
        if not texts or len(texts) != len(vectors):
            return 0
        with self._lock:
            items = [
                MemoryItem(
                    id=uuid.uuid4().hex[:12],
                    text=t,
                    source=source,
                    tags=list(tags or []),
                    created_at=time.time(),
                )
                for t in texts
            ]
            self._meta.extend(items)
            vecs = np.asarray(vectors, dtype=np.float32)
            if self._vectors.size == 0:
                self._vectors = vecs
            else:
                self._vectors = np.concatenate([self._vectors, vecs], axis=0)
            self._persist()
            return len(items)

    def search(
        self, query_vector: np.ndarray, top_k: int = 5, min_score: float = 0.0
    ) -> list[tuple[MemoryItem, float]]:
        with self._lock:
            if len(self._vectors) == 0:
                return []
            q = np.asarray(query_vector, dtype=np.float32).reshape(-1)
            # Vecteurs déjà normalisés en sortie d'Embedder → produit scalaire = cosinus
            scores = self._vectors @ q
            order = np.argsort(-scores)[:top_k]
            results = []
            for idx in order:
                score = float(scores[idx])
                if score < min_score:
                    break
                results.append((self._meta[idx], score))
            return results

    def delete(self, item_id: str) -> bool:
        with self._lock:
            for i, item in enumerate(self._meta):
                if item.id == item_id:
                    del self._meta[i]
                    self._vectors = np.delete(self._vectors, i, axis=0)
                    self._persist()
                    return True
            return False

    def clear(self) -> int:
        with self._lock:
            n = len(self._meta)
            self._meta = []
            self._vectors = np.zeros((0, self.dim), dtype=np.float32)
            self._persist()
            return n

    def stats(self) -> dict:
        with self._lock:
            sources: dict[str, int] = {}
            for item in self._meta:
                sources[item.source] = sources.get(item.source, 0) + 1
            return {
                "namespace": self.namespace,
                "count": len(self._meta),
                "dim": self.dim,
                "by_source": sources,
                "path": str(self.dir),
            }

    def list_items(self, limit: int = 50, source: str | None = None) -> list[dict]:
        with self._lock:
            items = self._meta if source is None else [m for m in self._meta if m.source == source]
            return [m.to_dict() for m in items[-limit:]]
