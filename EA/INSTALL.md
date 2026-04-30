# JarvisTrader.mq5 — Installation MetaTrader 5

## 1. Copier l'EA dans MT5

1. Dans MetaTrader 5 : **Fichier → Ouvrir le dossier de données**.
2. Va dans `MQL5/Experts/`.
3. Copies-y `JarvisTrader.mq5`.
4. Ouvre **MetaEditor** (F4 dans MT5), ouvre `JarvisTrader.mq5`, puis **Compile** (F7).

## 2. Autoriser les WebRequest vers Jarvis

1. Dans MT5 : **Outils → Options → Conseillers Experts**.
2. Coche **« Autoriser WebRequest pour les URLs listées »**.
3. Ajoute :
   - `http://127.0.0.1:8765` (Jarvis local)
   - `http://<IP_LAN>:8765` (Jarvis LAN, si tu lances le serveur depuis une autre machine)

## 3. Attacher l'EA à un graphique

1. Ouvre un graphique de **XAUUSD** (ou **XAUUSDm** sur Exness/IC Markets).
2. Drag & drop `JarvisTrader` depuis l'onglet **Conseillers Experts**.
3. Dans les paramètres :
   - `JarvisURL` : `http://127.0.0.1:8765` (ou ton IP LAN)
   - `JarvisToken` : la même valeur que `JARVIS_SECRET_TOKEN` dans `.env` à la racine du projet
   - `Symbol_` : laisse `XAUUSDm` (ou adapte au symbole exact de ton broker)
   - `RiskPercent` : 1.0 (= 1 % du compte par trade)
   - `AutoTrade` : `true` pour exécuter automatiquement les signaux
4. Onglet **Common** : coche **« Allow algorithmic trading »**.
5. Clic OK. L'icône en haut à droite du graphique doit devenir un sourire bleu.

## 4. Vérifier

1. Lance Jarvis : `python start.py server`.
2. Ouvre l'UI principale : http://localhost:8765/.
3. Clique sur le bouton **TRADING** → tu accèdes au dashboard.
4. Clique **CONNECTER** : le ticker BID/ASK doit apparaître au bout de ~15 s.
5. Clique **DÉMARRER** pour activer l'analyse Claude + l'exécution automatique.

## Endpoints exposés par Jarvis (utilisés par l'EA)

| Méthode | Endpoint                      | Rôle                                   |
| ------- | ----------------------------- | -------------------------------------- |
| POST    | `/api/market-data`            | L'EA pousse les données multi-TF       |
| GET     | `/api/trade-command?magic=…`  | L'EA poll les ordres en attente        |
| POST    | `/api/trade-confirm`          | L'EA confirme l'exécution / clôture    |
| WS      | `/api/trading/ws?token=…`     | Le dashboard reçoit le flux temps réel |
