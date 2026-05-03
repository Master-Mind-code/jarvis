import { useCallback, useState } from "react";

// ─── Types ───
export interface MarketTick {
  bid?: number;
  ask?: number;
  spread?: number | string;
  account?: { balance?: number; equity?: number; margin_free?: number };
}

export interface OpenPosition {
  ticket: number;
  type: "BUY" | "SELL";
  volume: number;
  open_price?: number;
  sl?: number;
  tp?: number;
  profit?: number;
}

export interface HistoryTrade {
  id?: number;
  ticket?: number;
  type: "BUY" | "SELL";
  open_price?: number;
  close_price?: number;
  sl?: number;
  tp?: number;
  profit?: number;
}

export interface TradingStats {
  total_trades?: number;
  winrate?: number;
  net_pnl?: number;
  avg_rr?: number;
  total_profit?: number;
  total_loss?: number;
  best_trade?: number;
  worst_trade?: number;
}

export type SignalDecision = "BUY" | "SELL" | "WAIT";

export interface SignalData {
  decision?: SignalDecision;
  confidence?: number;
  entry?: number;
  sl?: number;
  tp1?: number;
  rr?: number;
  analysis?: { reasoning?: string; confluences?: string[] };
  wait_reason?: string;
  analyzed_at?: string;
  timeframe_entry?: string;
  strategy?: string;
}

export interface SystemState {
  active?: boolean;
}

export type LogLevel = "info" | "success" | "warning" | "error";

export interface LogEntry {
  id: string;
  time: string;
  msg: string;
  level: LogLevel;
}

// ─── Hook ───
let _logId = 0;
const MAX_LOG = 100;

export function useTradingState() {
  const [market, setMarket] = useState<MarketTick>({});
  const [stats, setStats] = useState<TradingStats>({});
  const [open, setOpen] = useState<OpenPosition[]>([]);
  const [history, setHistory] = useState<HistoryTrade[]>([]);
  const [signal, setSignal] = useState<SignalData>({});
  const [system, setSystem] = useState<SystemState>({});
  const [log, setLog] = useState<LogEntry[]>([]);

  const addLog = useCallback((msg: string, level: LogLevel = "info") => {
    const time = new Date().toTimeString().slice(0, 8);
    const entry: LogEntry = { id: `l${Date.now().toString(36)}-${++_logId}`, time, msg, level };
    setLog((l) => [entry, ...l].slice(0, MAX_LOG));
  }, []);

  const clearLog = useCallback(() => setLog([]), []);

  /** Applique un payload `init` qui contient un peu tout. */
  const applyInit = useCallback((data: any) => {
    if (data?.stats)       setStats(data.stats);
    if (data?.open_trades) setOpen(data.open_trades);
    if (data?.history)     setHistory(data.history);
    if (data?.state)       setSystem(data.state);
  }, []);

  const applyMarketUpdate = useCallback((data: any) => {
    setMarket((m) => ({ ...m, ...data }));
    if (Array.isArray(data?.open_positions)) setOpen(data.open_positions);
  }, []);

  return {
    // state
    market, stats, open, history, signal, system, log,
    // setters granulaires (utilisés par le hook WS)
    setStats, setOpen, setHistory, setSignal, setSystem,
    // actions
    addLog, clearLog, applyInit, applyMarketUpdate,
  };
}
