# 🛢️ Djibril AI Trading System

[![CI](https://github.com/e49nana/Djibril-AI/actions/workflows/ci.yml/badge.svg)](https://github.com/e49nana/Djibril-AI/actions/workflows/ci.yml)


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

### 1. Clone & install

```bash
git clone https://github.com/e49nana/Djibril-AI.git
cd Djibril-AI
cp .env.example .env          # set ANTHROPIC_API_KEY (required)

cd backend
pip install -r requirements.txt
```

### 2. Run the backend (from `backend/`)

```bash
uvicorn api.api_server:app --reload --host 0.0.0.0 --port 8000
```

### 3. Run the dashboard (second terminal, from the repository root)

```bash
cd frontend
npm ci
npm run dev                   # http://localhost:5173
```

### 4. Set up the MT5 EA

1. Copy `mql5/DjibrilAI_EA.mq5` and `mql5/Include/` into your MT5 `MQL5/Experts/` folder.
2. In `.env`, set `SIGNAL_OUTPUT_DIR` to the terminal's `MQL5/Files/signals` folder (or `Common/Files/signals`): the EA reads `signals/latest_signal.json` there.
3. Compile in MetaEditor.
4. Attach the EA to an XTIUSD chart (or your broker's WTI symbol).

### 5. Run the tests (from `backend/`)

```bash
pip install -r requirements-dev.txt
pytest -q
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

## 📊 Tests

```
$ cd backend && pytest -q
106 passed in ~1 s
```

No network access and no API key needed: external APIs are mocked and every run writes to a temporary directory. CI runs the suite on Python 3.12 and 3.13 and builds the dashboard on every push and pull request.

| File | Tests | Covers |
|---|---:|---|
| `test_api.py` | 7 | REST endpoints, API-key auth |
| `test_models.py` | 13 | config, Pydantic models, signal JSON format |
| `test_logger.py` | 6 | structured logging, `@timed` |
| `test_rss.py` | 7 | RSS dedup, filtering, SQLite |
| `test_worldmonitor.py` | 7 | event parsing, relevance |
| `test_news_fetcher.py` | 6 | cache, dedup, queue |
| `test_claude_scorer.py` | 9 | prompt, parsing, fallback |
| `test_sentiment.py` | 6 | keyword scoring, bounds |
| `test_technical.py` | 11 | RSI, ATR, EMA, SuperTrend |
| `test_risk_engine.py` | 11 | composite score, VIX, conflicts |
| `test_kelly.py` | 7 | sizing, caps, lot types |
| `test_composer.py` | 9 | SL/TP, filters, session |
| `test_integration.py` | 7 | full pipeline, end to end |

## ⚠️ Disclaimer

This system is for educational and research purposes. Trading crude oil futures carries significant risk. Past performance does not guarantee future results. Always use proper risk management and never risk more than you can afford to lose.

---

**Built by [AlgoSphere Quant](https://algosphere-quant.com) · Precision before profit.**
