"""
Jarvis — Orchestrateur Central
Cerveau de l'assistant : reçoit une requête, appelle un LLM (Anthropic ou Gemini),
exécute les tools, retourne la réponse finale.

Provider sélectionné via JARVIS_PROVIDER (défaut: anthropic).
"""
import os
import json
from pathlib import Path
from dotenv import load_dotenv

# Charge .env depuis la racine du projet AVANT d'instancier les clients LLM
# (sinon les variables ne sont pas encore définies quand main.py importe ce module).
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from server.tools import ALL_HANDLERS
from server.providers import get_provider

# Provider initialisé en lazy : on ne crée le client qu'au premier appel,
# pour permettre à l'orchestrateur de s'importer même si la clé du provider sélectionné
# n'est pas encore définie (utile pour les workers qui n'ont pas besoin du LLM).
_provider = None

def _get_provider():
    global _provider
    if _provider is None:
        _provider = get_provider()
        print(f"[orchestrator] Provider actif : {_provider.name} ({_provider.model})")
    return _provider

# ─────────────────────────────────────────────────────────────────
# Définition des tools disponibles pour Claude
# ─────────────────────────────────────────────────────────────────
TOOLS = [
    {
        "name": "create_file",
        "description": "Crée un fichier avec un contenu donné sur l'appareil.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Chemin complet du fichier (ex: /home/user/notes.txt)"},
                "content": {"type": "string", "description": "Contenu à écrire dans le fichier"},
                "overwrite": {"type": "boolean", "description": "Écraser si le fichier existe déjà", "default": False},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "read_file",
        "description": "Lit et retourne le contenu d'un fichier.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Chemin du fichier à lire"},
                "max_chars": {"type": "integer", "description": "Nombre max de caractères à retourner", "default": 8000},
            },
            "required": ["path"],
        },
    },
    {
        "name": "list_directory",
        "description": "Liste le contenu d'un dossier.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Chemin du dossier", "default": "."},
                "show_hidden": {"type": "boolean", "description": "Afficher les fichiers cachés", "default": False},
            },
        },
    },
    {
        "name": "delete_file",
        "description": "Supprime un fichier ou dossier.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Chemin du fichier/dossier à supprimer"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "create_directory",
        "description": "Crée un dossier (et ses parents si nécessaire).",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Chemin du dossier à créer"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "move_file",
        "description": "Déplace ou renomme un fichier/dossier.",
        "input_schema": {
            "type": "object",
            "properties": {
                "src": {"type": "string", "description": "Chemin source"},
                "dst": {"type": "string", "description": "Chemin destination"},
            },
            "required": ["src", "dst"],
        },
    },
    {
        "name": "run_shell_command",
        "description": "Exécute une commande shell sur l'appareil (bash, cmd, etc.).",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "La commande shell à exécuter"},
                "cwd": {"type": "string", "description": "Dossier de travail (optionnel)"},
                "timeout": {"type": "integer", "description": "Timeout en secondes", "default": 30},
            },
            "required": ["command"],
        },
    },
    {
        "name": "run_python_script",
        "description": "Exécute du code Python directement.",
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Code Python à exécuter"},
                "timeout": {"type": "integer", "description": "Timeout en secondes", "default": 30},
            },
            "required": ["code"],
        },
    },
    {
        "name": "get_system_info",
        "description": "Retourne les informations système (OS, Python, home directory, etc.).",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "web_search",
        "description": "Effectue une recherche sur le web et retourne les résultats.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "La requête de recherche"},
                "max_results": {"type": "integer", "description": "Nombre max de résultats", "default": 5},
            },
            "required": ["query"],
        },
    },
    {
        "name": "fetch_url",
        "description": "Récupère le contenu texte d'une URL web.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "L'URL à récupérer"},
                "max_chars": {"type": "integer", "description": "Nombre max de caractères", "default": 5000},
            },
            "required": ["url"],
        },
    },
    {
        "name": "open_app",
        "description": "Ouvre une application ou un logiciel sur l'appareil.",
        "input_schema": {
            "type": "object",
            "properties": {
                "app_name": {"type": "string", "description": "Nom de l'application à ouvrir (ex: firefox, code, vlc)"},
            },
            "required": ["app_name"],
        },
    },
    {
        "name": "open_url_in_browser",
        "description": "Ouvre une URL dans le navigateur par défaut.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL à ouvrir"},
            },
            "required": ["url"],
        },
    },
    {
        "name": "list_running_processes",
        "description": "Liste les processus/applications en cours d'exécution.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "list_connected_devices",
        "description": "Liste les appareils (workers) actuellement connectés au serveur, "
                       "avec leur device_id et leur OS. À utiliser AVANT d'exécuter un tool "
                       "sur un autre appareil pour connaître les target_device disponibles.",
        "input_schema": {"type": "object", "properties": {}},
    },
]

# Tools qui interagissent avec le matériel/OS et acceptent un target_device.
# (web_search, fetch_url, list_connected_devices ne sont pas device-bound.)
_DEVICE_BOUND_TOOLS = {
    "create_file", "read_file", "list_directory", "delete_file", "create_directory",
    "move_file", "run_shell_command", "run_python_script", "get_system_info",
    "open_app", "open_url_in_browser", "list_running_processes",
}

