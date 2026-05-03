"""
Mode PANIC : kill switch global d'Orion.

Quand activé :
  - Tous les tools sont REFUSÉS (sauf list_*, status, audit_*)
  - Tous les workers WebSocket sont déconnectés
  - Le scheduler est arrêté
  - Notification multi-canal (audit alert + ntfy si configuré + Windows toast)
  - Persistance : data/panic.flag créé (l'état survit aux redémarrages)

Pour activer :
    POST /api/panic?token=XXX&reason=...
    OU créer manuellement data/panic.flag

Pour désactiver :
    POST /api/panic/release?token=XXX
    OU supprimer data/panic.flag

L'état est exposé dans GET /status → "panic": {...}
"""
from __future__ import annotations

import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PANIC_FLAG = ROOT / "data" / "panic.flag"

# Whitelist de tools qui RESTENT autorisés en mode panic (lecture seule, audit)
PANIC_SAFE_TOOLS = {
    "list_connected_devices",
    "list_directory",
    "read_file",
    "list_running_processes",
    "list_monitors",
    "get_system_info",
    "audit_recent",
    "audit_stats",
    "list_backups",
    "memory_recall",
    "memory_stats",
    "memory_list",
    "mouse_position",
    "termux_battery",
    "termux_location",
    "termux_clipboard_get",
}


def is_active() -> bool:
    return PANIC_FLAG.exists()


def details() -> dict:
    if not is_active():
        return {"active": False}
    try:
        data = json.loads(PANIC_FLAG.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    return {
        "active": True,
        "since": data.get("since"),
        "reason": data.get("reason", ""),
        "by_device": data.get("by_device", ""),
    }


def trigger(reason: str = "", by_device: str = "") -> dict:
    """Active le mode panic. Idempotent."""
    PANIC_FLAG.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "since": time.time(),
        "reason": (reason or "Manuel").strip()[:200],
        "by_device": by_device or "?",
    }
    PANIC_FLAG.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return {"success": True, "active": True, **payload}


def release() -> dict:
    if PANIC_FLAG.exists():
        PANIC_FLAG.unlink()
        return {"success": True, "active": False}
    return {"success": True, "active": False, "message": "déjà désactivé"}


def is_tool_allowed(tool_name: str) -> bool:
    """En mode panic, seuls les tools de la whitelist sont autorisés."""
    if not is_active():
        return True
    return tool_name in PANIC_SAFE_TOOLS
