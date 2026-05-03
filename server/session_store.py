"""
Persistance de l'historique de chat par device_id (SQLite).

Évite la perte d'historique au redémarrage du serveur. Format pivot Anthropic
sérialisé en JSON. Stocké dans data/sessions.db.

API :
    load_history(device_id)        → list[dict]
    save_history(device_id, hist)  → None
    clear_history(device_id)       → None
    list_devices()                 → list[(device_id, n_messages, last_seen)]
    truncate_history(device_id, max_messages=50) → None  (garde les N derniers)

Le serveur appelle :
  - load_history() au connect d'un nouveau controller
  - save_history() après chaque tour conversationnel
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from threading import RLock

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "sessions.db"

_lock = RLock()
_conn: sqlite3.Connection | None = None


def _connect() -> sqlite3.Connection:
    global _conn
    if _conn is not None:
        return _conn
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            device_id TEXT PRIMARY KEY,
            history   TEXT NOT NULL,           -- JSON serialized list
            updated_at REAL NOT NULL
        )
    """)
    _conn = conn
    return conn


def load_history(device_id: str) -> list:
    if not device_id:
        return []
    with _lock:
        conn = _connect()
        row = conn.execute(
            "SELECT history FROM sessions WHERE device_id = ?", (device_id,)
        ).fetchone()
    if not row:
        return []
    try:
        return json.loads(row[0])
    except json.JSONDecodeError:
        return []


def save_history(device_id: str, history: list) -> None:
    if not device_id:
        return
    payload = json.dumps(history, ensure_ascii=False, default=_json_default)
    with _lock:
        conn = _connect()
        conn.execute(
            "INSERT OR REPLACE INTO sessions (device_id, history, updated_at) VALUES (?, ?, ?)",
            (device_id, payload, time.time()),
        )


def clear_history(device_id: str) -> None:
    if not device_id:
        return
    with _lock:
        conn = _connect()
        conn.execute("DELETE FROM sessions WHERE device_id = ?", (device_id,))


def list_devices() -> list[tuple[str, int, float]]:
    """Retourne [(device_id, n_messages, last_seen_epoch), ...]"""
    with _lock:
        conn = _connect()
        rows = conn.execute(
            "SELECT device_id, history, updated_at FROM sessions ORDER BY updated_at DESC"
        ).fetchall()
    out = []
    for did, hist_json, ts in rows:
        try:
            n = len(json.loads(hist_json))
        except json.JSONDecodeError:
            n = 0
        out.append((did, n, ts))
    return out


def truncate_history(device_id: str, max_messages: int = 50) -> None:
    """Garde uniquement les N derniers messages (utile pour limiter la taille)."""
    history = load_history(device_id)
    if len(history) <= max_messages:
        return
    save_history(device_id, history[-max_messages:])


def _json_default(o):
    """Sérialise les objets exotiques (objets SDK, etc.) en chaînes."""
    if hasattr(o, "to_dict"):
        return o.to_dict()
    if hasattr(o, "__dict__"):
        return {k: v for k, v in o.__dict__.items() if not k.startswith("_")}
    return str(o)


def db_stats() -> dict:
    """Diagnostic : taille fichier, nombre de sessions."""
    if not DB_PATH.exists():
        return {"exists": False, "path": str(DB_PATH)}
    size = DB_PATH.stat().st_size
    devices = list_devices()
    return {
        "exists": True,
        "path": str(DB_PATH),
        "size_kb": size // 1024,
        "device_count": len(devices),
        "total_messages": sum(d[1] for d in devices),
    }
