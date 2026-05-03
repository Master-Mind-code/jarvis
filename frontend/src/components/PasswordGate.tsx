import { useEffect, useRef, useState } from "react";
import { Mic } from "lucide-react";
import { cn } from "@/lib/utils";
import { isPasswordMatch } from "@/lib/passwords";

interface PasswordGateProps {
  /** True quand le gate doit être visible. */
  open: boolean;
  /** Appelé quand l'utilisateur valide (texte ou voix). */
  onUnlock: () => void;
}

type HintKind = "info" | "error" | "success";

export function PasswordGate({ open, onUnlock }: PasswordGateProps) {
  const [pwd, setPwd] = useState("");
  const [hint, setHint] = useState<{ text: string; kind: HintKind }>({
    text: "Saisis ou prononce le mot de passe",
    kind: "info",
  });
  const [hiding, setHiding] = useState(false);
  const [listening, setListening] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const recognitionRef = useRef<any>(null);

  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 80);
  }, [open]);

  const tryUnlock = (raw: string, viaVoice = false) => {
    if (isPasswordMatch(raw)) {
      setHint({
        text: viaVoice ? "Déverrouillé par la voix." : "Identifié. Bienvenue, Dominique.",
        kind: "success",
      });
      setHiding(true);
      setTimeout(onUnlock, 700);
    } else {
      setHint({ text: "Mot de passe incorrect.", kind: "error" });
      setPwd("");
    }
  };

  const onSubmit = () => tryUnlock(pwd);

  const toggleMic = () => {
    const SR =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SR) {
      setHint({ text: "Reconnaissance vocale non supportée.", kind: "error" });
      return;
    }
    if (listening) {
      recognitionRef.current?.stop?.();
      return;
    }
    const rec = new SR();
    rec.lang = "fr-FR";
    rec.continuous = false;
    rec.interimResults = false;
    rec.onstart = () => {
      setListening(true);
      setHint({ text: "Écoute…", kind: "info" });
    };
    rec.onresult = (e: any) => {
      const t = e.results[0][0].transcript || "";
      setPwd(t);
      tryUnlock(t, true);
    };
    rec.onend = () => setListening(false);
    rec.onerror = () => setListening(false);
    recognitionRef.current = rec;
    rec.start();
  };

  if (!open) return null;

  return (
    <div
      className={cn(
        "fixed inset-0 z-[1000] flex items-center justify-center transition-opacity duration-700",
        "bg-[radial-gradient(ellipse_at_50%_50%,#080e1e_0%,#04060d_65%)]",
        hiding && "opacity-0 pointer-events-none",
      )}
    >
      <div className="gate-grid" />
      <div className="relative bg-[rgba(6,12,26,0.85)] border border-border
                      px-10 py-11 min-w-[380px] text-center backdrop-blur-[24px]
                      shadow-[0_0_80px_rgba(0,229,255,0.08),0_0_200px_rgba(0,229,255,0.04),inset_0_0_40px_rgba(0,229,255,0.02)]">
        <div className="flex flex-col items-center gap-4 mb-1.5">
          <img
            src="/assets/orion-mark.svg"
            alt="Logo Orion"
            className="w-[152px] drop-shadow-[0_0_20px_rgba(0,229,255,0.32)]"
          />
          <div className="relative font-orbitron font-black text-[36px] tracking-[12px] text-cyan logo-scan
                          [text-shadow:0_0_30px_rgba(0,229,255,0.4),0_0_80px_rgba(0,229,255,0.12)]">
            ORION
          </div>
        </div>

        <div className="font-orbitron text-[8px] tracking-[4px] text-text-dim uppercase mb-9">
          Système d'IA personnel — Authentification requise
        </div>

        <div className="w-12 h-px mx-auto mb-8
                        bg-gradient-to-r from-transparent via-cyan to-transparent" />

        <input
          ref={inputRef}
          type="password"
          value={pwd}
          onChange={(e) => setPwd(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              onSubmit();
            }
          }}
          placeholder="· · · · · ·"
          autoComplete="off"
          className="w-full px-4 py-3 bg-bg/80 border border-border rounded-sm
                     text-text font-mono text-lg text-center tracking-[6px]
                     outline-none transition-all caret-cyan
                     focus:border-cyan/45 focus:shadow-[0_0_20px_rgba(0,229,255,0.1)]"
        />

        <div className="flex gap-2.5 mt-4">
          <button
            onClick={onSubmit}
            className="flex-1 py-2.5 bg-cyan-dim border border-cyan/30 rounded-sm
                       text-cyan font-orbitron text-[9px] tracking-[2px] uppercase
                       cursor-pointer transition-all hover:bg-cyan/[0.14]"
          >
            Déverrouiller
          </button>
          <button
            onClick={toggleMic}
            className={cn(
              "flex-1 py-2.5 border rounded-sm font-orbitron text-[9px] tracking-[2px]",
              "uppercase cursor-pointer transition-all flex items-center justify-center gap-1.5",
              listening
                ? "border-red/45 bg-red/[0.08] text-red animate-pulse-fast"
                : "border-cyan/30 bg-cyan-dim text-cyan hover:bg-cyan/[0.14]",
            )}
          >
            <Mic size={12} />
            Voix
          </button>
        </div>

        <div
          className={cn(
            "mt-4 font-mono text-[10px] tracking-[1.5px] min-h-[16px]",
            hint.kind === "error" && "text-red",
            hint.kind === "success" && "text-green",
            hint.kind === "info" && "text-text-dim",
          )}
        >
          {hint.text}
        </div>
      </div>
    </div>
  );
}
