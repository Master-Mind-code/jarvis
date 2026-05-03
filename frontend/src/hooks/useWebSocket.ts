import { useEffect, useRef, useState, useCallback } from "react";

export type WSMessage = Record<string, any>;
export type WSStatus = "idle" | "connecting" | "open" | "closed" | "error";

interface UseWebSocketOpts {
  url: string;             // ws://host:port/ws/<device>?token=...
  onMessage: (msg: WSMessage) => void;
  enabled?: boolean;       // ne se connecte que si true
  pingIntervalMs?: number; // 0 = désactivé
}

/**
 * Hook WebSocket avec reconnexion auto exponentielle.
 * Le caller fournit l'URL complète (déjà avec token), c'est lui qui décide quand activer.
 */
export function useWebSocket({ url, onMessage, enabled = true, pingIntervalMs = 0 }: UseWebSocketOpts) {
  const [status, setStatus] = useState<WSStatus>("idle");
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);
  const onMessageRef = useRef(onMessage);
  const attemptRef = useRef(0);

  useEffect(() => { onMessageRef.current = onMessage; }, [onMessage]);

  const send = useCallback((data: WSMessage) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return false;
    try {
      ws.send(JSON.stringify(data));
      return true;
    } catch {
      return false;
    }
  }, []);

  const close = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      window.clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setStatus("closed");
  }, []);

  useEffect(() => {
    if (!enabled || !url) {
      close();
      return;
    }

    let cancelled = false;
    const connect = () => {
      if (cancelled) return;
      setStatus("connecting");
      try {
        const ws = new WebSocket(url);
        wsRef.current = ws;

        ws.onopen = () => {
          if (cancelled) return;
          attemptRef.current = 0;
          setStatus("open");
        };
        ws.onmessage = (evt) => {
          if (cancelled) return;
          try {
            const data = JSON.parse(evt.data);
            onMessageRef.current(data);
          } catch {
            /* ignore */
          }
        };
        ws.onerror = () => {
          if (cancelled) return;
          setStatus("error");
        };
        ws.onclose = () => {
          if (cancelled) return;
          setStatus("closed");
          // Reconnexion exponentielle (cap 30s)
          attemptRef.current++;
          const delay = Math.min(30000, 1000 * 2 ** Math.min(attemptRef.current, 5));
          reconnectTimeoutRef.current = window.setTimeout(connect, delay);
        };
      } catch (err) {
        setStatus("error");
        attemptRef.current++;
        const delay = Math.min(30000, 1000 * 2 ** Math.min(attemptRef.current, 5));
        reconnectTimeoutRef.current = window.setTimeout(connect, delay);
      }
    };
    connect();

    return () => {
      cancelled = true;
      close();
    };
  }, [url, enabled, close]);

  // Ping périodique
  useEffect(() => {
    if (!pingIntervalMs || status !== "open") return;
    const id = window.setInterval(() => send({ type: "ping" }), pingIntervalMs);
    return () => window.clearInterval(id);
  }, [pingIntervalMs, status, send]);

  return { status, send, close };
}
