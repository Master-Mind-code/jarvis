"""
Orion Trading — Routes API
Endpoints HTTP pour l'EA MT5 + WebSocket pour le dashboard.
"""
import os
import json
import asyncio
from datetime import datetime
from fastapi import APIRouter, Request, Header, HTTPException, WebSocket, WebSocketDisconnect, Depends
from fastapi.responses import JSONResponse
from branding import (
    DEFAULT_SECRET_TOKEN,
    LEGACY_TRADING_TOKEN_HEADER,
    TRADING_TOKEN_HEADER,
    get_env,
    sync_env_aliases,
)

from server.trading.analyzer import analyze_market, should_execute
from server.trading.trade_manager import (
    update_open_trades, get_open_trades, get_history,
    push_command, pop_command, compute_stats,
    get_trading_state, set_trading_state, add_to_history,
)

router = APIRouter(prefix="/api")
sync_env_aliases()
SECRET = get_env("SECRET_TOKEN", DEFAULT_SECRET_TOKEN)

# Délai minimum entre deux analyses Claude (économise les tokens API)
# Override possible via env ORION_TRADER_MIN_INTERVAL.
ANALYSIS_MIN_INTERVAL = float(get_env("TRADER_MIN_INTERVAL", "60"))

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


def trading_token(
    x_orion_token: str = Header(default="", alias=TRADING_TOKEN_HEADER),
    x_legacy_token: str = Header(default="", alias=LEGACY_TRADING_TOKEN_HEADER),
):
    return x_orion_token or x_legacy_token


# ─────────────────────────────────────────────────────────────────
# EA → Orion : réception des données marché
# ─────────────────────────────────────────────────────────────────
@router.post("/market-data")
async def receive_market_data(request: Request, token: str = Depends(trading_token)):
    check_token(token)

    raw_body = await request.body()
    try:
        market_data = json.loads(raw_body)
    except Exception as e:
        snippet = raw_body[:400].decode("utf-8", errors="replace")
        print(f"[ORION TRADING] /market-data JSON invalide: {e} | body[:400]={snippet!r}")
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
                "comment": f"ORION|{decision.get('strategy','')}|{decision.get('confidence',0)}%",
            }
            push_command(cmd)
            await broadcast_dashboard({
                "type": "trade_signal",
                "data": {**cmd, "decision": decision}
            })

    except Exception as e:
        print(f"[ORION TRADING] Erreur analyse: {e}")


# ─────────────────────────────────────────────────────────────────
# EA → Orion : polling des commandes
# ─────────────────────────────────────────────────────────────────
@router.get("/trade-command")
async def get_trade_command(magic: int = 0, token: str = Depends(trading_token)):
    check_token(token)
    cmd = pop_command(magic)
    return JSONResponse(content=cmd)


# ─────────────────────────────────────────────────────────────────
# EA → Orion : confirmation d'exécution
# ─────────────────────────────────────────────────────────────────
@router.post("/trade-confirm")
async def trade_confirm(request: Request, token: str = Depends(trading_token)):
    check_token(token)
    data = await request.json()

    if data.get("executed"):
        await broadcast_dashboard({"type": "trade_executed", "data": data})

    # Si l'EA notifie une fermeture avec P&L → archiver dans l'historique
    if data.get("closed") and data.get("ticket"):
        add_to_history(data)

    return {"status": "ok"}


# ─────────────────────────────────────────────────────────────────
# Dashboard → Orion : contrôle du système
# ─────────────────────────────────────────────────────────────────
@router.post("/trading/start")
async def start_trading(request: Request, token: str = Depends(trading_token)):
    check_token(token)
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
async def stop_trading(token: str = Depends(trading_token)):
    check_token(token)
    state = set_trading_state({"active": False})
    await broadcast_dashboard({"type": "system_status", "data": state})
    return {"status": "stopped", "state": state}


@router.post("/trading/close-all")
async def close_all(token: str = Depends(trading_token)):
    check_token(token)
    push_command({"action": "CLOSE_ALL"})
    await broadcast_dashboard({"type": "close_all_requested"})
    return {"status": "close_all_queued"}


@router.post("/trading/manual-trade")
async def manual_trade(request: Request, token: str = Depends(trading_token)):
    check_token(token)
    cmd = await request.json()
    push_command(cmd)
    return {"status": "queued", "command": cmd}


# ─────────────────────────────────────────────────────────────────
# Dashboard : données
# ─────────────────────────────────────────────────────────────────
@router.get("/trading/stats")
async def get_stats(token: str = Depends(trading_token)):
    check_token(token)
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
