# 🛢️ Djibril AI Trading System

**AI-powered crude oil trading based on real-time geopolitical analysis.**

Analyzes Iran/Middle East tensions via Claude AI, combines with technical and sentiment signals, and executes WTI/Brent trades automatically through a MetaTrader 5 Expert Advisor.

```
 ┌─────────────┐    ┌──────────────┐    ┌──────────────┐
 │  RSS Feeds   │───▶│              │    │              │
 │  NewsAPI     │    │  AI SCORING  │───▶│   SIGNAL     │
 │  WorldMon.   │───▶│  ENGINE      │    │   COMPOSER   │
 └─────────────┘    │              │    │              │
                    │ Claude Opus  │    └──────┬───────┘
 ┌─────────────┐    │ Sentiment    │           │
 │  yfinance    │───▶│ Technical    │     ┌─────▼──────┐
 │  (WTI data)  │    └──────────────┘     │  PUBLISHER  │
 └─────────────┘                          └──┬─────┬───┘
                                             │     │
                     ┌───────────────────────┘     │
                     ▼                             ▼
              ┌─────────────┐             ┌──────────────┐
              │   MQL5 EA    │             │   React      │
              │  (MT5 Trade) │             │  Dashboard   │
              └─────────────┘             └──────────────┘
```

## ⚡ Quick Start (10 minutes)

### 1. Clone & Install

```bash
git clone https://github.com/e49nana/djibril-ai.git
cd djibril-ai

# Backend
cd backend
pip install -r requirements.txt

# Copy and edit environment
cp ../.env.example ../.env
# Edit .env with your ANTHROPIC_API_KEY (required)
```

### 2. Run Backend

```bash
cd backend
uvicorn api.api_server:app --reload --host 0.0.0.0 --port 8000
```

### 3. Run Dashboard

```bash
cd frontend
npm install
npm run dev
# Open http://localhost:5173
```

### 4. Setup MT5 EA

1. Copy `mql5/DjibrilAI_EA.mq5` and `mql5/Include/` to your MT5 `MQL5/Experts/` folder
2. Copy `mql5/signals/` path to MT5's `MQL5/Files/signals/`
3. Compile in MetaEditor
4. Attach to XTIUSD (or your broker's WTI symbol) chart

### 5. Test

```bash
cd backend
python -m pytest tests/ -v  # Should pass 98 tests
```

## 🏗️ Architecture

### Layer 1 — Signal Collectors
| Module | Source | Purpose |
|--------|--------|---------|
| `rss_aggregator.py` | Al Jazeera, Reuters, BBC, France24, AP, TASS | Async RSS with dedup + keyword filter |
| `worldmonitor_client.py` | WorldMonitor.app | Geopolitical event extraction |
| `news_fetcher.py` | NewsAPI.org | Iran/oil focused headlines with retry + cache |

### Layer 2 — AI Scoring Engine
| Module | Purpose |
|--------|---------|
| `claude_scorer.py` | Claude claude-opus-4-6 geopolitical scoring (-10 to +10) with adaptive thinking |
| `sentiment_analyzer.py` | Twitter + StockTwits + Google Trends sentiment |
| `technical_analyzer.py` | RSI, ATR, EMA, SuperTrend, Volume ratio |
| `geo_risk_engine.py` | Weighted composite (40% geo + 40% tech + 20% sentiment) with VIX adjustment |

### Layer 3 — Signal Pipeline
| Module | Purpose |
|--------|---------|
| `kelly_calculator.py` | Half-Kelly position sizing with risk caps |
| `signal_composer.py` | SL/TP from ATR, R:R validation, session filter |
| `signal_publisher.py` | JSON file output + SQLite history + WebSocket queue |
| `alerts.py` | Telegram + Discord notifications with cooldown |

### Layer 4 — Execution & Visualization
| Component | Purpose |
|-----------|---------|
| `DjibrilAI_EA.mq5` | MetaTrader 5 EA with trailing stop, breakeven, partial close |
| `React Dashboard` | Real-time OSINT visualization with WebSocket |

## 🔧 Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | ✅ | Claude API key |
| `NEWSAPI_KEY` | Recommended | NewsAPI.org key |
| `TELEGRAM_BOT_TOKEN` | Optional | Telegram alert bot |
| `TELEGRAM_CHAT_ID` | Optional | Telegram chat ID |
| `DISCORD_WEBHOOK_URL` | Optional | Discord webhook |
| `API_KEY` | Optional | FastAPI auth key |
| `ACCOUNT_BALANCE` | Optional | Default: 10000 |
| `MAX_RISK_PER_TRADE` | Optional | Default: 0.05 (5%) |

See `.env.example` for the full list.

## 🐳 Docker Deployment

```bash
docker-compose up -d
```

Services: `backend` (FastAPI), `redis` (cache), `nginx` (reverse proxy).

## 📡 API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | System health check |
| GET | `/api/signal/latest` | Latest trade signal |
| GET | `/api/signal/history?limit=50` | Signal history |
| GET | `/api/geo-score` | Current geo risk score |
| GET | `/api/news?category=military&limit=20` | Filtered news |
| POST | `/api/force-scan` | Trigger immediate scan |
| WS | `/ws` | Real-time WebSocket feed |

## 🖥️ VPS Deployment (Ubuntu 22.04)

```bash
# Install dependencies
sudo apt update && sudo apt install -y python3.11 python3-pip nginx certbot

# Clone and setup
git clone https://github.com/e49nana/djibril-ai.git /opt/djibril-ai
cd /opt/djibril-ai/backend
pip install -r requirements.txt

# Create systemd service
sudo tee /etc/systemd/system/djibril.service << EOF
[Unit]
Description=Djibril AI Trading System
After=network.target

[Service]
User=www-data
WorkingDirectory=/opt/djibril-ai/backend
ExecStart=/usr/bin/uvicorn api.api_server:app --host 0.0.0.0 --port 8000
Restart=always
EnvironmentFile=/opt/djibril-ai/.env

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl enable --now djibril
```

## 📊 Test Results

```
98 tests passed across 10 test files:
  test_models.py       — 12 tests (config, Pydantic models)
  test_logger.py       —  6 tests (structured logging, @timed)
  test_rss.py          —  7 tests (RSS dedup, filtering, SQLite)
  test_worldmonitor.py —  7 tests (event parsing, relevance)
  test_news_fetcher.py —  6 tests (cache, dedup, queue)
  test_claude_scorer.py—  9 tests (prompt, parse, fallback)
  test_sentiment.py    —  6 tests (keyword scoring, bounds)
  test_technical.py    — 11 tests (RSI, ATR, EMA, SuperTrend)
  test_risk_engine.py  — 11 tests (composite, VIX, conflicts)
  test_kelly.py        —  7 tests (sizing, caps, lot types)
  test_composer.py     —  9 tests (SL/TP, filters, session)
  test_integration.py  —  7 tests (full pipeline, e2e)
```

## ⚠️ Disclaimer

This system is for educational and research purposes. Trading crude oil futures carries significant risk. Past performance does not guarantee future results. Always use proper risk management and never risk more than you can afford to lose.

---

**Built by [AlgoSphere Quant](https://algosphere-quant.com) · Precision before profit.**
