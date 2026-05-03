import type { HistoryTrade } from "@/hooks/useTradingState";
import { cn } from "@/lib/utils";

interface TradeHistoryProps {
  history: HistoryTrade[];
}

const COLS = "grid-cols-[50px_50px_80px_80px_80px_80px_1fr]";

export function TradeHistory({ history }: TradeHistoryProps) {
  return (
    <div className="card-trading col-span-full">
      <div className="card-trading-head">
        <span className="card-trading-title">Historique des trades</span>
      </div>
      <div className={cn("grid gap-2 px-3 py-1.5 border-b border-trading-border",
                         "font-orbitron text-[8px] tracking-wider text-trading-text3 uppercase",
                         COLS)}>
        <span>#</span>
        <span>TYPE</span>
        <span>ENTRÉE</span>
        <span>SORTIE</span>
        <span>SL</span>
        <span>TP</span>
        <span>P&L</span>
      </div>
      {history.length === 0 ? (
        <div className="text-center py-4 font-orbitron text-[10px] tracking-[2px] text-trading-text3">
          AUCUN HISTORIQUE
        </div>
      ) : (
        <div className="max-h-[220px] overflow-y-auto">
          {history.map((t, i) => (
            <HistoryRow key={t.id ?? t.ticket ?? i} trade={t} />
          ))}
        </div>
      )}
    </div>
  );
}

function HistoryRow({ trade }: { trade: HistoryTrade }) {
  const isBuy = trade.type === "BUY";
  const profit = trade.profit ?? 0;
  const isPos = profit >= 0;
  const fmt = (v?: number) => (v == null ? "—" : v.toFixed(2));

  return (
    <div className={cn(
      "grid gap-2 px-3 py-1.5 font-tech text-[11px]",
      "border-b border-[rgba(13,58,90,0.4)] hover:bg-trading-bg3 transition-colors",
      COLS,
    )}>
      <span>#{trade.id ?? trade.ticket}</span>
      <span className={cn("font-semibold", isBuy ? "text-trading-green" : "text-trading-red")}>
        {trade.type}
      </span>
      <span>{fmt(trade.open_price)}</span>
      <span>{fmt(trade.close_price)}</span>
      <span className="text-trading-red">{fmt(trade.sl)}</span>
      <span className="text-trading-green">{fmt(trade.tp)}</span>
      <span className={cn("font-semibold", isPos ? "text-trading-green" : "text-trading-red")}>
        {(isPos ? "+" : "") + profit.toFixed(2)}$
      </span>
    </div>
  );
}
