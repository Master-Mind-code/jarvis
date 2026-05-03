import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Header, type VoiceServiceState } from "@/components/Header";
import { Sphere, type SphereState } from "@/components/Sphere";
import { ConfirmModal, type ConfirmRequest } from "@/components/ConfirmModal";
import { ToastHost, useToasts } from "@/components/Toast";
import { SettingsPanel } from "@/components/SettingsPanel";
import { PasswordGate } from "@/components/PasswordGate";
import { ChatMessage } from "@/components/ChatMessage";
import { ChatThinking } from "@/components/ChatThinking";
import { ChatInput } from "@/components/ChatInput";
import { AuditToastHost, type AuditAlert } from "@/components/AuditToast";
import { useWebSocket } from "@/hooks/useWebSocket";
import { useMicRecorder } from "@/hooks/useMicRecorder";
import { useTTSStream } from "@/hooks/useTTSStream";
import { useChat } from "@/hooks/useChat";
import { usePanic } from "@/hooks/usePanic";
import { storage, wsToHttp } from "@/lib/utils";

const STATE_TEXT: Record<SphereState, string> = {
  idle: "STANDBY",
  listening: "ÉCOUTE",
  processing: "TRAITEMENT",
  speaking: "PARLE",
};

const STATE_COLOR: Record<SphereState, string> = {
  idle: "text-cyan",
  listening: "text-red",
  processing: "text-gold",
  speaking: "text-green",
};

let auditId = 0;

