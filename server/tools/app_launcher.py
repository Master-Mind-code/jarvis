"""
Jarvis Tool — App Launcher
Ouvre des applications et logiciels selon l'OS.
Android (Termux) supporté via `monkey` / `am start` / `pm list packages`.
"""
import subprocess
import platform
import shutil
import os


def _is_android() -> bool:
    """Détecte Android (Termux). platform.system() retourne 'Linux' donc on creuse."""
    if os.path.exists("/system/build.prop") or os.path.exists("/system/bin/am"):
        return True
    if "ANDROID_ROOT" in os.environ or "TERMUX_VERSION" in os.environ:
        return True
    return False


def _get_os():
    if _is_android():
        return "android"
    return platform.system().lower()  # 'linux', 'windows', 'darwin'


# Mapping des apps Android courantes : nom convivial → package id
ANDROID_PACKAGES = {
    "spotify": "com.spotify.music",
    "youtube": "com.google.android.youtube",
    "youtube music": "com.google.android.apps.youtube.music",
    "chrome": "com.android.chrome",
    "firefox": "org.mozilla.firefox",
    "whatsapp": "com.whatsapp",
    "telegram": "org.telegram.messenger",
    "messenger": "com.facebook.orca",
    "instagram": "com.instagram.android",
    "facebook": "com.facebook.katana",
    "twitter": "com.twitter.android",
    "x": "com.twitter.android",
    "tiktok": "com.zhiliaoapp.musically",
    "snapchat": "com.snapchat.android",
    "discord": "com.discord",
    "gmail": "com.google.android.gm",
    "drive": "com.google.android.apps.docs",
    "maps": "com.google.android.apps.maps",
    "google maps": "com.google.android.apps.maps",
    "calendar": "com.google.android.calendar",
    "agenda": "com.google.android.calendar",
    "photos": "com.google.android.apps.photos",
    "google photos": "com.google.android.apps.photos",
    "play store": "com.android.vending",
    "play": "com.android.vending",
    "netflix": "com.netflix.mediaclient",
    "spotify music": "com.spotify.music",
    "vlc": "org.videolan.vlc",
    "settings": "com.android.settings",
    "réglages": "com.android.settings",
    "parametres": "com.android.settings",
    "calculator": "com.google.android.calculator",
    "calculatrice": "com.google.android.calculator",
    "clock": "com.google.android.deskclock",
    "horloge": "com.google.android.deskclock",
    "messages": "com.google.android.apps.messaging",
    "phone": "com.google.android.dialer",
    "contacts": "com.google.android.contacts",
    "termux": "com.termux",
    "files": "com.google.android.documentsui",
    "fichiers": "com.google.android.documentsui",
    "camera": "com.google.android.GoogleCamera",
}


def _resolve_android_package(app_name: str) -> str | None:
    """Trouve le package Android correspondant à un nom convivial."""
    key = app_name.lower().strip()
    # 1. Mapping explicite
    if key in ANDROID_PACKAGES:
        return ANDROID_PACKAGES[key]
    # 2. Match partiel sur les clés
    for k, v in ANDROID_PACKAGES.items():
        if key in k or k in key:
            return v
    # 3. Cherche dans les packages installés via `pm list packages`
    try:
        result = subprocess.run(
            ["pm", "list", "packages"],
            capture_output=True, text=True, timeout=5,
        )
        packages = [
            line.replace("package:", "").strip()
            for line in result.stdout.splitlines()
            if line.startswith("package:")
        ]
        # Match dans les noms de packages
        candidates = [p for p in packages if key in p.lower()]
        if candidates:
            # Préfère les packages plus courts (souvent les apps "principales")
            candidates.sort(key=len)
            return candidates[0]
    except Exception:
        pass
    return None


