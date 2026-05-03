import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** Helper standard shadcn pour merger des classes Tailwind */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** localStorage avec fallback safe (SSR / privé) */
export const storage = {
  get(key: string, def = ""): string {
    try {
      return window.localStorage.getItem(key) ?? def;
    } catch {
      return def;
    }
  },
  set(key: string, value: string) {
    try {
      window.localStorage.setItem(key, value);
    } catch {
      /* noop */
    }
  },
};

/** Convertit ws:// → http:// pour les endpoints REST. */
export function wsToHttp(url: string): string {
  return url.replace(/^ws/, "http");
}

/** Échappe le HTML (utile pour insérer du texte transcrit dans innerHTML). */
export function escapeHtml(s: string): string {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[c]!);
}
