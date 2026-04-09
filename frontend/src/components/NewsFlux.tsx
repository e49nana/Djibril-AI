import { useState } from "react";
import type { NewsItem, NewsCategory } from "../types";

const CATEGORY_BADGE: Record<string, { bg: string; text: string }> = {
  military: { bg: "bg-dj-red/20", text: "text-dj-red" },
  conflict: { bg: "bg-orange-500/20", text: "text-orange-400" },
  sanctions: { bg: "bg-dj-amber/20", text: "text-dj-amber" },
  diplomatic: { bg: "bg-dj-blue/20", text: "text-dj-blue" },
  energy: { bg: "bg-dj-accent/20", text: "text-dj-accent" },
  infrastructure: { bg: "bg-purple-500/20", text: "text-purple-400" },
  market: { bg: "bg-dj-text-muted/20", text: "text-dj-text-muted" },
  other: { bg: "bg-dj-border", text: "text-dj-text-muted" },
};

const DANGER_WORDS = ["iran", "strike", "ormuz", "hormuz", "blockade", "sanctions", "missile", "attack", "nuclear", "escalat"];

function relativeTime(isoDate: string): string {
  const diff = Date.now() - new Date(isoDate).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "à l'instant";
  if (mins < 60) return `il y a ${mins} min`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `il y a ${hrs}h`;
  return `il y a ${Math.floor(hrs / 24)}j`;
}

function highlightDanger(text: string): React.ReactNode {
  const regex = new RegExp(`(${DANGER_WORDS.join("|")})`, "gi");
  const parts = text.split(regex);
  return parts.map((part, i) =>
    DANGER_WORDS.some((w) => part.toLowerCase().includes(w)) ? (
      <span key={i} className="text-dj-accent font-semibold">{part}</span>
    ) : (
      <span key={i}>{part}</span>
    )
  );
}

interface NewsFluxProps {
  news: NewsItem[];
  wsItems?: NewsItem[];
  sourceMode?: "live" | "polling";
  onCategoryFilter: (cat: string | null) => void;
}

export default function NewsFlux({ news, wsItems, sourceMode, onCategoryFilter }: NewsFluxProps) {
  const [activeFilter, setActiveFilter] = useState<string | null>(null);

  // Track WS item titles for flash animation
  const wsTitles = new Set((wsItems ?? []).map((i) => i.title));

  // Merge wsItems (priority) + news with dedup
  const merged = (() => {
    const ws = wsItems ?? [];
    const all = [...ws, ...news];
    const seen = new Set<string>();
    return all.filter((item) => {
      if (seen.has(item.title)) return false;
      seen.add(item.title);
      return true;
    });
  })();

  const categories = [...new Set(merged.map((n) => n.category))];
  const filtered = activeFilter ? merged.filter((n) => n.category === activeFilter) : merged;

  const handleFilter = (cat: string | null) => {
    setActiveFilter(cat);
    onCategoryFilter(cat);
  };

  return (
    <div className="bg-dj-surface border border-dj-border rounded-lg overflow-hidden flex flex-col">
      <div className="flex items-center justify-between px-4 py-3 border-b border-dj-border bg-dj-bg/50">
        <span className="text-[11px] font-bold tracking-[2px] text-dj-text-muted">NEWS FLUX</span>
        {sourceMode === "live" ? (
          <span className="text-[10px] font-bold text-dj-green flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-dj-green animate-pulse-slow" />
            LIVE
          </span>
        ) : (
          <span className="text-[10px] font-bold text-dj-text-muted tracking-wider">↻ POLLING</span>
        )}
      </div>

      {/* Filter chips */}
      <div className="flex flex-wrap gap-1.5 px-4 py-2 border-b border-dj-border">
        <FilterChip label="ALL" active={activeFilter === null} onClick={() => handleFilter(null)} />
        {categories.map((cat) => {
          const badge = CATEGORY_BADGE[cat] ?? CATEGORY_BADGE.other;
          return (
            <FilterChip
              key={cat}
              label={cat.toUpperCase()}
              active={activeFilter === cat}
              activeClass={`${badge.bg} ${badge.text} border-transparent`}
              onClick={() => handleFilter(activeFilter === cat ? null : cat)}
            />
          );
        })}
      </div>

      {/* News list */}
      <div className="overflow-y-auto max-h-[420px] px-4 pb-3">
        {filtered.length === 0 ? (
          <div className="text-dj-text-muted text-sm text-center py-10">Aucune actualité disponible</div>
        ) : (
          filtered.map((item, idx) => {
            const badge = CATEGORY_BADGE[item.category] ?? CATEGORY_BADGE.other;
            const isDangerous = DANGER_WORDS.some((w) => item.title.toLowerCase().includes(w));
            const isWsItem = wsTitles.has(item.title);

            return (
              <div key={`${item.title_hash}-${idx}`} className={`py-2.5 border-b border-dj-border last:border-b-0 flex gap-2.5 ${isWsItem ? "news-item-new" : ""}`}>
                <span className={`${badge.bg} ${badge.text} text-[9px] font-bold px-1.5 py-0.5 rounded h-fit mt-0.5 whitespace-nowrap`}>
                  {item.category.toUpperCase()}
                </span>
                <div className="flex-1 min-w-0">
                  <p className={`text-[13px] leading-snug ${isDangerous ? "font-semibold" : ""}`}>
                    {isDangerous && <span className="text-dj-accent mr-1">⚠</span>}
                    {highlightDanger(item.title)}
                  </p>
                  <p className="text-[11px] text-dj-text-muted mt-0.5">
                    {item.source_name} · {relativeTime(item.published_at)}
                  </p>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

function FilterChip({
  label,
  active,
  activeClass,
  onClick,
}: {
  label: string;
  active: boolean;
  activeClass?: string;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`text-[10px] font-semibold tracking-wide px-2.5 py-1 rounded border transition-all cursor-pointer ${
        active
          ? activeClass ?? "bg-dj-accent/20 text-dj-accent border-dj-accent/30"
          : "bg-transparent text-dj-text-muted border-dj-border hover:border-dj-border-active"
      }`}
    >
      {label}
    </button>
  );
}
