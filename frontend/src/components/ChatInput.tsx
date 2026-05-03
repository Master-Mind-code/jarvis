import { useState } from "react";
import { Mic, Send } from "lucide-react";
import { cn } from "@/lib/utils";

interface ChatInputProps {
  onSend: (text: string) => void;
  onMicToggle: () => void;
  isListening: boolean;
  disabled?: boolean;
}

export function ChatInput({ onSend, onMicToggle, isListening, disabled }: ChatInputProps) {
  const [text, setText] = useState("");

  const submit = () => {
    const trimmed = text.trim();
    if (!trimmed) return;
    onSend(trimmed);
    setText("");
  };

  return (
    <div className="flex items-center gap-2.5 px-6 py-3.5 border-t border-border
                    bg-[linear-gradient(0deg,rgba(4,6,13,0.98)_0%,rgba(4,6,13,0.7)_100%)]
                    backdrop-blur-panel">
      <button
        onClick={onMicToggle}
        disabled={disabled}
        title={isListening ? "Stop" : "Parler"}
        className={cn(
          "w-[42px] h-[42px] rounded-sm flex items-center justify-center shrink-0",
          "border transition-all backdrop-blur-panel cursor-pointer",
          "active:scale-95 disabled:opacity-40 disabled:cursor-not-allowed",
          isListening
            ? "border-red/50 text-red bg-red/[0.08] animate-mic-pulse"
            : "border-border bg-bg-3 text-text-dim hover:border-border-hi hover:text-cyan hover:bg-cyan-dim",
        )}
      >
        <Mic size={17} />
      </button>

      <div className="flex-1 relative">
        <input
          type="text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          placeholder="Parle à Orion…"
          autoComplete="off"
          className="w-full px-4 py-3 bg-[rgba(5,12,28,0.8)] border border-border rounded-sm
                     text-text font-space text-sm tracking-[0.2px] outline-none
                     placeholder:text-text-dim/60 caret-cyan
                     focus:border-cyan/40 focus:shadow-[0_0_0_2px_rgba(0,229,255,0.06),inset_0_0_20px_rgba(0,229,255,0.02)]
                     transition-all backdrop-blur-panel"
        />
      </div>

      <button
        onClick={submit}
        disabled={disabled || !text.trim()}
        title="Envoyer"
        className={cn(
          "w-[42px] h-[42px] rounded-sm flex items-center justify-center shrink-0",
          "border border-cyan/30 bg-cyan-dim text-cyan transition-all cursor-pointer",
          "active:scale-95 hover:bg-cyan/[0.14] hover:shadow-[0_0_16px_rgba(0,229,255,0.15)]",
          "disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:shadow-none",
        )}
      >
        <Send size={17} />
      </button>
    </div>
  );
}
