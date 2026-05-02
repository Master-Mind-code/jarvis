"""
Orion Tool — Automation souris/clavier (PyAutoGUI).

⚠ Outils sensibles : peut prendre le contrôle de la machine.
Désactivés par défaut. Active avec ORION_AUTOMATION_ENABLED=true dans .env.

Failsafe PyAutoGUI : déplacer la souris dans le coin haut-gauche déclenche
une exception et coupe l'automation immédiatement.
"""
from __future__ import annotations

import os


def _enabled() -> bool:
    return os.getenv("ORION_AUTOMATION_ENABLED", "false").strip().lower() in (
        "1", "true", "yes", "on", "oui",
    )


def _disabled_response() -> dict:
    return {
        "success": False,
        "error": "Automation désactivée. Active avec ORION_AUTOMATION_ENABLED=true dans .env.\n"
                 "Failsafe PyAutoGUI : bouge la souris dans le coin haut-gauche pour couper.",
    }


def _import_pyautogui():
    try:
        import pyautogui  # type: ignore[import-not-found]
        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.05
        return pyautogui
    except ImportError:
        return None


def mouse_position() -> dict:
    """Retourne la position actuelle de la souris (lecture seule, toujours autorisée)."""
    pg = _import_pyautogui()
    if pg is None:
        return {"success": False, "error": "pyautogui non installé."}
    x, y = pg.position()
    sw, sh = pg.size()
    return {"success": True, "x": x, "y": y, "screen_width": sw, "screen_height": sh}


def mouse_move(x: int, y: int, duration: float = 0.2) -> dict:
    if not _enabled():
        return _disabled_response()
    pg = _import_pyautogui()
    if pg is None:
        return {"success": False, "error": "pyautogui non installé."}
    try:
        pg.moveTo(int(x), int(y), duration=float(duration))
        return {"success": True, "x": int(x), "y": int(y)}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def mouse_click(
    x: int | None = None,
    y: int | None = None,
    button: str = "left",
    clicks: int = 1,
) -> dict:
    if not _enabled():
        return _disabled_response()
    pg = _import_pyautogui()
    if pg is None:
        return {"success": False, "error": "pyautogui non installé."}
    if button not in ("left", "right", "middle"):
        return {"success": False, "error": f"button doit être left|right|middle"}
    try:
        kwargs = {"button": button, "clicks": int(clicks)}
        if x is not None and y is not None:
            kwargs["x"] = int(x)
            kwargs["y"] = int(y)
        pg.click(**kwargs)
        return {"success": True, "button": button, "clicks": int(clicks)}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def keyboard_type(text: str, interval: float = 0.02) -> dict:
    if not _enabled():
        return _disabled_response()
    pg = _import_pyautogui()
    if pg is None:
        return {"success": False, "error": "pyautogui non installé."}
    try:
        pg.typewrite(text, interval=float(interval))
        return {"success": True, "typed_chars": len(text)}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def keyboard_press(keys: str | list[str]) -> dict:
    """Touche unique ('enter', 'esc', 'f5') ou hotkey (['ctrl', 'c'] = Ctrl+C)."""
    if not _enabled():
        return _disabled_response()
    pg = _import_pyautogui()
    if pg is None:
        return {"success": False, "error": "pyautogui non installé."}
    try:
        if isinstance(keys, str):
            pg.press(keys)
            return {"success": True, "pressed": keys}
        else:
            pg.hotkey(*keys)
            return {"success": True, "hotkey": "+".join(keys)}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


HANDLERS = {
    "mouse_position": lambda p: mouse_position(),
    "mouse_move": lambda p: mouse_move(**p),
    "mouse_click": lambda p: mouse_click(**p),
    "keyboard_type": lambda p: keyboard_type(**p),
    "keyboard_press": lambda p: keyboard_press(**p),
}