# Augmente le schéma de chaque tool device-bound avec un paramètre target_device optionnel.
for _tool in TOOLS:
    if _tool["name"] in _DEVICE_BOUND_TOOLS:
        _tool["input_schema"].setdefault("properties", {})["target_device"] = {
            "type": "string",
            "description": "device_id de l'appareil cible (ex: 'mon-telephone'). Omettre ou 'server' "
                           "pour exécuter sur le serveur. Utilise list_connected_devices d'abord.",
        }

# ─────────────────────────────────────────────────────────────────
# Prompt système de Jarvis
# ─────────────────────────────────────────────────────────────────
MAX_ITERATIONS = 25

SYSTEM_PROMPT = """Tu es Jarvis, un assistant IA personnel ultra-compétent.
Tu travailles directement sur l'appareil de l'utilisateur.

Tes capacités :
- Créer, lire, modifier, supprimer des fichiers et dossiers
- Exécuter des commandes shell et scripts Python
- Rechercher sur le web et lire des pages web
- Ouvrir des applications et logiciels

Principes :
- Sois proactif : si tu dois créer un fichier Python, crée-le ET exécute-le si c'est logique
- Confirme chaque action effectuée avec son résultat
- Si une commande échoue, propose une alternative
- Réponds en français sauf si on te parle dans une autre langue
- Pour les tâches complexes, décompose et exécute étape par étape
- Ne demande pas confirmation pour des actions non-destructives
- Pour supprimer/écraser des fichiers importants, confirme d'abord

Tu es sur l'appareil de l'utilisateur. Agis comme un assistant technique de confiance."""


# ─────────────────────────────────────────────────────────────────
# Moteur d'exécution
# ─────────────────────────────────────────────────────────────────
def execute_tool(tool_name: str, tool_input: dict, dispatcher=None, list_devices=None) -> str:
    """Exécute un tool et retourne le résultat en JSON string.

    Args:
        tool_name: Nom du tool Claude.
        tool_input: Paramètres ; peut contenir un 'target_device' optionnel.
        dispatcher: Callback (device_id, tool_name, tool_input) -> result_str
                    pour exécution sur un appareil distant.
        list_devices: Callback () -> list[dict] pour le tool list_connected_devices.
    """
    # Cas spécial : tool de listing géré côté serveur
    if tool_name == "list_connected_devices":
        if list_devices is None:
            return json.dumps({"success": True, "devices": [], "message": "Mode standalone : aucun appareil distant."})
        return json.dumps({"success": True, "devices": list_devices()}, ensure_ascii=False)

    # Extraction du target_device (présent uniquement sur les tools device-bound)
    tool_input = dict(tool_input)  # copie défensive
    target = tool_input.pop("target_device", None)

    if target and target not in ("", "server", "local") and dispatcher is not None:
        # Exécution distante via le dispatcher (worker WebSocket)
        try:
            return dispatcher(target, tool_name, tool_input)
        except Exception as e:
            return json.dumps({"success": False, "error": f"Dispatch vers '{target}' a échoué : {e}"})

    # Exécution locale
    handler = ALL_HANDLERS.get(tool_name)
    if not handler:
        return json.dumps({"success": False, "error": f"Tool inconnu : {tool_name}"})
    try:
        result = handler(tool_input)
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


def process_request(
    user_message: str,
    conversation_history: list = None,
    on_tool_call=None,
    dispatcher=None,
    list_devices=None,
) -> tuple[str, list]:
    """
    Traite une requête utilisateur avec boucle agentic.
    
    Args:
        user_message: Le message de l'utilisateur
        conversation_history: Historique de la conversation (modifié in-place)
        on_tool_call: Callback(tool_name, tool_input, result) appelé à chaque tool use
    
    Returns:
        (réponse_finale, historique_mis_à_jour)
    """
    if conversation_history is None:
        conversation_history = []

    # Ajoute le message utilisateur
    conversation_history.append({"role": "user", "content": user_message})

    final_response = ""
    provider = _get_provider()

    for _ in range(MAX_ITERATIONS):
        response = provider.call(
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=conversation_history,
            max_tokens=4096,
        )

        tool_uses = [b for b in response.content if b["type"] == "tool_use"]
        text_parts = [b["text"] for b in response.content if b["type"] == "text"]

        if text_parts:
            final_response = "\n".join(text_parts)

        # On stocke en dicts purs (pivot) — compatible Anthropic ET Gemini au tour suivant
        conversation_history.append({"role": "assistant", "content": response.content})

        if not tool_uses:
            return final_response, conversation_history

        tool_results = []
        for tool_block in tool_uses:
            result = execute_tool(
                tool_block["name"], tool_block["input"],
                dispatcher=dispatcher, list_devices=list_devices,
            )
            if on_tool_call:
                on_tool_call(tool_block["name"], tool_block["input"], result)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_block["id"],
                "content": result,
            })

        conversation_history.append({"role": "user", "content": tool_results})

    if not final_response:
        final_response = f"[Limite de {MAX_ITERATIONS} itérations atteinte]"
    return final_response, conversation_history
