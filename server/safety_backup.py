"""
Backup auto avant chaque action destructive sur fichier.

Avant `delete_file` ou `move_file` (qui peut écraser), on copie le fichier
source dans `data/backups/YYYY-MM-DD/HHMMSS_<basename>.bak`. L'utilisateur
peut restaurer via `restore_backup(backup_path, target?)`.

Rotation automatique : conserve N jours max (défaut 7), au-delà les vieux
dossiers sont supprimés.

Tools exposés au LLM :
    list_backups(hours, limit)      → liste les backups récents
    restore_backup(backup_path, target=None)
    purge_backups(older_than_days, confirm=False)

Désactivation : ORION_BACKUP_ENABLED=false dans .env.
"""
from __future__ import annotations

import json
import shutil
import time
from datetime import datetime, timedelta
from pathlib import Path

from branding import get_env

ROOT = Path(__file__).resolve().parent.parent
BACKUP_ROOT = ROOT / "data" / "backups"

# Taille max d'un fichier sauvegardé : au-delà on skip (ex: gros logs, vidéos)
def _max_file_size_mb() -> int:
    raw = get_env("BACKUP_MAX_MB") or "100"
    try: return max(1, int(raw))
    except ValueError: return 100


def _retention_days() -> int:
    raw = get_env("BACKUP_DAYS") or "7"
    try: return max(0, int(raw))
    except ValueError: return 7


def _enabled() -> bool:
    raw = (get_env("BACKUP_ENABLED") or "true").strip().lower()
    return raw in ("1", "true", "yes", "on", "oui")


def _today_dir() -> Path:
    return BACKUP_ROOT / datetime.now().strftime("%Y-%m-%d")


def _safe_basename(p: Path) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in p.name)[:80]


def backup_path_for(src: Path) -> Path:
    """Calcule le chemin du backup pour `src`. Crée le dossier du jour."""
    day = _today_dir()
    day.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%H%M%S_%f")[:-3]  # millisecondes
    base = _safe_basename(src)
    return day / f"{ts}_{base}.bak"


def backup_file_or_dir(src_path: str | Path) -> dict | None:
    """Sauvegarde src (fichier ou dossier) avant suppression/écrasement.

    Retourne {success, backup_path, size_kb} ou None si désactivé/skip.
    """
    if not _enabled():
        return None
    src = Path(src_path).expanduser()
    if not src.exists():
        return {"success": False, "skipped": "source inexistante"}

    # Skip si trop gros
    if src.is_file():
        size = src.stat().st_size
        if size > _max_file_size_mb() * 1024 * 1024:
            return {"success": False, "skipped": f"trop gros ({size // 1024 // 1024} MB)"}

    dest = backup_path_for(src)
    try:
        if src.is_file():
            shutil.copy2(str(src), str(dest))
            size_kb = dest.stat().st_size // 1024
        elif src.is_dir():
            # Pour un dossier, on archive en zip (sinon backup peut être très lourd)
            archive = str(dest.with_suffix(".zip"))
            shutil.make_archive(archive[:-4], "zip", root_dir=str(src.parent), base_dir=src.name)
            dest = Path(archive)
            size_kb = dest.stat().st_size // 1024
        else:
            return {"success": False, "skipped": "type non supporté"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}

    # Métadonnées légères dans data/backups/index.jsonl (1 ligne par backup)
    _append_index({
        "ts": time.time(),
        "src": str(src),
        "backup": str(dest),
        "size_kb": size_kb,
        "is_dir": src.is_dir() and not str(dest).endswith(".bak"),
    })

    # Rotation des vieux dossiers
    _rotate_old_days()
    return {"success": True, "backup_path": str(dest), "size_kb": size_kb}


def _index_path() -> Path:
    return BACKUP_ROOT / "index.jsonl"


