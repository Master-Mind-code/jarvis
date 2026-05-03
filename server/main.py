"""
Orion — Serveur Central WebSocket

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
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from branding import (
    APP_NAME,
    DEFAULT_SECRET_TOKEN,
    LEGACY_UI_FILE_NAME,
    ONLINE_STATUS,
    TRADING_UI_FILE_NAME,
    get_env,
    resolve_ui_file,
    sync_env_aliases,
)
from server.orchestrator import process_request, process_request_streaming
from server.trading.routes import router as trading_router
from server import session_store
from server.scheduler import SCHEDULER, setup_default_jobs
from server import confirm
from server import audit
from server import panic
from server import rate_limit
from server import auth

load_dotenv()
sync_env_aliases()

ROOT_DIR = Path(__file__).resolve().parent.parent
TRADING_UI_FILE = ROOT_DIR / TRADING_UI_FILE_NAME
VOICE_UI_FILE = ROOT_DIR / "voice_ui.html"   # legacy fallback
FRONTEND_DIST = ROOT_DIR / "frontend" / "dist"
ASSETS_DIR = ROOT_DIR / "assets"

SECRET_TOKEN = get_env("SECRET_TOKEN", DEFAULT_SECRET_TOKEN)
RPC_TIMEOUT = float(get_env("RPC_TIMEOUT", "60"))

app = FastAPI(title=f"{APP_NAME} Server", version="2.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/assets", StaticFiles(directory=ASSETS_DIR, check_dir=False), name="assets")

# Sert le bundle React produit par `npm run build` côté frontend.
# Le bundle est buildé avec base="/voice/", donc les assets sont sous /voice/assets/.
# Le même index.html est servi pour `/` (chat principal) et `/voice` (mode immersif),
# et le routing est géré côté React via window.location.pathname.
if (FRONTEND_DIST / "assets").exists():
    app.mount(
        "/voice/assets",
        StaticFiles(directory=FRONTEND_DIST / "assets", check_dir=False),
        name="voice_assets",
    )

app.include_router(trading_router)
security = HTTPBearer()


@app.on_event("startup")
async def _on_startup():
    """Démarre le scheduler de tâches récurrentes (briefing matinal, etc.)
    + branche le système de confirmation par mot de passe."""
    # Mémorise la boucle async principale pour permettre aux callbacks venant
    # d'autres threads (scheduler / confirm) d'envoyer des messages WebSocket.
    app.state.main_loop = asyncio.get_running_loop()
    setup_default_jobs()
    SCHEDULER.start()

    # Callback pour pousser les demandes de confirmation au client WebSocket
    def _push_confirm(device_id: str, payload: dict) -> bool:
        session = controllers.get(device_id)
        ws = session.get("ws") if session else None
        if ws is None:
            return False
        try:
            asyncio.run_coroutine_threadsafe(
                ws.send_json(payload), app.state.main_loop
            ).result(timeout=2)
            return True
        except Exception:
            return False
    confirm.set_push_callback(_push_confirm)
    cfg = confirm.status()
    if cfg["enabled"]:
        print(f"[confirm] Activé : {cfg['tools_count']} tools sous gating "
              f"(timeout={cfg['timeout_sec']}s, cache={cfg['cache_sec']}s).")
    else:
        print("[confirm] DÉSACTIVÉ : ORION_CONFIRM_PASSWORD non défini "
              "→ aucun tool n'est protégé par mot de passe.")

    # ─── Hook d'alerte audit (broadcast UI + toast système + ntfy.sh) ──
    def _audit_alert(row: dict):
        """Appelé après chaque tool sensible. Best-effort, jamais bloquant."""
        # 1. Broadcast WebSocket à toutes les UI ouvertes
        payload = {"type": "audit_alert", **{k: v for k, v in row.items() if k != "id"}}
        for did, sess in list(controllers.items()):
            ws = sess.get("ws")
            if ws is None:
                continue
            try:
                asyncio.run_coroutine_threadsafe(
                    ws.send_json(payload), app.state.main_loop,
                ).result(timeout=1)
            except Exception:
                pass

        # 2. Toast Windows local (si winotify dispo)
        try:
            from winotify import Notification
            ok = "✓" if row.get("success") else "✗"
            confirmed = " [conf]" if row.get("confirmed") else ""
            Notification(
                app_id="Orion",
                title=f"Orion · action sensible {ok}{confirmed}",
                msg=f"{row.get('tool_name', '?')} · {row.get('device_id', '?')}",
                duration="short",
            ).show()
        except Exception:
            pass  # winotify pas dispo ou non-Windows

        # 3. ntfy.sh push (optionnel, si ORION_NTFY_TOPIC défini)
        topic = (get_env("NTFY_TOPIC") or "").strip()
        if topic:
            ntfy_url = (get_env("NTFY_SERVER") or "https://ntfy.sh").rstrip("/")
            try:
                import httpx
                httpx.post(
                    f"{ntfy_url}/{topic}",
                    data=(f"{row.get('tool_name', '?')} sur {row.get('device_id', '?')}"
                          f" {'OK' if row.get('success') else 'ERR: ' + (row.get('error') or '')}").encode(),
                    headers={
                        "Title": "Orion · action sensible",
                        "Tags": "shield" if row.get("confirmed") else "warning",
                        "Priority": "default" if row.get("success") else "high",
                    },
                    timeout=3.0,
                )
            except Exception as exc:
                print(f"[ntfy!] {exc}")

    audit.set_alert_hook(_audit_alert)
    if audit._enabled():
        print(f"[audit] Activé · {audit.db_size_kb()} KB en base · "
              f"max {audit._max_rows()} entrées.")

# Sessions controllers : {device_id: {"history": [...], "ws": WebSocket}}
controllers: dict = {}
# Workers connectés : {device_id: {"ws": WebSocket, "info": {os: ..., ...}, "pending": {req_id: Future}}}
workers: dict = {}
# État du service voix (broadcast aux UI quand un service voice est actif)
# {device_id: {"state": "idle|wake|listening|thinking|speaking", "ts": <epoch>}}
voice_states: dict = {}


async def broadcast_voice_state(payload: dict, exclude_device: str | None = None):
    """Envoie l'état voix à tous les controllers UI (sauf l'émetteur lui-même)."""
    dead = []
    for did, session in controllers.items():
        if did == exclude_device:
            continue
        ws = session.get("ws")
        if ws is None:
            continue
        try:
            await ws.send_json(payload)
        except Exception:
            dead.append(did)
    for did in dead:
        controllers[did]["ws"] = None


def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Vérifie un token de scope ADMIN (pour les endpoints HTTP /devices, /audit, etc.)."""
    if not auth.verify(auth.ADMIN, credentials.credentials):
        raise HTTPException(status_code=401, detail="Token invalide")
    return credentials.credentials


