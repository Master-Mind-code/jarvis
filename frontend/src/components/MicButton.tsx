import { Mic } from "lucide-react";
import { cn } from "@/lib/utils";

interface MicButtonProps {
  isListening: boolean;
  onClick: () => void;
  hint?: string;
}

export function MicButton({ isListening, onClick, hint }: MicButtonProps) {
  return (
    <div className="fixed bottom-20 left-1/2 -translate-x-1/2 z-20 flex flex-col items-center gap-3.5">
      <button
        onClick={onClick}
        title="Parler à Orion"
        className={cn(
          "w-[84px] h-[84px] rounded-full border-2 cursor-pointer transition-all",
          "flex items-center justify-center relative",
          isListening
            ? "border-red text-red animate-mic-pulse " +
              "bg-[radial-gradient(circle_at_30%_30%,rgba(255,59,92,0.25),#080e1e)] " +
              "shadow-[inset_0_0_28px_rgba(255,59,92,0.2),0_0_50px_rgba(255,59,92,0.4)]"
            : "border-border-hi text-cyan " +
              "bg-[radial-gradient(circle_at_30%_30%,rgba(0,229,255,0.18),#080e1e)] " +
              "shadow-[inset_0_0_22px_rgba(0,229,255,0.12),0_0_30px_rgba(0,229,255,0.18)] " +
              "hover:border-cyan hover:shadow-[inset_0_0_28px_rgba(0,229,255,0.2),0_0_40px_rgba(0,229,255,0.4)]"
        )}
      >
        <Mic size={32} strokeWidth={1.5} />
      </button>
      <div className="font-orbitron text-[9px] tracking-[3px] text-text-dim uppercase text-center">
        {hint ?? "Appuie ou clique pour parler"}
      </div>
    </div>
  );
}
