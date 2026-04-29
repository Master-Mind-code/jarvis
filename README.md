# 🤖 Jarvis — Assistant IA Personnel

Un assistant IA autonome multi-appareils, inspiré de Jarvis (Iron Man).
Cerveau interchangeable : **Anthropic Claude** ou **Google Gemini** · Outils : fichiers, shell, Python, web, apps.
Interface : CLI ou UI navigateur (avec voix d'entrée/sortie + animation morphing).

---

## 🚀 Installation rapide

### 1. Récupérer le projet

```bash
cd ~
# Si git installé :
git clone <ton-repo> jarvis
# Sinon, copie le dossier jarvis/
cd jarvis
```

### 2. Installer les dépendances

```bash
pip install -r requirements.txt
```

### 3. Configurer les variables d'environnement

```bash
cp .env.example .env
# Édite .env avec ton éditeur préféré
```

Choisis ton provider et remplis les clés correspondantes :

```bash
# Provider à utiliser : "anthropic" (par défaut) ou "gemini"
JARVIS_PROVIDER=anthropic

# Pour Anthropic (https://console.anthropic.com)
ANTHROPIC_API_KEY=sk-ant-...

# OU pour Gemini gratuit (https://aistudio.google.com/apikey)
GEMINI_API_KEY=...

JARVIS_SECRET_TOKEN=un_mot_de_passe_fort_pour_le_serveur
```

### 4. Lancer Jarvis

```bash
# Lanceur interactif (recommandé)
python start.py

# Ou direct :
python start.py server      # serveur + ouverture de l'UI navigateur
python start.py cli         # CLI standalone (sans serveur)
python start.py worker      # mode worker (sur un appareil distant)
```

Sous Windows : double-clic sur `start.bat`. Sous Linux/macOS/Termux : `./start.sh`.

---

## 🧠 Choisir son provider LLM

Jarvis fonctionne avec deux fournisseurs interchangeables :

| Provider             | Modèle par défaut    | Coût                            | Quotas                          | Tool use     |
| -------------------- | -------------------- | ------------------------------- | ------------------------------- | ------------ |
| **Anthropic Claude** | `claude-sonnet-4-6`  | Payant (~3$/M tokens entrée)    | Selon plan                      | ⭐ Excellent |
| **Google Gemini**    | `gemini-2.0-flash`   | **Gratuit**                     | ~15 req/min, 1M tokens/jour     | ✅ Bon       |

Pour basculer : modifie `JARVIS_PROVIDER` dans `.env`. Aucun autre changement requis.

Pour changer de modèle dans le même provider :

- Anthropic : `JARVIS_ANTHROPIC_MODEL=claude-haiku-4-5-20251001`
- Gemini : `JARVIS_GEMINI_MODEL=gemini-2.0-flash-exp` (ou `gemini-1.5-pro`, etc.)

---

## 🖥️ Interface UI navigateur

Ouvre `jarvis_ui.html` dans ton navigateur (ou laisse `start.py server` le faire).

Fonctionnalités :

- **Mot de passe au lancement** : "Press on" (à la voix ou au clavier)
- **Animation morphing** : la sphère se transforme automatiquement en étoile, puis en lettres "DOMINIQUE", puis revient (toutes les 7s)
- **Reconnaissance vocale** (🎤 micro) : parle directement à Jarvis en français
- **Synthèse vocale** : Jarvis te répond à la voix (voix masculine grave si disponible)
- **États visuels** : la sphère change de couleur selon l'état (bleu = idle, rouge = écoute, doré = traitement, vert = parle)

Compatible Chrome, Edge et Safari (Firefox n'a pas la Web Speech API).

---

## 📱 Mode multi-appareils RÉEL

Contrairement à un simple proxy de chat, Jarvis peut **exécuter des tools sur n'importe quel appareil connecté**.

### Architecture

```text
┌─────────────┐                ┌──────────────────────┐                ┌──────────────┐
│  UI / chat  │ ─────WS──────→ │  Serveur central     │ ─── RPC ────→  │  Worker PC   │
│ (browser)   │ ←──── reply ── │  (Claude / Gemini)   │ ←── result ──  │              │
└─────────────┘                └──────────────────────┘                └──────────────┘
                                          ↑                                    ↓
                                          │  RPC ← result               Worker Téléphone
                                          │       (Termux)
                                          ↓
                                   Worker maison-pi (Raspberry…)
```

### Sur l'appareil principal (serveur)

```bash
python start.py server
```

### Sur chaque autre appareil (PC secondaire, téléphone Termux…)

```bash
export JARVIS_SERVER_URL="ws://IP_DU_SERVEUR:8765"
export JARVIS_SECRET_TOKEN="le_token_du_serveur"
export JARVIS_DEVICE_ID="telephone-dominique"
python start.py worker
```

L'appareil s'enregistre automatiquement avec son OS, hostname et liste de tools.

### Cibler un appareil depuis le chat

```text
"Liste les appareils connectés"
→ Claude/Gemini appelle list_connected_devices

"Ouvre Firefox sur telephone-dominique"
→ open_app(app_name="firefox", target_device="telephone-dominique")
→ s'exécute physiquement sur le téléphone
```

Tools cibles supportés (`target_device`) : `create_file`, `read_file`, `list_directory`, `delete_file`, `create_directory`, `move_file`, `run_shell_command`, `run_python_script`, `get_system_info`, `open_app`, `open_url_in_browser`, `list_running_processes`.

⚠️ **Limite actuelle** : montre connectée et TV ne sont pas supportées en l'état (pas de runtime Python). Pour intégrer une TV, utilise un Raspberry Pi à proximité comme worker.

---

## 💬 Exemples de commandes

```text
"Crée un fichier Python qui calcule les fibonacci et exécute-le"
"Recherche sur le web les dernières news sur Claude AI"
"Liste mon dossier home et crée un résumé"
"Ouvre Firefox sur youtube.com"
"Crée un script bash de backup et sauvegarde-le dans ~/scripts/"
"Quel est l'état de mes processus en cours ?"
"Lis mon fichier config.json et explique-moi ce qu'il fait"
"Liste les appareils connectés puis ouvre Spotify sur le téléphone"
```

---

## 🗂 Structure du projet

```text
jarvis/
├── server/
│   ├── __init__.py
│   ├── main.py              # Serveur FastAPI WebSocket (controllers + workers)
│   ├── orchestrator.py      # Boucle agentic + dispatcher des tools
│   ├── providers/
│   │   ├── __init__.py      # get_provider() — sélection par JARVIS_PROVIDER
│   │   ├── base.py          # Interface Provider (format pivot Anthropic)
│   │   ├── anthropic_provider.py
│   │   └── gemini_provider.py
│   └── tools/
│       ├── __init__.py      # ALL_HANDLERS agrégé
│       ├── file_manager.py
│       ├── code_runner.py
│       ├── web_search.py
│       └── app_launcher.py
├── agent/
│   ├── __init__.py
│   └── agent.py             # Client multi-mode : worker (RPC) ou controller (chat)
├── interface/
│   ├── __init__.py
│   └── cli.py               # CLI standalone (rich + prompt_toolkit)
├── jarvis_ui.html           # UI navigateur (sphère 3D, voix, mot de passe)
├── start.py                 # Lanceur unifié (menu interactif + sous-commandes)
├── start.bat / start.sh     # Wrappers Windows / Unix
├── .env.example
├── requirements.txt
└── README.md
```

---

## 🔒 Sécurité

- **Mot de passe UI** : "Press on" déverrouille le navigateur (côté client uniquement)
- **Token serveur** : `JARVIS_SECRET_TOKEN` — toute connexion WebSocket est rejetée sans
- **Chemins système bloqués** : `/etc/passwd`, `/etc/shadow`, `/boot`, `/sys`, `/proc` (Linux)
- **Patterns shell dangereux filtrés** : `rm -rf /`, `mkfs`, `dd if=`, fork bomb, etc.
- ⚠️ La protection `BLOCKED_PATHS` est principalement Unix — sous Windows, restez prudent
- ⚠️ N'expose **jamais** le serveur sur internet sans Tailscale/HTTPS et un token fort
- ⚠️ Ne commit jamais `.env` — ajoute-le au `.gitignore`

---

## 🌐 Accès depuis l'extérieur (Tailscale)

Pour accéder à Jarvis depuis n'importe où sans ouvrir de port :

1. Installe [Tailscale](https://tailscale.com) sur chaque appareil (gratuit)
2. Utilise l'IP Tailscale du serveur (`100.x.y.z`) au lieu de l'IP locale
3. Tunnel WireGuard chiffré bout-en-bout, sans port exposé

---

## 🔧 Commandes du lanceur

| Commande                       | Effet                                  |
| ------------------------------ | -------------------------------------- |
| `python start.py`              | Menu interactif                        |
| `python start.py server`       | Lance le serveur + ouvre l'UI          |
| `python start.py cli`          | CLI standalone (sans serveur)          |
| `python start.py worker`       | Connecte cet appareil comme worker     |
| `python start.py controller`   | Chat distant via le serveur            |
| `python start.py ui`           | Ouvre seulement l'UI navigateur        |

---

## ➕ Ajouter un nouveau tool

1. Ajoute une fonction dans `server/tools/ton_tool.py` qui retourne un `dict` `{"success": bool, ...}`
2. Ajoute-la au mapping `HANDLERS` à la fin du fichier
3. Importe-la dans `server/tools/__init__.py` et fusionne dans `ALL_HANDLERS`
4. Définis le schéma JSON dans la liste `TOOLS` de `server/orchestrator.py`
5. Si le tool interagit avec le matériel, ajoute-le au set `_DEVICE_BOUND_TOOLS` (juste après la liste `TOOLS`) — il acceptera automatiquement un `target_device`
6. C'est tout — Claude **et** Gemini l'utiliseront automatiquement, en local ou en RPC distant

---

## 🎤 Voix : reconnaissance et synthèse

L'UI utilise les **Web Speech API** natives du navigateur :

- **Reconnaissance vocale** (🎤 dans la barre d'input) : parle, ton message est transcrit en texte et envoyé. Lang : `fr-FR`.
- **Synthèse vocale** : chaque réponse de Jarvis est lue à voix haute. La voix masculine française est privilégiée si disponible (Paul, Thomas, Daniel…). Le markdown est nettoyé avant lecture.

Aucun service cloud requis pour la voix — tout passe par le navigateur, hors-ligne.

Pour désactiver la lecture audio : ouvre la console du navigateur et tape `window.speechSynthesis.cancel()` (ou commente l'appel `speak(data.content)` dans `jarvis_ui.html`).
