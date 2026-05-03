"""
Couche de confirmation par mot de passe pour les actions dangereuses d'Orion.

Usage côté orchestrator (sync) :
    from server.confirm import requires_confirmation, request_confirmation

    if requires_confirmation(tool_name, tool_input):
        ok = request_confirmation(device_id, tool_name, tool_input,
                                   reason="suppression de fichier")
        if not ok:
            return {"success": False, "error": "Confirmation refusée"}

Côté serveur main.py, brancher :
  - on_confirm_request_callback : appelé pour push le request au client WS
  - on incoming "confirm_response" message : appeler resolve(request_id, password)

Le mot de passe est lu depuis ORION_CONFIRM_PASSWORD (env). Si non défini,
fallback sur ORION_SECRET_TOKEN — moins propre mais évite de bloquer.

Cache : si ORION_CONFIRM_CACHE_SEC > 0, une confirmation réussie évite de
redemander pour le même device pendant ce délai. Désactivé par défaut (= 0).
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from concurrent.futures import Future
from dataclasses import dataclass, field

from branding import get_env

# ════════════════════════════════════════════════════════════════════════════
# Liste des tools nécessitant une confirmation
# ════════════════════════════════════════════════════════════════════════════
# raison brève → affichée à l'utilisateur dans le modal
DEFAULT_DANGEROUS: dict[str, str] = {
    # Destruction / écriture critique
    "delete_file":       "suppression de fichier ou dossier",
    "move_file":         "déplacement / écrasement de fichier",
    "create_file":       "écriture de fichier",
    "create_directory":  "création de dossier",
    # Exécution arbitraire de code
    "run_shell_command": "exécution d'une commande shell",
    "run_python_script": "exécution d'un script Python",
    # Contrôle souris/clavier
    "mouse_click":       "click de souris automatisé",
    "keyboard_type":     "frappe clavier automatisée",
    "keyboard_press":    "appui sur une combinaison de touches",
    # Mémoire long terme : effacement
    "memory_clear":      "effacement complet de la mémoire long terme",
    "memory_forget":     "suppression d'un souvenir",
    # Communications externes
    "termux_send_sms":   "envoi de SMS depuis le téléphone",
    "termux_call":       "appel téléphonique",
    "calendar_create_event": "création d'un événement Google Calendar",
    # Gmail : lecture nécessite déjà OAuth, mais on confirme la lecture
    # de contenu d'email (potentiellement sensible)
    "gmail_read_message": "lecture du contenu d'un email",
}


def _load_dangerous_set() -> dict[str, str]:
    """Permet d'override la liste via ORION_CONFIRM_TOOLS (CSV)."""
    override = (get_env("CONFIRM_TOOLS") or "").strip()
    if not override:
        return DEFAULT_DANGEROUS.copy()
    if override.lower() in ("none", "false", "off", "0"):
        return {}
    out: dict[str, str] = {}
    for tok in override.split(","):
        name = tok.strip()
        if name:
            out[name] = DEFAULT_DANGEROUS.get(name, "action sensible")
    return out


def _enabled() -> bool:
    """Confirmation activée si ORION_CONFIRM_PASSWORD est défini ET pas vide."""
    raw = get_env("CONFIRM_PASSWORD")
    return bool(raw and raw.strip())


def _expected_password() -> str:
    """Mot de passe attendu : ORION_CONFIRM_PASSWORD (sinon SECRET_TOKEN en fallback)."""
    return (
        (get_env("CONFIRM_PASSWORD") or "").strip()
        or (get_env("SECRET_TOKEN") or "").strip()
    )


def _cache_seconds() -> int:
    raw = get_env("CONFIRM_CACHE_SEC") or "0"
    try:
        return max(0, int(raw))
    except ValueError:
        return 0


def _timeout_seconds() -> int:
    raw = get_env("CONFIRM_TIMEOUT_SEC") or "120"
    try:
        return max(10, int(raw))
    except ValueError:
        return 120


# Run-time : peut être surchargé via env
_DANGEROUS = _load_dangerous_set()


def requires_confirmation(tool_name: str, tool_input: dict | None = None) -> bool:
    """True si ce tool doit déclencher une demande de confirmation."""
    if not _enabled():
        return False
    return tool_name in _DANGEROUS


def reason_for(tool_name: str) -> str:
    return _DANGEROUS.get(tool_name, "action sensible")