def _append_index(entry: dict):
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    with _index_path().open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _read_index() -> list[dict]:
    p = _index_path()
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _rotate_old_days():
    days = _retention_days()
    if days <= 0:
        return
    cutoff = datetime.now() - timedelta(days=days)
    if not BACKUP_ROOT.exists():
        return
    for child in BACKUP_ROOT.iterdir():
        if not child.is_dir():
            continue
        try:
            d = datetime.strptime(child.name, "%Y-%m-%d")
        except ValueError:
            continue
        if d < cutoff:
            try:
                shutil.rmtree(str(child))
                print(f"[backup] rotation : {child.name} supprimé (>{days}j)")
            except Exception:
                pass


# ════════════════════════════════════════════════════════════════════════════
# Tools exposés au LLM
# ════════════════════════════════════════════════════════════════════════════
def list_backups(hours: float = 24.0, limit: int = 50) -> dict:
    """Liste les N derniers backups dans la fenêtre temporelle donnée."""
    since = time.time() - max(0.1, float(hours)) * 3600
    rows = [r for r in _read_index() if r.get("ts", 0) >= since]
    rows.sort(key=lambda r: r["ts"], reverse=True)
    rows = rows[: max(1, min(int(limit), 200))]
    items = []
    for r in rows:
        items.append({
            "when": datetime.fromtimestamp(r["ts"]).strftime("%Y-%m-%d %H:%M:%S"),
            "src": r.get("src"),
            "backup": r.get("backup"),
            "size_kb": r.get("size_kb"),
            "is_dir": r.get("is_dir", False),
        })
    return {
        "success": True,
        "count": len(items),
        "window_hours": hours,
        "items": items,
        "retention_days": _retention_days(),
        "enabled": _enabled(),
    }


def restore_backup(backup_path: str, target: str | None = None,
                   overwrite: bool = False) -> dict:
    """Restaure un backup. Sans `target`, restaure à l'emplacement original.
    Refuse si la cible existe déjà sauf overwrite=True (qui crée un nouveau backup)."""
    bp = Path(backup_path).expanduser()
    if not bp.exists():
        return {"success": False, "error": f"Backup introuvable : {bp}"}
    # Trouve le src d'origine via l'index si pas de target
    if not target:
        for r in _read_index():
            if r.get("backup") == str(bp):
                target = r.get("src")
                break
        if not target:
            return {"success": False, "error": "Cible inconnue (pas dans l'index). Précise target=..."}
    dst = Path(target).expanduser()
    if dst.exists():
        if not overwrite:
            return {"success": False, "error": f"Cible existe déjà : {dst}. Passe overwrite=true."}
        # Backup de la cible actuelle avant overwrite (sécurité)
        backup_file_or_dir(str(dst))
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        if str(bp).endswith(".zip"):
            shutil.unpack_archive(str(bp), extract_dir=str(dst.parent))
        else:
            shutil.copy2(str(bp), str(dst))
    except Exception as exc:
        return {"success": False, "error": str(exc)}
    return {"success": True, "restored_to": str(dst), "from": str(bp)}


def purge_backups(older_than_days: int = 30, confirm: bool = False) -> dict:
    """Supprime les backups plus vieux que N jours. Demande confirm=True."""
    if not confirm:
        return {"success": False, "error": "Passe confirm=true pour exécuter."}
    cutoff = datetime.now() - timedelta(days=int(older_than_days))
    deleted = 0
    if BACKUP_ROOT.exists():
        for child in BACKUP_ROOT.iterdir():
            if not child.is_dir():
                continue
            try:
                d = datetime.strptime(child.name, "%Y-%m-%d")
            except ValueError:
                continue
            if d < cutoff:
                try:
                    shutil.rmtree(str(child))
                    deleted += 1
                except Exception:
                    pass
    return {"success": True, "deleted_days": deleted, "older_than_days": older_than_days}


HANDLERS = {
    "list_backups":   lambda p: list_backups(**p),
    "restore_backup": lambda p: restore_backup(**p),
    "purge_backups":  lambda p: purge_backups(**p),
}
