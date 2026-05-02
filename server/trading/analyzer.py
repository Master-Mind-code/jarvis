"""
Orion Trading — Analyseur IA (Claude API)
Reçoit les données marché multi-TF et retourne une décision de trade
basée sur SMC, ICT, Price Action, Supply/Demand.
"""
import os
import json
import re
from anthropic import Anthropic
from datetime import datetime
from branding import get_env

client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

TRADER_MODEL = get_env("TRADER_MODEL", "claude-haiku-4-5-20251001")

# ─────────────────────────────────────────────────────────────────
# Prompt système du trader IA
# ─────────────────────────────────────────────────────────────────
TRADER_SYSTEM = """Tu es ORION-TRADER, un système de trading algorithmique expert de niveau institutionnel.

Tu maîtrises :
- SMC (Smart Money Concepts) : BOS, CHoCH, Order Blocks, FVG, Liquidité BSL/SSL
- ICT (Inner Circle Trader) : Killzones, OTE, Breaker Blocks, Mitigation Blocks
- Price Action pure : structures, patterns de bougies, momentum
- Supply & Demand : zones institutionnelles fraîches vs usées
- Analyse multi-timeframe : HTF pour le biais, LTF pour l'entrée

RÈGLES ABSOLUES :
1. Ne trader QUE si le setup est propre et confluent (≥3 confirmations)
2. Risk/Reward minimum : 1:2 (idéal 1:3 ou plus)
3. SL obligatoirement DERRIÈRE une structure (OB, liquidity, swing)
4. TP sur prochaine liquidité significative
5. Jamais contre la tendance HTF (H4) sans CHoCH confirmé
6. Pas de trade pendant spread élevé ou volatilité extrême

RÉPONSE : Tu dois TOUJOURS retourner un JSON valide et rien d'autre.
Format obligatoire :
{
  "decision": "BUY" | "SELL" | "WAIT",
  "confidence": 0-100,
  "timeframe_entry": "M5|M15|M30|H1|H4",
  "strategy": "SMC|ICT|PA|SD|MIXED",
  "entry": <prix ou null>,
  "sl": <prix ou null>,
  "tp1": <prix ou null>,
  "tp2": <prix ou null>,
  "rr": <ratio ou null>,
  "lot_factor": <0.5|1.0|1.5|2.0>,
  "analysis": {
    "htf_bias": "BULLISH|BEARISH|NEUTRAL",
    "structure": "<description courte>",
    "key_levels": ["<niveau1>", "<niveau2>"],
    "confluences": ["<conf1>", "<conf2>", "<conf3>"],
    "invalidation": "<condition d'invalidation>",
    "reasoning": "<explication 2-3 phrases>"
  },
  "wait_reason": "<si WAIT: raison courte>"
}"""