# ════════════════════════════════════════════════════════════════════════════
# Registry des demandes en attente + cache de confirmations
# ════════════════════════════════════════════════════════════════════════════
@dataclass
class _PendingRequest:
    request_id: str
    device_id: str
    tool_name: str
    tool_input: dict
    reason: str
    future: Future = field(default_factory=Future)
    created_at: float = field(default_factory=time.time)


_lock = threading.RLock()
_pending: dict[str, _PendingRequest] = {}
_recent_ok: dict[str, float] = {}  # device_id → timestamp dernière conf OK


def _is_cached(device_id: str) -> bool:
    cache_sec = _cache_seconds()
    if cache_sec <= 0:
        return False
    ts = _recent_ok.get(device_id)
    if ts is None:
        return False
    if time.time() - ts > cache_sec:
        _recent_ok.pop(device_id, None)
        return False
    return True


# Callback que main.py installe pour push les requêtes au client WS
_push_callback = None


def set_push_callback(cb):
    """Installe le callback qui pousse {confirm_request} au client WebSocket.

    Signature : cb(device_id: str, payload: dict) -> bool (False si client absent)
    """
    global _push_callback
    _push_callback = cb


def request_confirmation(
    device_id: str,
    tool_name: str,
    tool_input: dict,
    reason: str | None = None,
) -> bool:
    """Bloque jusqu'à ce que l'utilisateur confirme (ou timeout / refus).

    Retourne True si confirmation OK, False sinon. Threadsafe (peut être
    appelé depuis un thread executor de FastAPI).
    """
    if not _enabled():
        return True  # Pas de password configuré → pas de gating
    if _is_cached(device_id):
        return True
    if _push_callback is None:
        # Pas de canal pour demander → on refuse par sécurité
        print(f"[confirm!] Pas de WS canal pour {device_id}, refus auto.")
        return False

    req_id = uuid.uuid4().hex[:16]
    pending = _PendingRequest(
        request_id=req_id,
        device_id=device_id,
        tool_name=tool_name,
        tool_input=tool_input,
        reason=reason or reason_for(tool_name),
    )
    with _lock:
        _pending[req_id] = pending

    payload = {
        "type": "confirm_request",
        "request_id": req_id,
        "tool": tool_name,
        # On expose une preview des inputs SANS exposer leur intégralité
        # (limite à 300 chars pour éviter d'afficher du contenu énorme)
        "input_preview": _preview_input(tool_input),
        "reason": pending.reason,
        "timeout_sec": _timeout_seconds(),
    }
    delivered = _push_callback(device_id, payload)
    if not delivered:
        # Client pas joignable
        with _lock:
            _pending.pop(req_id, None)
        print(f"[confirm!] Client '{device_id}' non joignable → refus.")
        return False

    try:
        approved = pending.future.result(timeout=_timeout_seconds())
    except Exception:
        approved = False
    with _lock:
        _pending.pop(req_id, None)

    if approved:
        _recent_ok[device_id] = time.time()
    return bool(approved)


def resolve(request_id: str, password: str) -> dict:
    """Appelé par le serveur quand l'UI répond. Retourne {accepted, error?}."""
    with _lock:
        pending = _pending.get(request_id)
    if pending is None:
        return {"accepted": False, "error": "Requête inconnue ou déjà traitée."}

    expected = _expected_password()
    accepted = bool(password and expected and password.strip() == expected)
    if not pending.future.done():
        pending.future.set_result(accepted)
    if accepted:
        return {"accepted": True}
    return {"accepted": False, "error": "Mot de passe incorrect."}


def deny(request_id: str) -> dict:
    """Refus explicite par l'utilisateur (bouton 'Annuler')."""
    with _lock:
        pending = _pending.get(request_id)
    if pending is None:
        return {"accepted": False, "error": "Requête inconnue."}
    if not pending.future.done():
        pending.future.set_result(False)
    return {"accepted": False, "error": "Refus utilisateur."}


def _preview_input(tool_input: dict | None) -> str:
    if not tool_input:
        return ""
    try:
        s = json.dumps(tool_input, ensure_ascii=False)
    except Exception:
        s = str(tool_input)
    if len(s) > 300:
        s = s[:300] + "…"
    return s


def status() -> dict:
    """Diagnostic : config courante + nombre de demandes en attente."""
    return {
        "enabled": _enabled(),
        "tools_count": len(_DANGEROUS),
        "tools": sorted(_DANGEROUS.keys()),
        "cache_sec": _cache_seconds(),
        "timeout_sec": _timeout_seconds(),
        "pending": len(_pending),
        "cached_devices": len(_recent_ok),
    }
