"""
Rate limiter pour Orion : limite le nombre d'actions sensibles par device
sur une fenêtre glissante.

Configuration :
    ORION_RATE_LIMIT_PER_MIN=10       (max 10 tools sensibles / min / device)
    ORION_RATE_LIMIT_WINDOW_SEC=60    (fenêtre)
    ORION_RATE_LIMIT_BURST=3          (max 3 tools sensibles dans une rafale de 5s)
    ORION_RATE_LIMIT_BURST_WINDOW=5

Pas de rate limit sur les tools de lecture ou les tools internes (memory_recall,
list_*, audit_recent, etc.). Seulement sur ce qui est marqué `sensitive`
(= la même liste que confirm.requires_confirmation).
"""
from __future__ import annotations

import time
from collections import deque
from threading import RLock

from branding import get_env


def _max_per_window() -> int:
    raw = get_env("RATE_LIMIT_PER_MIN") or "10"
    try: return max(1, int(raw))
    except ValueError: return 10


def _window_sec() -> int:
    raw = get_env("RATE_LIMIT_WINDOW_SEC") or "60"
    try: return max(5, int(raw))
    except ValueError: return 60


def _burst_max() -> int:
    raw = get_env("RATE_LIMIT_BURST") or "3"
    try: return max(1, int(raw))
    except ValueError: return 3


def _burst_window() -> int:
    raw = get_env("RATE_LIMIT_BURST_WINDOW") or "5"
    try: return max(1, int(raw))
    except ValueError: return 5


def _enabled() -> bool:
    raw = (get_env("RATE_LIMIT_ENABLED") or "true").strip().lower()
    return raw in ("1", "true", "yes", "on", "oui")


_lock = RLock()
# device_id → deque[float] (timestamps des appels sensibles)
_history: dict[str, deque[float]] = {}


def check_and_record(device_id: str) -> tuple[bool, str]:
    """Renvoie (autorisé, raison_si_refusé). Enregistre le timestamp si autorisé."""
    if not _enabled() or not device_id:
        return True, ""
    now = time.time()
    win = _window_sec()
    burst_win = _burst_window()
    max_win = _max_per_window()
    max_burst = _burst_max()

    with _lock:
        dq = _history.setdefault(device_id, deque())
        # Purge des timestamps trop vieux
        while dq and now - dq[0] > win:
            dq.popleft()

        # Check rafale
        burst_count = sum(1 for ts in dq if now - ts <= burst_win)
        if burst_count >= max_burst:
            return False, (
                f"Rate limit RAFALE : {burst_count} action(s) sensible(s) "
                f"dans les {burst_win}s (max {max_burst}). Ralentis."
            )

        # Check fenêtre longue
        if len(dq) >= max_win:
            oldest = dq[0]
            wait = int(win - (now - oldest))
            return False, (
                f"Rate limit : {len(dq)} action(s) sensible(s) dans les "
                f"{win}s (max {max_win}). Réessaie dans {wait}s."
            )

        dq.append(now)
        return True, ""


def reset(device_id: str | None = None):
    """Reset le compteur pour un device, ou tous (None)."""
    with _lock:
        if device_id is None:
            _history.clear()
        else:
            _history.pop(device_id, None)


def status() -> dict:
    with _lock:
        return {
            "enabled": _enabled(),
            "max_per_window": _max_per_window(),
            "window_sec": _window_sec(),
            "burst_max": _burst_max(),
            "burst_window_sec": _burst_window(),
            "tracked_devices": list(_history.keys()),
            "current_counts": {d: len(q) for d, q in _history.items()},
        }
