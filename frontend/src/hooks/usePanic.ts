import { useCallback, useState } from "react";
import { wsToHttp } from "@/lib/utils";

interface UsePanicOpts {
  serverUrl: string;
  token: string;
  onLog: (msg: string, isError?: boolean) => void;
}

export function usePanic({ serverUrl, token, onLog }: UsePanicOpts) {
  const [active, setActive] = useState(false);
  const [reason, setReason] = useState<string | null>(null);

  /** Met à jour l'état localement (appelé sur message panic_state du WS). */
  const onPanicState = useCallback((data: { active: boolean; reason?: string }) => {
    setActive(!!data.active);
    setReason(data.reason ?? null);
    if (data.active) {
      onLog("⚠ MODE PANIC ACTIVÉ" + (data.reason ? " — " + data.reason : ""), true);
      document.title = "⚠ PANIC · ORION";
    } else {
      onLog("Mode panic désactivé.");
      document.title = "ORION";
    }
  }, [onLog]);

  /** Déclenche le mode panic via POST /api/panic. */
  const trigger = useCallback(async () => {
    if (active) {
      // déjà actif → release
      if (!window.confirm("Désactiver le mode panic ?")) return;
      try {
        const url = `${wsToHttp(serverUrl)}/api/panic/release?token=${encodeURIComponent(token)}`;
        const r = await fetch(url, { method: "POST" });
        if (r.ok) onLog("Mode panic désactivé.");
        else onLog("Échec : HTTP " + r.status, true);
      } catch (e) {
        onLog("Échec : " + (e as Error).message, true);
      }
      return;
    }

    if (!window.confirm(
      "⚠ ACTIVER LE MODE PANIC ?\n\n" +
      "Tous les tools sensibles seront refusés, tous les workers seront déconnectés, " +
      "et le scheduler arrêté.\n\nPour rétablir : POST /api/panic/release"
    )) return;

    const why = window.prompt("Raison (optionnel) :", "manuel") || "manuel";
    try {
      const url = `${wsToHttp(serverUrl)}/api/panic?token=${encodeURIComponent(token)}` +
                  `&reason=${encodeURIComponent(why)}&by=browser`;
      const r = await fetch(url, { method: "POST" });
      if (!r.ok) {
        onLog("Échec PANIC : HTTP " + r.status, true);
        return;
      }
      onLog("⚠ MODE PANIC ACTIVÉ", true);
    } catch (e) {
      onLog("Échec PANIC : " + (e as Error).message, true);
    }
  }, [active, serverUrl, token, onLog]);

  return { active, reason, trigger, onPanicState };
}
