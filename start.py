"""
Orion — Lanceur unifié.

Modes :
  python start.py                    → menu interactif
  python start.py server             → lance le serveur central + ouvre l'UI dans le navigateur
  python start.py server --no-ui     → lance le serveur sans ouvrir l'UI
  python start.py cli                → lance la CLI standalone (pas besoin de serveur)
  python start.py worker             → lance l'agent en mode worker (à utiliser depuis un autre appareil)
  python start.py controller         → lance l'agent en mode chat controller (CLI distante)
  python start.py ui                 → ouvre seulement l'UI navigateur
  python start.py install-startup    → active le démarrage auto Windows (mode server, sans UI)
  python start.py remove-startup     → désactive le démarrage auto Windows

Le script vérifie .env, les dépendances, et démarre proprement.
"""
import os
import sys
import json
import socket
import subprocess
import threading
import time
import webbrowser
from pathlib import Path
from typing import List, Sequence
from urllib.error import URLError
from urllib.request import urlopen
from branding import (
    DEFAULT_SECRET_TOKEN,
    LEGACY_APP_NAME,
    LEGACY_APP_SLUG,
    LEGACY_ONLINE_STATUS,
    ONLINE_STATUS,
    env_key,
    get_env,
    resolve_ui_file,
    sync_env_aliases,
)

ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT / ".env"
ENV_EXAMPLE = ROOT / ".env.example"
UI_FILE = resolve_ui_file(ROOT)
REQ_FILE = ROOT / "requirements.txt"
STARTUP_HELPER_DIR = ROOT / "data" / "startup"
STARTUP_LOG_DIR = ROOT / "data" / "logs"
AUTOSTART_RUNNER = STARTUP_HELPER_DIR / "orion_autostart.cmd"
AUTOSTART_VBS_NAME = "Orion Autostart.vbs"
LEGACY_AUTOSTART_RUNNER = STARTUP_HELPER_DIR / f"{LEGACY_APP_SLUG}_autostart.cmd"
LEGACY_AUTOSTART_VBS_NAME = f"{LEGACY_APP_NAME} Autostart.vbs"
STARTUP_MODES = {"server", "cli", "worker", "controller", "ui"}

PYTHON = sys.executable

# Charge .env le plus tôt possible pour que ORION_SERVER_URL, ORION_SECRET_TOKEN, etc.
# soient disponibles dans os.environ avant tout subprocess.
try:
    from dotenv import load_dotenv
    if ENV_FILE.exists():
        load_dotenv(ENV_FILE)
except ImportError:
    # python-dotenv pas encore installé : fallback parser minimal pour ne pas bloquer
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

sync_env_aliases()


def configure_output():
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


configure_output()


def banner():
    print("═" * 60)
    print("                O R I O N — Lanceur".center(60))
    print("═" * 60)


def check_env():
    """Vérifie que .env existe et contient ANTHROPIC_API_KEY."""
    if not ENV_FILE.exists():
        print(f"\n[!] Fichier .env manquant.")
        if ENV_EXAMPLE.exists():
            print(f"    Copie {ENV_EXAMPLE.name} vers .env et remplis tes clés :")
            print(f"      cp .env.example .env")
        sys.exit(1)

    content = ENV_FILE.read_text(encoding="utf-8")
    if "ANTHROPIC_API_KEY=sk-ant-" not in content and "ANTHROPIC_API_KEY=" in content:
        # Charge sans dépendre de python-dotenv pour la vérif initiale
        for line in content.splitlines():
            line = line.strip()
            if line.startswith("ANTHROPIC_API_KEY="):
                value = line.split("=", 1)[1].strip().strip('"').strip("'")
                if not value or value.startswith("sk-ant-xxxx"):
                    print("\n[!] ANTHROPIC_API_KEY semble être une valeur de placeholder.")
                    print("    Édite .env et mets ta vraie clé Claude API.")
                    sys.exit(1)
                return
        print("\n[!] ANTHROPIC_API_KEY introuvable dans .env")
        sys.exit(1)


