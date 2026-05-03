"""
Orion — Orchestrateur Central
Cerveau de l'assistant : reçoit une requête, appelle un LLM (Anthropic ou Gemini),
exécute les tools, retourne la réponse finale.

Provider sélectionné via ORION_PROVIDER (défaut: anthropic).
"""
import os
import json
from pathlib import Path
from dotenv import load_dotenv
from branding import sync_env_aliases

# Charge .env depuis la racine du projet AVANT d'instancier les clients LLM
# (sinon les variables ne sont pas encore définies quand main.py importe ce module).
load_dotenv(Path(__file__).resolve().parent.parent / ".env")
sync_env_aliases()

from server.tools import ALL_HANDLERS
from server.providers import get_provider, ProviderResponse
from server import confirm
from server import audit
from server import safety_backup
from server import rate_limit
from server import panic

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
    {
        "name": "gmail_search",
        "description": "Cherche des emails dans la boîte Gmail de l'utilisateur. "
                       "Utilise la syntaxe Gmail standard pour la query "
                       "(ex: 'is:unread', 'from:boss@example.com', 'subject:facture'). "
                       "Retourne id, expéditeur, sujet, date, snippet et statut unread.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Query Gmail (ex: 'is:unread newer_than:2d')", "default": ""},
                "max_results": {"type": "integer", "description": "Nombre max d'emails (1-50)", "default": 10},
            },
        },
    },
    {
        "name": "gmail_read_message",
        "description": "Lit le contenu complet d'un email Gmail (corps texte, headers).",
        "input_schema": {
            "type": "object",
            "properties": {
                "message_id": {"type": "string", "description": "ID Gmail du message (obtenu via gmail_search)"},
                "max_chars": {"type": "integer", "description": "Tronque le corps à N caractères", "default": 8000},
            },
            "required": ["message_id"],
        },
    },
    {
        "name": "calendar_list_events",
        "description": "Liste les événements à venir dans Google Calendar. "
                       "Par défaut : 10 événements sur les 7 prochains jours.",
        "input_schema": {
            "type": "object",
            "properties": {
                "max_results": {"type": "integer", "description": "Nombre max d'événements (1-50)", "default": 10},
                "days_ahead": {"type": "integer", "description": "Fenêtre de jours à venir", "default": 7},
                "calendar_id": {"type": "string", "description": "ID du calendrier (défaut: 'primary')", "default": "primary"},
            },
        },
    },
    {
        "name": "calendar_create_event",
        "description": "Crée un événement dans Google Calendar. Les dates doivent être en ISO 8601 "
                       "(ex: '2026-05-15T14:00:00+02:00'). Utiliser 'YYYY-MM-DD' pour journée entière.",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "Titre de l'événement"},
                "start": {"type": "string", "description": "Début ISO 8601 ou YYYY-MM-DD"},
                "end": {"type": "string", "description": "Fin ISO 8601 ou YYYY-MM-DD"},
                "description": {"type": "string", "description": "Description (optionnel)"},
                "location": {"type": "string", "description": "Lieu (optionnel)"},
                "attendees": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Liste d'emails des participants (optionnel)",
                },
                "calendar_id": {"type": "string", "description": "ID du calendrier (défaut: 'primary')", "default": "primary"},
            },
            "required": ["summary", "start", "end"],
        },
    },
    # ─── Notifications système ────────────────────────────────
    {
        "name": "notify",
        "description": "Affiche une notification système (toast Windows / libnotify Linux / osascript macOS).",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Titre de la notification"},
                "message": {"type": "string", "description": "Corps du message"},
                "duration": {"type": "string", "description": "short | long (Windows uniquement)", "default": "short"},
            },
            "required": ["title"],
        },
    },
    # ─── Capture d'écran ──────────────────────────────────────
    {
        "name": "screenshot",
        "description": "Capture d'écran. Sans région : tout l'écran. Sauvegardé en PNG.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Chemin du fichier de sortie (auto si vide)"},
                "monitor": {"type": "integer", "description": "0=tous, 1+=écran spécifique", "default": 0},
                "region": {
                    "type": "object",
                    "properties": {
                        "x": {"type": "integer"},
                        "y": {"type": "integer"},
                        "width": {"type": "integer"},
                        "height": {"type": "integer"},
                    },
                    "description": "Région à capturer (optionnel)",
                },
                "return_base64": {"type": "boolean", "description": "Inclure l'image en base64 dans la réponse", "default": False},
            },
        },
    },
    {
        "name": "list_monitors",
        "description": "Liste les écrans connectés (résolution, position).",
        "input_schema": {"type": "object", "properties": {}},
    },
    # ─── Documents ────────────────────────────────────────────
    {
        "name": "read_pdf",
        "description": "Extrait le texte d'un fichier PDF (texte natif uniquement, pas d'OCR).",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Chemin du PDF"},
                "max_chars": {"type": "integer", "description": "Tronquer à N caractères", "default": 8000},
                "pages": {"type": "string", "description": "Range optionnel : '1-5' ou '3'"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "read_docx",
        "description": "Extrait le texte d'un fichier Word (.docx). Inclut les tableaux.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Chemin du .docx"},
                "max_chars": {"type": "integer", "description": "Tronquer à N caractères", "default": 8000},
            },
            "required": ["path"],
        },
    },
    # ─── Automation souris/clavier ────────────────────────────
    {
        "name": "mouse_position",
        "description": "Retourne la position actuelle de la souris (lecture, toujours autorisée).",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "mouse_move",
        "description": "Déplace la souris vers (x, y). Nécessite ORION_AUTOMATION_ENABLED=true.",
        "input_schema": {
            "type": "object",
            "properties": {
                "x": {"type": "integer"},
                "y": {"type": "integer"},
                "duration": {"type": "number", "description": "Durée du mouvement en secondes", "default": 0.2},
            },
            "required": ["x", "y"],
        },
    },
    {
        "name": "mouse_click",
        "description": "Click souris. Sans coordonnées : à la position actuelle. Nécessite ORION_AUTOMATION_ENABLED=true.",
        "input_schema": {
            "type": "object",
            "properties": {
                "x": {"type": "integer"},
                "y": {"type": "integer"},
                "button": {"type": "string", "description": "left | right | middle", "default": "left"},
                "clicks": {"type": "integer", "default": 1},
            },
        },
    },
    {
        "name": "keyboard_type",
        "description": "Tape du texte au clavier. Nécessite ORION_AUTOMATION_ENABLED=true.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "interval": {"type": "number", "description": "Délai entre chaque caractère", "default": 0.02},
            },
            "required": ["text"],
        },
    },
    {
        "name": "keyboard_press",
        "description": "Appuie sur une touche ou une combinaison. "
                       "Touche unique : 'enter', 'esc', 'f5'. Hotkey : ['ctrl', 'c'] = Ctrl+C. "
                       "Nécessite ORION_AUTOMATION_ENABLED=true.",
        "input_schema": {
            "type": "object",
            "properties": {
                "keys": {
                    "oneOf": [
                        {"type": "string"},
                        {"type": "array", "items": {"type": "string"}},
                    ],
                    "description": "'enter' OU ['ctrl','c']",
                },
            },
            "required": ["keys"],
        },
    },
    # ─── Génération d'images ──────────────────────────────────
    {
        "name": "generate_image",
        "description": "Génère une image depuis un prompt texte via Google Gemini Imagen. "
                       "Sauvegardée en PNG dans data/images/. Nécessite GEMINI_API_KEY.",
        "input_schema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Description de l'image à générer"},
                "output_path": {"type": "string", "description": "Chemin du fichier de sortie (auto si vide)"},
                "aspect_ratio": {"type": "string", "description": "1:1 | 3:4 | 4:3 | 9:16 | 16:9", "default": "1:1"},
                "n": {"type": "integer", "description": "Nombre d'images (1-4)", "default": 1},
                "model": {"type": "string", "description": "imagen-3.0-fast-generate-001 (défaut) ou imagen-3.0-generate-002"},
            },
            "required": ["prompt"],
        },
    },
    # ─── Mémoire long terme RAG ───────────────────────────────
    {
        "name": "memory_remember",
        "description": "Mémorise un fait, une note ou une préférence dans la mémoire long terme vectorielle. "
                       "À utiliser pour 'retiens que X', 'note que Y'. Recherchable ensuite par similarité.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Le fait à mémoriser (1 phrase ou 1 paragraphe)"},
                "source": {"type": "string", "description": "Origine ('user', 'chat', 'note')", "default": "manual"},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "Tags optionnels"},
                "namespace": {"type": "string", "description": "Espace mémoire séparé", "default": "default"},
            },
            "required": ["text"],
        },
    },
    {
        "name": "memory_recall",
        "description": "Recherche dans la mémoire long terme les souvenirs proches sémantiquement de la query. "
                       "Utilise systématiquement avant de répondre à une question personnelle de l'utilisateur.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Question ou mots-clés"},
                "top_k": {"type": "integer", "description": "Nombre de résultats", "default": 5},
                "min_score": {"type": "number", "description": "Score cosinus min [0..1]", "default": 0.25},
                "namespace": {"type": "string", "description": "Espace mémoire à interroger", "default": "default"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "memory_forget",
        "description": "Supprime un souvenir par son ID (obtenu via memory_recall ou memory_list).",
        "input_schema": {
            "type": "object",
            "properties": {
                "item_id": {"type": "string"},
                "namespace": {"type": "string", "default": "default"},
            },
            "required": ["item_id"],
        },
    },
    {
        "name": "memory_clear",
        "description": "Vide entièrement un namespace de mémoire (DESTRUCTIF, demander confirmation).",
        "input_schema": {
            "type": "object",
            "properties": {
                "namespace": {"type": "string", "default": "default"},
                "confirm": {"type": "boolean", "description": "Doit être true pour exécuter", "default": False},
            },
        },
    },
    {
        "name": "memory_stats",
        "description": "Compteurs mémoire : nombre d'entrées par namespace, par source.",
        "input_schema": {
            "type": "object",
            "properties": {
                "namespace": {"type": "string", "description": "Namespace spécifique (sinon tous)"},
            },
        },
    },
    {
        "name": "memory_list",
        "description": "Liste les N derniers souvenirs d'un namespace (debug ou exploration).",
        "input_schema": {
            "type": "object",
            "properties": {
                "namespace": {"type": "string", "default": "default"},
                "limit": {"type": "integer", "default": 50},
                "source": {"type": "string", "description": "Filtre optionnel sur source"},
            },
        },
    },
    {
        "name": "memory_index_file",
        "description": "Indexe le contenu d'un fichier (PDF, DOCX, TXT, MD, code) dans la mémoire vectorielle. "
                       "Découpe automatique en chunks de ~800 caractères.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Chemin du fichier"},
                "namespace": {"type": "string", "default": "default"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "chunk_chars": {"type": "integer", "default": 800},
            },
            "required": ["path"],
        },
    },
    {
        "name": "memory_index_dir",
        "description": "Indexe récursivement un dossier dans la mémoire vectorielle. "
                       "Par défaut : pdf, docx, txt, md, py, js, ts, json, yml.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Chemin du dossier"},
                "namespace": {"type": "string", "default": "default"},
                "extensions": {"type": "array", "items": {"type": "string"}, "description": "Extensions à inclure (sans le point)"},
                "recursive": {"type": "boolean", "default": True},
                "max_files": {"type": "integer", "default": 100},
            },
            "required": ["path"],
        },
    },
    # ─── Tools mobiles (worker Termux/Android uniquement) ─────
    {
        "name": "termux_battery",
        "description": "État de la batterie du téléphone (worker Termux). Utiliser target_device.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "termux_location",
        "description": "Position GPS du téléphone (worker Termux).",
        "input_schema": {
            "type": "object",
            "properties": {
                "provider": {"type": "string", "description": "network | gps | passive", "default": "network"},
            },
        },
    },
    {
        "name": "termux_send_sms",
        "description": "Envoie un SMS depuis le téléphone (worker Termux).",
        "input_schema": {
            "type": "object",
            "properties": {
                "number": {"type": "string", "description": "+33... ou 06..."},
                "text": {"type": "string"},
            },
            "required": ["number", "text"],
        },
    },
    {
        "name": "termux_list_sms",
        "description": "Liste les derniers SMS reçus (worker Termux).",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 10},
            },
        },
    },
    {
        "name": "termux_contacts",
        "description": "Liste les contacts du téléphone (worker Termux).",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "termux_call",
        "description": "Lance un appel téléphonique (worker Termux).",
        "input_schema": {
            "type": "object",
            "properties": {"number": {"type": "string"}},
            "required": ["number"],
        },
    },
    {
        "name": "termux_vibrate",
        "description": "Fait vibrer le téléphone (worker Termux).",
        "input_schema": {
            "type": "object",
            "properties": {
                "duration_ms": {"type": "integer", "default": 500},
            },
        },
    },
    {
        "name": "termux_notification",
        "description": "Notification dans la barre de notif Android (worker Termux).",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["title"],
        },
    },
    {
        "name": "termux_clipboard_get",
        "description": "Lit le presse-papier du téléphone (worker Termux).",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "termux_clipboard_set",
        "description": "Écrit dans le presse-papier du téléphone (worker Termux).",
        "input_schema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    },
    {
        "name": "termux_torch",
        "description": "Allume/éteint la lampe torche du téléphone (worker Termux).",
        "input_schema": {
            "type": "object",
            "properties": {"on": {"type": "boolean", "default": True}},
        },
    },
    # ─── Backups (récupération si Orion supprime/écrase) ──────
    {
        "name": "list_backups",
        "description": "Liste les sauvegardes automatiques créées avant chaque "
                       "delete_file/move_file. Permet de retrouver et restaurer.",
        "input_schema": {
            "type": "object",
            "properties": {
                "hours": {"type": "number", "description": "Fenêtre temporelle", "default": 24},
                "limit": {"type": "integer", "description": "Max d'entrées", "default": 50},
            },
        },
    },
    {
        "name": "restore_backup",
        "description": "Restaure une sauvegarde. Sans target → restaure à l'emplacement original.",
        "input_schema": {
            "type": "object",
            "properties": {
                "backup_path": {"type": "string", "description": "Chemin du .bak (obtenu via list_backups)"},
                "target":      {"type": "string", "description": "Cible alternative (optionnel)"},
                "overwrite":   {"type": "boolean", "description": "Écraser la cible existante", "default": False},
            },
            "required": ["backup_path"],
        },
    },
    {
        "name": "purge_backups",
        "description": "Supprime les backups plus vieux que N jours. DESTRUCTIF, demande confirm.",
        "input_schema": {
            "type": "object",
            "properties": {
                "older_than_days": {"type": "integer", "default": 30},
                "confirm":         {"type": "boolean", "default": False},
            },
        },
    },
    # ─── Audit log (consultation des actions passées) ─────────
    {
        "name": "audit_recent",
        "description": "Liste les actions récentes exécutées par Orion (audit log). "
                       "Utilise pour répondre à 'qu'est-ce que tu as fait ?', "
                       "'liste les actions sensibles', 'erreurs récentes'. "
                       "Retourne timestamp, device, tool, succès, durée.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit":  {"type": "integer", "description": "Nombre max d'entrées (1-100)", "default": 20},
                "hours":  {"type": "number",  "description": "Fenêtre temporelle en heures", "default": 24},
                "sensitive_only": {"type": "boolean", "description": "Filtrer sur actions sensibles uniquement", "default": False},
                "failed_only":    {"type": "boolean", "description": "Filtrer sur échecs uniquement", "default": False},
            },
        },
    },
    {
        "name": "audit_stats",
        "description": "Statistiques agrégées de l'audit log : total, succès, échecs, "
                       "actions sensibles, top 5 des tools les plus utilisés.",
        "input_schema": {
            "type": "object",
            "properties": {
                "hours": {"type": "number", "description": "Fenêtre temporelle en heures", "default": 24},
            },
        },
    },
    # ─── Vision (analyse d'image) ─────────────────────────────
    {
        "name": "analyze_image",
        "description": "Analyse une image (PNG, JPG, etc.) et retourne une description textuelle. "
                       "Utilise Claude/Gemini Vision. Combine avec screenshot pour 'regarde mon écran et dis-moi…'. "
                       "Idéal pour : décrire une photo, lire le texte d'une capture, analyser un graphique, "
                       "comprendre une erreur visible à l'écran.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Chemin de l'image (PNG, JPG, GIF, WebP, BMP)"},
                "prompt": {
                    "type": "string",
                    "description": "Question ou consigne sur l'image (ex: 'lis le texte', 'décris', 'que voit-on ?')",
                    "default": "Décris cette image en détail.",
                },
                "provider": {
                    "type": "string",
                    "description": "anthropic | gemini | ollama (défaut: provider Orion courant)",
                },
            },
            "required": ["path"],
        },
    },
]

