"""
Jarvis — Serveur Central WebSocket

Deux types de connexions :
  - Controller (chat client) : /ws/{device_id} → envoie des messages, reçoit des réponses.
  - Worker (agent distant qui exécute des tools sur sa propre machine) : /ws/worker/{device_id}
    → reçoit des tool_request, renvoie des tool_response.

Quand l'orchestrateur exécute un tool avec target_device défini, le serveur dispatche
la requête au worker correspondant via un canal RPC corrélé par request_id.
"""
import os
import json
import uuid
import asyncio
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from dotenv import load_dotenv
from server.orchestrator import process_request

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parent.parent
UI_FILE = ROOT_DIR / "jarvis_ui.html"

SECRET_TOKEN = os.getenv("JARVIS_SECRET_TOKEN", "jarvis_secret_change_me")
RPC_TIMEOUT = float(os.getenv("JARVIS_RPC_TIMEOUT", "60"))

app = FastAPI(title="Jarvis Server", version="2.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
security = HTTPBearer()

# Sessions controllers : {device_id: {"history": [...], "ws": WebSocket}}
controllers: dict = {}
# Workers connectés : {device_id: {"ws": WebSocket, "info": {os: ..., ...}, "pending": {req_id: Future}}}
workers: dict = {}


def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if credentials.credentials != SECRET_TOKEN:
        raise HTTPException(status_code=401, detail="Token invalide")
    return credentials.credentials


@app.get("/")
def serve_ui():
    """Sert l'UI Jarvis directement. Accessible depuis n'importe quel navigateur."""
    if UI_FILE.exists():
        return FileResponse(UI_FILE, media_type="text/html")
    return JSONResponse({"error": "jarvis_ui.html introuvable à la racine du projet"}, status_code=404)


@app.get("/status")
def status():
    return {
        "status": "Jarvis online",
        "controllers": list(controllers.keys()),
        "workers": [{"id": did, **w["info"]} for did, w in workers.items()],
    }


@app.get("/devices")
def list_devices_http(token: str = Depends(verify_token)):
    return {
        "controllers": [{"id": did, "history_len": len(s["history"])} for did, s in controllers.items()],
        "workers": [{"id": did, **w["info"]} for did, w in workers.items()],
    }


# ─────────────────────────────────────────────────────────────────
# RPC : envoi d'un tool_request à un worker, attente de la réponse
# ─────────────────────────────────────────────────────────────────
async def dispatch_to_worker(device_id: str, tool_name: str, tool_input: dict) -> str:
    """Envoie un tool_request au worker et attend tool_response. Retourne le JSON string."""
    worker = workers.get(device_id)
    if not worker or worker["ws"] is None:
        return json.dumps({"success": False, "error": f"Appareil '{device_id}' non connecté."})

    req_id = uuid.uuid4().hex
    loop = asyncio.get_running_loop()
    fut: asyncio.Future = loop.create_future()
    worker["pending"][req_id] = fut

    try:
        await worker["ws"].send_json({
            "type": "tool_request",
            "request_id": req_id,
            "tool": tool_name,
            "input": tool_input,
        })
        result = await asyncio.wait_for(fut, timeout=RPC_TIMEOUT)
        return result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
    except asyncio.TimeoutError:
        return json.dumps({"success": False, "error": f"Timeout RPC ({RPC_TIMEOUT}s) sur '{device_id}'"})
    except Exception as e:
        return json.dumps({"success": False, "error": f"Erreur RPC : {e}"})
    finally:
        worker["pending"].pop(req_id, None)


def make_dispatcher(loop: asyncio.AbstractEventLoop):
    """Wrappe dispatch_to_worker en version sync utilisable depuis un thread executor."""
    def dispatcher(device_id: str, tool_name: str, tool_input: dict) -> str:
        fut = asyncio.run_coroutine_threadsafe(
            dispatch_to_worker(device_id, tool_name, tool_input), loop
        )
        return fut.result(timeout=RPC_TIMEOUT + 5)
    return dispatcher


def list_workers_info():
    return [{"device_id": did, **w["info"]} for did, w in workers.items() if w["ws"] is not None]


# ─────────────────────────────────────────────────────────────────
# WebSocket Worker (agent distant qui exécute des tools localement)
# ─────────────────────────────────────────────────────────────────
@app.websocket("/ws/worker/{device_id}")
async def worker_endpoint(websocket: WebSocket, device_id: str):
    token = websocket.query_params.get("token", "")
    if token != SECRET_TOKEN:
        await websocket.close(code=4001, reason="Token invalide")
        return
    await websocket.accept()

    workers[device_id] = {"ws": websocket, "info": {"os": "unknown"}, "pending": {}}
    print(f"[worker +] {device_id} connecté")
    await websocket.send_json({"type": "registered", "device_id": device_id})

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            t = data.get("type")

            if t == "register":
                # L'agent annonce ses infos (OS, hostname, etc.)
                workers[device_id]["info"] = data.get("info", {})
                print(f"[worker i] {device_id} : {workers[device_id]['info']}")

            elif t == "tool_response":
                req_id = data.get("request_id")
                result = data.get("result")
                fut = workers[device_id]["pending"].get(req_id)
                if fut and not fut.done():
                    fut.set_result(result)

            elif t == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        print(f"[worker -] {device_id} déconnecté")
    finally:
        # Annule les RPC en attente pour ce worker
        for fut in list(workers.get(device_id, {}).get("pending", {}).values()):
            if not fut.done():
                fut.set_result(json.dumps({"success": False, "error": "Worker déconnecté."}))
        if device_id in workers:
            workers[device_id]["ws"] = None


# ─────────────────────────────────────────────────────────────────
# WebSocket Controller (chat client : navigateur, agent.py interactif)
# ─────────────────────────────────────────────────────────────────
@app.websocket("/ws/{device_id}")
async def controller_endpoint(websocket: WebSocket, device_id: str):
    token = websocket.query_params.get("token", "")
    if token != SECRET_TOKEN:
        await websocket.close(code=4001, reason="Token invalide")
        return
    await websocket.accept()

    if device_id not in controllers:
        controllers[device_id] = {"history": [], "ws": websocket}
    else:
        controllers[device_id]["ws"] = websocket
    session = controllers[device_id]

    print(f"[controller +] {device_id} connecté")
    await websocket.send_json({"type": "connected", "device_id": device_id, "message": "Jarvis en ligne ✓"})

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                data = {"type": "message", "content": raw}
            msg_type = data.get("type", "message")

            if msg_type == "message":
                user_input = data.get("content", "")
                loop = asyncio.get_running_loop()

                def on_tool(tool_name, tool_input, result):
                    fut = asyncio.run_coroutine_threadsafe(
                        websocket.send_json({
                            "type": "tool_action",
                            "tool": tool_name,
                            "input": tool_input,
                            "result": json.loads(result),
                        }),
                        loop,
                    )
                    try:
                        fut.result(timeout=5)
                    except Exception:
                        pass

                dispatcher = make_dispatcher(loop)

                try:
                    response, session["history"] = await loop.run_in_executor(
                        None,
                        lambda: process_request(
                            user_input,
                            session["history"],
                            on_tool_call=on_tool,
                            dispatcher=dispatcher,
                            list_devices=list_workers_info,
                        ),
                    )
                    await websocket.send_json({"type": "response", "content": response})
                except Exception as e:
                    # Erreur API (crédit insuffisant, rate limit, modèle invalide…) :
                    # on la remonte à l'UI au lieu de tuer la WebSocket.
                    err_msg = f"{type(e).__name__} : {e}"
                    print(f"[!] Erreur lors du traitement : {err_msg}")
                    await websocket.send_json({"type": "error", "content": err_msg})

            elif msg_type == "clear_history":
                session["history"] = []
                await websocket.send_json({"type": "info", "message": "Historique effacé."})

            elif msg_type == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        print(f"[controller -] {device_id} déconnecté")
        if device_id in controllers:
            controllers[device_id]["ws"] = None


if __name__ == "__main__":
    import uvicorn
    host = os.getenv("SERVER_HOST", "0.0.0.0")
    port = int(os.getenv("SERVER_PORT", "8765"))
    print(f"Jarvis Server démarré sur ws://{host}:{port}")
    uvicorn.run(app, host=host, port=port)