export function OrionUI() {
  // ─── Config persistée ───
  const [serverUrl, setServerUrl] = useState(() => {
    const saved = storage.get("orionServerUrl");
    if (saved) return saved;
    if (typeof window !== "undefined" && (location.protocol === "http:" || location.protocol === "https:")) {
      return `${location.protocol === "https:" ? "wss:" : "ws:"}//${location.host}`;
    }
    return "ws://localhost:8765";
  });
  const [token, setToken] = useState(() => storage.get("orionToken"));
  const [deviceId, setDeviceId] = useState(() => storage.get("orionDevice", "browser"));
  const [settingsOpen, setSettingsOpen] = useState(!token);
  const [enabled, setEnabled] = useState(!!token);
  const [gateOpen, setGateOpen] = useState(true);

  useEffect(() => storage.set("orionServerUrl", serverUrl), [serverUrl]);
  useEffect(() => storage.set("orionToken", token), [token]);
  useEffect(() => storage.set("orionDevice", deviceId), [deviceId]);

  // ─── Sphere / état UI ───
  const [state, setState] = useState<SphereState>("idle");
  const [shapeLabel, setShapeLabel] = useState("SPHÈRE");
  const audioLevelRef = useRef(0);
  const [voicePct, setVoicePct] = useState(0);
  const [voiceServiceState, setVoiceServiceState] = useState<VoiceServiceState>("offline");
  const [voiceServiceDevice, setVoiceServiceDevice] = useState<string | undefined>();

  // ─── Chat / TTS / Toasts ───
  const chat = useChat();
  const tts = useTTSStream();
  const { toasts, push: toast, dismiss } = useToasts();
  const [auditAlerts, setAuditAlerts] = useState<AuditAlert[]>([]);
  const dismissAlert = (id: string) => setAuditAlerts((a) => a.filter((x) => x.id !== id));

  // ─── Confirm ───
  const [confirmReq, setConfirmReq] = useState<ConfirmRequest | null>(null);
  const [confirmError, setConfirmError] = useState<string | null>(null);

  // ─── Panic ───
  const panic = usePanic({
    serverUrl,
    token,
    onLog: (msg, isError) => chat.addSystem(msg, isError),
  });

  // ─── WebSocket ───
  const wsUrl = useMemo(() => {
    if (!enabled || !token) return "";
    return `${serverUrl}/ws/${encodeURIComponent(deviceId)}?token=${encodeURIComponent(token)}`;
  }, [enabled, serverUrl, deviceId, token]);

  // ─── Streaming TTS ───
  const handleStreamChunk = useCallback((text: string) => {
    if (!text) return;
    chat.handleChunk(text);
    if (state !== "speaking") setState("speaking");
    tts.appendChunk(text);
  }, [chat, tts, state]);

  const handleStreamFinal = useCallback((fullContent: string) => {
    chat.handleFinal(fullContent);
    tts.flush(fullContent);
    setTimeout(() => setState((s) => (s === "speaking" ? "idle" : s)), 400);
  }, [chat, tts]);

  // ─── WS message handler ───
  const onWSMessage = useCallback((data: any) => {
    switch (data.type) {
      case "connected":
        chat.addSystem(data.message || "Connexion établie. Orion est prêt.");
        return;
      case "tool_action":
        chat.addToolChip(data.tool, data.result?.success !== false);
        return;
      case "response_chunk":
        handleStreamChunk(data.text || "");
        return;
      case "response":
        handleStreamFinal(data.content || "");
        return;
      case "error":
        setState("idle");
        chat.handleFinal("");
        chat.addSystem("Erreur : " + (data.content || "inconnue"), true);
        return;
      case "info":
        if (data.message) chat.addSystem(data.message);
        return;
      case "confirm_request":
        setConfirmError(null);
        setConfirmReq(data);
        return;
      case "confirm_result":
        if (data.accepted) {
          setConfirmReq(null);
          setConfirmError(null);
          toast("Action autorisée.");
        } else {
          setConfirmError(data.error || "Mot de passe incorrect.");
        }
        return;
      case "audit_alert":
        setAuditAlerts((prev) => [
          ...prev,
          {
            id: `a${Date.now().toString(36)}-${++auditId}`,
            tool_name: data.tool_name || "unknown",
            device_id: data.device_id,
            success: !!data.success,
            confirmed: !!data.confirmed,
            duration_ms: data.duration_ms,
            target: data.target,
            error: data.error,
          },
        ]);
        return;
      case "panic_state":
        panic.onPanicState(data);
        return;
      case "voice_state":
        setVoiceServiceState((data.state || "idle") as VoiceServiceState);
        setVoiceServiceDevice(data.device_id);
        return;
      case "unlock":
        setGateOpen(false);
        toast("Déverrouillé par la voix.");
        return;
      default:
        return;
    }
  }, [chat, handleStreamChunk, handleStreamFinal, panic, toast]);

  const ws = useWebSocket({ url: wsUrl, onMessage: onWSMessage, enabled });
  const isConnected = ws.status === "open";

  // ─── Mic ───
  const mic = useMicRecorder({
    onAudioLevel: (lvl) => {
      audioLevelRef.current = lvl;
      setVoicePct(Math.round(lvl * 100));
    },
  });

  useEffect(() => {
    if (mic.lastError) toast(mic.lastError, true);
  }, [mic.lastError, toast]);

  const uploadAudio = useCallback(async (blob: Blob) => {
    setState("processing");
    chat.startThinking();
    const url = `${wsToHttp(serverUrl)}/api/transcribe?token=${encodeURIComponent(token)}&language=fr`;
    try {
      const resp = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": blob.type || "audio/webm" },
        body: blob,
      });
      if (!resp.ok) {
        toast("Transcription : HTTP " + resp.status, true);
        setState("idle");
        chat.handleFinal("");
        return;
      }
      const data = await resp.json();
      if (!data.success || !data.text?.trim()) {
        toast(data.error || "Je n'ai rien compris.", true);
        setState("idle");
        chat.handleFinal("");
        return;
      }
      const text = data.text.trim();
      sendMessage(text);
    } catch (err) {
      toast("Échec : " + (err as Error).message, true);
      setState("idle");
      chat.handleFinal("");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [serverUrl, token, chat, toast]);

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

  // ─── Envoi message ───
  const sendMessage = useCallback((text: string) => {
    if (!text.trim()) return;
    if (!isConnected) {
      toast("Non connecté. Configure les paramètres (⚙).", true);
      return;
    }
    tts.reset();
    chat.addUser(text);
    chat.startThinking();
    setState("processing");
    const sent = ws.send({ type: "message", content: text });
    if (!sent) {
      toast("Échec d'envoi.", true);
      setState("idle");
      chat.handleFinal("");
    }
  }, [isConnected, ws, tts, chat, toast]);

  const toggleMic = useCallback(() => {
    if (!isConnected) {
      toast("Non connecté.", true);
      return;
    }
    if (mic.isRecording) {
      mic.stop();
    } else {
      window.speechSynthesis?.cancel();
      setState("listening");
      void mic.start();
    }
  }, [isConnected, mic, toast]);

  // ─── Confirm handlers ───
  const onConfirmApprove = useCallback((pwd: string) => {
    if (!confirmReq) return;
    ws.send({ type: "confirm_response", request_id: confirmReq.request_id, password: pwd });
  }, [confirmReq, ws]);

  const onConfirmDeny = useCallback(() => {
    if (!confirmReq) return;
    ws.send({ type: "confirm_response", request_id: confirmReq.request_id, refused: true });
    setConfirmReq(null);
    setConfirmError(null);
  }, [confirmReq, ws]);

  // ─── Message d'accueil au premier mount ───
  useEffect(() => {
    if (chat.messages.length === 0) {
      chat.addOrion(
        "Bonjour. Je suis Orion, ton assistant personnel. Configure le serveur dans les paramètres (⚙), puis connecte-toi.",
      );
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ─── Auto-scroll chat sur nouveau message ───
  const chatScrollRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = chatScrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [chat.messages, chat.phase]);

  return (
    <div className="h-screen flex flex-col">
      <div className="scanlines" />

      <PasswordGate open={gateOpen} onUnlock={() => setGateOpen(false)} />

      <Header
        variant="orion"
        connected={isConnected}
        onOpenSettings={() => setSettingsOpen((s) => !s)}
        panicActive={panic.active}
        onPanicToggle={panic.trigger}
        voiceServiceState={voiceServiceState}
        voiceDeviceId={voiceServiceDevice}
      />

      <main className="relative z-[5] flex-1 flex overflow-hidden">
        {/* ─── Panneau Sphère (gauche) ─── */}
        <aside className="relative w-[400px] min-w-[400px] flex flex-col items-center justify-center
                          border-r border-border overflow-hidden
                          bg-[linear-gradient(135deg,rgba(4,6,13,0)_0%,rgba(0,229,255,0.015)_100%)]">
          {/* Anneaux rotatifs */}
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2
                          w-[360px] h-[360px] rounded-full border border-cyan/[0.08]
                          animate-ring-spin pointer-events-none z-[2]">
            <div className="absolute -top-px left-[20%] w-3/5 h-0.5
                            bg-gradient-to-r from-transparent via-cyan to-transparent
                            shadow-[0_0_12px_var(--tw-shadow-color)] shadow-cyan-glow" />
          </div>
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2
                          w-[290px] h-[290px] rounded-full border border-dashed border-cyan/[0.06]
                          animate-ring-spin-rev pointer-events-none z-[2]" />

          {/* HUD readouts (positionnés relativement au panneau) */}
          <SphereHud />

          <Sphere
            state={state}
            audioLevelRef={audioLevelRef}
            size={300}
            particles={120}
            onShapeChange={(name) => {
              const labels: Record<string, string> = {
                sphere: "SPHÈRE", star: "ÉTOILE", cube: "CUBE",
                arcreactor: "ARC REACTOR", atom: "ATOME", hub: "HUB NEURONAL",
                tore: "TORE", face: "VISAGE IA", letterO: "LETTRE O", orion: "ORION",
              };
              setShapeLabel(labels[name] ?? name.toUpperCase());
            }}
          />

          <div className="relative z-[4] flex flex-col items-center gap-1 -mt-7">
            <div className="font-orbitron text-[8px] tracking-[4px] text-text-dim uppercase">
              Réseau neuronal IA
            </div>
            <div
              className={`font-orbitron text-[11px] tracking-[4px] uppercase h-[18px]
                          transition-colors ${STATE_COLOR[state]}
                          [text-shadow:0_0_12px_currentColor]`}
            >
              {STATE_TEXT[state]}
            </div>
          </div>

          {/* Shape indicator */}
          <div className="absolute bottom-[110px] right-5 text-right
                          font-mono text-[9px] tracking-[1px] leading-[1.8] text-text-dim z-[4]">
            SHAPE
            <br />
            <span className="hud-val">{shapeLabel}</span>
          </div>

          {/* Energy bars en bas */}
          <SphereEnergyBars voicePct={voicePct} />

          {/* Gradient overlay bas */}
          <div className="absolute bottom-0 left-0 right-0 h-[100px] pointer-events-none z-[3]
                          bg-gradient-to-t from-bg to-transparent" />
        </aside>

        {/* ─── Zone chat (droite) ─── */}
        <section className="flex-1 flex flex-col overflow-hidden">
          <div ref={chatScrollRef}
               className="flex-1 overflow-y-auto px-7 py-6 flex flex-col gap-5">
            {chat.messages.map((msg) => (
              <ChatMessage key={msg.id} msg={msg} />
            ))}
            {chat.phase === "thinking" && <ChatThinking tools={chat.pendingTools} />}
          </div>

          <ChatInput
            onSend={sendMessage}
            onMicToggle={toggleMic}
            isListening={mic.isRecording}
            disabled={!isConnected}
          />
        </section>
      </main>

      {/* ─── Overlays ─── */}
      <ToastHost toasts={toasts} onDismiss={dismiss} />
      <AuditToastHost alerts={auditAlerts} onDismiss={dismissAlert} />

      <ConfirmModal
        request={confirmReq}
        error={confirmError}
        onApprove={onConfirmApprove}
        onDeny={onConfirmDeny}
      />

      <SettingsPanel
        open={settingsOpen}
        serverUrl={serverUrl}
        setServerUrl={setServerUrl}
        token={token}
        setToken={setToken}
        deviceId={deviceId}
        setDeviceId={setDeviceId}
        onConnect={() => {
          setEnabled(true);
          setSettingsOpen(false);
        }}
        onDisconnect={() => {
          setEnabled(false);
          ws.close();
        }}
      />
    </div>
  );
}

/** HUD readouts en absolute (relatif au panneau sphère). */
function SphereHud() {
  const [load, setLoad] = useState("72%");
  const [temp, setTemp] = useState("38.0°C");
  const [lat, setLat] = useState("12ms");
  const [pkt, setPkt] = useState("99.8%");
  const [freq, setFreq] = useState("1.4kHz");

  useEffect(() => {
    const id = window.setInterval(() => {
      setLoad(Math.round(65 + Math.random() * 20) + "%");
      setTemp((38 + Math.random() * 4 - 2).toFixed(1) + "°C");
      setLat(Math.round(8 + Math.random() * 20) + "ms");
      setPkt((99.5 + Math.random() * 0.5).toFixed(1) + "%");
      setFreq((1 + Math.random() * 0.8).toFixed(1) + "kHz");
    }, 1200);
    return () => window.clearInterval(id);
  }, []);

  return (
    <>
      <div className="absolute top-5 left-5 font-mono text-[9px] tracking-[1px] leading-[1.8] text-text-dim z-[4]">
        SYS / NEURAL
        <br />LOAD&nbsp;&nbsp;<span className="hud-val">{load}</span>
        <br />TEMP&nbsp;&nbsp;<span className="hud-val">{temp}</span>
      </div>
      <div className="absolute top-5 right-5 text-right font-mono text-[9px] tracking-[1px] leading-[1.8] text-text-dim z-[4]">
        RÉSEAU
        <br />LAT&nbsp;&nbsp;&nbsp;<span className="hud-val">{lat}</span>
        <br />PKT&nbsp;&nbsp;&nbsp;<span className="hud-val">{pkt}</span>
      </div>
      <div className="absolute bottom-[110px] left-5 font-mono text-[9px] tracking-[1px] leading-[1.8] text-text-dim z-[4]">
        FREQ&nbsp;<span className="hud-val">{freq}</span>
      </div>
    </>
  );
}

/** Barres d'énergie internes au panneau sphère. */
function SphereEnergyBars({ voicePct }: { voicePct: number }) {
  const [neural, setNeural] = useState(72);
  const [net, setNet] = useState(35);

  useEffect(() => {
    const id = window.setInterval(() => {
      setNeural(Math.round(60 + Math.random() * 30));
      setNet(Math.round(25 + Math.random() * 25));
    }, 1200);
    return () => window.clearInterval(id);
  }, []);

  const rows = [
    { label: "NEURAL", pct: neural },
    { label: "VOICE",  pct: voicePct },
    { label: "NET",    pct: net },
  ];

  return (
    <div className="absolute bottom-6 left-6 right-6 z-[4] flex flex-col gap-1">
      {rows.map((r) => (
        <div key={r.label} className="flex items-center gap-2">
          <div className="font-mono text-[8px] tracking-[1.5px] text-text-dim min-w-[56px] uppercase">
            {r.label}
          </div>
          <div className="flex-1 h-0.5 bg-cyan/[0.06] rounded-sm overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-cyan to-cyan/60 rounded-sm
                         shadow-[0_0_6px_var(--tw-shadow-color)] shadow-cyan-glow
                         transition-[width] duration-500"
              style={{ width: `${r.pct}%` }}
            />
          </div>
          <div className="font-mono text-[8px] text-cyan min-w-[32px] text-right">{r.pct}%</div>
        </div>
      ))}
    </div>
  );
}
