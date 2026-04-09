// Djibril AI — TypeScript Type Definitions
// Mirrors all Pydantic models from the Python backend.

export type Urgency = "low" | "medium" | "high" | "critical";
export type TradeAction = "BUY" | "SELL" | "FLAT";
export type NewsCategory = "military" | "sanctions" | "diplomatic" | "infrastructure" | "energy" | "conflict" | "market" | "other";
export type WSMessageType = "signal" | "geo_score" | "news" | "heartbeat" | "error" | "agent_brief";

export interface NewsItem {
  title: string;
  description: string;
  url: string;
  source_name: string;
  source_type: string;
  category: NewsCategory;
  published_at: string;
  fetched_at: string;
  keywords_matched: string[];
  relevance_score: number;
  title_hash: string;
}

export interface GeoScore {
  score: number;
  urgency: Urgency;
  reasoning: string;
  key_events: string[];
  oil_impact: string;
  scored_at: string;
  headlines_analyzed: number;
  model_used: string;
}

export interface TechnicalScore {
  score: number;
  rsi_14: number;
  atr_14: number;
  ema_20: number;
  ema_50: number;
  supertrend_direction: string;
  volume_ratio: number;
  current_price: number;
  symbol: string;
  timeframe: string;
  computed_at: string;
}

export interface SentimentScore {
  score: number;
  twitter_sentiment: number;
  google_trends_score: number;
  stocktwits_sentiment: number;
  sample_size: number;
  computed_at: string;
}

export interface TradeSignal {
  signal_id: string;
  action: TradeAction;
  symbol: string;
  confidence: number;
  entry_price: number;
  stop_loss: number;
  take_profit: number;
  lot_size: number;
  kelly_fraction: number;
  sl_pips: number;
  tp_pips: number;
  risk_reward_ratio: number;
  max_spread_allowed: number;
  reasoning: string;
  geo_score: number;
  technical_score_value: number;
  sentiment_score_value: number;
  urgency: Urgency;
  risk_flags: string[];
  created_at: string;
  expires_at: string | null;
  source: string;
  version: string;
}

export interface WSMessage {
  type: WSMessageType;
  payload: Record<string, unknown>;
  timestamp: string;
}

export interface HealthResponse {
  status: string;
  timestamp: string;
  version: string;
  components: Record<string, string | number>;
}

export interface GeoScoreResponse {
  score: number;
  urgency: Urgency;
  reasoning: string;
  confidence: number;
  timestamp: string;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  timestamp: string;
}

export interface ChatResponse {
  response: string;
  agent: string;
  timestamp: string;
}
