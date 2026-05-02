"""
Orion Tool — Capture d'écran cross-platform via mss + Pillow.

Capture full screen, monitor spécifique, ou région (x, y, width, height).
Sauvegarde PNG dans data/screenshots/ par défaut.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DIR = ROOT / "data" / "screenshots"


def screenshot(
    path: str | None = None,
    monitor: int = 0,
    region: dict | None = None,
    return_base64: bool = False,
) -> dict:
    """Capture d'écran. region = {x, y, width, height} (optionnel)."""
    try:
        import mss
        import mss.tools
    except ImportError:
        return {
            "success": False,
            "error": "mss n'est pas installé. Installe avec :\n"
                     "    pip install -r requirements-extras.txt",
        }

    if path is None:
        DEFAULT_DIR.mkdir(parents=True, exist_ok=True)
        path = str(DEFAULT_DIR / f"orion_{datetime.now():%Y%m%d_%H%M%S}.png")
    else:
        Path(path).parent.mkdir(parents=True, exist_ok=True)

    try:
        with mss.mss() as sct:
            if region and all(k in region for k in ("x", "y", "width", "height")):
                bbox = {
                    "left": int(region["x"]),
                    "top": int(region["y"]),
                    "width": int(region["width"]),
                    "height": int(region["height"]),
                    "mon": int(monitor) if monitor else 1,
                }
            else:
                # monitor=0 = tous les écrans combinés, 1+ = écran spécifique
                idx = int(monitor) if monitor and monitor < len(sct.monitors) else 0
                bbox = sct.monitors[idx]
            shot = sct.grab(bbox)
            mss.tools.to_png(shot.rgb, shot.size, output=path)
    except Exception as exc:
        return {"success": False, "error": f"{type(exc).__name__}: {exc}"}

    result = {
        "success": True,
        "path": path,
        "size": {"width": shot.size[0], "height": shot.size[1]},
    }
    if return_base64:
        import base64
        with open(path, "rb") as f:
            result["base64"] = base64.b64encode(f.read()).decode("ascii")
    return result


def list_monitors() -> dict:
    """Liste les écrans détectés."""
    try:
        import mss
        with mss.mss() as sct:
            mons = []
            for i, m in enumerate(sct.monitors):
                mons.append({
                    "index": i,
                    "width": m["width"],
                    "height": m["height"],
                    "left": m["left"],
                    "top": m["top"],
                    "primary": i == 1,
                    "all_screens": i == 0,
                })
        return {"success": True, "monitors": mons}
    except ImportError:
        return {"success": False, "error": "mss n'est pas installé."}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


HANDLERS = {
    "screenshot": lambda p: screenshot(**p),
    "list_monitors": lambda p: list_monitors(),
}
