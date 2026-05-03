import { ArrowLeft } from "lucide-react";
import type { MarketTick } from "@/hooks/useTradingState";
import { cn } from "@/lib/utils";

export type TradingStatus = "active" | "idle" | "error" | "connecting";

interface TradingHeaderProps {
  market: MarketTick;
  status: TradingStatus;
  statusLabel: string;
}

const DOT_CLS: Record<TradingStatus, string> = {
  active:     "bg-trading-green shadow-[0_0_8px_#00e676] animate-blink",
  idle:       "bg-trading-text3",
  error:      "bg-trading-red",
  connecting: "bg-trading-gold animate-blink",
};

export function TradingHeader({ market, status, statusLabel }: TradingHeaderProps) {
  const fmt = (v?: number) => (v == null ? "—" : v.toFixed(2));
  const account = market.account;

  return (
    <header className="relative z-10 flex items-center justify-between gap-4 flex-wrap
                       px-6 py-3 border-b border-trading-border bg-[rgba(6,9,15,0.96)]">
      <div className="flex items-center gap-3.5">
        <a
          href="/"
          className="font-orbitron text-[9px] tracking-[2px] px-3 py-1.5 inline-flex items-center gap-1.5
                     border border-trading-border bg-trading-bg3 text-trading-text2 rounded-sm
                     no-underline transition-all
                     hover:border-trading-cyan hover:text-trading-cyan hover:bg-trading-cyan/[0.06]"
        >
          <ArrowLeft size={11} strokeWidth={2} /> ORION
        </a>
        <div className="flex items-center gap-3">
          <img src="/assets/orion-mark.svg" alt="Orion" className="w-7 h-7
                       drop-shadow-[0_0_12px_rgba(0,212,255,0.4)]" />
          <div className="flex flex-col font-orbitron font-black text-[14px] tracking-[5px] leading-none
                          text-trading-cyan [text-shadow:0_0_15px_rgba(0,212,255,0.5)]">
            ORION
            <span className="mt-1 text-[8px] tracking-[3px] text-trading-text2">TRADER</span>
          </div>
        </div>
      </div>

      <div className="flex items-center gap-5 flex-wrap">
        <div className="font-tech text-[13px] flex items-baseline gap-1">
          <span className="text-trading-text2 text-[11px] tracking-wide">BID</span>
          <span className="text-trading-green">{fmt(market.bid)}</span>
          <span className="text-trading-text2 text-[11px] tracking-wide ml-3">ASK</span>
          <span className="text-trading-red">{fmt(market.ask)}</span>
          <span className="text-trading-text2 text-[11px] tracking-wide ml-3">SPREAD</span>
          <span className="text-trading-text2">{market.spread ?? "—"}</span>
        </div>
        {account && (
          <div className="font-tech text-[11px] text-trading-text2">
            Balance : {fmt(account.balance)}$ · Equity : {fmt(account.equity)}$
            {account.margin_free != null && <> · Free : {fmt(account.margin_free)}$</>}
          </div>
        )}
      </div>

      <div className="flex items-center gap-2 font-orbitron text-[9px] tracking-[2px] text-trading-text2">
        <span className={cn("w-2 h-2 rounded-full", DOT_CLS[status])} />
        <span>{statusLabel}</span>
      </div>
    </header>
  );
}