@app.get("/")
@app.get("/orion")
def serve_ui():
    """Sert l'UI Orion (chat principal) — bundle React si dispo, sinon HTML legacy."""
    react_index = FRONTEND_DIST / "index.html"
    if react_index.exists():
        return FileResponse(
            react_index,
            media_type="text/html",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )
    ui_file = resolve_ui_file(ROOT_DIR)
    if ui_file.exists():
        return FileResponse(ui_file, media_type="text/html")
    return JSONResponse(
        {"error": "Ni frontend/dist/index.html ni orion_ui.html trouvés. "
                  "Build le frontend avec : cd frontend && npm run build"},
        status_code=404,
    )


@app.get("/orion_ui.html")
@app.get(f"/{LEGACY_UI_FILE_NAME}", include_in_schema=False)
def serve_ui_legacy():
    """Ancienne UI HTML (fallback / debug). À supprimer quand React est validé."""
    ui_file = resolve_ui_file(ROOT_DIR)
    if ui_file.exists():
        return FileResponse(ui_file, media_type="text/html")
    return JSONResponse({"error": f"{ui_file.name} introuvable à la racine du projet"}, status_code=404)


@app.get("/trading")
def serve_trading_ui():
    """Sert le dashboard de trading — bundle React si dispo, sinon HTML legacy."""
    react_index = FRONTEND_DIST / "index.html"
    if react_index.exists():
        return FileResponse(
            react_index,
            media_type="text/html",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )
    if TRADING_UI_FILE.exists():
        return FileResponse(
            TRADING_UI_FILE,
            media_type="text/html",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )
    return JSONResponse(
        {"error": "Ni frontend/dist/index.html ni trading_dashboard.html trouvés."},
        status_code=404,
    )


