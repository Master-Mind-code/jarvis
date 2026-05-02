"""
Orion Tool — File Manager
Créer, lire, modifier, supprimer des fichiers et dossiers.
"""
import os
import shutil
from pathlib import Path


BLOCKED_PATHS = ["/etc/passwd", "/etc/shadow", "/boot", "/sys", "/proc"]


def _is_safe_path(path: str) -> bool:
    resolved = str(Path(path).resolve())
    for blocked in BLOCKED_PATHS:
        if resolved.startswith(blocked):
            return False
    return True


def create_file(path: str, content: str = "", overwrite: bool = False) -> dict:
    if not _is_safe_path(path):
        return {"success": False, "error": "Chemin interdit."}
    p = Path(path)
    if p.exists() and not overwrite:
        return {"success": False, "error": f"Le fichier existe déjà : {path}. Passe overwrite=true pour écraser."}
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return {"success": True, "message": f"Fichier créé : {path} ({len(content)} caractères)"}


def read_file(path: str, max_chars: int = 8000) -> dict:
    if not _is_safe_path(path):
        return {"success": False, "error": "Chemin interdit."}
    p = Path(path)
    if not p.exists():
        return {"success": False, "error": f"Fichier introuvable : {path}"}
    try:
        content = p.read_text(encoding="utf-8", errors="replace")
        truncated = len(content) > max_chars
        return {
            "success": True,
            "content": content[:max_chars],
            "truncated": truncated,
            "size": p.stat().st_size,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def list_directory(path: str = ".", show_hidden: bool = False) -> dict:
    if not _is_safe_path(path):
        return {"success": False, "error": "Chemin interdit."}
    p = Path(path)
    if not p.exists():
        return {"success": False, "error": f"Dossier introuvable : {path}"}
    items = []
    for item in sorted(p.iterdir()):
        if not show_hidden and item.name.startswith("."):
            continue
        items.append({
            "name": item.name,
            "type": "dossier" if item.is_dir() else "fichier",
            "size": item.stat().st_size if item.is_file() else None,
        })
    return {"success": True, "path": str(p.resolve()), "items": items, "count": len(items)}


def delete_file(path: str) -> dict:
    if not _is_safe_path(path):
        return {"success": False, "error": "Chemin interdit."}
    p = Path(path)
    if not p.exists():
        return {"success": False, "error": f"Introuvable : {path}"}
    if p.is_dir():
        shutil.rmtree(p)
        return {"success": True, "message": f"Dossier supprimé : {path}"}
    else:
        p.unlink()
        return {"success": True, "message": f"Fichier supprimé : {path}"}


def create_directory(path: str) -> dict:
    if not _is_safe_path(path):
        return {"success": False, "error": "Chemin interdit."}
    Path(path).mkdir(parents=True, exist_ok=True)
    return {"success": True, "message": f"Dossier créé : {path}"}


def move_file(src: str, dst: str) -> dict:
    if not _is_safe_path(src) or not _is_safe_path(dst):
        return {"success": False, "error": "Chemin interdit."}
    shutil.move(src, dst)
    return {"success": True, "message": f"Déplacé : {src} → {dst}"}


# Mapping nom → fonction (utilisé par l'orchestrateur)
HANDLERS = {
    "create_file": lambda p: create_file(**p),
    "read_file": lambda p: read_file(**p),
    "list_directory": lambda p: list_directory(**p),
    "delete_file": lambda p: delete_file(**p),
    "create_directory": lambda p: create_directory(**p),
    "move_file": lambda p: move_file(**p),
}