def build_analysis_prompt(market_data: dict) -> str:
    symbol   = market_data.get("symbol", "XAUUSD")
    bid      = market_data.get("bid", 0)
    ask      = market_data.get("ask", 0)
    spread   = market_data.get("spread", 0)
    account  = market_data.get("account", {})
    balance  = account.get("balance", 0)
    equity   = account.get("equity", 0)
    tfs      = market_data.get("timeframes", {})
    open_pos = market_data.get("open_positions", [])

    def fmt_candles(candles: list, n=10) -> str:
        recent = candles[-n:] if len(candles) >= n else candles
        lines = []
        for c in recent:
            ts = datetime.fromtimestamp(c['t']).strftime('%H:%M') if 't' in c else ''
            lines.append(f"  {ts} O:{c['o']:.2f} H:{c['h']:.2f} L:{c['l']:.2f} C:{c['c']:.2f} V:{c.get('v',0)}")
        return "\n".join(lines)

    def momentum(candles: list) -> str:
        if len(candles) < 5: return "N/A"
        last5 = candles[-5:]
        bullish = sum(1 for c in last5 if c['c'] > c['o'])
        return f"{bullish}/5 haussières"

    prompt = f"""=== DONNÉES MARCHÉ TEMPS RÉEL ===
Symbole : {symbol}
Prix actuel : Bid={bid:.5f} Ask={ask:.5f} Spread={spread}pts
Compte : Balance={balance:.2f}$ Equity={equity:.2f}$
Positions ouvertes : {len(open_pos)} trade(s)

"""
    tf_order = ["H4", "H1", "M30", "M15", "M5"]
    for tf in tf_order:
        if tf not in tfs: continue
        d = tfs[tf]
        candles = d.get("candles", [])
        atr     = d.get("atr", 0)
        s_high  = d.get("swing_high", 0)
        s_low   = d.get("swing_low", 0)

        prompt += f"--- {tf} ---\n"
        prompt += f"ATR14={atr:.5f} | Swing High={s_high:.5f} | Swing Low={s_low:.5f}\n"
        prompt += f"Momentum: {momentum(candles)}\n"
        prompt += f"Dernières bougies:\n{fmt_candles(candles, 8)}\n\n"

    if open_pos:
        prompt += "=== POSITIONS OUVERTES ===\n"
        for p in open_pos:
            prompt += f"  #{p.get('ticket')} {p.get('type')} | Vol:{p.get('volume')} | "
            prompt += f"Entry:{p.get('open_price'):.5f} SL:{p.get('sl'):.5f} TP:{p.get('tp'):.5f} | "
            prompt += f"P&L: {p.get('profit'):.2f}$\n"
        prompt += "\n"

    prompt += """=== INSTRUCTION ===
Analyse ces données avec ta méthodologie institutionnelle complète.
Identifie le meilleur setup si présent. Retourne UNIQUEMENT le JSON de décision."""

    return prompt


def analyze_market(market_data: dict) -> dict:
    """
    Appelle Claude pour analyser le marché et retourner une décision.
    Retourne le dict de décision parsé.
    """
    prompt = build_analysis_prompt(market_data)

    try:
        response = client.messages.create(
            model=TRADER_MODEL,  # Haiku = rapide + économique pour les analyses fréquentes
            max_tokens=1000,
            # Prompt caching : le system prompt (~600 tokens) est identique à chaque appel.
            # → après le 1er appel, les hits sont facturés ~10 % de leur prix normal.
            system=[{
                "type": "text",
                "text": TRADER_SYSTEM,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": prompt}],
        )

        raw = response.content[0].text.strip()

        # Extraction JSON robuste
        json_match = re.search(r'\{[\s\S]*\}', raw)
        if json_match:
            decision = json.loads(json_match.group())
        else:
            decision = json.loads(raw)

        # Validation minimale
        required = ["decision", "confidence", "entry", "sl", "tp1"]
        for field in required:
            if field not in decision:
                decision[field] = None

        decision["raw_response"] = raw
        decision["analyzed_at"]  = datetime.now().isoformat()
        decision["symbol"]       = market_data.get("symbol", "")
        decision["bid"]          = market_data.get("bid", 0)

        return decision

    except json.JSONDecodeError as e:
        return {
            "decision": "WAIT",
            "confidence": 0,
            "wait_reason": f"Erreur parsing JSON: {str(e)}",
            "analyzed_at": datetime.now().isoformat(),
            "error": True,
        }
    except Exception as e:
        return {
            "decision": "WAIT",
            "confidence": 0,
            "wait_reason": f"Erreur analyse: {str(e)}",
            "analyzed_at": datetime.now().isoformat(),
            "error": True,
        }


def should_execute(decision: dict, min_confidence: int = 70) -> bool:
    """Détermine si une décision doit être exécutée."""
    if decision.get("decision") == "WAIT":
        return False
    if decision.get("error"):
        return False
    confidence = decision.get("confidence", 0)
    if confidence < min_confidence:
        return False
    if not decision.get("entry") or not decision.get("sl") or not decision.get("tp1"):
        return False
    rr = decision.get("rr", 0)
    if rr and rr < 2.0:  # RR minimum 1:2
        return False
    return True
