"""
Jarvis Trading — Gestionnaire de Trades
Stocke et gère l'état des trades, l'historique, les statistiques.
"""
import json
from datetime import datetime
from pathlib import Path
from threading import Lock

# Racine du projet : server/trading/trade_manager.py → ../../..
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = ROOT_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
TRADES_FILE   = DATA_DIR / "trades.json"
HISTORY_FILE  = DATA_DIR / "history.json"
COMMANDS_FILE = DATA_DIR / "pending_commands.json"
STATE_FILE    = DATA_DIR / "trading_state.json"

_lock = Lock()


def _load(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return default


def _save(path: Path, data):
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


# ─────────────────────────────────────────────────────────────────
# Trades ouverts (synchronisés avec l'EA)
# ─────────────────────────────────────────────────────────────────

def update_open_trades(positions: list):
    with _lock:
        _save(TRADES_FILE, positions)


def get_open_trades() -> list:
    return _load(TRADES_FILE, [])


# ─────────────────────────────────────────────────────────────────
# Historique des trades
# ─────────────────────────────────────────────────────────────────

def add_to_history(trade_data: dict):
    with _lock:
        history = _load(HISTORY_FILE, [])
        trade_data["id"] = len(history) + 1
        trade_data["closed_at"] = datetime.now().isoformat()
        history.append(trade_data)
        _save(HISTORY_FILE, history)
        return trade_data["id"]


def get_history(limit: int = 50) -> list:
    history = _load(HISTORY_FILE, [])
    return history[-limit:][::-1]  # Plus récents en premier


# ─────────────────────────────────────────────────────────────────
# Commandes vers l'EA (queue)
# ─────────────────────────────────────────────────────────────────

def push_command(command: dict):
    """Ajoute une commande de trade à la queue pour l'EA."""
    with _lock:
        commands = _load(COMMANDS_FILE, [])
        command["created_at"] = datetime.now().isoformat()
        command["executed"] = False
        commands.append(command)
        _save(COMMANDS_FILE, commands)


def pop_command(magic: int = None) -> dict:
    """Récupère et supprime la prochaine commande non-exécutée."""
    with _lock:
        commands = _load(COMMANDS_FILE, [])
        pending = [c for c in commands if not c.get("executed")]
        if not pending:
            return {"action": "none"}

        cmd = pending[0]
        for c in commands:
            if c.get("created_at") == cmd.get("created_at"):
                c["executed"] = True
                break
        _save(COMMANDS_FILE, commands)
        return cmd


def clear_commands():
    with _lock:
        _save(COMMANDS_FILE, [])


# ─────────────────────────────────────────────────────────────────
# Statistiques
# ─────────────────────────────────────────────────────────────────

def compute_stats() -> dict:
    history = _load(HISTORY_FILE, [])
    open_trades = get_open_trades()

    if not history:
        return {
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "winrate": 0,
            "total_profit": 0,
            "total_loss": 0,
            "net_pnl": 0,
            "avg_rr": 0,
            "best_trade": 0,
            "worst_trade": 0,
            "open_trades": len(open_trades),
            "open_pnl": sum(p.get("profit", 0) for p in open_trades),
        }

    profits = [t.get("profit", 0) for t in history if t.get("profit", 0) > 0]
    losses  = [t.get("profit", 0) for t in history if t.get("profit", 0) <= 0]
    all_pnl = [t.get("profit", 0) for t in history]
    rrs     = [t.get("rr", 0) for t in history if t.get("rr", 0) > 0]

    total = len(history)
    wins  = len(profits)
    open_pnl = sum(p.get("profit", 0) for p in open_trades)

    return {
        "total_trades": total,
        "wins": wins,
        "losses": len(losses),
        "winrate": round(wins / total * 100, 1) if total > 0 else 0,
        "total_profit": round(sum(profits), 2),
        "total_loss": round(abs(sum(losses)), 2),
        "net_pnl": round(sum(all_pnl), 2),
        "avg_rr": round(sum(rrs) / len(rrs), 2) if rrs else 0,
        "best_trade": round(max(all_pnl), 2) if all_pnl else 0,
        "worst_trade": round(min(all_pnl), 2) if all_pnl else 0,
        "open_trades": len(open_trades),
        "open_pnl": round(open_pnl, 2),
        "consecutive_wins": _consecutive(history, win=True),
        "consecutive_losses": _consecutive(history, win=False),
    }


def _consecutive(history, win=True):
    count = best = 0
    for t in reversed(history):
        p = t.get("profit", 0)
        if (win and p > 0) or (not win and p <= 0):
            count += 1
            best = max(best, count)
        else:
            count = 0
    return best


# ─────────────────────────────────────────────────────────────────
# État du système de trading
# ─────────────────────────────────────────────────────────────────

def get_trading_state() -> dict:
    return _load(STATE_FILE, {
        "active": False,
        "mode": "manual",
        "min_confidence": 72,
        "risk_percent": 1.0,
        "max_trades": 3,
        "allowed_symbols": ["XAUUSDm", "XAUUSD"],
        "last_analysis": None,
        "last_signal": None,
        "started_at": None,
    })


def set_trading_state(updates: dict):
    with _lock:
        state = get_trading_state()
        state.update(updates)
        _save(STATE_FILE, state)
        return state
