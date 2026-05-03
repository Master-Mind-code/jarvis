"""
Tool LLM pour interroger l'audit log d'Orion.

Usages :
    "Qu'est-ce que tu as fait dans la dernière heure ?"
    "Liste les actions sensibles d'aujourd'hui"
    "Y a-t-il eu des erreurs récemment ?"
"""
from __future__ import annotations

import time
from datetime import datetime

from server import audit


def audit_recent(
    limit: int = 20,
    hours: float = 24.0,
    sensitive_only: bool = False,
    failed_only: bool = False,
) -> dict:
    """Liste les N dernières actions exécutées par Orion.

    hours : fenêtre temporelle (24 = les dernières 24h, 0.5 = 30 dernières min)
    """
    limit = max(1, min(int(limit or 20), 100))
    since = time.time() - max(0.1, float(hours)) * 3600
    rows = audit.get_recent(
        limit=limit,
        sensitive_only=bool(sensitive_only),
        failed_only=bool(failed_only),
        since_ts=since,
    )
    items = []
    for r in rows:
        ts = datetime.fromtimestamp(r["ts"]).strftime("%Y-%m-%d %H:%M:%S")
        items.append({
            "when": ts,
            "device": r["device_id"],
            "tool": r["tool_name"],
            "input": r["input_preview"],
            "target": r["target"] or "server",
            "success": bool(r["success"]),
            "error": r["error"] or None,
            "duration_ms": r["duration_ms"],
            "sensitive": bool(r["sensitive"]),
            "confirmed": bool(r["confirmed"]),
        })
    return {
        "success": True,
        "count": len(items),
        "window_hours": hours,
        "filters": {
            "sensitive_only": bool(sensitive_only),
            "failed_only": bool(failed_only),
        },
        "items": items,
    }


def audit_stats(hours: float = 24.0) -> dict:
    """Stats agrégées de l'audit log sur les dernières N heures."""
    since = time.time() - max(0.1, float(hours)) * 3600
    s = audit.get_stats(since_ts=since)
    s["db_size_kb"] = audit.db_size_kb()
    return s


HANDLERS = {
    "audit_recent": lambda p: audit_recent(**p),
    "audit_stats":  lambda p: audit_stats(**p),
}
