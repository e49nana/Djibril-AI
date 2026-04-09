// Djibril AI — Signal History Hook
// Fetches and caches signal history from the REST API.

import { useCallback, useEffect, useState } from "react";
import type { TradeSignal, GeoScoreResponse, NewsItem } from "../types";

const API_BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
const API_KEY = import.meta.env.VITE_API_KEY ?? "";

async function apiFetch<T>(path: string): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (API_KEY) headers["X-API-Key"] = API_KEY;

  const res = await fetch(`${API_BASE}${path}`, { headers });
  if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`);
  return res.json() as Promise<T>;
}

export function useSignalHistory(limit: number = 50) {
  const [signals, setSignals] = useState<TradeSignal[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setLoading(true);
      const data = await apiFetch<TradeSignal[]>(`/api/signal/history?limit=${limit}`);
      setSignals(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }, [limit]);

  useEffect(() => { void refresh(); }, [refresh]);

  return { signals, loading, error, refresh };
}

export function useLatestSignal() {
  const [signal, setSignal] = useState<TradeSignal | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const data = await apiFetch<TradeSignal>("/api/signal/latest");
      setSignal(data);
    } catch {
      setSignal(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  return { signal, loading, refresh, setSignal };
}

export function useGeoScore() {
  const [score, setScore] = useState<GeoScoreResponse | null>(null);

  const refresh = useCallback(async () => {
    try {
      const data = await apiFetch<GeoScoreResponse>("/api/geo-score");
      setScore(data);
    } catch {
      setScore(null);
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  return { score, refresh, setScore };
}

export function useNews(
  category?: string,
  limit: number = 20,
  wsItems?: NewsItem[],
) {
  const [restItems, setRestItems] = useState<NewsItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [lastWsAt, setLastWsAt] = useState<number>(0);

  const refresh = useCallback(async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams({ limit: String(limit) });
      if (category) params.set("category", category);
      const data = await apiFetch<NewsItem[]>(`/api/news?${params}`);
      setRestItems(data);
    } catch {
      setRestItems([]);
    } finally {
      setLoading(false);
    }
  }, [category, limit]);

  useEffect(() => { void refresh(); }, [refresh]);

  // Track last WS item arrival
  useEffect(() => {
    if (wsItems && wsItems.length > 0) {
      setLastWsAt(Date.now());
    }
  }, [wsItems]);

  // Merge WS items (priority) + REST items with dedup by title
  const items: NewsItem[] = (() => {
    const ws = wsItems ?? [];
    const merged = [...ws, ...restItems];
    const seen = new Set<string>();
    return merged
      .filter((item) => {
        if (seen.has(item.title)) return false;
        seen.add(item.title);
        return true;
      })
      .slice(0, limit);
  })();

  const sourceMode: "live" | "polling" =
    Date.now() - lastWsAt < 60_000 ? "live" : "polling";

  return { items, loading, refresh, sourceMode };
}
