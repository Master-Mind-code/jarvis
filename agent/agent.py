"""
Jarvis — Agent Local

Deux modes :
  - worker (par défaut) : se connecte au serveur, attend des tool_request,
    exécute les tools localement (via server.tools.ALL_HANDLERS) et renvoie le résultat.
    → C'est ce qui permet à un téléphone Termux ou à un PC distant d'être contrôlé
      depuis un autre appareil via le serveur central.
  - controller : se connecte comme un client de chat (équivalent au navigateur).

Variables d'env :
  JARVIS_SERVER_URL   ex: ws://192.168.1.42:8765
  JARVIS_DEVICE_ID    ex: telephone-dominique
  JARVIS_SECRET_TOKEN
  JARVIS_AGENT_MODE   worker | controller   (défaut: worker)
"""
import os
import sys
import json
import asyncio
import platform
from pathlib import Path

# Ajoute la racine du projet au path pour importer server.tools.*
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import websockets

from server.tools import ALL_HANDLERS

SERVER_URL = os.getenv("JARVIS_SERVER_URL", "ws://localhost:8765")
DEVICE_ID = os.getenv("JARVIS_DEVICE_ID", f"{platform.node()}-{platform.system().lower()}")
SECRET_TOKEN = os.getenv("JARVIS_SECRET_TOKEN", "jarvis_secret_change_me")
MODE = os.getenv("JARVIS_AGENT_MODE", "worker").lower()


def device_info() -> dict:
    return {
        "os": platform.system(),
        "os_version": platform.release(),
        "hostname": platform.node(),
        "python": platform.python_version(),
        "tools": sorted(ALL_HANDLERS.keys()),
    }


# ═════════════════════════════════════════════════════════════════
# Mode WORKER : exécute les tools localement à la demande du serveur
# ═════════════════════════════════════════════════════════════════
async def run_worker():
    url = f"{SERVER_URL}/ws/worker/{DEVICE_ID}?token={SECRET_TOKEN}"
    print(f"[worker] Connexion à {url}")

    async with websockets.connect(url) as ws:
        # Annonce nos infos
        await ws.send(json.dumps({"type": "register", "info": device_info()}))
        print(f"[worker] Enregistré comme '{DEVICE_ID}' ({platform.system()})")
        print(f"[worker] {len(ALL_HANDLERS)} tools disponibles localement")

        async for raw in ws:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            t = data.get("type")

            if t == "tool_request":
                req_id = data.get("request_id")
                tool_name = data.get("tool")
                tool_input = data.get("input", {})

                handler = ALL_HANDLERS.get(tool_name)
                if not handler:
                    result = {"success": False, "error": f"Tool inconnu : {tool_name}"}
                else:
                    try:
                        # Les handlers peuvent être lents (shell, fichiers volumineux) :
                        # on les exécute dans un thread pour ne pas bloquer la boucle async.
                        result = await asyncio.to_thread(handler, tool_input)
                    except Exception as e:
                        result = {"success": False, "error": str(e)}

                await ws.send(json.dumps({
                    "type": "tool_response",
                    "request_id": req_id,
                    "result": json.dumps(result, ensure_ascii=False),
                }))
                print(f"[worker] {tool_name} → {'OK' if result.get('success', True) else 'ERR'}")


# ═════════════════════════════════════════════════════════════════
# Mode CONTROLLER : client de chat textuel (équivalent navigateur)
# ═════════════════════════════════════════════════════════════════
async def run_controller():
    url = f"{SERVER_URL}/ws/{DEVICE_ID}?token={SECRET_TOKEN}"
    print(f"[controller] Connexion à {url}")

    async with websockets.connect(url) as ws:
        welcome = json.loads(await ws.recv())
        print(f"✓ {welcome.get('message', 'Connecté')}")

        async def chat_loop():
            loop = asyncio.get_running_loop()
            while True:
                user_input = await loop.run_in_executor(None, input, "\nVous : ")
                user_input = user_input.strip()
                if not user_input:
                    continue
                if user_input.lower() in ("/quit", "/exit", "/q"):
                    return
                if user_input.lower() == "/clear":
                    await ws.send(json.dumps({"type": "clear_history"}))
                    continue
                await ws.send(json.dumps({"type": "message", "content": user_input}))

        async def recv_loop():
            async for raw in ws:
                data = json.loads(raw)
                t = data.get("type")
                if t == "tool_action":
                    ok = "✓" if data.get("result", {}).get("success", True) else "✗"
                    print(f"  [{ok} {data.get('tool')}]")
                elif t == "response":
                    print(f"\nJarvis : {data.get('content')}")
                elif t == "info":
                    print(f"  [i] {data.get('message')}")

        chat_task = asyncio.create_task(chat_loop())
        recv_task = asyncio.create_task(recv_loop())
        _, pending = await asyncio.wait({chat_task, recv_task}, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()


async def main():
    if MODE == "controller":
        await run_controller()
    else:
        await run_worker()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nDéconnecté.")