# Tools qui interagissent avec le matériel/OS et acceptent un target_device.
# (web_search, fetch_url, list_connected_devices, gmail_*, calendar_*,
#  generate_image, memory_* ne sont pas device-bound : ils tournent sur le serveur.)
_DEVICE_BOUND_TOOLS = {
    "create_file", "read_file", "list_directory", "delete_file", "create_directory",
    "move_file", "run_shell_command", "run_python_script", "get_system_info",
    "open_app", "open_url_in_browser", "list_running_processes",
    # Nouveaux device-bound
    "notify", "screenshot", "list_monitors", "read_pdf", "read_docx",
    "mouse_position", "mouse_move", "mouse_click", "keyboard_type", "keyboard_press",
    # Tools Termux : ne s'exécutent QUE sur worker Android
    "termux_battery", "termux_location", "termux_send_sms", "termux_list_sms",
    "termux_contacts", "termux_call", "termux_vibrate", "termux_notification",
    "termux_clipboard_get", "termux_clipboard_set", "termux_torch",
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
# Prompt système d'Orion
# ─────────────────────────────────────────────────────────────────
MAX_ITERATIONS = 25

SYSTEM_PROMPT = """Tu es Orion, un assistant IA personnel ultra-compétent.
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

# Suffixe ajouté quand l'utilisateur parle via le service voix (device_id "voice-*").
# Le TTS lit le texte tel quel : pas de markdown, pas d'emoji, phrases courtes.
VOICE_SYSTEM_SUFFIX = """

═══ MODE VOCAL ACTIF ═══
L'utilisateur te parle via micro. Tes réponses sont lues à haute voix par un TTS.
Règles strictes pour la voix :
- AUCUN emoji, AUCUN caractère décoratif (😊 ✓ → etc.). Le TTS les prononce.
- AUCUN markdown : pas de **gras**, pas d'*italique*, pas de listes à puces, pas de #titres.
- AUCUN bloc de code : si tu dois donner du code, dis "le code est dans le fichier X".
- Phrases COURTES et naturelles (max 2-3 phrases par réponse en général).
- Pas de salutations longues. Va à l'essentiel.
- Si tu lances une action longue (web_search, fetch_url), annonce d'abord en une phrase :
  "Je cherche…" puis donne le résultat.
- Si l'utilisateur demande quelque chose d'ambigu, pose UNE question courte plutôt
  que de proposer 5 options."""


def _build_system_prompt(device_id: str | None = None) -> str:
    """Construit le system prompt avec adaptations contextuelles."""
    prompt = SYSTEM_PROMPT
    if device_id and device_id.startswith("voice-"):
        prompt += VOICE_SYSTEM_SUFFIX
    return prompt


# ─────────────────────────────────────────────────────────────────
# Moteur d'exécution
# ─────────────────────────────────────────────────────────────────
def execute_tool(tool_name: str, tool_input: dict, dispatcher=None,
                 list_devices=None, device_id: str | None = None) -> str:
    """Exécute un tool et retourne le résultat en JSON string.

    Args:
        tool_name: Nom du tool Claude.
        tool_input: Paramètres ; peut contenir un 'target_device' optionnel.
        dispatcher: Callback (device_id, tool_name, tool_input) -> result_str
                    pour exécution sur un appareil distant.
        list_devices: Callback () -> list[dict] pour le tool list_connected_devices.
        device_id:  Identifiant du client appelant (sert pour la confirmation
                    par mot de passe et l'audit log).
    """
    # Cas spécial : tool de listing géré côté serveur (pas de log intéressant)
    if tool_name == "list_connected_devices":
        if list_devices is None:
            return json.dumps({"success": True, "devices": [], "message": "Mode standalone : aucun appareil distant."})
        return json.dumps({"success": True, "devices": list_devices()}, ensure_ascii=False)

    # Extraction du target_device (présent uniquement sur les tools device-bound)
    tool_input = dict(tool_input)  # copie défensive
    target = tool_input.pop("target_device", None)

    import time as _time
    is_sensitive = confirm.requires_confirmation(tool_name, tool_input)
    confirmed = False

    # ── Mode PANIC : refus tout sauf whitelist lecture ──
    if not panic.is_tool_allowed(tool_name):
        err = (f"Mode PANIC actif — '{tool_name}' refusé. "
               f"Désactive avec POST /api/panic/release pour rétablir.")
        row_id = audit.log_tool_call(
            device_id=device_id or "?", tool_name=tool_name,
            tool_input=tool_input, success=False, error=err,
            duration_ms=0, target=target, sensitive=True, confirmed=False,
        )
        audit._trigger_alert(row_id, True,
                             tool_name=tool_name, device_id=device_id,
                             success=False, error=err, confirmed=False)
        return json.dumps({"success": False, "error": err}, ensure_ascii=False)

    # ── Rate limit sur tools sensibles (anti-abus) ──
    if device_id and is_sensitive:
        ok, reason = rate_limit.check_and_record(device_id)
        if not ok:
            row_id = audit.log_tool_call(
                device_id=device_id, tool_name=tool_name,
                tool_input=tool_input, success=False, error=reason,
                duration_ms=0, target=target, sensitive=True, confirmed=False,
            )
            audit._trigger_alert(row_id, True,
                                 tool_name=tool_name, device_id=device_id,
                                 success=False, error=reason, confirmed=False)
            return json.dumps({"success": False, "error": reason}, ensure_ascii=False)

    # ── Couche de confirmation pour actions dangereuses ──
    if device_id and is_sensitive:
        approved = confirm.request_confirmation(
            device_id=device_id,
            tool_name=tool_name,
            tool_input=tool_input,
            reason=confirm.reason_for(tool_name),
        )
        if not approved:
            err = (f"Action '{tool_name}' refusée par l'utilisateur "
                   f"(confirmation par mot de passe requise).")
            row_id = audit.log_tool_call(
                device_id=device_id or "?", tool_name=tool_name,
                tool_input=tool_input, success=False, error=err,
                duration_ms=0, target=target, sensitive=True, confirmed=False,
            )
            audit._trigger_alert(row_id, True,
                                 tool_name=tool_name, device_id=device_id,
                                 success=False, error=err, confirmed=False)
            return json.dumps({"success": False, "error": err}, ensure_ascii=False)
        confirmed = True

    # ── Backup auto avant action destructive locale ──
    # (skip si exécution distante : trop coûteux à transférer)
    if (not target or target in ("", "server", "local")):
        try:
            if tool_name == "delete_file":
                src = tool_input.get("path")
                if src:
                    safety_backup.backup_file_or_dir(src)
            elif tool_name == "move_file" and tool_input.get("dst"):
                # Si la destination existe → backup avant écrasement
                from pathlib import Path as _P
                dst = _P(tool_input["dst"]).expanduser()
                if dst.exists():
                    safety_backup.backup_file_or_dir(str(dst))
        except Exception as exc:
            print(f"[backup!] {exc}")

    # ── Exécution distante via worker ──
    t0 = _time.time()
    if target and target not in ("", "server", "local") and dispatcher is not None:
        try:
            result_str = dispatcher(target, tool_name, tool_input)
        except Exception as e:
            result_str = json.dumps({"success": False, "error": f"Dispatch vers '{target}' a échoué : {e}"})
    else:
        # Exécution locale
        handler = ALL_HANDLERS.get(tool_name)
        if not handler:
            result_str = json.dumps({"success": False, "error": f"Tool inconnu : {tool_name}"})
        else:
            try:
                result = handler(tool_input)
                result_str = json.dumps(result, ensure_ascii=False)
            except Exception as e:
                result_str = json.dumps({"success": False, "error": str(e)})
    duration_ms = int((_time.time() - t0) * 1000)

    # ── Log audit (best-effort, n'interrompt jamais le flow) ──
    try:
        result_obj = json.loads(result_str) if isinstance(result_str, str) else result_str
        success = bool(result_obj.get("success", True))
        error = (result_obj.get("error") or "")[:300]
    except Exception:
        success, error = True, ""
    row_id = audit.log_tool_call(
        device_id=device_id or "?", tool_name=tool_name,
        tool_input=tool_input, success=success, error=error,
        duration_ms=duration_ms, target=target,
        sensitive=is_sensitive, confirmed=confirmed,
    )
    audit._trigger_alert(row_id, is_sensitive,
                         tool_name=tool_name, device_id=device_id,
                         success=success, error=error,
                         confirmed=confirmed, duration_ms=duration_ms,
                         target=target)
    return result_str


def process_request(
    user_message: str,
    conversation_history: list = None,
    on_tool_call=None,
    dispatcher=None,
    list_devices=None,
    device_id: str | None = None,
) -> tuple[str, list]:
    """
    Traite une requête utilisateur avec boucle agentic.

    Args:
        user_message: Le message de l'utilisateur
        conversation_history: Historique de la conversation (modifié in-place)
        on_tool_call: Callback(tool_name, tool_input, result) appelé à chaque tool use
        device_id: ID du client appelant (sert à adapter le system prompt :
                   les sessions "voice-*" reçoivent des règles vocales).

    Returns:
        (réponse_finale, historique_mis_à_jour)
    """
    if conversation_history is None:
        conversation_history = []

    # Ajoute le message utilisateur
    conversation_history.append({"role": "user", "content": user_message})

    final_response = ""
    provider = _get_provider()
    system_prompt = _build_system_prompt(device_id)

    for _ in range(MAX_ITERATIONS):
        response = provider.call(
            system=system_prompt,
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
                device_id=device_id,
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


def process_request_streaming(
    user_message: str,
    conversation_history: list = None,
    on_text_delta=None,         # Callback(str) appelé pour chaque fragment de texte
    on_tool_call=None,          # Callback(name, input, result) après exécution d'un tool
    dispatcher=None,
    list_devices=None,
    device_id: str | None = None,
) -> tuple[str, list]:
    """
    Version streamée de process_request : appelle on_text_delta(fragment) en temps réel.

    Idéal pour réduire la latence perçue côté UI/voix : la réponse commence à
    s'afficher dès le premier token généré par le LLM, au lieu d'attendre la fin.

    Returns:
        (réponse_finale_complète, historique_mis_à_jour)
    """
    if conversation_history is None:
        conversation_history = []

    conversation_history.append({"role": "user", "content": user_message})

    final_response = ""
    provider = _get_provider()
    system_prompt = _build_system_prompt(device_id)

    for _ in range(MAX_ITERATIONS):
        response: ProviderResponse | None = None
        for chunk in provider.stream(
            system=system_prompt,
            tools=TOOLS,
            messages=conversation_history,
            max_tokens=4096,
        ):
            ctype = chunk.get("type")
            if ctype == "text_delta":
                text = chunk.get("text") or ""
                if text and on_text_delta:
                    try:
                        on_text_delta(text)
                    except Exception:
                        pass
            elif ctype == "done":
                response = chunk.get("response")

        if response is None:
            break

        tool_uses = [b for b in response.content if b.get("type") == "tool_use"]
        text_parts = [b["text"] for b in response.content if b.get("type") == "text"]
        if text_parts:
            final_response = "\n".join(text_parts)

        conversation_history.append({"role": "assistant", "content": response.content})

        if not tool_uses:
            return final_response, conversation_history

        tool_results = []
        for tool_block in tool_uses:
            result = execute_tool(
                tool_block["name"], tool_block["input"],
                dispatcher=dispatcher, list_devices=list_devices,
                device_id=device_id,
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
