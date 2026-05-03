import { useEffect, useState } from "react";
import { Settings, ArrowLeft, Mic, TrendingUp, AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";

export type VoiceServiceState = "offline" | "idle" | "wake" | "listening" | "thinking" | "speaking";

interface HeaderProps {
  variant?: "voice" | "orion";
  connected: boolean;
  onOpenSettings: () => void;
  panicActive?: boolean;
  onPanicToggle?: () => void;
  voiceServiceState?: VoiceServiceState;
  voiceDeviceId?: string;
}

function useClock() {
  const [time, setTime] = useState("");
  useEffect(() => {
    const tick = () => {
      const now = new Date();
      setTime(
        `${String(now.getHours()).padStart(2, "0")}:` +
        `${String(now.getMinutes()).padStart(2, "0")}:` +
        `${String(now.getSeconds()).padStart(2, "0")}`
      );
    };
    tick();
    const id = window.setInterval(tick, 1000);
    return () => window.clearInterval(id);
  }, []);
  return time;
}

const VOICE_LABELS: Record<VoiceServiceState, string> = {
  offline:   "VOIX",
  idle:      'VOIX · INACTIF',
  wake:      'VOIX · "HEY ORION"',
  listening: "VOIX · ÉCOUTE",
  thinking:  "VOIX · TRAITEMENT",
  speaking:  "VOIX · PARLE",
};

function VoicePill({ state, deviceId }: { state: VoiceServiceState; deviceId?: string }) {
  if (state === "offline") return null;
  const cls = cn(
    "hud-pill",
    state === "idle"      && "border-cyan/20 text-cyan [&>span:first-child]:bg-cyan",
    state === "wake"      && "border-cyan/30 text-cyan [&>span:first-child]:bg-cyan [&>span:first-child]:animate-pulse-dot",
    state === "listening" && "border-red/45 text-red [&>span:first-child]:bg-red [&>span:first-child]:animate-pulse-fast",
    state === "thinking"  && "border-gold/45 text-gold [&>span:first-child]:bg-gold [&>span:first-child]:animate-pulse-fast",
    state === "speaking"  && "border-green/45 text-green [&>span:first-child]:bg-green [&>span:first-child]:animate-pulse-fast",
  );
  return (
    <div className={cls} title={`Service voix · ${deviceId || "?"}`}>
      <span className="w-1.5 h-1.5 rounded-full" />
      <span>{VOICE_LABELS[state]}</span>
    </div>
  );
}

export function Header({
  variant = "voice",
  connected,
  onOpenSettings,
  panicActive,
  onPanicToggle,
  voiceServiceState = "offline",
  voiceDeviceId,
}: HeaderProps) {
  const time = useClock();
  const subtitle = variant === "voice" ? "VOICE MODE" : "PERSONAL AI";

  return (
    <header className="relative z-20 flex items-center justify-between px-5 py-3.5
                       border-b border-border bg-bg-3 backdrop-blur-panel">
      <div className="flex items-center gap-3">
        <img src="/assets/orion-mark.svg" alt="Orion" className="w-7 h-7" />
        <div className="font-orbitron text-[14px] tracking-[5px] font-black
                        text-cyan [text-shadow:0_0_12px_var(--tw-shadow-color)]
                        shadow-cyan-glow leading-none">
          ORION
          <span className="block text-[7px] tracking-[4px] text-text-dim font-normal mt-[2px]">
            {subtitle}
          </span>
        </div>
      </div>

      <div className="flex items-center gap-2">
        <div className="font-mono text-[11px] tracking-wider text-text-dim min-w-[68px] text-right">
          {time}
        </div>

        <div
          className={cn(
            "hud-pill",
            connected
              ? "border-green/35 text-green [&>span:first-child]:bg-green [&>span:first-child]:shadow-[0_0_8px_#00ffa3]"
              : ""
          )}
        >
          <span className={cn(
            "w-1.5 h-1.5 rounded-full animate-pulse-dot",
            connected ? "bg-green shadow-[0_0_8px_#00ffa3]" : "bg-text-dim/40"
          )} />
          <span>{connected ? "EN LIGNE" : "HORS LIGNE"}</span>
        </div>

        {variant === "orion" && (
          <VoicePill state={voiceServiceState} deviceId={voiceDeviceId} />
        )}

        {onPanicToggle && (
          <button
            onClick={onPanicToggle}
            title={panicActive ? "PANIC ACTIF · click pour rétablir" : "Activer le mode PANIC"}
            className={cn(
              "hud-btn",
              panicActive
                ? "border-red text-red bg-red/30 shadow-[0_0_20px_rgba(255,59,92,0.7)] animate-pulse-fast"
                : "border-red/40 text-red bg-red/[0.06] hover:bg-red/[0.18]"
            )}
          >
            <AlertTriangle size={13} strokeWidth={1.8} />
            PANIC
          </button>
        )}

        {variant === "orion" && (
          <a href="/voice" className="hud-btn border-cyan/35 text-cyan bg-cyan/[0.06] hover:bg-cyan/[0.14]"
             title="Mode voix dédié (sphère immersive)">
            <Mic size={13} strokeWidth={1.8} />
            VOICE
          </a>
        )}

        {variant === "orion" && (
          <a href="/trading" className="hud-btn border-gold/35 text-gold bg-gold/[0.08] hover:bg-gold/[0.18]"
             title="Espace de trading" target="_blank" rel="noopener">
            <TrendingUp size={13} strokeWidth={1.8} />
            TRADING
          </a>
        )}

        {variant === "voice" && (
          <a href="/" className="hud-btn border-border text-text-dim hover:text-cyan hover:border-border-hi"
             title="Retour à l'UI principale">
            <ArrowLeft size={13} strokeWidth={1.8} />
            CHAT
          </a>
        )}

        <button
          onClick={onOpenSettings}
          className="w-9 h-9 inline-flex items-center justify-center
                     border border-border bg-bg-3 rounded-sm text-text-dim
                     hover:border-border-hi hover:text-cyan hover:bg-cyan-dim
                     transition-all backdrop-blur-panel cursor-pointer"
          title="Paramètres"
        >
          <Settings size={15} />
        </button>
      </div>
    </header>
  );
}
