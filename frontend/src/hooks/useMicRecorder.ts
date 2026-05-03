import { useCallback, useRef, useState } from "react";

interface UseMicRecorderOpts {
  /** Callback appelé en boucle avec audioLevel (0..1) tant que enregistrement actif. */
  onAudioLevel?: (level: number) => void;
  /** Délai de silence (ms) après détection de parole avant de stop auto. */
  silenceMs?: number;
  /** Limite max de l'enregistrement (ms). */
  maxMs?: number;
  /** Seuil de détection de parole (0-128, ~12 = sensible mais robuste). */
  speechThreshold?: number;
}

const PREFERRED_MIMES = [
  "audio/webm;codecs=opus",
  "audio/webm",
  "audio/ogg;codecs=opus",
  "audio/mp4",
];

function pickMime(): string {
  if (typeof window === "undefined" || !window.MediaRecorder) return "";
  for (const m of PREFERRED_MIMES) {
    if (MediaRecorder.isTypeSupported(m)) return m;
  }
  return "";
}

/**
 * Capture micro avec MediaRecorder + détection silence (Web Audio AnalyserNode).
 * Stop auto après `silenceMs` de silence APRÈS détection de parole.
 *
 * Retourne :
 *  - isRecording : booléen pour l'UI
 *  - start() / stop() : contrôle
 *  - lastBlob : le dernier blob enregistré (pour upload)
 */
export function useMicRecorder({
  onAudioLevel,
  silenceMs = 1400,
  maxMs = 20000,
  speechThreshold = 12,
}: UseMicRecorderOpts = {}) {
  const [isRecording, setIsRecording] = useState(false);
  const [lastBlob, setLastBlob] = useState<Blob | null>(null);
  const [lastError, setLastError] = useState<string | null>(null);

  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const rafRef = useRef<number | null>(null);
  const maxTimeoutRef = useRef<number | null>(null);
  const onAudioLevelRef = useRef(onAudioLevel);
  onAudioLevelRef.current = onAudioLevel;

  const cleanup = useCallback(() => {
    if (rafRef.current) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    if (maxTimeoutRef.current) {
      clearTimeout(maxTimeoutRef.current);
      maxTimeoutRef.current = null;
    }
    try { sourceRef.current?.disconnect(); } catch { /* ignore */ }
    try { analyserRef.current?.disconnect(); } catch { /* ignore */ }
    try { audioCtxRef.current?.close(); } catch { /* ignore */ }
    audioCtxRef.current = null;
    analyserRef.current = null;
    sourceRef.current = null;
    streamRef.current?.getTracks().forEach(t => t.stop());
    streamRef.current = null;
    recorderRef.current = null;
  }, []);

  const stop = useCallback(() => {
    const r = recorderRef.current;
    if (r && r.state === "recording") {
      r.stop(); // déclenchera onstop qui assemble le blob
    } else {
      cleanup();
      setIsRecording(false);
    }
  }, [cleanup]);

  const start = useCallback(async () => {
    if (isRecording) return;
    setLastError(null);
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      setLastError("Capture audio non supportée par ce navigateur.");
      return;
    }
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, sampleRate: 16000 },
      });
    } catch (err) {
      setLastError("Accès micro refusé : " + (err as Error).message);
      return;
    }
    streamRef.current = stream;
    const mime = pickMime();

    let recorder: MediaRecorder;
    try {
      recorder = mime
        ? new MediaRecorder(stream, { mimeType: mime })
        : new MediaRecorder(stream);
    } catch (err) {
      stream.getTracks().forEach(t => t.stop());
      setLastError("MediaRecorder : " + (err as Error).message);
      return;
    }
    recorderRef.current = recorder;
    chunksRef.current = [];

    recorder.ondataavailable = (e) => {
      if (e.data?.size) chunksRef.current.push(e.data);
    };
    recorder.onstop = () => {
      const blob = chunksRef.current.length
        ? new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" })
        : null;
      chunksRef.current = [];
      cleanup();
      setIsRecording(false);
      onAudioLevelRef.current?.(0);
      setLastBlob(blob);
    };
    recorder.onerror = () => {
      cleanup();
      setIsRecording(false);
      setLastError("Erreur MediaRecorder.");
    };

    // Web Audio analyser pour silence detect + level meter
    try {
      const ctx = new (window.AudioContext || (window as any).webkitAudioContext)();
      const source = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 256;
      source.connect(analyser);
      audioCtxRef.current = ctx;
      sourceRef.current = source;
      analyserRef.current = analyser;

      const buf = new Uint8Array(analyser.frequencyBinCount);
      let silenceStart: number | null = null;
      let hasSpeech = false;

      const loop = () => {
        if (!analyserRef.current) return;
        analyserRef.current.getByteTimeDomainData(buf);
        let max = 0;
        for (let i = 0; i < buf.length; i++) {
          const v = Math.abs(buf[i] - 128);
          if (v > max) max = v;
        }
        const lvl = Math.min(1, max / 64);
        onAudioLevelRef.current?.(lvl);

        if (max > speechThreshold) {
          silenceStart = null;
          hasSpeech = true;
        } else if (hasSpeech) {
          if (silenceStart === null) silenceStart = performance.now();
          else if (performance.now() - silenceStart > silenceMs) {
            stop();
            return;
          }
        }
        rafRef.current = requestAnimationFrame(loop);
      };
      loop();
    } catch {
      /* Audio analysis pas dispo : on fonctionne quand même, juste sans silence detect */
    }

    maxTimeoutRef.current = window.setTimeout(() => stop(), maxMs);
    recorder.start();
    setIsRecording(true);
  }, [isRecording, cleanup, stop, silenceMs, maxMs, speechThreshold]);

  return { isRecording, lastBlob, lastError, start, stop };
}
