import type { LogEntry, LogLevel } from "@/hooks/useTradingState";
import { cn } from "@/lib/utils";

interface SystemLogProps {
  entries: LogEntry[];
  onClear: () => void;
}

const LEVEL_CLS: Record<LogLevel, string> = {
  info:    "text-trading-text",
  success: "text-trading-green",
  warning: "text-trading-gold",
  error:   "text-trading-red",
};

export function SystemLog({ entries, onClear }: SystemLogProps) {
  return (
    <div className="card-trading col-span-2">
      <div className="card-trading-head">
        <span className="card-trading-title">Journal système</span>
        <button
          onClick={onClear}
          className="bg-transparent border-none text-trading-text3 text-[10px] cursor-pointer
                     hover:text-trading-cyan transition-colors"
        >
          Effacer
        </button>
      </div>
      <div className="px-3 py-1 max-h-[150px] overflow-y-auto">
        {entries.length === 0 ? (
          <div className="text-center py-3 font-orbitron text-[9px] tracking-wider text-trading-text3">
            (vide)
          </div>
        ) : (
          entries.map((e) => (
            <div
              key={e.id}
              className="flex gap-2.5 py-1 font-tech text-[11px] border-b border-[rgba(13,58,90,0.3)] last:border-b-0"
            >
              <span className="text-trading-text3 w-[50px] shrink-0">{e.time}</span>
              <span className={cn(LEVEL_CLS[e.level])}>{e.msg}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
