import { useCallback, useRef, useState } from "react";
import type { ChatMessageData, ToolChip } from "@/components/ChatMessage";

let _id = 0;
const nextId = () => `m${Date.now().toString(36)}-${++_id}`;

export type ChatPhase = "idle" | "thinking" | "streaming";

export function useChat() {
  const [messages, setMessages] = useState<ChatMessageData[]>([]);
  const [phase, setPhase] = useState<ChatPhase>("idle");
  const [pendingTools, setPendingTools] = useState<ToolChip[]>([]);
  const streamingIdRef = useRef<string | null>(null);

  /** Ajoute un message utilisateur dans le fil. */
  const addUser = useCallback((text: string) => {
    setMessages((m) => [...m, { id: nextId(), role: "user", text }]);
  }, []);

  /** Ajoute un message Orion final (cas non-streaming). */
  const addOrion = useCallback((text: string) => {
    setMessages((m) => [...m, { id: nextId(), role: "orion", text }]);
  }, []);

  /** Ajoute une note système (séparateur centré). */
  const addSystem = useCallback((text: string, isError = false) => {
    setMessages((m) => [...m, { id: nextId(), role: "system", text, isError }]);
  }, []);

  /** Démarre une demande : passe en "thinking" et nettoie les chips précédents. */
  const startThinking = useCallback(() => {
    setPhase("thinking");
    setPendingTools([]);
  }, []);

  /** Le serveur signale qu'un tool a été appelé. */
  const addToolChip = useCallback((name: string, success: boolean) => {
    setPendingTools((t) => [...t, { name, success }]);
  }, []);

  /** Premier chunk de streaming : on crée un message Orion vide et on le remplira. */
  const handleChunk = useCallback((text: string) => {
    if (!text) return;
    if (!streamingIdRef.current) {
      const id = nextId();
      streamingIdRef.current = id;
      setPhase("streaming");
      setMessages((m) => [...m, { id, role: "orion", text }]);
    } else {
      const id = streamingIdRef.current;
      setMessages((m) => m.map((msg) => (msg.id === id ? { ...msg, text: msg.text + text } : msg)));
    }
  }, []);

  /** Réponse finale : si on a streamé, on remplace le contenu, sinon on ajoute. */
  const handleFinal = useCallback(
    (fullContent: string) => {
      const tools = pendingTools;
      if (streamingIdRef.current) {
        const id = streamingIdRef.current;
        setMessages((m) =>
          m.map((msg) =>
            msg.id === id ? { ...msg, text: fullContent || msg.text, tools } : msg,
          ),
        );
        streamingIdRef.current = null;
      } else if (fullContent) {
        setMessages((m) => [...m, { id: nextId(), role: "orion", text: fullContent, tools }]);
      }
      setPhase("idle");
      setPendingTools([]);
    },
    [pendingTools],
  );

  const reset = useCallback(() => {
    setMessages([]);
    setPhase("idle");
    setPendingTools([]);
    streamingIdRef.current = null;
  }, []);

  return {
    messages,
    phase,
    pendingTools,
    addUser,
    addOrion,
    addSystem,
    startThinking,
    addToolChip,
    handleChunk,
    handleFinal,
    reset,
  };
}