@app.get("/trading_legacy")
def serve_trading_ui_legacy():
    """Ancienne UI Trading HTML (fallback / debug). À supprimer après validation React."""
    if TRADING_UI_FILE.exists():
        return FileResponse(TRADING_UI_FILE, media_type="text/html")
    return JSONResponse({"error": "trading_dashboard.html introuvable"}, status_code=404)


@app.get("/voice")
@app.get("/voice_ui.html", include_in_schema=False)
def serve_voice_ui():
    """Sert l'UI Voice React (frontend/dist/index.html).
    Fallback sur l'ancien voice_ui.html si le bundle React n'est pas buildé."""
    react_index = FRONTEND_DIST / "index.html"
    if react_index.exists():
        return FileResponse(
            react_index,
            media_type="text/html",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )
    if VOICE_UI_FILE.exists():
        return FileResponse(
            VOICE_UI_FILE,
            media_type="text/html",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )
    return JSONResponse(
        {"error": "Ni frontend/dist/index.html ni voice_ui.html trouvés. "
                  "Build le frontend avec : cd frontend && npm run build"},
        status_code=404,
    )


@app.get("/voice_legacy")
def serve_voice_ui_legacy():
    """Ancienne UI voice HTML (au cas où). À supprimer quand React est validé."""
    if VOICE_UI_FILE.exists():
        return FileResponse(VOICE_UI_FILE, media_type="text/html")
    return JSONResponse({"error": "voice_ui.html introuvable"}, status_code=404)


@app.get("/status")
def status():
    return {
        "status": ONLINE_STATUS,
        "controllers": list(controllers.keys()),
        "workers": [{"id": did, **w["info"]} for did, w in workers.items()],
        "voice": voice_states,
        "panic": panic.details(),
        "rate_limit": rate_limit.status(),
        "confirm": {"enabled": confirm._enabled()},
        "audit_db_kb": audit.db_size_kb(),
    }


async def _broadcast_panic(state: dict):
    """Envoie l'état panic à toutes les UI ouvertes."""
    payload = {"type": "panic_state", **state}
    for did, sess in list(controllers.items()):
        ws = sess.get("ws")
        if ws is None:
            continue
        try:
            await ws.send_json(payload)
        except Exception:
            pass


@app.post("/api/panic")
async def api_panic_trigger(token: str | None = None, reason: str | None = None,
                             by: str | None = None):
    """Active le mode panic : kill switch global."""
    if not auth.verify(auth.ADMIN, token):
        raise HTTPException(status_code=401, detail="Token invalide")
    state = panic.trigger(reason=reason or "via /api/panic", by_device=by or "?")
    print(f"[PANIC ⚠] Activé par {by or '?'} : {reason or '(sans raison)'}")

    # Déconnecte tous les workers (par sécurité, ils ne pourront plus exécuter)
    for did, w in list(workers.items()):
        ws = w.get("ws")
        if ws:
            try:
                await ws.close(code=4002, reason="Mode panic")
            except Exception:
                pass
            workers[did]["ws"] = None

    # Stoppe le scheduler (plus de briefing automatique pendant le panic)
    try:
        SCHEDULER.stop()
    except Exception:
        pass

    # Audit + broadcast
    audit.log_tool_call(
        device_id=by or "panic_endpoint", tool_name="_panic_trigger",
        tool_input={"reason": reason or ""}, success=True,
        duration_ms=0, sensitive=True, confirmed=True,
    )
    await _broadcast_panic(state)
    return state


@app.post("/api/panic/release")
async def api_panic_release(token: str | None = None):
    """Désactive le mode panic."""
    if not auth.verify(auth.ADMIN, token):
        raise HTTPException(status_code=401, detail="Token invalide")
    state = panic.release()
    print("[PANIC ✓] Désactivé.")
    audit.log_tool_call(
        device_id="panic_endpoint", tool_name="_panic_release",
        tool_input={}, success=True, duration_ms=0,
        sensitive=True, confirmed=True,
    )
    await _broadcast_panic({"active": False})
    return state


@app.get("/devices")
def list_devices_http(token: str = Depends(verify_token)):
    return {
        "controllers": [{"id": did, "history_len": len(s["history"])} for did, s in controllers.items()],
        "workers": [{"id": did, **w["info"]} for did, w in workers.items()],
    }


