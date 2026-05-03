import { cn } from "@/lib/utils";
import type { ToolChip } from "./ChatMessage";

interface ChatThinkingProps {
  tools: ToolChip[];
}

/** Bulle "Traitement en cours…" affichée tant que la réponse n'a pas commencé. */
export function ChatThinking({ tools }: ChatThinkingProps) {
  return (
    <div className="msg-in flex gap-3.5">
      <div className="w-[30px] h-[30px] rounded-sm shrink-0 mt-1
                      bg-cyan-dim border border-cyan/20
                      bg-[url('/assets/orion-mark.svg')] bg-no-repeat bg-center"
           style={{ backgroundSize: "22px 22px" }} />
      <div className="flex flex-col gap-1.5 max-w-[72%]">
        <div className="font-orbitron text-[8px] tracking-[2.5px] uppercase text-cyan/45">
          ORION
        </div>
        <div className="px-4 py-3 bg-[rgba(5,12,28,0.7)] border border-border
                        border-l-[1.5px] border-l-cyan backdrop-blur-panel
                        font-orbitron text-[9px] tracking-[2.5px] text-cyan/55 uppercase
                        flex items-center gap-2.5">
          Traitement en cours
          <span className="inline-flex gap-0.5">
            <Dot />
            <Dot />
            <Dot />
          </span>
          {tools.length > 0 && (
            <div className="flex flex-wrap gap-1.5 normal-case ml-2">
              {tools.map((t, i) => (
                <span
                  key={i}
                  className={cn(
                    "inline-flex items-center gap-1 px-2 py-0.5 rounded-sm",
                    "font-mono text-[9px] tracking-wide uppercase",
                    t.success
                      ? "bg-green/[0.05] border border-green/25 text-green"
                      : "bg-red/[0.05] border border-red/25 text-red",
                  )}
                >
                  <span className={cn("w-1 h-1 rounded-full", t.success ? "bg-green" : "bg-red")} />
                  {t.name}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Dot() {
  return (
    <span className="bounce-dot inline-block w-[3px] h-[3px] mx-0.5 rounded-full bg-cyan" />
  );
}
