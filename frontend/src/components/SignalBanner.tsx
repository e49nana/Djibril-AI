import type { TradeSignal, TradeAction, Urgency } from "../types";

const ACTION_CONFIG: Record<TradeAction, { color: string; emoji: string; label: string }> = {
  BUY: { color: "dj-green", emoji: "📈", label: "LONG" },
  SELL: { color: "dj-red", emoji: "📉", label: "SHORT" },
  FLAT: { color: "dj-text-muted", emoji: "⏸", label: "NEUTRAL" },
};

const URGENCY_COLORS: Record<Urgency, string> = {
  low: "bg-dj-green/20 text-dj-green",
  medium: "bg-dj-amber/20 text-dj-amber",
  high: "bg-orange-500/20 text-orange-400",
  critical: "bg-dj-red/20 text-dj-red",
};

interface SignalBannerProps {
  signal: TradeSignal | null;
}

export default function SignalBanner({ signal }: SignalBannerProps) {
  if (!signal) {
    return (
      <div className="bg-dj-surface border border-dj-border border-l-4 border-l-dj-border rounded-lg px-5 py-4">
        <div className="flex items-center gap-3">
          <span className="inline-block w-2 h-2 rounded-full bg-dj-text-muted animate-pulse-slow" />
          <span className="font-mono text-lg font-bold text-dj-text-muted tracking-wider">
            AWAITING SIGNAL
          </span>
        </div>
        <p className="text-dj-text-muted text-sm mt-1">
          System initializing — waiting for first analysis cycle.
        </p>
      </div>
    );
  }

  const cfg = ACTION_CONFIG[signal.action];
  const borderColor =
    signal.action === "BUY"
      ? "border-l-dj-green"
      : signal.action === "SELL"
        ? "border-l-dj-red"
        : "border-l-dj-text-muted";

  return (
    <div
      className={`bg-dj-surface border border-dj-border border-l-4 ${borderColor} rounded-lg px-5 py-4 transition-all duration-300`}
    >
      {/* Top row */}
      <div className="flex flex-wrap items-center gap-4">
        <div className="flex items-center gap-2">
          <span className={`inline-block w-2.5 h-2.5 rounded-full bg-${cfg.color} animate-pulse-slow`} />
          <span className={`font-mono text-2xl font-extrabold tracking-wide text-${cfg.color}`}>
            {cfg.emoji} {signal.action} {signal.symbol}
          </span>
        </div>

        <span
          className={`text-xs font-semibold px-3 py-1 rounded border ${
            signal.action === "BUY"
              ? "bg-dj-green/10 border-dj-green/30 text-dj-green"
              : signal.action === "SELL"
                ? "bg-dj-red/10 border-dj-red/30 text-dj-red"
                : "bg-dj-border text-dj-text-muted border-dj-border"
          }`}
        >
          {cfg.label} · {(signal.confidence * 100).toFixed(0)}% CONF
        </span>

        <span className={`text-[10px] font-bold px-2 py-0.5 rounded uppercase tracking-wider ${URGENCY_COLORS[signal.urgency]}`}>
          {signal.urgency}
        </span>
      </div>

      {/* Stats row */}
      {signal.action !== "FLAT" && (
        <div className="flex flex-wrap gap-6 mt-3">
          <StatCell label="ENTRY" value={`$${signal.entry_price.toFixed(2)}`} />
          <StatCell label="SL" value={`$${signal.stop_loss.toFixed(2)}`} className="text-dj-red" />
          <StatCell label="TP" value={`$${signal.take_profit.toFixed(2)}`} className="text-dj-green" />
          <StatCell label="R:R" value={signal.risk_reward_ratio.toFixed(2)} />
          <StatCell label="LOTS" value={signal.lot_size.toFixed(2)} />
          <StatCell label="GEO" value={`${signal.geo_score > 0 ? "+" : ""}${signal.geo_score}`} className="text-dj-accent" />
        </div>
      )}

      {/* Reasoning */}
      <p className="text-dj-text-muted text-xs mt-2 leading-relaxed">
        {signal.reasoning.slice(0, 120)}
        {signal.reasoning.length > 120 ? "…" : ""}
      </p>
    </div>
  );
}

function StatCell({
  label,
  value,
  className = "text-dj-text-bright",
}: {
  label: string;
  value: string;
  className?: string;
}) {
  return (
    <div>
      <div className="text-[10px] text-dj-text-muted tracking-widest">{label}</div>
      <div className={`font-mono text-base font-bold ${className}`}>{value}</div>
    </div>
  );
}
