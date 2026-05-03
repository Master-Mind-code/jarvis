import { useEffect, useRef, useState } from "react";

export interface ConfirmRequest {
  request_id: string;
  tool: string;
  reason?: string;
  input_preview?: string;
  timeout_sec?: number;
}

interface ConfirmModalProps {
  request: ConfirmRequest | null;
  error?: string | null;        // Affiché si mauvais password rejeté par serveur
  onApprove: (password: string) => void;
  onDeny: () => void;
}

export function ConfirmModal({ request, error, onApprove, onDeny }: ConfirmModalProps) {
  const [pwd, setPwd] = useState("");
  const [remaining, setRemaining] = useState(120);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!request) return;
    setPwd("");
    setRemaining(request.timeout_sec ?? 120);
    setTimeout(() => inputRef.current?.focus(), 50);
  }, [request?.request_id]);

  useEffect(() => {
    if (!request) return;
    const id = window.setInterval(() => {
      setRemaining(r => {
        if (r <= 1) {
          window.clearInterval(id);
          onDeny();
          return 0;
        }
        return r - 1;
      });
    }, 1000);
    return () => window.clearInterval(id);
  }, [request?.request_id, onDeny]);

  useEffect(() => {
    if (!request) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Enter")  { e.preventDefault(); if (pwd) onApprove(pwd); }
      if (e.key === "Escape") { e.preventDefault(); onDeny(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [request?.request_id, pwd, onApprove, onDeny]);

  if (!request) return null;

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center
                    bg-bg/85 backdrop-blur-md animate-in fade-in duration-200">
      <div className="relative bg-bg-2 border border-red/45 rounded-sm
                      max-w-[480px] w-[90%] p-7
                      shadow-[0_0_60px_rgba(255,59,92,0.15),0_20px_40px_rgba(0,0,0,0.6)]">
        <div className="absolute -top-px left-[20%] w-3/5 h-0.5
                        bg-gradient-to-r from-transparent via-red to-transparent
                        shadow-[0_0_14px_#ff3b5c]" />
        <div className="font-orbitron text-xs tracking-[4px] text-red uppercase text-center mb-1.5">
          ⚠ Confirmation requise
        </div>
        <div className="font-mono text-[10px] tracking-[1.5px] text-text-dim uppercase text-center mb-4">
          {request.reason ?? "Action sensible"}
        </div>
        <div className="bg-red/[0.08] border border-red/25 rounded-sm
                        px-3 py-2.5 mb-3.5 font-mono text-[11px] text-text break-all">
          <b className="text-red">{request.tool}</b>
          {request.input_preview && (
            <> · <span>{request.input_preview}</span></>
          )}
        </div>
        <input
          ref={inputRef}
          type="password"
          value={pwd}
          onChange={(e) => setPwd(e.target.value)}
          placeholder="· · · · · ·"
          autoComplete="off"
          className="w-full px-3.5 py-3 bg-black/50 border border-red/40
                     rounded-sm text-text font-mono text-sm tracking-[4px]
                     text-center outline-none mb-3
                     focus:border-red focus:shadow-[0_0_14px_rgba(255,59,92,0.25)]"
        />
        {error && (
          <div className="font-mono text-[11px] text-red text-center mb-3 min-h-[14px]">
            {error}
          </div>
        )}
        <div className="font-orbitron text-[9px] tracking-[2px] text-text-dim text-center mb-4">
          Expire dans {remaining}s — refus auto
        </div>
        <div className="flex gap-2.5">
          <button
            onClick={onDeny}
            className="flex-1 py-2.5 border border-border rounded-sm
                       font-orbitron text-[10px] tracking-[3px] uppercase cursor-pointer
                       text-text-dim hover:text-text hover:border-border-hi transition-all"
          >
            Annuler
          </button>
          <button
            onClick={() => pwd && onApprove(pwd)}
            disabled={!pwd}
            className="flex-1 py-2.5 border border-red/50 bg-red/[0.05] rounded-sm
                       font-orbitron text-[10px] tracking-[3px] uppercase cursor-pointer
                       text-red hover:bg-red/[0.18] transition-all
                       disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Autoriser
          </button>
        </div>
      </div>
    </div>
  );
}
