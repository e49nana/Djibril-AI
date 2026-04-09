import { useState, useCallback } from "react";
import "./index.css";
import type { TradeSignal, NewsItem, GeoScoreResponse, WSMessage } from "./types";
import { useWebSocket } from "./hooks/useWebSocket";
import { useLatestSignal, useGeoScore, useSignalHistory, useNews } from "./hooks/useSignalHistory";
import SignalBanner from "./components/SignalBanner";
import GeoScoreCard from "./components/GeoScoreCard";
import ConfidenceMeter from "./components/ConfidenceMeter";
import RiskPanel from "./components/RiskPanel";
import NewsFlux from "./components/NewsFlux";
import OilChart from "./components/OilChart";
import DjibrilChat from "./components/DjibrilChat";

const WS_URL = import.meta.env.VITE_WS_URL ?? "ws://localhost:8000/ws";

export default function App() {
  const { signal, setSignal } = useLatestSignal();
  const { score, setScore } = useGeoScore();
  const [wsNewsItems, setWsNewsItems] = useState<NewsItem[]>([]);
  const { items: news, sourceMode } = useNews(undefined, 50, wsNewsItems);
  const { signals: signalHistory } = useSignalHistory(30);

  // Agent v2.0 state
  const [chatOpen, setChatOpen] = useState(false);
  const [agentBrief, setAgentBrief] = useState("");

  const handleWsMessage = useCallback(
    (msg: WSMessage) => {
      if (msg.type === "signal") {
        setSignal(msg.payload as unknown as TradeSignal);
      } else if (msg.type === "geo_score") {
        setScore(msg.payload as unknown as GeoScoreResponse);
      } else if (msg.type === "news") {
        const payload = msg.payload as { items?: NewsItem[] };
        if (payload.items) {
          const newItems = payload.items as NewsItem[];
          setWsNewsItems((prev) => {
            const merged = [...newItems, ...prev];
            const seen = new Set<string>();
            return merged
              .filter((i) => {
                if (seen.has(i.title)) return false;
                seen.add(i.title);
                return true;
              })
              .slice(0, 100);
          });
        }
      } else if (msg.type === "agent_brief") {
        const payload = msg.payload as { brief?: string };
        if (payload.brief) {
          setAgentBrief(payload.brief);
        }
      }
    },
    [setSignal, setScore],
  );

  const { isConnected, clientCount } = useWebSocket({
    url: WS_URL,
    onMessage: handleWsMessage,
  });

  const handleCategoryFilter = useCallback((_cat: string | null) => {
    // Filter handled inside NewsFlux
  }, []);

  return (
    <div className="min-h-screen bg-dj-bg text-dj-text">
      {/* ── Header ── */}
      <header className="flex items-center justify-between px-6 py-3 border-b border-dj-border bg-dj-surface">
        <div className="flex items-center gap-3">
          <span className="text-xl font-extrabold tracking-[2px] text-dj-text-bright">
            🛢️ DJIBRIL AI
          </span>
          <span className="hidden sm:inline text-[11px] text-dj-text-muted tracking-[3px] uppercase">
            Geopolitical OSINT · Crude Oil
          </span>
        </div>

        <div className="flex items-center gap-4">
          <button
            onClick={() => setChatOpen(true)}
            className="text-xs font-bold px-3 py-1.5 rounded-lg border border-dj-accent/30 bg-dj-accent/10 text-dj-accent hover:bg-dj-accent/20 transition-colors cursor-pointer"
          >
            💬 Ask DJIBRIL
          </button>

          <div className="flex items-center gap-2">
            <span
              className={`w-2 h-2 rounded-full ${
                isConnected ? "bg-dj-green shadow-[0_0_8px_#27AE60]" : "bg-dj-red shadow-[0_0_8px_#E74C3C]"
              }`}
            />
            <span className="text-[11px] text-dj-text-muted font-mono">
              {isConnected ? `LIVE · ${clientCount} clients` : "DISCONNECTED"}
            </span>
          </div>
        </div>
      </header>

      {/* ── Agent Brief Banner ── */}
      {agentBrief && (
        <div className="bg-dj-blue/5 border-b border-dj-blue/10 px-6 py-2">
          <p className="text-xs text-dj-text-muted max-w-[1440px] mx-auto">
            <span className="text-dj-blue font-bold mr-1.5">DJIBRIL</span>
            {agentBrief.slice(0, 200)}
          </p>
        </div>
      )}

      {/* ── Main ── */}
      <main className="max-w-[1440px] mx-auto px-4 sm:px-6 py-5 space-y-5">
        <SignalBanner signal={signal} />

        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          <GeoScoreCard geoScore={score} />
          <ConfidenceMeter signal={signal} geoScore={score} />
          <RiskPanel signal={signal} />
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <NewsFlux news={news} wsItems={wsNewsItems} sourceMode={sourceMode} onCategoryFilter={handleCategoryFilter} />
          <OilChart signals={signalHistory} />
        </div>
      </main>

      {/* ── Footer ── */}
      <footer className="text-center py-5 mt-10 border-t border-dj-border">
        <p className="text-[11px] text-dj-text-muted tracking-wider">
          Djibril AI v2.0 · Precision before profit · Powered by Claude Opus
        </p>
        <p className="text-[10px] text-dj-text-muted/50 mt-1">
          ExMachina Trading Systems · github.com/e49nana
        </p>
      </footer>

      {/* ── DJIBRIL Chat ── */}
      <DjibrilChat isOpen={chatOpen} onClose={() => setChatOpen(false)} agentBrief={agentBrief} />
    </div>
  );
}
