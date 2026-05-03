"""
Audit log Orion : trace chaque exécution de tool dans SQLite.

Stocke : timestamp, device_id, tool_name, preview des args, success, error,
         durée, si la confirmation par mot de passe a été requise/passée.

Permet à l'utilisateur de demander : "Qu'est-ce qui s'est passé pendant la nuit ?"
ou "Liste les actions sensibles des dernières 24h" (via le tool audit_recent).

Stockage : data/audit.db (séparé de sessions.db pour pouvoir purger
indépendamment).
"""
from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from threading import RLock

from branding import get_env

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "audit.db"

_lock = RLock()
_conn: sqlite3.Connection | None = None

# Configuration
def _max_rows() -> int:
    raw = get_env("AUDIT_MAX_ROWS") or "10000"
    try: return max(100, int(raw))
    except ValueError: return 10000


def _enabled() -> bool:
    raw = (get_env("AUDIT_ENABLED") or "true").strip().lower()
    return raw in ("1", "true", "yes", "on", "oui")


def _connect() -> sqlite3.Connection:
    global _conn
    if _conn is not None:
        return _conn
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            ts           REAL NOT NULL,
            device_id    TEXT NOT NULL,
            tool_name    TEXT NOT NULL,
            input_preview TEXT,
            target       TEXT,                  -- target_device si exécution distante
            success      INTEGER NOT NULL,      -- 0/1
            error        TEXT,
            duration_ms  INTEGER NOT NULL DEFAULT 0,
            sensitive    INTEGER NOT NULL DEFAULT 0,  -- 1 si tool dangereux (gating actif)
            confirmed    INTEGER NOT NULL DEFAULT 0   -- 1 si validé via password modal
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log(ts DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_device ON audit_log(device_id, ts DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_sensitive ON audit_log(sensitive, ts DESC)")
    _conn = conn
    return conn


def _truncate_input(tool_input: dict | None, max_chars: int = 400) -> str:
    if not tool_input:
        return ""
    try:
        s = json.dumps(tool_input, ensure_ascii=False)
    except Exception:
        s = str(tool_input)
    return s[:max_chars] + ("…" if len(s) > max_chars else "")


def log_tool_call(
    device_id: str,
    tool_name: str,
    tool_input: dict | None,
    success: bool,
    error: str = "",
    duration_ms: int = 0,
    target: str | None = None,
    sensitive: bool = False,
    confirmed: bool = False,
) -> int | None:
    """Enregistre un appel de tool. Retourne l'id de la ligne ou None si désactivé."""
    if not _enabled():
        return None
    try:
        with _lock:
            conn = _connect()
            cur = conn.execute(
                """INSERT INTO audit_log
                   (ts, device_id, tool_name, input_preview, target, success, error,
                    duration_ms, sensitive, confirmed)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    time.time(),
                    device_id or "?",
                    tool_name,
                    _truncate_input(tool_input),
                    target or "",
                    1 if success else 0,
                    (error or "")[:300],
                    int(duration_ms),
                    1 if sensitive else 0,
                    1 if confirmed else 0,
                ),
            )
            row_id = cur.lastrowid
            # Purge si dépassé
            _purge_if_needed(conn)
            return row_id
    except Exception as exc:
        print(f"[audit!] {exc}")
        return None


def _purge_if_needed(conn: sqlite3.Connection):
    max_rows = _max_rows()
    count = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
    if count > max_rows:
        # Garde les max_rows plus récents, supprime les autres
        conn.execute(
            "DELETE FROM audit_log WHERE id IN (SELECT id FROM audit_log ORDER BY ts ASC LIMIT ?)",
            (count - max_rows,),
        )


def get_recent(
    limit: int = 50,
    sensitive_only: bool = False,
    failed_only: bool = False,
    device_id: str | None = None,
    since_ts: float | None = None,
) -> list[dict]:
    """Récupère les N derniers événements (filtrables)."""
    if not _enabled():
        return []
    where = []
    params: list = []
    if sensitive_only:
        where.append("sensitive = 1")
    if failed_only:
        where.append("success = 0")
    if device_id:
        where.append("device_id = ?")
        params.append(device_id)
    if since_ts:
        where.append("ts >= ?")
        params.append(float(since_ts))
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    sql = f"""
        SELECT id, ts, device_id, tool_name, input_preview, target, success, error,
               duration_ms, sensitive, confirmed
        FROM audit_log
        {where_sql}
        ORDER BY ts DESC
        LIMIT ?
    """
    params.append(int(limit))
    with _lock:
        conn = _connect()
        rows = conn.execute(sql, params).fetchall()
    cols = ["id","ts","device_id","tool_name","input_preview","target","success",
            "error","duration_ms","sensitive","confirmed"]
    return [dict(zip(cols, r)) for r in rows]


def get_stats(since_ts: float | None = None) -> dict:
    """Stats agrégées : nombre de tools, succès, échecs, sensibles."""
    if not _enabled():
        return {"enabled": False}
    where = "WHERE ts >= ?" if since_ts else ""
    params = [since_ts] if since_ts else []
    with _lock:
        conn = _connect()
        total = conn.execute(f"SELECT COUNT(*) FROM audit_log {where}", params).fetchone()[0]
        ok    = conn.execute(f"SELECT COUNT(*) FROM audit_log {where} {'AND' if where else 'WHERE'} success=1",
                             params).fetchone()[0]
        sens  = conn.execute(f"SELECT COUNT(*) FROM audit_log {where} {'AND' if where else 'WHERE'} sensitive=1",
                             params).fetchone()[0]
        # Top 5 tools
        top = conn.execute(
            f"""SELECT tool_name, COUNT(*) c FROM audit_log {where}
                GROUP BY tool_name ORDER BY c DESC LIMIT 5""",
            params,
        ).fetchall()
    return {
        "enabled": True,
        "total": total,
        "success": ok,
        "failed": total - ok,
        "sensitive": sens,
        "top_tools": [{"tool": t, "count": c} for t, c in top],
        "since_ts": since_ts,
    }


def db_size_kb() -> int:
    if not DB_PATH.exists():
        return 0
    return DB_PATH.stat().st_size // 1024


# ════════════════════════════════════════════════════════════════════════════
# Hook pour notifications push (set par main.py au démarrage)
# ════════════════════════════════════════════════════════════════════════════
_alert_hook = None


def set_alert_hook(cb):
    """Installe un callback appelé après chaque tool sensible :
       cb(audit_row: dict) → None (best-effort, non bloquant)"""
    global _alert_hook
    _alert_hook = cb


def _trigger_alert(row_id: int | None, sensitive: bool, **fields):
    if not sensitive or _alert_hook is None or row_id is None:
        return
    try:
        _alert_hook({"id": row_id, **fields})
    except Exception as exc:
        print(f"[audit-alert!] {exc}")
