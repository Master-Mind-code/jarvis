# 📡 Guide de déploiement Jarvis

Guide complet pour publier Jarvis sur GitHub et déployer un worker sur d'autres appareils (PC, téléphone Android, Raspberry Pi, etc.).

---

## ⚠️ Préalable : sécurité

Avant tout push public ou partage de fichiers :

1. **Régénère un token serveur fort** (`JARVIS_SECRET_TOKEN` dans `.env`) :

    ```bash
    python -c "import secrets; print(secrets.token_hex(32))"
    ```

    Copie le résultat dans `.env` ligne `JARVIS_SECRET_TOKEN=...`.

2. **Vérifie que `.gitignore` couvre `.env`** :

    ```bash
    git check-ignore -v .env
    ```

    Doit afficher `.gitignore:2:.env  .env`. Sinon → STOP, ne commit pas.

3. **Ne commit jamais** : `.env`, `*.key`, ou tout fichier contenant des clés API.

---

## 🐙 1. Pousser sur GitHub

### Option A — via le navigateur

1. Va sur <https://github.com/new>
2. **Repository name** : `jarvis`
3. **Privé** ✅ (recommandé)
4. **Ne coche aucune case** (README/.gitignore/license sont déjà dans le repo local)
5. Crée le repo, puis dans ton terminal local :

    ```bash
    git remote add origin https://github.com/<TON_USERNAME>/jarvis.git
    git push -u origin main
    ```

GitHub demandera ton authentification. Si tu n'as pas de Personal Access Token : <https://github.com/settings/tokens> → "Generate new token (classic)" → coche `repo`.

### Option B — via GitHub CLI

```bash
# Une fois : https://cli.github.com
gh auth login
gh repo create jarvis --private --source=. --remote=origin --push
```

### Vérification post-push

Ouvre ton repo sur github.com et **vérifie que `.env` n'apparaît PAS** dans la liste des fichiers. S'il y est : supprime le repo immédiatement et révoque toutes les clés API exposées.

---

## 📱 2. Déploiement sur Android (Termux)

### Installer Termux

⚠️ **N'installe PAS Termux depuis le Play Store** — la version y est obsolète et cassée.

1. Installe **F-Droid** : <https://f-droid.org/F-Droid.apk>
2. Dans F-Droid, cherche et installe **Termux**
3. Lance Termux

### Setup Termux

```bash
pkg update && pkg upgrade -y
pkg install -y python git rust openssl libffi clang
termux-setup-storage   # optionnel, donne accès au stockage du téléphone
```

### Cloner Jarvis

```bash
cd ~
git clone https://github.com/<TON_USERNAME>/jarvis.git
cd jarvis
```

### Installer les dépendances minimales

Sur téléphone, on installe **uniquement** ce qu'il faut pour un worker (pas le serveur, pas le LLM, pas l'UI) :

```bash
pip install -r requirements-worker.txt
```

→ ~10s d'installation au lieu de ~5min avec le `requirements.txt` complet.

### Configurer le worker

```bash
cp .env.example .env
nano .env
```

Renseigne uniquement les variables nécessaires :

```bash
JARVIS_SECRET_TOKEN=<le_meme_token_que_le_serveur_PC>
JARVIS_SERVER_URL=ws://<IP_DU_PC>:8765
JARVIS_DEVICE_ID=telephone-dominique
JARVIS_AGENT_MODE=worker
```

(Pas besoin de `ANTHROPIC_API_KEY` ni `GEMINI_API_KEY` ici — le cerveau reste sur le PC.)

### Lancer le worker

```bash
python start.py worker
```

Sortie attendue :

```text
[worker] Connexion à ws://192.168.x.x:8765/ws/worker/telephone-dominique
[worker] Enregistré comme 'telephone-dominique' (Linux)
[worker] 14 tools disponibles localement
```

### Garder le worker actif en arrière-plan

Termux s'endort quand l'écran s'éteint. Pour maintenir le worker :

```bash
# Empêche Android de tuer le process
termux-wake-lock

# Lance en arrière-plan, redirige les logs
nohup python start.py worker > jarvis.log 2>&1 &
```

Pour arrêter :

```bash
pkill -f "agent.py"
termux-wake-unlock
```

Pour voir les logs en direct : `tail -f jarvis.log`.

---

## 🍎 3. iPhone (limitation)

**Pas de support direct** : iOS interdit l'exécution de Python en arrière-plan.

**Alternative pratique** : utilise simplement **Safari sur l'IP du PC** pour parler à Jarvis comme un client de chat :

```text
http://<IP_DU_PC>:8765/jarvis_ui.html
```

