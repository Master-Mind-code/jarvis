import { Play, Square, X, Zap } from "lucide-react";
import { cn } from "@/lib/utils";

export interface TradingParams {
  risk_percent: number;
  min_confidence: number;
  max_trades: number;
}

interface ControlBarProps {
  connected: boolean;
  systemActive: boolean;
  params: TradingParams;
  setParams: (p: TradingParams) => void;
  token: string;
  setToken: (t: string) => void;
  onConnect: () => void;
  onStart: () => void;
  onStop: () => void;
  onCloseAll: () => void;
}

export function ControlBar({
  connected, systemActive, params, setParams,
  token, setToken,
  onConnect, onStart, onStop, onCloseAll,
}: ControlBarProps) {
  return (
    <div className="card-trading col-span-full">
      <div className="flex items-center gap-3 flex-wrap px-3.5 py-3">
        <Btn variant="connect" onClick={onConnect}>
          <Zap size={12} /> {connected ? "RECONNECTER" : "CONNECTER"}
        </Btn>
        <Btn variant="start" onClick={onStart} disabled={systemActive || !connected}>
          <Play size={12} fill="currentColor" /> DÉMARRER
        </Btn>
        <Btn variant="stop" onClick={onStop} disabled={!systemActive}>
          <Square size={12} fill="currentColor" /> ARRÊTER
        </Btn>
        <Btn variant="closeAll" onClick={onCloseAll} disabled={!connected}>
          <X size={13} strokeWidth={2.5} /> CLÔTURER TOUT
        </Btn>

        <Param
          label="RISQUE %"
          value={params.risk_percent}
          min={0.1}
          max={5}
          step={0.1}
          onChange={(v) => setParams({ ...params, risk_percent: v })}
        />
        <Param
          label="CONFIANCE MIN"
          value={params.min_confidence}
          min={50}
          max={95}
          step={1}
          onChange={(v) => setParams({ ...params, min_confidence: v })}
        />
        <Param
          label="MAX TRADES"
          value={params.max_trades}
          min={1}
          max={10}
          step={1}
          onChange={(v) => setParams({ ...params, max_trades: v })}
        />

        <div className="ml-auto flex items-center gap-2">
          <span className="font-orbitron text-[9px] tracking-wider text-trading-text2">TOKEN</span>
          <input
            type="password"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            placeholder="ORION_SECRET_TOKEN"
            className="w-[200px] px-2 py-1.5 bg-trading-bg3 border border-trading-border rounded-sm
                       text-trading-text font-tech text-[12px] outline-none
                       focus:border-trading-cyan transition-colors"
          />
        </div>
      </div>
    </div>
  );
}

const VARIANTS = {
  connect: "bg-trading-cyan/15 border-trading-cyan text-trading-cyan hover:bg-trading-cyan/25",
  start:   "bg-trading-green/15 border-trading-green text-trading-green hover:bg-trading-green/25 hover:shadow-[0_0_12px_rgba(0,230,118,0.3)]",
  stop:    "bg-trading-red/15 border-trading-red text-trading-red hover:bg-trading-red/25",
  closeAll: "bg-trading-gold/10 border-trading-gold text-trading-gold hover:bg-trading-gold/20",
} as const;

function Btn({
  children, variant, onClick, disabled,
}: {
  children: React.ReactNode;
  variant: keyof typeof VARIANTS;
  onClick: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={cn(
        "inline-flex items-center gap-1.5 px-4 py-2 rounded-sm border transition-all cursor-pointer",
        "font-orbitron text-[9px] tracking-[2px] uppercase whitespace-nowrap",
        VARIANTS[variant],
        "disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:shadow-none",
      )}
    >
      {children}
    </button>
  );
}

function Param({
  label, value, min, max, step, onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (v: number) => void;
}) {
  return (
    <div className="flex items-center gap-2">
      <span className="font-orbitron text-[9px] tracking-wider text-trading-text2 whitespace-nowrap">
        {label}
      </span>
      <input
        type="number"
        value={value}
        min={min}
        max={max}
        step={step}
        onChange={(e) => onChange(parseFloat(e.target.value) || 0)}
        className="w-[70px] px-2 py-1.5 bg-trading-bg3 border border-trading-border rounded-sm
                   text-trading-text font-tech text-[12px] outline-none
                   focus:border-trading-cyan transition-colors"
      />
    </div>
  );
}
