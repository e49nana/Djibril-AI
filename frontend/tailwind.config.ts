import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        "dj-bg": "#080A12",
        "dj-surface": "#0D1017",
        "dj-surface-hover": "#111620",
        "dj-border": "#1A1F2E",
        "dj-border-active": "#2A3040",
        "dj-text": "#C8CDD8",
        "dj-text-muted": "#6B7280",
        "dj-text-bright": "#E8ECF2",
        "dj-accent": "#E8A020",
        "dj-green": "#27AE60",
        "dj-red": "#E74C3C",
        "dj-cyan": "#06B6D4",
        "dj-blue": "#3B82F6",
        "dj-amber": "#F59E0B",
        "dj-critical": "#DC2626",
      },
      fontFamily: {
        sans: ["Syne", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "monospace"],
      },
      animation: {
        "pulse-slow": "pulse 3s cubic-bezier(0.4,0,0.6,1) infinite",
      },
    },
  },
  plugins: [],
} satisfies Config;