(Si tu veux que l'iPhone exécute des tools localement, il faut une app native iOS — hors-périmètre de ce projet.)

---

## 🐧 4. Linux / macOS / Raspberry Pi

```bash
git clone https://github.com/<TON_USERNAME>/jarvis.git
cd jarvis

# Choix : full ou worker-only
pip install -r requirements-worker.txt    # léger (recommandé pour Pi)
# ou
pip install -r requirements.txt            # complet (serveur + LLM)

cp .env.example .env
nano .env
# configure JARVIS_SERVER_URL, JARVIS_SECRET_TOKEN, JARVIS_DEVICE_ID

./start.sh worker
```

### Démarrage automatique au boot (systemd)

Crée le service :

```bash
sudo nano /etc/systemd/system/jarvis-worker.service
```

Contenu :

```ini
[Unit]
Description=Jarvis Worker
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/jarvis
ExecStart=/usr/bin/python3 /home/pi/jarvis/start.py worker
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Active et démarre :

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now jarvis-worker
sudo systemctl status jarvis-worker
```

Logs en direct : `journalctl -u jarvis-worker -f`.

---

## 💻 5. Windows (autre PC)

```powershell
git clone https://github.com/<TON_USERNAME>/jarvis.git
cd jarvis
pip install -r requirements.txt
copy .env.example .env
notepad .env

# Configure JARVIS_SERVER_URL, JARVIS_SECRET_TOKEN, JARVIS_DEVICE_ID

.\start.bat worker
```

### Démarrage automatique

Place un raccourci de `start.bat worker` dans `shell:startup` :

1. Win+R → tape `shell:startup` → Enter
2. Crée un raccourci vers `start.bat` avec l'argument `worker`

---

## 🌐 6. Accès depuis l'extérieur (Tailscale)

Sur le réseau local (Wi-Fi, Ethernet) ça marche déjà. Pour utiliser Jarvis depuis le bureau, le métro, etc. :

1. Crée un compte gratuit sur <https://tailscale.com>
2. Installe Tailscale sur **chaque appareil** :
    - PC serveur
    - Téléphone (Tailscale est dans le Play Store et l'App Store)
    - Tous les autres workers
3. Connecte chaque appareil avec le **même compte Tailscale**
4. Récupère l'IP Tailscale du PC :

    ```bash
    tailscale ip -4
    # → ex : 100.64.1.23
    ```

5. Sur chaque worker, dans `.env` :

    ```bash
    JARVIS_SERVER_URL=ws://100.64.1.23:8765
    ```

Plus besoin de port-forwarding ni d'IP publique. Le trafic passe dans un tunnel WireGuard chiffré bout-en-bout.

---

## 🧪 7. Tester le multi-appareils

Sur le PC (serveur) :

```bash
python start.py server
```

Sur le téléphone / autre appareil (worker) :

```bash
python start.py worker
```

Dans l'UI navigateur (déverrouillée avec "Press on") tape :

```text
"Liste les appareils connectés"
```

Tu dois voir `telephone-dominique` dans la réponse. Puis :

```text
"Quel est l'OS de telephone-dominique ?"
```

Le LLM appelle `get_system_info` avec `target_device="telephone-dominique"` → le serveur RPC au téléphone → le téléphone répond avec ses infos système.

---

## 📋 Checklist post-déploiement

- [ ] Token serveur fort (≥32 chars hex), aligné entre tous les appareils
- [ ] `.env` jamais commité (vérifié sur github.com)
- [ ] Repo privé tant que pas audité 100 %
- [ ] Clés Anthropic/Gemini révoquées si exposées par accident, puis régénérées
- [ ] Tailscale installé sur tous les appareils si accès distant souhaité
- [ ] Worker téléphone testé en local avant Tailscale
- [ ] `termux-wake-lock` actif côté Android
- [ ] Service systemd activé côté Raspberry Pi

---

## 🆘 Dépannage

| Symptôme | Cause probable | Fix |
|---|---|---|
| `connection rejected (403 Forbidden)` | Tokens différents entre client et serveur | Aligne `JARVIS_SECRET_TOKEN` partout |
| `ModuleNotFoundError: server` | Lancé depuis un mauvais dossier | `cd` dans la racine du projet, ou utilise `start.py` |
| `RESOURCE_EXHAUSTED` (Gemini) | Quota gratuit absent ou épuisé | Recrée la clé via <https://aistudio.google.com/apikey> |
| `credit balance is too low` (Anthropic) | Compte sans crédit | Recharge sur <https://console.anthropic.com/settings/billing> |
| Worker se déconnecte au bout de quelques min sur Android | Économiseur d'énergie | `termux-wake-lock`, ou pin Termux dans les apps protégées |
| `pip install` lent/cassé sur Termux | Compilation native (Pydantic, cryptography) | Utilise `requirements-worker.txt` à la place |
