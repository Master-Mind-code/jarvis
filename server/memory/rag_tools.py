"""
Tools RAG exposés au LLM Orion.

  memory_remember     : ajoute un fait/note à la mémoire long terme
  memory_recall       : recherche les souvenirs pertinents pour une query
  memory_forget       : supprime un souvenir par id
  memory_clear        : vide un namespace (avec confirm)
  memory_stats        : compteurs par namespace
  memory_list         : liste les N derniers souvenirs
  memory_index_file   : indexe le contenu d'un fichier (PDF/DOCX/TXT/MD)
  memory_index_dir    : indexe récursivement un dossier (avec extensions filtrables)
"""
from __future__ import annotations

import os
from pathlib import Path

from .embedder import get_embedder
from .vector_store import VectorStore

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DIR = ROOT / "data" / "memory"

_stores: dict[str, VectorStore] = {}


def _store(namespace: str = "default") -> VectorStore:
    if namespace not in _stores:
        embedder = get_embedder()
        _stores[namespace] = VectorStore(DEFAULT_DIR, namespace=namespace, dim=embedder.dim)
    return _stores[namespace]


# ─── Chunking texte ──────────────────────────────────────────────────────
def _chunk_text(text: str, target_chars: int = 800, overlap: int = 100) -> list[str]:
    """Découpe naïve en chunks de ~target_chars avec overlap, en respectant les
    frontières de paragraphe."""
    text = (text or "").strip()
    if len(text) <= target_chars:
        return [text] if text else []

    chunks: list[str] = []
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    buf = ""
    for para in paragraphs:
        if len(buf) + len(para) + 2 <= target_chars:
            buf = (buf + "\n\n" + para).strip()
        else:
            if buf:
                chunks.append(buf)
            if len(para) > target_chars:
                # Para trop long : on coupe brutalement
                for i in range(0, len(para), target_chars - overlap):
                    chunks.append(para[i:i + target_chars])
                buf = ""
            else:
                buf = para
    if buf:
        chunks.append(buf)
    return chunks


# ─── Tools ──────────────────────────────────────────────────────────────
def memory_remember(text: str, source: str = "manual", tags: list[str] | None = None,
                    namespace: str = "default") -> dict:
    """Ajoute un souvenir court (1 entrée). Pour des fichiers, utilise memory_index_file."""
    text = (text or "").strip()
    if not text:
        return {"success": False, "error": "text vide"}
    try:
        embedder = get_embedder()
        vec = embedder.embed_one(text)
        item = _store(namespace).add(text, vec, source=source, tags=tags or [])
    except ImportError as exc:
        return {"success": False, "error": str(exc)}
    except Exception as exc:
        return {"success": False, "error": f"{type(exc).__name__}: {exc}"}
    return {"success": True, "id": item.id, "namespace": namespace, "stored_chars": len(text)}


def memory_recall(query: str, top_k: int = 5, min_score: float = 0.25,
                  namespace: str = "default") -> dict:
    """Cherche les souvenirs les plus proches d'une query. Score = cosinus [0..1]."""
    query = (query or "").strip()
    if not query:
        return {"success": False, "error": "query vide"}
    top_k = max(1, min(int(top_k or 5), 20))
    try:
        embedder = get_embedder()
        q = embedder.embed_one(query)
        results = _store(namespace).search(q, top_k=top_k, min_score=float(min_score))
    except ImportError as exc:
        return {"success": False, "error": str(exc)}
    except Exception as exc:
        return {"success": False, "error": f"{type(exc).__name__}: {exc}"}
    return {
        "success": True,
        "query": query,
        "namespace": namespace,
        "count": len(results),
        "results": [
            {"id": item.id, "score": round(score, 3), "text": item.text,
             "source": item.source, "tags": item.tags}
            for item, score in results
        ],
    }


def memory_forget(item_id: str, namespace: str = "default") -> dict:
    item_id = (item_id or "").strip()
    if not item_id:
        return {"success": False, "error": "item_id requis"}
    try:
        ok = _store(namespace).delete(item_id)
    except Exception as exc:
        return {"success": False, "error": str(exc)}
    return {"success": ok, "deleted": ok, "id": item_id, "namespace": namespace}


def memory_clear(namespace: str = "default", confirm: bool = False) -> dict:
    if not confirm:
        return {"success": False, "error": "Passe confirm=true pour vider le namespace"}
    try:
        n = _store(namespace).clear()
    except Exception as exc:
        return {"success": False, "error": str(exc)}
    return {"success": True, "deleted": n, "namespace": namespace}


