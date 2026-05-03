import { useCallback, useRef } from "react";

const SENTENCE_END_RE = /[.!?…]+(\s|$)/g;

function pickFrenchVoice(): SpeechSynthesisVoice | null {
  const voices = window.speechSynthesis?.getVoices() ?? [];
  if (!voices.length) return null;
  const fr = voices.filter(v => v.lang.toLowerCase().startsWith("fr"));
  if (!fr.length) return voices[0];
  const prefs = ["paul", "thomas", "henri", "google français", "microsoft paul"];
  for (const p of prefs) {
    const m = fr.find(v => v.name.toLowerCase().includes(p));
    if (m) return m;
  }
  return fr[0];
}

function cleanForSpeech(text: string): string {
  let t = text;
  t = t.replace(/```[\s\S]*?```/g, " ");
  t = t.replace(/`([^`]+)`/g, "$1");
  // Emojis & pictogrammes (Unicode property escape)
  t = t.replace(/[\p{Extended_Pictographic}\u{1F1E6}-\u{1F1FF}\u{2600}-\u{27BF}]/gu, " ");
  t = t.replace(/[*_#>]/g, "");
  t = t.replace(/^\s*[-*+]\s+/gm, "");
  t = t.replace(/^\s*\d+[.)]\s+/gm, "");
  t = t.replace(/\n{2,}/g, ". ").replace(/\n/g, " ");
  t = t.replace(/\s+/g, " ").trim();
  return t;
}

/**
 * TTS streaming : on accumule des chunks de texte au fur et à mesure de la
 * réception (streaming LLM). Dès qu'on a une phrase complète (terminée par
 * `.!?…`), on l'envoie à SpeechSynthesisUtterance qui s'enchaîne sans gap.
 */
export function useTTSStream() {
  const accRef = useRef("");
  const spokenIdxRef = useRef(0);

  const reset = useCallback(() => {
    accRef.current = "";
    spokenIdxRef.current = 0;
    window.speechSynthesis?.cancel();
  }, []);

  const speakOne = useCallback((text: string) => {
    if (!window.speechSynthesis) return;
    const clean = cleanForSpeech(text);
    if (!clean) return;
    const u = new SpeechSynthesisUtterance(clean);
    const v = pickFrenchVoice();
    if (v) u.voice = v;
    u.lang = "fr-FR";
    u.rate = 1.05;
    u.pitch = 1.0;
    window.speechSynthesis.speak(u);
  }, []);

  const appendChunk = useCallback((chunk: string) => {
    if (!chunk) return;
    accRef.current += chunk;
    const remaining = accRef.current.slice(spokenIdxRef.current);
    let lastBoundaryEnd = 0;
    let m: RegExpExecArray | null;
    SENTENCE_END_RE.lastIndex = 0;
    while ((m = SENTENCE_END_RE.exec(remaining)) !== null) {
      lastBoundaryEnd = m.index + m[0].length;
    }
    if (lastBoundaryEnd > 0) {
      const toSpeak = remaining.slice(0, lastBoundaryEnd).trim();
      if (toSpeak.length >= 8) {
        speakOne(toSpeak);
        spokenIdxRef.current += lastBoundaryEnd;
      }
    }
  }, [speakOne]);

  /** Flush la dernière partie non parlée (ex: pas de ponctuation finale). */
  const flush = useCallback((finalText?: string) => {
    const fullText = finalText ?? accRef.current;
    const tail = fullText.slice(spokenIdxRef.current).trim();
    if (tail) speakOne(tail);
    accRef.current = "";
    spokenIdxRef.current = 0;
  }, [speakOne]);

  return { appendChunk, flush, reset };
}
