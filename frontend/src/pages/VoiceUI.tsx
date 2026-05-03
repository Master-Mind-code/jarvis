import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Header } from "@/components/Header";
import { Sphere, type SphereState } from "@/components/Sphere";
import { DecorativeRings } from "@/components/Rings";
import { SystemHud, NetworkHud, FreqHud, ShapeHud } from "@/components/HudReadout";
import { EnergyBars } from "@/components/EnergyBars";
import { MicButton } from "@/components/MicButton";
import { ConfirmModal, type ConfirmRequest } from "@/components/ConfirmModal";
import { ToastHost, useToasts } from "@/components/Toast";
import { SettingsPanel } from "@/components/SettingsPanel";
import { useWebSocket } from "@/hooks/useWebSocket";
import { useMicRecorder } from "@/hooks/useMicRecorder";
import { useTTSStream } from "@/hooks/useTTSStream";
import { storage, wsToHttp } from "@/lib/utils";

const STATE_LABELS: Record<SphereState, string> = {
  idle: "STANDBY",
  listening: "ÉCOUTE",
  processing: "TRAITEMENT",
  speaking: "PARLE",
};

export function VoiceUI() {
  // ─── Config (persistée) ───
  const [serverUrl, setServerUrl] = useState(() => {
    const saved = storage.get("orionVoiceServerUrl");
    if (saved) return saved;
    if (typeof window !== "undefined" && (location.protocol === "http:" || location.protocol === "https:")) {
      return `${location.protocol === "https:" ? "wss:" : "ws:"}//${location.host}`;
    }
    return "ws://localhost:8765";
  });
  const [token, setToken] = useState(() => storage.get("orionVoiceToken"));
  const [deviceId, setDeviceId] = useState(() => storage.get("orionVoiceDevice", "voice-browser"));
  const [settingsOpen, setSettingsOpen] = useState(!token);
  useEffect(() => storage.set("orionVoiceServerUrl", serverUrl), [serverUrl]);
  useEffect(() => storage.set("orionVoiceToken", token), [token]);
  useEffect(() => storage.set("orionVoiceDevice", deviceId), [deviceId]);

  // ─── État UI ───
  const [state, setState] = useState<SphereState>("idle");
  const [orionText, setOrionText] = useState("Appuie sur le micro pour parler.");
  const [userText, setUserText] = useState("");
  const [toolHint, setToolHint] = useState("");
  const [shapeLabel, setShapeLabel] = useState("SPHÈRE");
  const [confirmReq, setConfirmReq] = useState<ConfirmRequest | null>(null);
  const [confirmError, setConfirmError] = useState<string | null>(null);
  const [enabled, setEnabled] = useState(!!token);

  const { toasts, push: toast, dismiss } = useToasts();
  const tts = useTTSStream();

  // Audio level via ref (la sphère lit en boucle, pas de re-render)
  const audioLevelRef = useRef(0);
  const [voicePct, setVoicePct] = useState(0);

  // ─── WebSocket ───
  const wsUrl = useMemo(() => {
    if (!enabled || !token) return "";
    return `${serverUrl}/ws/${encodeURIComponent(deviceId)}?token=${encodeURIComponent(token)}`;
  }, [enabled, serverUrl, deviceId, token]);

  // ─── Streaming TTS phrase-par-phrase ───
  const streamHadFirstChunkRef = useRef(false);
  const handleResponseChunk = useCallback((text: string) => {
    if (!text) return;
    if (!streamHadFirstChunkRef.current) {
      streamHadFirstChunkRef.current = true;
      setState("speaking");
      setToolHint("");
    }
    setOrionText(prev => prev + text);
    tts.appendChunk(text);
  }, [tts]);

  const handleResponseFinal = useCallback((fullContent: string) => {
    if (!streamHadFirstChunkRef.current && fullContent) {
      setState("speaking");
      setOrionText(fullContent);
      tts.appendChunk(fullContent);
    }
    tts.flush(fullContent);
    if (fullContent) setOrionText(fullContent);
    streamHadFirstChunkRef.current = false;
    window.setTimeout(() => setState(s => (s === "speaking" ? "idle" : s)), 500);
  }, [tts]);

  const onWSMessage = useCallback((data: any) => {
    if (data.type === "connected") return;
    if (data.type === "tool_action") {
      const ok = data.result?.success !== false ? "✓" : "✗";
      setToolHint(`${ok} ${data.tool}`);
    } else if (data.type === "response_chunk") {
      handleResponseChunk(data.text || "");
    } else if (data.type === "response") {
      handleResponseFinal(data.content || "");
    } else if (data.type === "error") {
      setState("idle");
      setOrionText("Erreur : " + (data.content || "inconnue"));
      toast(data.content || "erreur", true);
    } else if (data.type === "info") {
      toast(data.message || "");
    } else if (data.type === "confirm_request") {
      setConfirmError(null);
      setConfirmReq(data);
    } else if (data.type === "confirm_result") {
      if (data.accepted) {
        setConfirmReq(null);
        setConfirmError(null);
        toast("Action autorisée.");
      } else {
        setConfirmError(data.error || "Mot de passe incorrect.");
      }
    } else if (data.type === "audit_alert") {
      const ok = data.success ? "✓" : "✗";
      const conf = data.confirmed ? " [conf]" : "";
      toast(`${ok}${conf} ${data.tool_name} · ${data.device_id || "?"}`, !data.success);
    }
  }, [handleResponseChunk, handleResponseFinal, toast]);

  const ws = useWebSocket({ url: wsUrl, onMessage: onWSMessage, enabled });
  const isConnected = ws.status === "open";

  // ─── Micro / transcription ───
  const mic = useMicRecorder({
    onAudioLevel: (lvl) => {
      audioLevelRef.current = lvl;
      setVoicePct(Math.round(lvl * 100));
    },
  });

  // Quand on a un nouveau blob → upload
  useEffect(() => {
    if (!mic.lastBlob) return;
    const blob = mic.lastBlob;
    if (blob.size < 500) {
      toast("Trop court ou silence.", true);
      setState("idle");
      return;
    }
    void uploadAudio(blob);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mic.lastBlob]);

  // Erreurs micro
  useEffect(() => {
    if (mic.lastError) {
      toast(mic.lastError, true);
    }
  }, [mic.lastError, toast]);

  const uploadAudio = useCallback(async (blob: Blob) => {
    setState("processing");
    setOrionText("Transcription…");
    const url = `${wsToHttp(serverUrl)}/api/transcribe?token=${encodeURIComponent(token)}&language=fr`;
    try {
      const resp = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": blob.type || "audio/webm" },
        body: blob,
      });
      if (!resp.ok) {
        toast("HTTP " + resp.status, true);
        setState("idle"); setOrionText("Erreur transcription.");
        return;
      }
      const data = await resp.json();
      if (!data.success || !data.text?.trim()) {
        toast(data.error || "Je n'ai rien compris.", true);
        setState("idle"); setOrionText("Je n'ai rien compris.");
        return;
      }
      const text = data.text.trim();
      setUserText(text);
      // Reset stream + envoie au serveur
      tts.reset();
      streamHadFirstChunkRef.current = false;
      setOrionText("Réflexion…");
      const sent = ws.send({ type: "message", content: text });
      if (sent) setState("processing");
      else { toast("Pas connecté.", true); setState("idle"); }
    } catch (err) {
      toast("Échec : " + (err as Error).message, true);
      setState("idle"); setOrionText("Erreur réseau.");
    }
  }, [serverUrl, token, tts, ws, toast]);

  const toggleMic = useCallback(() => {
    if (!isConnected) {
      toast("Pas connecté au serveur.", true);
      return;
    }
    if (mic.isRecording) mic.stop();
    else {
      window.speechSynthesis?.cancel();
      setUserText("");
      setToolHint("");
      setOrionText("Je t'écoute.");
      setState("listening");
      void mic.start();
    }
  }, [isConnected, mic, toast]);

  // Confirm modal handlers
  const onApprove = useCallback((pwd: string) => {
    if (!confirmReq) return;
    ws.send({ type: "confirm_response", request_id: confirmReq.request_id, password: pwd });
  }, [confirmReq, ws]);
  const onDeny = useCallback(() => {
    if (!confirmReq) return;
    ws.send({ type: "confirm_response", request_id: confirmReq.request_id, refused: true });
    setConfirmReq(null);
    setConfirmError(null);
  }, [confirmReq, ws]);

  // Raccourcis : Espace = parler / Échap = stop
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (target?.tagName === "INPUT") return;
      if (e.code === "Space") { e.preventDefault(); toggleMic(); }
      if (e.code === "Escape" && mic.isRecording) { e.preventDefault(); mic.stop(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [toggleMic, mic]);

  // Hint micro
  const micHint = state === "listening"
    ? "J'écoute…"
    : state === "processing"
    ? "Réflexion…"
    : state === "speaking"
    ? "Je réponds…"
    : "Espace pour parler · Échap pour stop";

  // Couleur état
  const stateColor =
    state === "listening"  ? "text-red"
    : state === "processing" ? "text-gold"
    : state === "speaking"  ? "text-green"
    :                          "text-cyan";

  return (
    <div className="h-screen flex flex-col">
      <Header
        connected={isConnected}
        onOpenSettings={() => setSettingsOpen(s => !s)}
      />

      <SystemHud  position="top-left" />
      <NetworkHud position="top-right" />
      <FreqHud    position="bot-left" rotation={0} />
      <ShapeHud   position="bot-right" label={shapeLabel} />

      <main className="relative z-[5] flex-1 flex flex-col items-center justify-center px-5">
        <DecorativeRings />

        <Sphere
          state={state}
          audioLevelRef={audioLevelRef}
          onShapeChange={(name) => {
            // Mappe shape name → label déjà capitalisé
            const labels: Record<string, string> = {
              sphere: "SPHÈRE", star: "ÉTOILE", cube: "CUBE",
              arcreactor: "ARC REACTOR", atom: "ATOME", hub: "HUB NEURONAL",
              tore: "TORE", face: "VISAGE IA", letterO: "LETTRE O", orion: "ORION",
            };
            setShapeLabel(labels[name] ?? name.toUpperCase());
          }}
        />

        <div className="relative z-[4] flex flex-col items-center gap-1.5 -mt-10">
          <div className="font-orbitron text-[9px] tracking-[4px] text-text-dim uppercase">
            Réseau neuronal IA
          </div>
          <div className={`font-orbitron text-sm tracking-[6px] uppercase h-5
                          transition-colors ${stateColor}`}>
            {STATE_LABELS[state]}
          </div>
        </div>

        <div className="relative z-[4] mt-6 w-full max-w-[720px] min-h-[100px]
                        flex flex-col gap-2.5 text-center">
          {userText && (
            <div className="font-space text-sm leading-snug py-2 text-text-dim italic">
              <span className="text-cyan">« </span>{userText}<span className="text-cyan"> »</span>
            </div>
          )}
          <div className="font-space text-base font-medium text-text leading-snug py-2">
            {orionText}
          </div>
          {toolHint && (
            <div className="font-mono text-[10px] tracking-[1.5px] text-gold uppercase">
              {toolHint}
            </div>
          )}
        </div>
      </main>

      <MicButton
        isListening={mic.isRecording}
        onClick={toggleMic}
        hint={micHint}
      />

      <EnergyBars voiceLevel={voicePct / 100} />

      <ToastHost toasts={toasts} onDismiss={dismiss} />

      <ConfirmModal
        request={confirmReq}
        error={confirmError}
        onApprove={onApprove}
        onDeny={onDeny}
      />

      <SettingsPanel
        open={settingsOpen}
        serverUrl={serverUrl} setServerUrl={setServerUrl}
        token={token} setToken={setToken}
        deviceId={deviceId} setDeviceId={setDeviceId}
        onConnect={() => { setEnabled(true); setSettingsOpen(false); }}
        onDisconnect={() => { setEnabled(false); ws.close(); }}
      />
    </div>
  );
}
