import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";
import type { TradeSignal } from "../types";

interface OilChartProps {
  signals: TradeSignal[];
}

interface ChartPoint {
  time: string;
  confidence: number;
  geoScore: number;
  action: string;
  signalId: string;
  reasoning: string;
}

function formatSignals(signals: TradeSignal[]): ChartPoint[] {
  return signals
    .slice()
    .reverse()
    .map((s) => ({
      time: new Date(s.created_at).toLocaleTimeString("en-US", {
        hour: "2-digit",
        minute: "2-digit",
      }),
      confidence: Math.round(s.confidence * 100),
      geoScore: s.geo_score,
      action: s.action,
      signalId: s.signal_id,
      reasoning: s.reasoning.slice(0, 80),
    }));
}

function CustomTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: Array<{ payload: ChartPoint }>;
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;

  const actionColor =
    d.action === "BUY" ? "text-dj-green" : d.action === "SELL" ? "text-dj-red" : "text-dj-text-muted";

  return (
    <div className="bg-dj-surface border border-dj-border rounded-lg p-3 shadow-xl max-w-[220px]">
      <div className="flex items-center justify-between gap-3 mb-1.5">
        <span className={`font-mono text-sm font-bold ${actionColor}`}>{d.action}</span>
        <span className="text-[10px] text-dj-text-muted">{d.time}</span>
      </div>
      <div className="flex gap-4 text-xs mb-1.5">
        <span>
          Conf: <span className="text-dj-green font-mono font-bold">{d.confidence}%</span>
        </span>
        <span>
          Geo: <span className="text-dj-accent font-mono font-bold">{d.geoScore > 0 ? "+" : ""}{d.geoScore}</span>
        </span>
      </div>
      <p className="text-[10px] text-dj-text-muted leading-snug">{d.reasoning}…</p>
    </div>
  );
}

export default function OilChart({ signals }: OilChartProps) {
  const data = formatSignals(signals);

  if (data.length === 0) {
    return (
      <div className="bg-dj-surface border border-dj-border rounded-lg overflow-hidden">
        <div className="text-[11px] font-bold tracking-[2px] text-dj-text-muted px-4 py-3 border-b border-dj-border bg-dj-bg/50">
          SIGNAL HISTORY
        </div>
        <div className="flex items-center justify-center h-56 text-dj-text-muted text-sm">
          En attente de signaux…
        </div>
      </div>
    );
  }

  return (
    <div className="bg-dj-surface border border-dj-border rounded-lg overflow-hidden">
      <div className="text-[11px] font-bold tracking-[2px] text-dj-text-muted px-4 py-3 border-b border-dj-border bg-dj-bg/50">
        SIGNAL HISTORY
      </div>
      <div className="p-4">
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={data} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1A1F2E" />
            <XAxis
              dataKey="time"
              tick={{ fontSize: 10, fill: "#6B7280" }}
              axisLine={{ stroke: "#1A1F2E" }}
              tickLine={false}
            />
            <YAxis
              domain={[0, 100]}
              tick={{ fontSize: 10, fill: "#6B7280" }}
              axisLine={{ stroke: "#1A1F2E" }}
              tickLine={false}
            />
            <Tooltip content={<CustomTooltip />} />
            <ReferenceLine y={60} stroke="#27AE60" strokeDasharray="4 4" strokeOpacity={0.4} />
            <Line
              type="monotone"
              dataKey="confidence"
              stroke="#27AE60"
              strokeWidth={2}
              dot={(props: Record<string, unknown>) => {
                const entry = props.payload as ChartPoint;
                const cx = props.cx as number;
                const cy = props.cy as number;
                const fill =
                  entry.action === "BUY" ? "#27AE60" : entry.action === "SELL" ? "#E74C3C" : "#6B7280";
                return <circle key={props.index as number} cx={cx} cy={cy} r={4} fill={fill} stroke="#0D1017" strokeWidth={2} />;
              }}
              activeDot={{ r: 6, stroke: "#E8A020", strokeWidth: 2 }}
            />
            <Line
              type="monotone"
              dataKey="geoScore"
              stroke="#E8A020"
              strokeWidth={1.5}
              strokeDasharray="5 3"
              dot={false}
            />
          </LineChart>
        </ResponsiveContainer>
        <div className="flex gap-5 justify-center mt-2">
          <Legend color="#27AE60" label="Confidence %" />
          <Legend color="#E8A020" label="Geo Score" dashed />
          <Legend color="#27AE60" label="● BUY" dot />
          <Legend color="#E74C3C" label="● SELL" dot />
        </div>
      </div>
    </div>
  );
}

function Legend({
  color,
  label,
  dashed,
  dot,
}: {
  color: string;
  label: string;
  dashed?: boolean;
  dot?: boolean;
}) {
  return (
    <div className="flex items-center gap-1.5 text-[10px] text-dj-text-muted">
      {dot ? (
        <span style={{ color }} className="text-xs">●</span>
      ) : (
        <span
          className="inline-block w-4 h-[2px] rounded"
          style={{
            backgroundColor: color,
            borderTop: dashed ? `2px dashed ${color}` : undefined,
            background: dashed ? "transparent" : color,
          }}
        />
      )}
      {label}
    </div>
  );
}
