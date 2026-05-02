"""
Orion — Interface CLI Standalone
Version autonome : pas besoin de serveur WebSocket.
Tourne directement sur l'appareil avec le cerveau en local.
Parfait pour débuter et tester sur Termux.
"""
import os
import sys
import json
from pathlib import Path
from dotenv import load_dotenv
from branding import sync_env_aliases

# Permet d'importer les modules du projet depuis n'importe où
sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv(Path(__file__).parent.parent / ".env")
sync_env_aliases()

# ─── Essaie d'importer rich pour une belle interface ─────────────
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text
    from rich.rule import Rule
    from rich.markdown import Markdown
    RICH = True
except ImportError:
    RICH = False

from server.orchestrator import process_request

console = Console() if RICH else None


def print_banner():
    if RICH:
        console.print(Panel(
            "[bold cyan]O R I O N[/bold cyan]\n"
            "[dim]Assistant IA Personnel — Mode Standalone[/dim]",
            border_style="cyan",
            padding=(1, 4),
        ))
        console.print("[dim]Commandes : /clear (effacer historique) | /exit (quitter) | /help[/dim]\n")
    else:
        print("=" * 50)
        print("         O R I O N - Assistant IA")
        print("=" * 50)
        print("Commandes : /clear | /exit | /help\n")


def print_tool_action(tool_name: str, tool_input: dict, result: str):
    result_data = json.loads(result) if isinstance(result, str) else result
    ok = result_data.get("success", True)
    icon = "✓" if ok else "✗"
    color = "green" if ok else "red"

    # Résumé court de l'input
    summary = ""
    if "path" in tool_input:
        summary = f" → {tool_input['path']}"
    elif "command" in tool_input:
        summary = f" → {tool_input['command'][:50]}"
    elif "query" in tool_input:
        summary = f" → \"{tool_input['query']}\""
    elif "app_name" in tool_input:
        summary = f" → {tool_input['app_name']}"

    if RICH:
        console.print(f"  [{color}]{icon}[/{color}] [bold]{tool_name}[/bold][dim]{summary}[/dim]")
    else:
        print(f"  [{icon}] {tool_name}{summary}")


def print_response(text: str):
    if RICH:
        console.print()
        console.print(Panel(Markdown(text), title="[bold cyan]Orion[/bold cyan]", border_style="cyan", padding=(0, 1)))
    else:
        print(f"\nOrion : {text}\n")


def print_user_input_prompt():
    if RICH:
        console.print("\n[bold yellow]Vous[/bold yellow] ", end="")
    else:
        print("Vous : ", end="")


def show_help():
    help_text = """
**Exemples de commandes :**

- "Crée un fichier Python qui calcule les nombres premiers jusqu'à 100 et exécute-le"
- "Recherche sur le web les dernières nouvelles sur l'IA"  
- "Liste le contenu de mon dossier home"
- "Ouvre Firefox"
- "Crée un script bash qui sauvegarde mon bureau"
- "Lis le fichier /etc/hosts"
- "Quelles applis sont en cours d'exécution ?"

**Commandes spéciales :**
- `/clear` — Efface l'historique de conversation
- `/exit` ou `/quit` — Quitter
- `/help` — Afficher cette aide
- `/info` — Infos système
"""
    if RICH:
        console.print(Markdown(help_text))
    else:
        print(help_text)


def main():
    # Vérifie la clé API
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("ERREUR : ANTHROPIC_API_KEY manquante dans .env")
        print("Copie .env.example en .env et ajoute ta clé API.")
        sys.exit(1)

    print_banner()

    conversation_history = []

    while True:
        try:
            print_user_input_prompt()
            user_input = input().strip()
        except (EOFError, KeyboardInterrupt):
            print("\nAu revoir !")
            break

        if not user_input:
            continue

        # Commandes spéciales
        if user_input.lower() in ["/exit", "/quit", "/q"]:
            if RICH:
                console.print("[dim]À bientôt ![/dim]")
            else:
                print("À bientôt !")
            break

        if user_input.lower() == "/clear":
            conversation_history = []
            if RICH:
                console.print("[dim]Historique effacé.[/dim]")
            else:
                print("[Historique effacé]")
            continue

        if user_input.lower() == "/help":
            show_help()
            continue

        if user_input.lower() == "/info":
            from server.tools.code_runner import get_system_info
            info = get_system_info()
            if RICH:
                console.print_json(json.dumps(info, indent=2))
            else:
                print(json.dumps(info, indent=2))
            continue

        # Traitement par le cerveau
        if RICH:
            console.print("\n[dim]Orion réfléchit...[/dim]")
        else:
            print("\n[Orion réfléchit...]")

        try:
            response, conversation_history = process_request(
                user_input,
                conversation_history,
                on_tool_call=print_tool_action,
            )
            print_response(response)

        except Exception as e:
            error_msg = f"Erreur : {str(e)}"
            if RICH:
                console.print(f"[red]{error_msg}[/red]")
            else:
                print(error_msg)


if __name__ == "__main__":
    main()
