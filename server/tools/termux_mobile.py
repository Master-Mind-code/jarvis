"""
Orion Tool — Capacités mobiles via Termux:API.

Ces tools sont conçus pour s'exécuter sur un worker Android/Termux distant
(via target_device). Côté serveur Linux/Windows/macOS, ils retournent une
erreur "non disponible".

Prérequis sur le téléphone Android :
  - Termux installé (https://f-droid.org/packages/com.termux/)
  - Termux:API app installée
  - Dans Termux : `pkg install termux-api`

Documentation : https://wiki.termux.com/wiki/Termux:API
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess


def _is_termux() -> bool:
    if "TERMUX_VERSION" in os.environ:
        return True
    if os.path.exists("/data/data/com.termux"):
        return True
    return False


def _has(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def _run_json(cmd: list[str], timeout: int = 30) -> dict:
    """Exécute une commande termux-* et parse la sortie JSON."""
    if not _is_termux():
        return {"success": False, "error": "Cet outil ne fonctionne que sur un worker Android/Termux."}
    if not _has(cmd[0]):
        return {
            "success": False,
            "error": f"`{cmd[0]}` introuvable. Installe Termux:API : `pkg install termux-api`",
        }
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if result.returncode != 0:
            return {"success": False, "error": result.stderr.strip() or "code retour non zéro"}
        try:
            return {"success": True, "data": json.loads(result.stdout) if result.stdout.strip() else None}
        except json.JSONDecodeError:
            return {"success": True, "output": result.stdout.strip()}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"Timeout {timeout}s"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def termux_battery() -> dict:
    """État de la batterie."""
    return _run_json(["termux-battery-status"])


def termux_location(provider: str = "network") -> dict:
    """Position GPS. provider = network | gps | passive."""
    return _run_json(["termux-location", "-p", provider], timeout=60)


def termux_send_sms(number: str, text: str) -> dict:
    """Envoie un SMS. number = +33... ou 06..."""
    if not _is_termux():
        return {"success": False, "error": "Tool réservé aux workers Android/Termux."}
    if not _has("termux-sms-send"):
        return {"success": False, "error": "termux-api manquant : `pkg install termux-api`"}
    if not number or not text:
        return {"success": False, "error": "number et text requis"}
    try:
        result = subprocess.run(
            ["termux-sms-send", "-n", str(number), str(text)],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            return {"success": False, "error": result.stderr.strip() or "envoi échoué"}
        return {"success": True, "message": f"SMS envoyé à {number}"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def termux_list_sms(limit: int = 10) -> dict:
    """Liste les derniers SMS reçus."""
    return _run_json(["termux-sms-list", "-l", str(int(limit))])


def termux_contacts() -> dict:
    """Liste tous les contacts du téléphone."""
    return _run_json(["termux-contact-list"])


def termux_call(number: str) -> dict:
    """Lance un appel téléphonique."""
    if not _is_termux():
        return {"success": False, "error": "Tool réservé aux workers Android/Termux."}
    if not _has("termux-telephony-call"):
        return {"success": False, "error": "termux-api manquant."}
    try:
        subprocess.run(["termux-telephony-call", str(number)], timeout=10)
        return {"success": True, "message": f"Appel lancé : {number}"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def termux_vibrate(duration_ms: int = 500) -> dict:
    """Fait vibrer le téléphone."""
    if not _is_termux():
        return {"success": False, "error": "Tool réservé aux workers Android/Termux."}
    if not _has("termux-vibrate"):
        return {"success": False, "error": "termux-api manquant."}
    try:
        subprocess.run(["termux-vibrate", "-d", str(int(duration_ms))], timeout=5)
        return {"success": True, "duration_ms": int(duration_ms)}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def termux_notification(title: str, content: str = "") -> dict:
    """Notification dans la barre de notification Android."""
    if not _is_termux():
        return {"success": False, "error": "Tool réservé aux workers Android/Termux."}
    if not _has("termux-notification"):
        return {"success": False, "error": "termux-api manquant."}
    try:
        subprocess.run(
            ["termux-notification", "--title", title, "--content", content],
            timeout=5,
        )
        return {"success": True, "message": f"Notification : {title}"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def termux_clipboard_get() -> dict:
    return _run_json(["termux-clipboard-get"])


def termux_clipboard_set(text: str) -> dict:
    if not _is_termux():
        return {"success": False, "error": "Tool réservé aux workers Android/Termux."}
    if not _has("termux-clipboard-set"):
        return {"success": False, "error": "termux-api manquant."}
    try:
        subprocess.run(["termux-clipboard-set", str(text)], timeout=5)
        return {"success": True, "chars": len(text)}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def termux_torch(on: bool = True) -> dict:
    """Allume/éteint la lampe torche du téléphone."""
    if not _is_termux():
        return {"success": False, "error": "Tool réservé aux workers Android/Termux."}
    if not _has("termux-torch"):
        return {"success": False, "error": "termux-api manquant."}
    try:
        subprocess.run(["termux-torch", "on" if on else "off"], timeout=5)
        return {"success": True, "torch": "on" if on else "off"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


HANDLERS = {
    "termux_battery":        lambda p: termux_battery(),
    "termux_location":       lambda p: termux_location(**p),
    "termux_send_sms":       lambda p: termux_send_sms(**p),
    "termux_list_sms":       lambda p: termux_list_sms(**p),
    "termux_contacts":       lambda p: termux_contacts(),
    "termux_call":           lambda p: termux_call(**p),
    "termux_vibrate":        lambda p: termux_vibrate(**p),
    "termux_notification":   lambda p: termux_notification(**p),
    "termux_clipboard_get":  lambda p: termux_clipboard_get(),
    "termux_clipboard_set":  lambda p: termux_clipboard_set(**p),
    "termux_torch":          lambda p: termux_torch(**p),
}
