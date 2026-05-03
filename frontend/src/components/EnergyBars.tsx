interface EnergyBarsProps {
  /** Niveau audio voix (0..1) — typiquement passé en ref pour réactivité frame-by-frame */
  voiceLevel: number;
  neural?: number; // 0-100, défault auto-flicker
  net?: number;    // 0-100, défault auto-flicker
}

import { useEffect, useState } from "react";

export function EnergyBars({ voiceLevel, neural, net }: EnergyBarsProps) {
  const [autoNeural, setAutoNeural] = useState(72);
  const [autoNet, setAutoNet] = useState(35);

  useEffect(() => {
    const id = window.setInterval(() => {
      setAutoNeural(Math.round(60 + Math.random() * 30));
      setAutoNet(Math.round(25 + Math.random() * 25));
    }, 1200);
    return () => window.clearInterval(id);
  }, []);

  const voicePct = Math.round(voiceLevel * 100);
  const rows = [
    { label: "NEURAL", pct: neural ?? autoNeural },
    { label: "VOICE",  pct: voicePct },
    { label: "NET",    pct: net ?? autoNet },
  ];

  return (
    <div className="fixed bottom-6 left-1/2 -translate-x-1/2 w-[min(560px,90vw)]
                    z-10 flex flex-col gap-1">
      {rows.map(r => (
        <div key={r.label} className="flex items-center gap-2.5">
          <div className="font-mono text-[8px] tracking-[1.5px] text-text-dim min-w-[56px] uppercase">
            {r.label}
          </div>
          <div className="flex-1 h-0.5 bg-cyan/[0.06] rounded-sm overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-cyan to-cyan/60 rounded-sm
                         shadow-[0_0_6px_var(--tw-shadow-color)] shadow-cyan-glow
                         transition-[width] duration-500"
              style={{ width: `${r.pct}%` }}
            />
          </div>
          <div className="font-mono text-[9px] text-text-dim min-w-[36px] text-right">
            {r.pct}%
          </div>
        </div>
      ))}
    </div>
  );
}