def memory_stats(namespace: str | None = None) -> dict:
    if namespace:
        try:
            return {"success": True, **_store(namespace).stats()}
        except Exception as exc:
            return {"success": False, "error": str(exc)}
    # Toutes les namespaces sur disque
    if not DEFAULT_DIR.exists():
        return {"success": True, "namespaces": []}
    namespaces = []
    for child in DEFAULT_DIR.iterdir():
        if child.is_dir() and (child / "vectors.npy").exists():
            try:
                namespaces.append(_store(child.name).stats())
            except Exception:
                pass
    return {"success": True, "namespaces": namespaces}


def memory_list(namespace: str = "default", limit: int = 50, source: str | None = None) -> dict:
    try:
        items = _store(namespace).list_items(limit=int(limit), source=source)
    except Exception as exc:
        return {"success": False, "error": str(exc)}
    return {"success": True, "namespace": namespace, "count": len(items), "items": items}


# ─── Indexation de fichiers ─────────────────────────────────────────────
def _read_file_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError:
            return ""
        try:
            reader = PdfReader(str(path))
            return "\n\n".join((p.extract_text() or "") for p in reader.pages)
        except Exception:
            return ""
    if suffix in (".docx",):
        try:
            from docx import Document  # type: ignore[import-not-found]
        except ImportError:
            return ""
        try:
            doc = Document(str(path))
            return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
        except Exception:
            return ""
    # Texte brut
    if suffix in (".txt", ".md", ".markdown", ".log", ".csv", ".json", ".yml", ".yaml",
                  ".py", ".js", ".ts", ".html", ".css", ".rst"):
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return ""
    return ""


def memory_index_file(path: str, namespace: str = "default", tags: list[str] | None = None,
                      chunk_chars: int = 800) -> dict:
    p = Path(path).expanduser()
    if not p.exists() or not p.is_file():
        return {"success": False, "error": f"Fichier introuvable : {p}"}

    text = _read_file_text(p)
    if not text.strip():
        return {"success": False, "error": f"Aucun texte extrait de {p.name} (format non supporté ou PDF scanné)"}

    chunks = _chunk_text(text, target_chars=int(chunk_chars))
    if not chunks:
        return {"success": False, "error": "Texte vide après chunking"}

    try:
        embedder = get_embedder()
        vectors = embedder.embed(chunks)
        n = _store(namespace).add_batch(
            chunks, vectors, source=str(p), tags=tags or [],
        )
    except ImportError as exc:
        return {"success": False, "error": str(exc)}
    except Exception as exc:
        return {"success": False, "error": f"{type(exc).__name__}: {exc}"}

    return {
        "success": True,
        "path": str(p),
        "namespace": namespace,
        "chunks_added": n,
        "total_chars": len(text),
    }


def memory_index_dir(path: str, namespace: str = "default", extensions: list[str] | None = None,
                     recursive: bool = True, max_files: int = 100) -> dict:
    d = Path(path).expanduser()
    if not d.exists() or not d.is_dir():
        return {"success": False, "error": f"Dossier introuvable : {d}"}

    exts = set(e.lower().lstrip(".") for e in (extensions or
        ["pdf", "docx", "txt", "md", "markdown", "py", "js", "ts", "json", "yml", "yaml"]))
    files = []
    iterator = d.rglob("*") if recursive else d.glob("*")
    for f in iterator:
        if f.is_file() and f.suffix.lower().lstrip(".") in exts:
            files.append(f)
            if len(files) >= int(max_files):
                break

    if not files:
        return {"success": False, "error": f"Aucun fichier matchant trouvé dans {d}"}

    indexed = 0
    chunks_total = 0
    failures = []
    for f in files:
        result = memory_index_file(str(f), namespace=namespace)
        if result.get("success"):
            indexed += 1
            chunks_total += result.get("chunks_added", 0)
        else:
            failures.append({"path": str(f), "error": result.get("error", "")})

    return {
        "success": True,
        "directory": str(d),
        "namespace": namespace,
        "files_indexed": indexed,
        "chunks_added": chunks_total,
        "files_failed": len(failures),
        "failures": failures[:5],  # top 5 only
    }


HANDLERS = {
    "memory_remember":    lambda p: memory_remember(**p),
    "memory_recall":      lambda p: memory_recall(**p),
    "memory_forget":      lambda p: memory_forget(**p),
    "memory_clear":       lambda p: memory_clear(**p),
    "memory_stats":       lambda p: memory_stats(**p),
    "memory_list":        lambda p: memory_list(**p),
    "memory_index_file":  lambda p: memory_index_file(**p),
    "memory_index_dir":   lambda p: memory_index_dir(**p),
}
