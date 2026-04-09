import type { TradeSignal, GeoScoreResponse } from "../types";

interface ConfidenceMeterProps {
  signal: TradeSignal | null;
  geoScore: GeoScoreResponse | null;
}

interface BarData {
  label: string;
  value: number;
  color: string;
  bgColor: string;
}

export default function ConfidenceMeter({ signal, geoScore }: ConfidenceMeterProps) {
  const geoValue = geoScore ? Math.abs(geoScore.score) / 10 : 0;
  const techValue = signal ? (signal.technical_score_value + 1) / 2 : 0;
  const sentValue = signal ? (signal.sentiment_score_value + 1) / 2 : 0;
  const confValue = signal?.confidence ?? 0;

  const bars: BarData[] = [
    { label: "GÉOPOLITIQUE", value: geoValue, color: "bg-dj-red", bgColor: "bg-dj-red/20" },
    { label: "TECHNIQUE", value: techValue, color: "bg-dj-blue", bgColor: "bg-dj-blue/20" },
    { label: "SENTIMENT", value: sentValue, color: "bg-dj-amber", bgColor: "bg-dj-amber/20" },
    { label: "CONFIANCE", value: confValue, color: "bg-dj-green", bgColor: "bg-dj-green/20" },
  ];

  return (
    <div className="bg-dj-surface border border-dj-border rounded-lg overflow-hidden">
      <div className="text-[11px] font-bold tracking-[2px] text-dj-text-muted px-4 py-3 border-b border-dj-border bg-dj-bg/50">
        CONFIDENCE METER
      </div>

      <div className="p-4 flex flex-col gap-3.5">
        {bars.map((bar) => {
          const pct = Math.max(0, Math.min(100, bar.value * 100));
          return (
            <div key={bar.label}>
              <div className="flex items-center justify-between mb-1">
                <span className="text-[10px] text-dj-text-muted tracking-widest font-medium">
                  {bar.label}
                </span>
                <span className="font-mono text-xs font-bold text-dj-text-bright">
                  {pct.toFixed(0)}%
                </span>
              </div>
              <div className={`h-1.5 rounded-full ${bar.bgColor} overflow-hidden`}>
                <div
                  className={`h-full rounded-full ${bar.color} transition-all duration-700 ease-out`}
                  style={{ width: `${pct}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
