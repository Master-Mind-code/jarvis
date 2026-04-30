"""
Jarvis Trading — Routes API
Endpoints HTTP pour l'EA MT5 + WebSocket pour le dashboard.
"""
import os
import json
import asyncio
from datetime import datetime
from fastapi import APIRouter, Request, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from server.trading.analyzer import analyze_market, should_execute
from server.trading.trade_manager import (
    update_open_trades, get_open_trades, get_history,
    push_command, pop_command, compute_stats,
    get_trading_state, set_trading_state, add_to_history,
)

router = APIRouter(prefix="/api")
SECRET = os.getenv("JARVIS_SECRET_TOKEN", "jarvis_secret_change_me")

# Délai minimum entre deux analyses Claude (économise les tokens API)
# Override possible via env JARVIS_TRADER_MIN_INTERVAL.
ANALYSIS_MIN_INTERVAL = float(os.getenv("JARVIS_TRADER_MIN_INTERVAL", "60"))

# WebSocket clients du dashboard
dashboard_clients: list = []

# Timestamp de la dernière analyse Claude (pour throttling)
_last_analysis_ts: float = 0.0


# ─────────────────────────────────────────────────────────────────
# Auth helper
# ─────────────────────────────────────────────────────────────────
def check_token(token: str):
    if token != SECRET:
        raise HTTPException(status_code=401, detail="Token invalide")


# ─────────────────────────────────────────────────────────────────
# EA → Jarvis : réception des données marché
# ─────────────────────────────────────────────────────────────────
@router.post("/market-data")
async def receive_market_data(request: Request, x_jarvis_token: str = Header(default="")):
    check_token(x_jarvis_token)

    raw_body = await request.body()
    try:
        market_data = json.loads(raw_body)
    except Exception as e:
        snippet = raw_body[:400].decode("utf-8", errors="replace")
        print(f"[JARVIS TRADING] /market-data JSON invalide: {e} | body[:400]={snippet!r}")
        raise HTTPException(status_code=400, detail=f"JSON invalide: {e}")

    positions = market_data.get("open_positions", [])
    update_open_trades(positions)

    await broadcast_dashboard({
        "type": "market_update",
        "data": {
            "symbol": market_data.get("symbol"),
            "bid": market_data.get("bid"),
            "ask": market_data.get("ask"),
            "spread": market_data.get("spread"),
            "account": market_data.get("account", {}),
            "open_positions": positions,
            "timestamp": market_data.get("timestamp"),
        }
    })

    state = get_trading_state()

    # Throttle : on analyse au max toutes les ANALYSIS_MIN_INTERVAL secondes
    # même si l'EA push des données plus souvent. Économise les tokens Claude.
    global _last_analysis_ts
    import time as _time
    now_ts = _time.time()
    if state.get("active") and (now_ts - _last_analysis_ts) >= ANALYSIS_MIN_INTERVAL:
        _last_analysis_ts = now_ts
        asyncio.create_task(run_analysis(market_data, state))

    return {"status": "ok", "positions": len(positions)}


async def run_analysis(market_data: dict, state: dict):
    """Analyse IA + décision de trade (tâche asynchrone)."""
    try:
        open_trades = get_open_trades()
        max_trades  = state.get("max_trades", 3)
        if len(open_trades) >= max_trades:
            return

        decision = await asyncio.get_event_loop().run_in_executor(
            None, analyze_market, market_data
        )

        set_trading_state({
            "last_analysis": datetime.now().isoformat(),
            "last_signal": decision.get("decision"),
        })

        await broadcast_dashboard({
            "type": "analysis",
            "data": decision,
        })

        min_conf = state.get("min_confidence", 72)
        if should_execute(decision, min_confidence=min_conf):
            cmd = {
                "action": decision["decision"],
                "entry":  decision.get("entry"),
                "sl":     decision.get("sl"),
                "tp":     decision.get("tp1"),
                "comment": f"JARVIS|{decision.get('strategy','')}|{decision.get('confidence',0)}%",
            }
            push_command(cmd)
            await broadcast_dashboard({
                "type": "trade_signal",
                "data": {**cmd, "decision": decision}
            })

    except Exception as e:
        print(f"[JARVIS TRADING] Erreur analyse: {e}")


