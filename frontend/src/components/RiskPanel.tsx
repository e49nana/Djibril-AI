import type { TradeSignal } from "../types";

interface RiskPanelProps {
  signal: TradeSignal | null;
}

export default function RiskPanel({ signal }: RiskPanelProps) {
  return (
    <div className="bg-dj-surface border border-dj-border rounded-lg overflow-hidden">
      <div className="text-[11px] font-bold tracking-[2px] text-dj-text-muted px-4 py-3 border-b border-dj-border bg-dj-bg/50">
        RISK PANEL
      </div>

      <div className="grid grid-cols-2 gap-3 p-4">
        <RiskStat label="Lot Size" value={signal?.lot_size.toFixed(2) ?? "—"} />
        <RiskStat label="Kelly" value={signal ? `${(signal.kelly_fraction * 100).toFixed(1)}%` : "—"} />
        <RiskStat label="Stop Loss" value={signal ? `$${signal.stop_loss.toFixed(2)}` : "—"} className="text-dj-red" />
        <RiskStat label="Take Profit" value={signal ? `$${signal.take_profit.toFixed(2)}` : "—"} className="text-dj-green" />
        <RiskStat label="R:R Ratio" value={signal?.risk_reward_ratio.toFixed(2) ?? "—"} />
        <RiskStat label="Max Spread" value={signal ? String(signal.max_spread_allowed) : "—"} />
        <RiskStat
          label="Statut"
          value={signal ? (signal.action === "FLAT" ? "En attente" : "Actif") : "—"}
          className={signal?.action === "FLAT" ? "text-dj-text-muted" : "text-dj-green"}
        />
        <RiskStat label="SL Pips" value={signal?.sl_pips.toFixed(0) ?? "—"} />
      </div>

      {/* Risk flags */}
      {signal && signal.risk_flags.length > 0 && (
        <div className="px-4 pb-4">
          <div className="text-[10px] text-dj-amber tracking-widest font-bold mb-1.5">⚠ RISK FLAGS</div>
          <div className="flex flex-wrap gap-1.5">
            {signal.risk_flags.map((flag, i) => (
              <span
                key={i}
                className="bg-dj-red/10 text-dj-red text-[10px] px-2 py-0.5 rounded border border-dj-red/20"
              >
                {flag.length > 50 ? flag.slice(0, 50) + "…" : flag}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function RiskStat({
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
      <div className="text-[10px] text-dj-text-muted tracking-wide">{label}</div>
      <div className={`font-mono text-sm font-bold ${className}`}>{value}</div>
    </div>
  );
}
