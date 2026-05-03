import type { SignalData, SignalDecision } from "@/hooks/useTradingState";
import { cn } from "@/lib/utils";

interface SignalPanelProps {
  signal: SignalData;
}

const BADGE_CLS: Record<SignalDecision, string> = {
  BUY:  "bg-trading-green/15 border-trading-green text-trading-green",
  SELL: "bg-trading-red/15 border-trading-red text-trading-red",
  WAIT: "bg-[rgba(100,100,100,0.1)] border-[#444] text-[#888]",
};

export function SignalPanel({ signal }: SignalPanelProps) {
  const decision = (signal.decision ?? "WAIT") as SignalDecision;
  const conf = signal.confidence ?? 0;
  const fillColor =
    conf >= 75 ? "bg-trading-green"
    : conf >= 55 ? "bg-trading-gold"
    : "bg-trading-red";
  const fmt = (v?: number) => (v == null ? "—" : v.toFixed(2));
  const confluences = signal.analysis?.confluences ?? [];
  const reasoning = signal.analysis?.reasoning || signal.wait_reason || "—";

  return (
    <div className="card-trading">
      <div className="card-trading-head">
        <span className="card-trading-title">Signal IA · Dernière analyse</span>
      </div>
      <div className="card-trading-body">
        <div className="flex items-center gap-3 mb-3.5">
          <div className={cn(
            "font-orbitron text-[14px] font-bold tracking-[3px] px-4 py-2 rounded-[3px] border",
            BADGE_CLS[decision],
          )}>
            {decision}
          </div>
          <div className="flex-1">
            <div className="h-1.5 bg-trading-bg3 rounded-[3px] overflow-hidden">
              <div className={cn("h-full rounded-[3px] transition-[width] duration-500", fillColor)}
                   style={{ width: `${conf}%` }} />
            </div>
            <div className="font-orbitron text-[8px] text-trading-text2 mt-1">
              CONFIANCE : <span className="text-trading-text">{conf}%</span>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-1.5 mb-2.5">
          <Level name="ENTRÉE"     value={fmt(signal.entry)} />
          <Level name="STOP LOSS"  value={fmt(signal.sl)}    valueColor="text-trading-red" />
          <Level name="TP1"        value={fmt(signal.tp1)}   valueColor="text-trading-green" />
          <Level name="R/R"        value={signal.rr ? "1:" + signal.rr : "—"} valueColor="text-trading-gold" />
        </div>

        <div className="text-[12px] text-trading-text2 leading-snug min-h-[40px] mb-2">
          {reasoning}
        </div>

        {confluences.length > 0 && (
          <div className="flex flex-col gap-1">
            {confluences.map((c, i) => (
              <div key={i} className="flex items-center gap-1.5 text-[12px]">
                <span className="w-1.5 h-1.5 rounded-full bg-trading-cyan shrink-0" />
                <span>{c}</span>
              </div>
            ))}
          </div>
        )}

        <div className="mt-2.5 font-orbitron text-[8px] text-trading-text3">
          Analyse : {signal.analyzed_at || "—"}
          {signal.timeframe_entry && <> · TF : {signal.timeframe_entry}</>}
          {signal.strategy && <> · {signal.strategy}</>}
        </div>
      </div>
    </div>
  );
}

function Level({
  name, value, valueColor,
}: { name: string; value: string; valueColor?: string }) {
  return (
    <div className="bg-trading-bg3 border border-trading-border rounded-[3px] px-2.5 py-2">
      <div className="font-orbitron text-[8px] tracking-wider text-trading-text2 mb-1">
        {name}
      </div>
      <div className={cn("font-tech text-[13px]", valueColor)}>{value}</div>
    </div>
  );
}