def _open_android_app(app_name: str) -> dict:
    """Lance une app Android via `monkey` (plus robuste que am start)."""
    package = _resolve_android_package(app_name)
    if not package:
        return {
            "success": False,
            "error": f"App Android '{app_name}' non trouvée. "
                     f"Essaie un nom plus précis ou consulte `pm list packages`.",
        }
    try:
        # `monkey` lance l'activity LAUNCHER de l'app sans avoir à connaître son nom exact
        result = subprocess.run(
            ["monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0 and "Events injected: 1" in result.stdout:
            return {"success": True, "message": f"App Android lancée : {app_name} ({package})"}
        # Fallback : am start
        subprocess.run(
            ["am", "start", "-n", f"{package}/.MainActivity"],
            capture_output=True, timeout=5,
        )
        return {"success": True, "message": f"App Android lancée : {app_name} ({package})"}
    except FileNotFoundError:
        return {"success": False, "error": "`monkey`/`am` indisponible. Utilises-tu Termux sur un Android moderne ?"}
    except Exception as e:
        return {"success": False, "error": f"Échec lancement '{app_name}' : {e}"}


# Aliases d'apps communs (nom humain → commande)
APP_ALIASES = {
    "linux": {
        "navigateur": ["firefox", "chromium", "google-chrome", "brave"],
        "terminal": ["gnome-terminal", "xterm", "konsole", "termux"],
        "editeur": ["code", "gedit", "nano", "vim"],
        "fichiers": ["nautilus", "thunar", "dolphin"],
        "musique": ["rhythmbox", "vlc", "spotify"],
        "calculatrice": ["gnome-calculator", "kcalc"],
    },
    "windows": {
        "navigateur": ["start chrome", "start firefox", "start msedge"],
        "terminal": ["start cmd", "start powershell"],
        "editeur": ["code", "notepad"],
        "fichiers": ["explorer"],
        "musique": ["start spotify"],
        "calculatrice": ["calc"],
    },
    "darwin": {
        "navigateur": ["open -a Safari", "open -a 'Google Chrome'", "open -a Firefox"],
        "terminal": ["open -a Terminal"],
        "editeur": ["open -a 'Visual Studio Code'", "open -a TextEdit"],
        "fichiers": ["open ."],
        "musique": ["open -a Music", "open -a Spotify"],
        "calculatrice": ["open -a Calculator"],
    },
}


def open_app(app_name: str) -> dict:
    """Ouvre une application par son nom."""
    os_name = _get_os()

    # Android : route dédiée via monkey/am start (les apps ne sont pas des binaires)
    if os_name == "android":
        return _open_android_app(app_name)

    # Commande directe si connue
    if shutil.which(app_name):
        subprocess.Popen([app_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {"success": True, "message": f"Application lancée : {app_name}"}

    # Cherche dans les aliases
    aliases = APP_ALIASES.get(os_name, {})
    app_lower = app_name.lower()
    for category, commands in aliases.items():
        if app_lower in category or app_lower in " ".join(commands).lower():
            for cmd in commands:
                if shutil.which(cmd.split()[0]):
                    subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return {"success": True, "message": f"Ouvert : {cmd}"}

    # Tentative directe selon l'OS
    try:
        if os_name == "linux":
            subprocess.Popen([app_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif os_name == "windows":
            os.startfile(app_name)
        elif os_name == "darwin":
            subprocess.Popen(["open", "-a", app_name])
        return {"success": True, "message": f"Tentative d'ouverture de : {app_name}"}
    except Exception as e:
        return {"success": False, "error": f"Impossible d'ouvrir '{app_name}' : {str(e)}"}


def open_url_in_browser(url: str) -> dict:
    """Ouvre une URL dans le navigateur par défaut."""
    if _is_android():
        try:
            subprocess.Popen(
                ["am", "start", "-a", "android.intent.action.VIEW", "-d", url],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            return {"success": True, "message": f"URL ouverte sur Android : {url}"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    import webbrowser
    try:
        webbrowser.open(url)
        return {"success": True, "message": f"URL ouverte : {url}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def list_running_processes() -> dict:
    """Liste les processus en cours."""
    os_name = _get_os()
    if os_name == "windows":
        result = subprocess.run(["tasklist"], capture_output=True, text=True)
    else:
        result = subprocess.run(["ps", "aux", "--no-headers"], capture_output=True, text=True)

    lines = result.stdout.strip().split("\n")[:20]
    return {"success": True, "processes": lines}


HANDLERS = {
    "open_app": lambda p: open_app(**p),
    "open_url_in_browser": lambda p: open_url_in_browser(**p),
    "list_running_processes": lambda p: list_running_processes(),
}
