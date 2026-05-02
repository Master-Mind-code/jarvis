# OrionTrader.mq5 — Installation MetaTrader 5

## 1. Copier l'EA dans MT5

1. Dans MetaTrader 5 : **Fichier → Ouvrir le dossier de données**.
2. Va dans `MQL5/Experts/`.
3. Copies-y `OrionTrader.mq5`.
4. Ouvre **MetaEditor** (F4 dans MT5), ouvre `OrionTrader.mq5`, puis **Compile** (F7).

## 2. Autoriser les WebRequest vers Orion

1. Dans MT5 : **Outils → Options → Conseillers Experts**.
2. Coche **« Autoriser WebRequest pour les URLs listées »**.
3. Ajoute :
   - `http://127.0.0.1:8765` (Orion local)
   - `http://<IP_LAN>:8765` (Orion LAN, si tu lances le serveur depuis une autre machine)

## 3. Attacher l'EA à un graphique

1. Ouvre un graphique de **XAUUSD** (ou **XAUUSDm** sur Exness/IC Markets).
2. Drag & drop `OrionTrader` depuis l'onglet **Conseillers Experts**.
3. Dans les paramètres :
   - `OrionURL` : `http://127.0.0.1:8765` (ou ton IP LAN)
   - `OrionToken` : la même valeur que `ORION_SECRET_TOKEN` dans `.env` à la racine du projet
   - `Symbol_` : laisse `XAUUSDm` (ou adapte au symbole exact de ton broker)
   - `RiskPercent` : 1.0 (= 1 % du compte par trade)
   - `AutoTrade` : `true` pour exécuter automatiquement les signaux
4. Onglet **Common** : coche **« Allow algorithmic trading »**.
5. Clic OK. L'icône en haut à droite du graphique doit devenir un sourire bleu.

## 4. Vérifier

1. Lance Orion : `python start.py server`.
2. Ouvre l'UI principale : http://localhost:8765/.
3. Clique sur le bouton **TRADING** → tu accèdes au dashboard.
4. Clique **CONNECTER** : le ticker BID/ASK doit apparaître au bout de ~15 s.
5. Clique **DÉMARRER** pour activer l'analyse Claude + l'exécution automatique.

## Endpoints exposés par Orion (utilisés par l'EA)

| Méthode | Endpoint                      | Rôle                                   |
| ------- | ----------------------------- | -------------------------------------- |
| POST    | `/api/market-data`            | L'EA pousse les données multi-TF       |
| GET     | `/api/trade-command?magic=…`  | L'EA poll les ordres en attente        |
| POST    | `/api/trade-confirm`          | L'EA confirme l'exécution / clôture    |
| WS      | `/api/trading/ws?token=…`     | Le dashboard reçoit le flux temps réel |
