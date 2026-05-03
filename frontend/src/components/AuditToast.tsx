import { useEffect } from "react";
import { cn } from "@/lib/utils";

export interface AuditAlert {
  id: string;
  tool_name: string;
  device_id?: string;
  success: boolean;
  confirmed?: boolean;
  duration_ms?: number;
  target?: string;
  error?: string;
}

interface AuditToastHostProps {
  alerts: AuditAlert[];
  onDismiss: (id: string) => void;
}

export function AuditToastHost({ alerts, onDismiss }: AuditToastHostProps) {
  return (
    <div className="fixed bottom-5 right-5 z-[90] flex flex-col-reverse gap-2 max-w-[360px]">
      {alerts.map((a) => (
        <AuditToast key={a.id} alert={a} onDismiss={() => onDismiss(a.id)} />
      ))}
    </div>
  );
}

function AuditToast({ alert, onDismiss }: { alert: AuditAlert; onDismiss: () => void }) {
  useEffect(() => {
    const id = window.setTimeout(onDismiss, 8000);
    return () => window.clearTimeout(id);
  }, [onDismiss]);

  const variant = !alert.success ? "fail" : alert.confirmed ? "confirmed" : "default";
  const ok = alert.success ? "OK" : "ERR";
  const conf = alert.confirmed ? "[confirmé]" : "[non-confirmé]";
  const meta =
    `${ok} · ${conf}` +
    (alert.duration_ms ? ` · ${alert.duration_ms}ms` : "") +
    (alert.target ? ` · → ${alert.target}` : "");

  return (
    <div
      onClick={onDismiss}
      title="Click pour fermer"
      className={cn(
        "bg-bg-3 backdrop-blur-[14px] border border-border-hi rounded-sm",
        "px-3 py-2.5 font-mono text-[11px] text-text cursor-pointer",
        "shadow-[0_4px_16px_rgba(0,0,0,0.4)] msg-in",
        "border-l-[3px]",
        variant === "fail" && "border-l-red",
        variant === "confirmed" && "border-l-green",
        variant === "default" && "border-l-cyan",
      )}
    >
      <div
        className={cn(
          "font-orbitron text-[10px] tracking-[1.5px] uppercase mb-0.5",
          variant === "fail" && "text-red",
          variant === "confirmed" && "text-green",
          variant === "default" && "text-cyan",
        )}
      >
        {alert.tool_name}
      </div>
      <div>
        device: <b>{alert.device_id || "?"}</b>
      </div>
      <div className="text-text-dim text-[9px] mt-1">{meta}</div>
      {alert.error && (
        <div className="text-red text-[9px] mt-1">{alert.error}</div>
      )}
    </div>
  );
}
