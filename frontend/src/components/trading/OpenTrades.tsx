import type { OpenPosition } from "@/hooks/useTradingState";
import { cn } from "@/lib/utils";

interface OpenTradesProps {
  positions: OpenPosition[];
}

export function OpenTrades({ positions }: OpenTradesProps) {
  const totalPnl = positions.reduce((s, p) => s + (p.profit || 0), 0);
  const isPos = totalPnl >= 0;

  return (
    <div className="card-trading col-span-2">
      <div className="card-trading-head">
        <span className="card-trading-title">Positions ouvertes</span>
        <span className={cn(
          "font-tech text-[11px]",
          isPos ? "text-trading-green" : "text-trading-red",
        )}>
          {positions.length} trade(s) · P&L : {isPos ? "+" : ""}{totalPnl.toFixed(2)}$
        </span>
      </div>
      <div className="px-2 py-2">
        {positions.length === 0 ? (
          <div className="text-center py-5 font-orbitron text-[10px] tracking-[2px] text-trading-text3">
            AUCUNE POSITION
          </div>
        ) : (
          <div className="flex flex-col gap-1.5 max-h-[260px] overflow-y-auto">
            {positions.map((p) => (
              <TradeRow key={p.ticket} pos={p} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function TradeRow({ pos }: { pos: OpenPosition }) {
  const isBuy = pos.type === "BUY";
  const profit = pos.profit ?? 0;
  const isPnLPos = profit >= 0;
  const fmt = (v?: number) => (v == null ? "—" : v.toFixed(2));

  return (
    <div className="grid grid-cols-[60px_50px_70px_80px_80px_80px_1fr] gap-2 items-center
                    bg-trading-bg3 border border-trading-border rounded-[3px]
                    px-2.5 py-2 font-tech text-[11px] hover:border-trading-cyan/40 transition-colors">
      <Cell label="TICKET" value={`#${pos.ticket}`} />
      <span className={cn("font-semibold", isBuy ? "text-trading-green" : "text-trading-red")}>
        {pos.type}
      </span>
      <Cell label="LOT" value={pos.volume} />
      <Cell label="ENTRÉE" value={fmt(pos.open_price)} />
      <Cell label="SL" value={fmt(pos.sl)} />
      <Cell label="TP" value={fmt(pos.tp)} />
      <span className={cn(
        "font-semibold text-right",
        isPnLPos ? "text-trading-green" : "text-trading-red",
      )}>
        {(isPnLPos ? "+" : "") + profit.toFixed(2)}$
      </span>
    </div>
  );
}

function Cell({ label, value }: { label: string; value: string | number }) {
  return (
    <span>
      <span className="block font-orbitron text-[8px] text-trading-text2 leading-none mb-0.5">
        {label}
      </span>
      {value}
    </span>
  );
}
