"""
Jarvis — Lanceur unifié.

Modes :
  python start.py                    → menu interactif
  python start.py server             → lance le serveur central + ouvre l'UI dans le navigateur
  python start.py cli                → lance la CLI standalone (pas besoin de serveur)
  python start.py worker             → lance l'agent en mode worker (à utiliser depuis un autre appareil)
  python start.py controller         → lance l'agent en mode chat controller (CLI distante)
  python start.py ui                 → ouvre seulement l'UI navigateur

Le script vérifie .env, les dépendances, et démarre proprement.
"""
import os
import sys
import subprocess
import webbrowser
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT / ".env"
ENV_EXAMPLE = ROOT / ".env.example"
UI_FILE = ROOT / "jarvis_ui.html"
REQ_FILE = ROOT / "requirements.txt"

PYTHON = sys.executable

# Charge .env le plus tôt possible pour que JARVIS_SERVER_URL, JARVIS_SECRET_TOKEN, etc.
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


def banner():
    print("═" * 60)
    print("                J A R V I S — Lanceur".center(60))
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
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "localhost"


def run_server(open_ui: bool = True):
    print("\n→ Démarrage du serveur Jarvis...")
    ip = get_local_ip()
    port = os.getenv("SERVER_PORT", "8765")
    print(f"  Local      : ws://localhost:{port}")
    print(f"  Réseau     : ws://{ip}:{port}    (à donner aux autres appareils)")
    if UI_FILE.exists() and open_ui:
        print(f"  UI         : ouverture de {UI_FILE.name} dans 2s...")
    print()

    if open_ui and UI_FILE.exists():
        # Ouvre l'UI après un petit délai pour laisser le serveur démarrer
        import threading, time
        def open_browser():
            time.sleep(2)
            webbrowser.open(UI_FILE.as_uri())
        threading.Thread(target=open_browser, daemon=True).start()

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
    if not os.getenv("JARVIS_SERVER_URL"):
        url = input("  URL du serveur (ex: ws://192.168.1.42:8765) : ").strip()
        if not url:
            print("  [!] URL requise.")
            sys.exit(1)
        os.environ["JARVIS_SERVER_URL"] = url
    if not os.getenv("JARVIS_DEVICE_ID"):
        default_id = (
            os.uname().nodename if hasattr(os, "uname")
            else os.environ.get("COMPUTERNAME", "device")
        ).lower()
        device_id = input(f"  device_id [{default_id}] : ").strip() or default_id
        os.environ["JARVIS_DEVICE_ID"] = device_id
    if not os.getenv("JARVIS_SECRET_TOKEN"):
        print("  [!] JARVIS_SECRET_TOKEN manquant. Mets-le dans .env ou exporte-le.")
        sys.exit(1)

    print(f"  URL        : {os.environ['JARVIS_SERVER_URL']}")
    print(f"  Device     : {os.environ['JARVIS_DEVICE_ID']}")
    print(f"  Token      : {'*' * 8} (chargé)")

    env = os.environ.copy()
    env["JARVIS_AGENT_MODE"] = mode
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    subprocess.run([PYTHON, "agent/agent.py"], cwd=str(ROOT), env=env)


def run_ui_only():
    if not UI_FILE.exists():
        print(f"  [!] {UI_FILE.name} introuvable.")
        sys.exit(1)
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
    check_env()
    check_deps()

    cmd = sys.argv[1].lower() if len(sys.argv) > 1 else None

    if cmd == "server":
        run_server()
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
