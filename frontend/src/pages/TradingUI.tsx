import { useCallback, useEffect, useMemo, useState } from "react";
import { TradingHeader, type TradingStatus } from "@/components/trading/TradingHeader";
import { ControlBar, type TradingParams } from "@/components/trading/ControlBar";
import { StatsGrid } from "@/components/trading/StatsGrid";
import { OpenTrades } from "@/components/trading/OpenTrades";
import { SignalPanel } from "@/components/trading/SignalPanel";
import { TradeHistory } from "@/components/trading/TradeHistory";
import { SystemLog } from "@/components/trading/SystemLog";
import { ToastHost, useToasts } from "@/components/Toast";
import { useTradingState } from "@/hooks/useTradingState";
import { useWebSocket } from "@/hooks/useWebSocket";
import { storage } from "@/lib/utils";

const TOKEN_KEY = "orion_trading_token";

export function TradingUI() {
  const [token, setTokenRaw] = useState(() => {
    // Token via ?token=... a priorité (puis nettoyage de l'URL)
    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search);
      const fromUrl = params.get("token");
      if (fromUrl) {
        storage.set(TOKEN_KEY, fromUrl);
        history.replaceState({}, "", window.location.pathname);
        return fromUrl;
      }
    }
    return storage.get(TOKEN_KEY);
  });
  const setToken = useCallback((t: string) => {
    setTokenRaw(t);
    storage.set(TOKEN_KEY, t);
  }, []);

  const [params, setParams] = useState<TradingParams>({
    risk_percent: 1,
    min_confidence: 72,
    max_trades: 3,
  });

  const [enabled, setEnabled] = useState(!!token);
  const state = useTradingState();
  const { toasts, push: toast, dismiss } = useToasts();

  // ─── WebSocket trading ───
  const wsUrl = useMemo(() => {
    if (!enabled || !token) return "";
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${proto}//${window.location.host}/api/trading/ws?token=${encodeURIComponent(token)}`;
  }, [enabled, token]);

  const onWSMessage = useCallback((msg: any) => {
    switch (msg.type) {
      case "init":
        state.applyInit(msg.data);
        return;
      case "market_update":
        state.applyMarketUpdate(msg.data);
        return;
      case "analysis":
        state.setSignal(msg.data || {});
        state.addLog(
          `Signal IA : ${msg.data?.decision ?? "WAIT"} (${msg.data?.confidence ?? 0}%) ` +
          `· TF : ${msg.data?.timeframe_entry ?? "—"} · ${msg.data?.strategy ?? "—"}`,
          msg.data?.decision !== "WAIT" ? "success" : "info",
        );
        return;
      case "trade_signal":
        state.addLog(
          `Signal ${msg.data?.action} · Entry:${msg.data?.entry} SL:${msg.data?.sl} TP:${msg.data?.tp}`,
          "warning",
        );
        toast(`SIGNAL ${msg.data?.action}`, msg.data?.action !== "BUY");
        return;
      case "trade_executed":
        state.addLog(`Trade exécuté #${msg.data?.ticket} · ${msg.data?.action}`, "success");
        toast("TRADE OUVERT");
        void refreshStats();
        return;
      case "system_status":
        state.setSystem(msg.data || {});
        return;
      case "close_all_requested":
        state.addLog("Clôture de toutes les positions demandée", "warning");
        return;
      default:
        return;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state, toast]);

  const ws = useWebSocket({
    url: wsUrl,
    onMessage: onWSMessage,
    enabled,
    pingIntervalMs: 5000,
  });

  // ─── Status pill ───
  const status: TradingStatus =
    ws.status === "open" ? (state.system.active ? "active" : "idle")
    : ws.status === "connecting" ? "connecting"
    : ws.status === "error" ? "error"
    : "idle";

  const statusLabel =
    ws.status === "open" ? (state.system.active ? "ACTIF" : "EN LIGNE")
    : ws.status === "connecting" ? "CONNEXION…"
    : ws.status === "error" ? "ERREUR"
    : "HORS LIGNE";

  // Body class pour grille trading
  useEffect(() => {
    document.body.classList.add("trading-mode");
    return () => document.body.classList.remove("trading-mode");
  }, []);

  // ─── Connexions WS sur changement d'état ───
  useEffect(() => {
    if (ws.status === "open") {
      state.addLog("Connecté au serveur Orion", "success");
      toast("Connecté");
    } else if (ws.status === "closed") {
      state.addLog("Connexion perdue, reconnexion automatique…", "error");
    } else if (ws.status === "error") {
      state.addLog("Erreur de connexion", "error");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ws.status]);

  // ─── Actions REST ───
  const apiFetch = useCallback(async (path: string, init?: RequestInit) => {
    return fetch(path, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        "X-Orion-Token": token,
        ...(init?.headers ?? {}),
      },
    });
  }, [token]);

  const onConnect = useCallback(() => {
    if (!token.trim()) {
      toast("Token requis", true);
      return;
    }
    if (enabled) {
      // Force une reconnexion en désactivant puis réactivant
      setEnabled(false);
      setTimeout(() => setEnabled(true), 100);
    } else {
      setEnabled(true);
    }
  }, [token, enabled, toast]);

  const onStart = useCallback(async () => {
    try {
      const r = await apiFetch("/api/trading/start", {
        method: "POST",
        body: JSON.stringify(params),
      });
      if (r.ok) {
        toast("Trading démarré");
        state.addLog("Système de trading démarré", "success");
      } else {
        toast("Erreur démarrage : HTTP " + r.status, true);
      }
    } catch (e) {
      toast("Erreur : " + (e as Error).message, true);
    }
  }, [apiFetch, params, toast, state]);

  const onStop = useCallback(async () => {
    try {
      const r = await apiFetch("/api/trading/stop", { method: "POST" });
      if (r.ok) {
        toast("Trading arrêté");
        state.addLog("Système de trading arrêté", "warning");
      }
    } catch (e) {
      toast("Erreur : " + (e as Error).message, true);
    }
  }, [apiFetch, toast, state]);

  const onCloseAll = useCallback(async () => {
    if (!window.confirm("Clôturer toutes les positions ouvertes ?")) return;
    try {
      const r = await apiFetch("/api/trading/close-all", { method: "POST" });
      if (r.ok) {
        toast("Clôture envoyée");
        state.addLog("Clôture de toutes les positions demandée", "warning");
      }
    } catch (e) {
      toast("Erreur : " + (e as Error).message, true);
    }
  }, [apiFetch, toast, state]);

  const refreshStats = useCallback(async () => {
    if (ws.status !== "open") return;
    try {
      const r = await apiFetch("/api/trading/stats");
      if (r.ok) {
        const data = await r.json();
        if (data.stats)       state.setStats(data.stats);
        if (data.open_trades) state.setOpen(data.open_trades);
        if (data.history)     state.setHistory(data.history);
      }
    } catch {
      /* silencieux */
    }
  }, [apiFetch, ws.status, state]);

  // Refresh stats périodique
  useEffect(() => {
    if (ws.status !== "open") return;
    const id = window.setInterval(refreshStats, 30000);
    return () => window.clearInterval(id);
  }, [ws.status, refreshStats]);

  // Auto-connexion si token présent au montage
  useEffect(() => {
    if (token && !enabled) {
      setEnabled(true);
      state.addLog("Token chargé · auto-connexion", "info");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Init logs
  useEffect(() => {
    state.addLog("Dashboard Orion Trader initialisé", "info");
    if (!token) state.addLog("Renseigne le token et clique CONNECTER", "info");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="min-h-screen bg-trading-bg text-trading-text font-rajdhani overflow-x-hidden">
      <TradingHeader
        market={state.market}
        status={status}
        statusLabel={statusLabel}
      />

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3 p-4 max-w-[1400px] mx-auto">
        <ControlBar
          connected={ws.status === "open"}
          systemActive={!!state.system.active}
          params={params}
          setParams={setParams}
          token={token}
          setToken={setToken}
          onConnect={onConnect}
          onStart={onStart}
          onStop={onStop}
          onCloseAll={onCloseAll}
        />

        <StatsGrid stats={state.stats} />

        <OpenTrades positions={state.open} />
        <SignalPanel signal={state.signal} />

        <TradeHistory history={state.history} />

        <SystemLog entries={state.log} onClear={state.clearLog} />
      </div>

      <ToastHost toasts={toasts} onDismiss={dismiss} />
    </div>
  );
}
