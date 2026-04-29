"""
Jarvis Tool — App Launcher
Ouvre des applications et logiciels selon l'OS.
"""
import subprocess
import platform
import shutil
import os


def _get_os():
    return platform.system().lower()  # 'linux', 'windows', 'darwin'


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