def check_deps():
    """Vérifie que les dépendances Python critiques sont installées."""
    missing = []
    for pkg, mod in [("anthropic", "anthropic"), ("fastapi", "fastapi"),
                     ("uvicorn", "uvicorn"), ("websockets", "websockets"),
                     ("python-dotenv", "dotenv"), ("rich", "rich")]:
        try:
            __import__(mod)
        except ImportError:
            missing.append(pkg)
    if missing:
        print(f"\n[!] Dépendances manquantes : {', '.join(missing)}")
        print(f"    Installe avec :  {PYTHON} -m pip install -r requirements.txt")
        choice = input("    Installer maintenant ? [y/N] ").strip().lower()
        if choice == "y":
            subprocess.check_call([PYTHON, "-m", "pip", "install", "-r", str(REQ_FILE)])
        else:
            sys.exit(1)


def get_local_ip():
    """Devine l'IP locale (utile pour afficher l'URL aux autres appareils)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "localhost"


def get_server_port() -> str:
    return os.getenv("SERVER_PORT", "8765")


def get_server_http_url(port: str | None = None) -> str:
    return f"http://127.0.0.1:{port or get_server_port()}"


def is_tcp_port_open(port: str, host: str = "127.0.0.1", timeout: float = 0.4) -> bool:
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except OSError:
        return False


def is_orion_server_online(port: str, timeout: float = 0.8) -> bool:
    try:
        with urlopen(f"{get_server_http_url(port)}/status", timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8", errors="replace"))
        return payload.get("status") in {ONLINE_STATUS, LEGACY_ONLINE_STATUS}
    except (OSError, ValueError, URLError):
        return False


def open_browser_async(url: str, delay: float = 0.0):
    def _open():
        if delay > 0:
            time.sleep(delay)
        webbrowser.open(url)
    threading.Thread(target=_open, daemon=True).start()


def get_windows_startup_dir() -> Path:
    appdata = os.getenv("APPDATA")
    if not appdata:
        raise RuntimeError("APPDATA introuvable. Impossible de trouver le dossier Startup Windows.")
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def parse_mode_arg(args: Sequence[str], default: str = "server") -> str:
    for arg in args:
        if not arg.startswith("-"):
            return arg.lower()
    return default


def validate_startup_mode(mode: str) -> str:
    if mode not in STARTUP_MODES:
        modes = ", ".join(sorted(STARTUP_MODES))
        print(f"\n[!] Mode startup inconnu : {mode}")
        print(f"    Modes supportés : {modes}")
        sys.exit(1)
    return mode


def get_startup_command(mode: str) -> List[str]:
    command = [PYTHON, str(ROOT / "start.py"), mode]
    if mode == "server":
        command.append("--no-ui")
    return command


def escape_vbs(value: str) -> str:
    return value.replace('"', '""')


def ensure_startup_prerequisites(mode: str):
    if os.name != "nt":
        raise RuntimeError("Le démarrage automatique intégré est uniquement prévu pour Windows.")

    if mode in {"server", "cli", "controller"} and not ENV_FILE.exists():
        raise RuntimeError(
            "Fichier .env manquant. Configure Orion d'abord, puis relance install-startup."
        )

    if mode == "ui" and not UI_FILE.exists():
        raise RuntimeError(f"{UI_FILE.name} introuvable.")

    if mode in {"worker", "controller"}:
        missing = []
        if not get_env("SERVER_URL"):
            missing.append("ORION_SERVER_URL")
        if not get_env("SECRET_TOKEN"):
            missing.append("ORION_SECRET_TOKEN")
        if missing:
            missing_str = ", ".join(missing)
            raise RuntimeError(
                f"Variables manquantes dans .env pour le mode {mode} : {missing_str}"
            )


def install_windows_startup(mode: str = "server"):
    mode = validate_startup_mode(mode)
    ensure_startup_prerequisites(mode)

    startup_dir = get_windows_startup_dir()
    startup_dir.mkdir(parents=True, exist_ok=True)
    STARTUP_HELPER_DIR.mkdir(parents=True, exist_ok=True)
    STARTUP_LOG_DIR.mkdir(parents=True, exist_ok=True)

    legacy_startup_vbs = startup_dir / LEGACY_AUTOSTART_VBS_NAME
    for legacy_path in (legacy_startup_vbs, LEGACY_AUTOSTART_RUNNER):
        if legacy_path.exists():
            legacy_path.unlink()

    log_file = STARTUP_LOG_DIR / f"orion-startup-{mode}.log"
    command = subprocess.list2cmdline(get_startup_command(mode))
    runner_content = "\r\n".join([
        "@echo off",
        f'cd /d "{ROOT}"',
        f'{command} >> "{log_file}" 2>&1',
        "",
    ])
    AUTOSTART_RUNNER.write_text(runner_content, encoding="utf-8")

    startup_vbs = startup_dir / AUTOSTART_VBS_NAME
    vbs_content = "\r\n".join([
        'Set shell = CreateObject("WScript.Shell")',
        f'shell.CurrentDirectory = "{escape_vbs(str(ROOT))}"',
        f'shell.Run Chr(34) & "{escape_vbs(str(AUTOSTART_RUNNER.resolve()))}" & Chr(34), 0, False',
        "",
    ])
    startup_vbs.write_text(vbs_content, encoding="utf-8")

    print("\n[OK] Démarrage automatique activé.")
    print(f"  Mode       : {mode}")
    print("  Déclencheur: ouverture de session Windows")
    print(f"  Lanceur    : {startup_vbs}")
    print(f"  Script     : {AUTOSTART_RUNNER}")
    print(f"  Logs       : {log_file}")
    if mode == "server":
        print("  Note       : le serveur démarre en fond sans ouvrir le navigateur.")


def remove_windows_startup():
    if os.name != "nt":
        print("\n[!] remove-startup est prévu pour Windows.")
        sys.exit(1)

    removed = []

    startup_vbs = get_windows_startup_dir() / AUTOSTART_VBS_NAME
    legacy_startup_vbs = get_windows_startup_dir() / LEGACY_AUTOSTART_VBS_NAME
    for path in (startup_vbs, AUTOSTART_RUNNER, legacy_startup_vbs, LEGACY_AUTOSTART_RUNNER):
        if path.exists():
            path.unlink()
            removed.append(path)

    if removed:
        print("\n[OK] Démarrage automatique désactivé.")
        for path in removed:
            print(f"  Supprimé   : {path}")
    else:
        print("\n[i] Aucun démarrage automatique Orion n'était installé.")


def run_server(open_ui: bool = True):
    print("\n→ Démarrage du serveur Orion...")
    ip = get_local_ip()
    port = get_server_port()
    ui_url = get_server_http_url(port)
    print(f"  Local      : ws://localhost:{port}")
    print(f"  Réseau     : ws://{ip}:{port}    (à donner aux autres appareils)")
    if UI_FILE.exists() and open_ui:
        print(f"  UI         : ouverture de {ui_url} dans 2s...")
    print()

    if is_orion_server_online(port):
        print("  [i] Un serveur Orion tourne déjà sur ce port.")
        if open_ui and UI_FILE.exists():
            open_browser_async(ui_url)
        return

    if is_tcp_port_open(port):
        print(f"  [!] Le port {port} est déjà utilisé par un autre processus.")
        print("      Ferme ce processus ou change SERVER_PORT dans .env.")
        return

    if open_ui and UI_FILE.exists():
        # Ouvre l'UI après un petit délai pour laisser le serveur démarrer
        open_browser_async(ui_url, delay=2)

    # Lance uvicorn en passant la racine au PYTHONPATH pour résoudre 'server.main'
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    subprocess.run([PYTHON, "-m", "uvicorn", "server.main:app",
                    "--host", os.getenv("SERVER_HOST", "0.0.0.0"),
                    "--port", port], cwd=str(ROOT), env=env)


def run_cli():
    print("\n→ Démarrage de la CLI standalone...")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    subprocess.run([PYTHON, "interface/cli.py"], cwd=str(ROOT), env=env)


def run_agent(mode: str):
    print(f"\n→ Démarrage de l'agent en mode {mode}...")
    server_url = get_env("SERVER_URL")
    if not server_url:
        url = input("  URL du serveur (ex: ws://192.168.1.42:8765) : ").strip()
        if not url:
            print("  [!] URL requise.")
            sys.exit(1)
        os.environ[env_key("SERVER_URL")] = url
        os.environ[env_key("SERVER_URL", legacy=True)] = url
        server_url = url
    device_id = get_env("DEVICE_ID")
    if not device_id:
        default_id = (
            os.uname().nodename if hasattr(os, "uname")
            else os.environ.get("COMPUTERNAME", "device")
        ).lower()
        device_id = input(f"  device_id [{default_id}] : ").strip() or default_id
        os.environ[env_key("DEVICE_ID")] = device_id
        os.environ[env_key("DEVICE_ID", legacy=True)] = device_id
    secret_token = get_env("SECRET_TOKEN")
    if not secret_token:
        print("  [!] ORION_SECRET_TOKEN manquant. Mets-le dans .env ou exporte-le.")
        sys.exit(1)

    print(f"  URL        : {server_url}")
    print(f"  Device     : {device_id}")
    print(f"  Token      : {'*' * 8} (chargé)")

    env = os.environ.copy()
    env[env_key("AGENT_MODE")] = mode
    env[env_key("AGENT_MODE", legacy=True)] = mode
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    subprocess.run([PYTHON, "agent/agent.py"], cwd=str(ROOT), env=env)


def run_ui_only():
    if not UI_FILE.exists():
        print(f"  [!] {UI_FILE.name} introuvable.")
        sys.exit(1)
    port = get_server_port()
    if is_orion_server_online(port):
        ui_url = get_server_http_url(port)
        print(f"\n→ Ouverture de l'UI : {ui_url}")
        webbrowser.open(ui_url)
        return
    print(f"\n→ Ouverture de l'UI : {UI_FILE}")
    webbrowser.open(UI_FILE.as_uri())


def menu():
    while True:
        print("\nQue veux-tu lancer ?")
        print("  [1] Serveur central + UI navigateur")
        print("  [2] CLI standalone (mode local, pas de serveur)")
        print("  [3] Agent worker (cet appareil exécute des tools à distance)")
        print("  [4] Agent controller (chat distant)")
        print("  [5] UI uniquement (le serveur tourne déjà ailleurs)")
        print("  [q] Quitter")
        choice = input("\n> ").strip().lower()
        if choice == "1":
            run_server()
        elif choice == "2":
            run_cli()
        elif choice == "3":
            run_agent("worker")
        elif choice == "4":
            run_agent("controller")
        elif choice == "5":
            run_ui_only()
        elif choice in ("q", "quit", "exit"):
            return
        else:
            print("Choix invalide.")


def main():
    banner()
    cmd = sys.argv[1].lower() if len(sys.argv) > 1 else None
    extra_args = sys.argv[2:] if len(sys.argv) > 2 else []

    if cmd == "install-startup":
        mode = parse_mode_arg(extra_args, default="server")
        try:
            install_windows_startup(mode)
        except RuntimeError as exc:
            print(f"\n[!] {exc}")
            sys.exit(1)
        return

    if cmd == "remove-startup":
        remove_windows_startup()
        return

    if cmd in (None, "server", "cli", "worker", "controller"):
        check_env()
        check_deps()

    if cmd == "server":
        run_server(open_ui="--no-ui" not in extra_args)
    elif cmd == "cli":
        run_cli()
    elif cmd == "worker":
        run_agent("worker")
    elif cmd == "controller":
        run_agent("controller")
    elif cmd == "ui":
        run_ui_only()
    elif cmd is None:
        menu()
    else:
        print(f"Commande inconnue : {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrompu.")