@app.get("/api/audit")
def api_audit(
    token: str | None = None,
    limit: int = 50,
    hours: float = 24.0,
    sensitive_only: bool = False,
    failed_only: bool = False,
    device_id: str | None = None,
):
    """Visualise l'audit log dans le navigateur. Ex:
       /api/audit?token=XXX&limit=50&hours=24&sensitive_only=true"""
    if not auth.verify(auth.ADMIN, token):
        raise HTTPException(status_code=401, detail="Token invalide")
    import time as _time
    since = _time.time() - max(0.1, float(hours)) * 3600
    items = audit.get_recent(
        limit=int(limit),
        sensitive_only=bool(sensitive_only),
        failed_only=bool(failed_only),
        device_id=device_id,
        since_ts=since,
    )
    return {
        "stats": audit.get_stats(since_ts=since),
        "items": items,
    }


@app.post("/api/transcribe")
async def api_transcribe(request: Request, token: str | None = None, language: str | None = None):
    """Transcription Whisper d'un blob audio brut (POST raw body).

    Le client envoie le blob audio dans le body de la requête avec
    Content-Type: audio/webm (ou audio/wav, audio/ogg…). Évite multipart pour
    ne pas dépendre de python-multipart côté serveur.

    Auth : ?token=... en query string (cohérent avec /ws/...).
    """
    if not auth.verify(auth.ADMIN, token):
        raise HTTPException(status_code=401, detail="Token invalide")

    blob = await request.body()
    if not blob:
        return JSONResponse({"success": False, "error": "Audio vide"}, status_code=400)

    # Devine le suffix d'après le Content-Type (utile à faster-whisper/ffmpeg)
    content_type = (request.headers.get("content-type") or "").lower()
    if "webm" in content_type:
        suffix = ".webm"
    elif "wav" in content_type:
        suffix = ".wav"
    elif "ogg" in content_type or "opus" in content_type:
        suffix = ".ogg"
    elif "mp3" in content_type or "mpeg" in content_type:
        suffix = ".mp3"
    elif "mp4" in content_type or "m4a" in content_type:
        suffix = ".m4a"
    else:
        suffix = ".webm"

    try:
        from server.transcribe import transcribe_blob
        text = await asyncio.to_thread(transcribe_blob, blob, language, suffix)
    except ImportError as exc:
        return JSONResponse({"success": False, "error": str(exc)}, status_code=503)
    except Exception as exc:
        return JSONResponse(
            {"success": False, "error": f"{type(exc).__name__}: {exc}"},
            status_code=500,
        )
    return {"success": True, "text": text, "language": language or "fr"}


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
    # Le worker doit avoir au minimum le scope WORKER (ADMIN passe aussi)
    if not auth.verify(auth.WORKER, token):
        await websocket.close(code=4001, reason="Token invalide")
        return
    await websocket.accept()

    workers[device_id] = {"ws": websocket, "info": {"os": "unknown"}, "pending": {}}
    print(f"[worker +] {device_id} connecté")
    try:
        await websocket.send_json({"type": "registered", "device_id": device_id})
    except (WebSocketDisconnect, RuntimeError):
        print(f"[worker -] {device_id} (déconnecté avant ack)")
        return

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
    # Le controller doit avoir au minimum le scope USER (ADMIN passe aussi)
    if not auth.verify(auth.USER, token):
        await websocket.close(code=4001, reason="Token invalide")
        return
    await websocket.accept()

    if device_id not in controllers:
        # Premier connect de ce device dans cette session serveur :
        # restore l'historique persistant depuis SQLite (peut être vide)
        persisted = session_store.load_history(device_id)
        controllers[device_id] = {"history": persisted, "ws": websocket}
    else:
        controllers[device_id]["ws"] = websocket
    session = controllers[device_id]

    print(f"[controller +] {device_id} connecté")
    try:
        await websocket.send_json({"type": "connected", "device_id": device_id, "message": "Orion en ligne ✓"})
        # Resync : envoie au nouveau client l'état actuel des services voix actifs
        for did, info in voice_states.items():
            await websocket.send_json({
                "type": "voice_state",
                "device_id": did,
                "state": info.get("state", "idle"),
            })
    except (WebSocketDisconnect, RuntimeError):
        # Le client s'est déconnecté avant qu'on envoie le welcome (typique mobile)
        print(f"[controller -] {device_id} (déconnecté avant welcome)")
        return

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

                # Streaming activé par défaut. L'UI peut désactiver en envoyant
                # {"type": "message", "stream": false, ...}
                use_stream = data.get("stream", True)

                def on_text_delta(text):
                    fut = asyncio.run_coroutine_threadsafe(
                        websocket.send_json({"type": "response_chunk", "text": text}),
                        loop,
                    )
                    try:
                        fut.result(timeout=2)
                    except Exception:
                        pass

                try:
                    if use_stream:
                        response, session["history"] = await loop.run_in_executor(
                            None,
                            lambda: process_request_streaming(
                                user_input,
                                session["history"],
                                on_text_delta=on_text_delta,
                                on_tool_call=on_tool,
                                dispatcher=dispatcher,
                                list_devices=list_workers_info,
                                device_id=device_id,
                            ),
                        )
                    else:
                        response, session["history"] = await loop.run_in_executor(
                            None,
                            lambda: process_request(
                                user_input,
                                session["history"],
                                on_tool_call=on_tool,
                                dispatcher=dispatcher,
                                list_devices=list_workers_info,
                                device_id=device_id,
                            ),
                        )
                    try:
                        session_store.save_history(device_id, session["history"])
                    except Exception as exc:
                        print(f"[session_store!] {exc}")
                    # Le 'response' final contient le texte complet ; l'UI peut s'en
                    # servir pour reconstruire si elle a manqué des chunks.
                    await websocket.send_json({"type": "response", "content": response})
                except Exception as e:
                    # Erreur API (crédit insuffisant, rate limit, modèle invalide…) :
                    # on la remonte à l'UI au lieu de tuer la WebSocket.
                    err_msg = f"{type(e).__name__} : {e}"
                    print(f"[!] Erreur lors du traitement : {err_msg}")
                    await websocket.send_json({"type": "error", "content": err_msg})

            elif msg_type == "clear_history":
                session["history"] = []
                try:
                    session_store.clear_history(device_id)
                except Exception as exc:
                    print(f"[session_store!] {exc}")
                await websocket.send_json({"type": "info", "message": "Historique effacé."})

            elif msg_type == "voice_state":
                # Le service voix annonce son état (idle/wake/listening/thinking/speaking).
                # On le stocke et on le broadcast aux autres UI pour visualisation.
                state = data.get("state", "idle")
                voice_states[device_id] = {"state": state, "ts": asyncio.get_event_loop().time()}
                await broadcast_voice_state(
                    {"type": "voice_state", "device_id": device_id, "state": state},
                    exclude_device=device_id,
                )

            elif msg_type == "confirm_response":
                # Réponse à un confirm_request : accepter (avec password) ou refuser
                req_id = data.get("request_id", "")
                password = data.get("password", "")
                refused = data.get("refused", False)
                if refused:
                    result = confirm.deny(req_id)
                else:
                    result = confirm.resolve(req_id, password)
                # Echo discret pour l'UI (utilisé pour rejouer le modal en cas de mauvais pwd)
                try:
                    await websocket.send_json({
                        "type": "confirm_result",
                        "request_id": req_id,
                        **result,
                    })
                except Exception:
                    pass

            elif msg_type == "unlock_request":
                # Demande de déverrouillage du password gate des UI navigateur.
                # Émise par le service voix quand l'utilisateur prononce un mot d'unlock.
                # On broadcast à tous les autres clients (les UI réagissent).
                print(f"[unlock] demandé par {device_id}")
                await broadcast_voice_state(
                    {"type": "unlock", "from": device_id},
                    exclude_device=device_id,
                )

            elif msg_type == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        print(f"[controller -] {device_id} déconnecté")
        if device_id in controllers:
            controllers[device_id]["ws"] = None
        # Si c'était un service voix, on retire son état et on notifie les UI
        if device_id in voice_states:
            voice_states.pop(device_id, None)
            await broadcast_voice_state(
                {"type": "voice_state", "device_id": device_id, "state": "offline"},
                exclude_device=device_id,
            )


if __name__ == "__main__":
    import uvicorn
    host = os.getenv("SERVER_HOST", "0.0.0.0")
    port = int(os.getenv("SERVER_PORT", "8765"))
    print(f"Orion Server démarré sur ws://{host}:{port}")
    uvicorn.run(app, host=host, port=port)
