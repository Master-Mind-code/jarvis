import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";

export type ToastEntry = { id: string; text: string; isError?: boolean; ttl?: number };

interface ToastHostProps {
  toasts: ToastEntry[];
  onDismiss: (id: string) => void;
}

export function ToastHost({ toasts, onDismiss }: ToastHostProps) {
  return (
    <div className="fixed top-20 left-1/2 -translate-x-1/2 z-50 flex flex-col gap-2 max-w-[80vw]">
      {toasts.map(t => (
        <Toast key={t.id} entry={t} onDismiss={() => onDismiss(t.id)} />
      ))}
    </div>
  );
}

function Toast({ entry, onDismiss }: { entry: ToastEntry; onDismiss: () => void }) {
  useEffect(() => {
    const id = window.setTimeout(onDismiss, entry.ttl ?? 4000);
    return () => window.clearTimeout(id);
  }, [entry.ttl, onDismiss]);

  return (
    <div
      onClick={onDismiss}
      className={cn(
        "bg-bg-3 backdrop-blur-panel border rounded-sm px-4 py-2.5",
        "font-mono text-[11px] cursor-pointer transition-all",
        "shadow-[0_4px_16px_rgba(0,0,0,0.4)]",
        entry.isError
          ? "border-red/40 text-red"
          : "border-border-hi text-text"
      )}
    >
      {entry.text}
    </div>
  );
}

/** Hook pratique pour gérer la file de toasts. */
export function useToasts() {
  const [toasts, setToasts] = useState<ToastEntry[]>([]);
  const push = (text: string, isError = false, ttl = 4000) => {
    setToasts(prev => [...prev, { id: Math.random().toString(36).slice(2, 9), text, isError, ttl }]);
  };
  const dismiss = (id: string) => setToasts(prev => prev.filter(t => t.id !== id));
  return { toasts, push, dismiss };
}
