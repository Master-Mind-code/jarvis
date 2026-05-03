import type { TradingStats } from "@/hooks/useTradingState";
import { cn } from "@/lib/utils";

interface StatsGridProps {
  stats: TradingStats;
}

export function StatsGrid({ stats }: StatsGridProps) {
  const fmt = (v?: number, decimals = 2) => (v == null ? "—" : v.toFixed(decimals));
  const fmtSign = (v?: number, decimals = 2) =>
    v == null ? "—" : (v >= 0 ? "+" : "") + v.toFixed(decimals);

  type Color = "cyan" | "green" | "red" | "gold";
  const greenIf = (b: boolean): Color => (b ? "green" : "red");
  const items: { label: string; val: string | number; color: Color }[] = [
    { label: "Trades",        val: stats.total_trades ?? "—",                color: "cyan" },
    { label: "Win Rate",      val: (stats.winrate ?? "—") + "%",             color: greenIf((stats.winrate ?? 0) >= 50) },
    { label: "Net P&L $",     val: fmtSign(stats.net_pnl) + "$",             color: greenIf((stats.net_pnl ?? 0) >= 0) },
    { label: "RR Moyen",      val: stats.avg_rr ? "1:" + stats.avg_rr : "—", color: "gold" },
    { label: "Profit total",  val: "+" + fmt(stats.total_profit) + "$",      color: "green" },
    { label: "Perte totale",  val: "-" + fmt(stats.total_loss) + "$",        color: "red" },
    { label: "Meilleur trade", val: "+" + fmt(stats.best_trade) + "$",       color: "green" },
    { label: "Pire trade",    val: fmt(stats.worst_trade) + "$",             color: "red" },
  ];

  return (
    <div className="card-trading col-span-full">
      <div className="card-trading-head">
        <span className="card-trading-title">Statistiques</span>
      </div>
      <div className="card-trading-body">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          {items.map((it) => (
            <StatBox key={it.label} {...it} />
          ))}
        </div>
      </div>
    </div>
  );
}

const COLOR_CLS = {
  cyan:  "text-trading-cyan",
  green: "text-trading-green",
  red:   "text-trading-red",
  gold:  "text-trading-gold",
} as const;

function StatBox({
  label, val, color,
}: { label: string; val: string | number; color: keyof typeof COLOR_CLS }) {
  return (
    <div className="bg-trading-bg3 border border-trading-border rounded-[3px] px-3 py-2.5 text-center">
      <div className={cn("font-tech text-[18px] font-semibold leading-none mb-1", COLOR_CLS[color])}>
        {val}
      </div>
      <div className="font-orbitron text-[8px] tracking-[2px] text-trading-text2 uppercase">
        {label}
      </div>
    </div>
  );
}
