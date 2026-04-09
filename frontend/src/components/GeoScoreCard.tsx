import type { GeoScoreResponse, Urgency } from "../types";

const TENSION_LABELS: Record<string, { label: string; color: string }> = {
  critical_high: { label: "CRITIQUE", color: "#DC2626" },
  high: { label: "ÉLEVÉ", color: "#F97316" },
  medium: { label: "MODÉRÉ", color: "#F59E0B" },
  low: { label: "FAIBLE", color: "#27AE60" },
  deescalation: { label: "DÉTENTE", color: "#06B6D4" },
};

function getTension(score: number): { label: string; color: string } {
  if (score >= 8) return TENSION_LABELS.critical_high;
  if (score >= 5) return TENSION_LABELS.high;
  if (score >= 1) return TENSION_LABELS.medium;
  if (score >= -2) return TENSION_LABELS.low;
  return TENSION_LABELS.deescalation;
}

interface GeoScoreCardProps {
  geoScore: GeoScoreResponse | null;
}

export default function GeoScoreCard({ geoScore }: GeoScoreCardProps) {
  const score = geoScore?.score ?? 0;
  const tension = getTension(score);

  const radius = 54;
  const circumference = 2 * Math.PI * radius;
  const progress = ((score + 10) / 20) * circumference;

  return (
    <div className="bg-dj-surface border border-dj-border rounded-lg overflow-hidden">
      <div className="text-[11px] font-bold tracking-[2px] text-dj-text-muted px-4 py-3 border-b border-dj-border bg-dj-bg/50">
        GEO SCORE
      </div>

      <div className="flex items-center justify-center py-5">
        <svg width="140" height="140" viewBox="0 0 140 140">
          {/* Track */}
          <circle cx="70" cy="70" r={radius} fill="none" stroke="#1A1F2E" strokeWidth="8" />
          {/* Progress arc */}
          <circle
            cx="70"
            cy="70"
            r={radius}
            fill="none"
            stroke={tension.color}
            strokeWidth="8"
            strokeDasharray={`${progress} ${circumference}`}
            strokeLinecap="round"
            transform="rotate(-90 70 70)"
            className="transition-all duration-700 ease-out"
          />
          {/* Score number */}
          <text
            x="70"
            y="62"
            textAnchor="middle"
            fill={tension.color}
            fontSize="30"
            fontWeight="800"
            fontFamily="'JetBrains Mono', monospace"
          >
            {score > 0 ? "+" : ""}
            {score}
          </text>
          {/* Tension label */}
          <text
            x="70"
            y="82"
            textAnchor="middle"
            fill={tension.color}
            fontSize="10"
            fontWeight="700"
            letterSpacing="2"
          >
            {tension.label}
          </text>
        </svg>
      </div>

      <div className="px-4 pb-4">
        <p className="text-dj-text-muted text-xs italic leading-relaxed">
          {geoScore?.reasoning ?? "Awaiting analysis…"}
        </p>
      </div>
    </div>
  );
}