# ─────────────────────────────────────────────────────────────────
# EA → Jarvis : polling des commandes
# ─────────────────────────────────────────────────────────────────
@router.get("/trade-command")
async def get_trade_command(magic: int = 0, x_jarvis_token: str = Header(default="")):
    check_token(x_jarvis_token)
    cmd = pop_command(magic)
    return JSONResponse(content=cmd)


# ─────────────────────────────────────────────────────────────────
# EA → Jarvis : confirmation d'exécution
# ─────────────────────────────────────────────────────────────────
@router.post("/trade-confirm")
async def trade_confirm(request: Request, x_jarvis_token: str = Header(default="")):
    check_token(x_jarvis_token)
    data = await request.json()

    if data.get("executed"):
        await broadcast_dashboard({"type": "trade_executed", "data": data})

    # Si l'EA notifie une fermeture avec P&L → archiver dans l'historique
    if data.get("closed") and data.get("ticket"):
        add_to_history(data)

    return {"status": "ok"}


# ─────────────────────────────────────────────────────────────────
# Dashboard → Jarvis : contrôle du système
# ─────────────────────────────────────────────────────────────────
@router.post("/trading/start")
async def start_trading(request: Request, x_jarvis_token: str = Header(default="")):
    check_token(x_jarvis_token)
    body = await request.json()
    state = set_trading_state({
        "active": True,
        "started_at": datetime.now().isoformat(),
        "min_confidence": body.get("min_confidence", 72),
        "risk_percent": body.get("risk_percent", 1.0),
        "max_trades": body.get("max_trades", 3),
    })
    await broadcast_dashboard({"type": "system_status", "data": state})
    return {"status": "started", "state": state}


@router.post("/trading/stop")
async def stop_trading(x_jarvis_token: str = Header(default="")):
    check_token(x_jarvis_token)
    state = set_trading_state({"active": False})
    await broadcast_dashboard({"type": "system_status", "data": state})
    return {"status": "stopped", "state": state}


@router.post("/trading/close-all")
async def close_all(x_jarvis_token: str = Header(default="")):
    check_token(x_jarvis_token)
    push_command({"action": "CLOSE_ALL"})
    await broadcast_dashboard({"type": "close_all_requested"})
    return {"status": "close_all_queued"}


@router.post("/trading/manual-trade")
async def manual_trade(request: Request, x_jarvis_token: str = Header(default="")):
    check_token(x_jarvis_token)
    cmd = await request.json()
    push_command(cmd)
    return {"status": "queued", "command": cmd}


# ─────────────────────────────────────────────────────────────────
# Dashboard : données
# ─────────────────────────────────────────────────────────────────
@router.get("/trading/stats")
async def get_stats(x_jarvis_token: str = Header(default="")):
    check_token(x_jarvis_token)
    return {
        "stats": compute_stats(),
        "open_trades": get_open_trades(),
        "history": get_history(30),
        "state": get_trading_state(),
    }


# ─────────────────────────────────────────────────────────────────
# WebSocket Dashboard (temps réel)
# ─────────────────────────────────────────────────────────────────
@router.websocket("/trading/ws")
async def trading_ws(websocket: WebSocket, token: str = ""):
    if token != SECRET:
        await websocket.close(code=4001)
        return

    await websocket.accept()
    dashboard_clients.append(websocket)

    await websocket.send_json({
        "type": "init",
        "data": {
            "stats": compute_stats(),
            "open_trades": get_open_trades(),
            "history": get_history(30),
            "state": get_trading_state(),
        }
    })

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except Exception:
                continue
            if data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        if websocket in dashboard_clients:
            dashboard_clients.remove(websocket)


async def broadcast_dashboard(message: dict):
    """Envoie un message à tous les clients dashboard connectés."""
    dead = []
    for ws in dashboard_clients:
        try:
            await ws.send_json(message)
        except Exception:
            dead.append(ws)
    for d in dead:
        if d in dashboard_clients:
            dashboard_clients.remove(d)
