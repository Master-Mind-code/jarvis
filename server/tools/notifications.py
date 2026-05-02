"""
Orion Tool — Notifications système (toast).

Windows : winotify (toast moderne).
Linux   : notify-send (libnotify).
macOS   : osascript display notification.
"""
from __future__ import annotations

import platform
import shutil
import subprocess


def _system() -> str:
    return platform.system().lower()


def notify(title: str, message: str = "", duration: str = "short") -> dict:
    """Affiche une notification système. duration: 'short' | 'long' (Windows uniquement)."""
    title = (title or "Orion").strip()
    message = (message or "").strip()
    osname = _system()

    if osname == "windows":
        try:
            from winotify import Notification, audio
        except ImportError:
            return {
                "success": False,
                "error": "winotify n'est pas installé. Installe avec :\n"
                         "    pip install -r requirements-extras.txt",
            }
        toast = Notification(
            app_id="Orion",
            title=title,
            msg=message,
            duration=duration if duration in ("short", "long") else "short",
        )
        try:
            toast.set_audio(audio.Default, loop=False)
        except Exception:
            pass
        toast.show()
        return {"success": True, "message": f"Notification affichée : {title}"}

    if osname == "linux":
        if not shutil.which("notify-send"):
            return {"success": False, "error": "notify-send introuvable (paquet libnotify-bin)"}
        try:
            subprocess.run(["notify-send", title, message], check=False, timeout=5)
            return {"success": True, "message": f"Notification : {title}"}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    if osname == "darwin":
        # Échappe les guillemets dans le texte
        safe_msg = message.replace('"', '\\"')
        safe_title = title.replace('"', '\\"')
        script = f'display notification "{safe_msg}" with title "{safe_title}"'
        try:
            subprocess.run(["osascript", "-e", script], check=False, timeout=5)
            return {"success": True, "message": f"Notification : {title}"}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    return {"success": False, "error": f"OS non supporté : {osname}"}


HANDLERS = {
    "notify": lambda p: notify(**p),
}
