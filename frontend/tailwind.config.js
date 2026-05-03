/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Tokens design Orion (mêmes que orion_ui.html)
        cyan: {
          DEFAULT: "#00e5ff",
          glow: "rgba(0,229,255,0.4)",
          dim: "rgba(0,229,255,0.08)",
        },
        gold: "#f5c518",
        green: "#00ffa3",
        red: "#ff3b5c",
        violet: { DEFAULT: "#7b5ea7", 400: "rgba(123,94,167,0.6)" },

        // Palette spécifique au dashboard trading (préservée du legacy)
        trading: {
          bg:     "#06090f",
          bg2:    "#0d1425",
          bg3:    "#111b30",
          bg4:    "#0a1020",
          cyan:   "#00d4ff",
          green:  "#00e676",
          red:    "#ff4466",
          gold:   "#ffd700",
          purple: "#b060ff",
          text:   "#c8e8ff",
          text2:  "#6a9ab8",
          text3:  "#3a6a8a",
          border: "#0d3a5a",
        },
        bg: { DEFAULT: "#04060d", 2: "#080e1e", 3: "rgba(6,14,32,0.72)" },
        text: { DEFAULT: "#b8d8f0", dim: "rgba(120,170,210,0.45)" },
        border: {
          DEFAULT: "rgba(0,229,255,0.1)",
          hi: "rgba(0,229,255,0.35)",
        },
      },
      fontFamily: {
        orbitron: ['"Orbitron"', "monospace"],
        space: ['"Space Grotesk"', "sans-serif"],
        mono: ['"JetBrains Mono"', "monospace"],
        rajdhani: ['"Rajdhani"', "sans-serif"],
        tech: ['"Share Tech Mono"', "monospace"],
      },
      animation: {
        "ring-spin": "ring-spin 20s linear infinite",
        "ring-spin-rev": "ring-spin 35s linear infinite reverse",
        "pulse-dot": "pulse-dot 2.5s ease-in-out infinite",
        "pulse-fast": "pulse-dot 1s ease-in-out infinite",
        "mic-pulse": "mic-pulse 1.2s ease-in-out infinite",
      },
      keyframes: {
        "ring-spin": {
          from: { transform: "rotate(0deg)" },
          to: { transform: "rotate(360deg)" },
        },
        "pulse-dot": {
          "0%, 100%": { opacity: "1", transform: "scale(1)" },
          "50%": { opacity: "0.35", transform: "scale(0.6)" },
        },
        "mic-pulse": {
          "0%, 100%": { transform: "scale(1)" },
          "50%": { transform: "scale(1.05)" },
        },
      },
      backdropBlur: { panel: "18px" },
    },
  },
  plugins: [],
};
