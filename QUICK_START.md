# ⚡ Djibril AI — Quick Start Guide

Get the system running locally in under 10 minutes.

## Prerequisites

- Python 3.11+ 
- Node.js 18+ (for dashboard)
- MetaTrader 5 (for live trading — optional for testing)
- An Anthropic API key (get one at https://console.anthropic.com)

## Step 1: Environment Setup (2 min)

```bash
cd djibril-ai
cp .env.example .env
```

Edit `.env` and set at minimum:
```
ANTHROPIC_API_KEY=sk-ant-your-key-here
```

Optional but recommended:
```
NEWSAPI_KEY=your-newsapi-key          # Free at newsapi.org
TELEGRAM_BOT_TOKEN=your-bot-token     # For trade alerts
TELEGRAM_CHAT_ID=your-chat-id
```

## Step 2: Install Backend (2 min)

```bash
cd backend
pip install -r requirements.txt
```

## Step 3: Run Tests (1 min)

```bash
python -m pytest tests/ -v
# Expected: 98 passed
```

## Step 4: Start the API Server (1 min)

```bash
uvicorn api.api_server:app --reload --host 0.0.0.0 --port 8000
```

Verify: open http://localhost:8000/health — you should see:
```json
{"status": "ok", "version": "1.0.0", ...}
```

## Step 5: Start the Dashboard (2 min)

In a new terminal:
```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 — the Djibril AI dashboard should load.

## Step 6: Run the Full Pipeline (2 min)

In a new terminal:
```bash
cd backend
python main_loop.py
```

This starts:
- News scanning every 2 minutes
- AI scoring every 5 minutes  
- Signal checks every 30 seconds

## Step 7: MT5 Setup (Optional)

1. Copy these files to your MetaTrader 5 installation:
   ```
   mql5/DjibrilAI_EA.mq5        → MQL5/Experts/DjibrilAI_EA.mq5
   mql5/Include/SignalBridge.mqh → MQL5/Experts/Include/SignalBridge.mqh
   mql5/Include/RiskManager.mqh → MQL5/Experts/Include/RiskManager.mqh
   ```

2. Open MetaEditor → File → Open → `DjibrilAI_EA.mq5` → Compile (F7)

3. In MT5, open a XTIUSD (WTI) chart → Attach the EA

4. Configure the `Signal Dir` input to point to wherever the Python backend
   writes `latest_signal.json` (default: `MQL5/Files/signals/`)

## API Quick Reference

```bash
# Latest signal
curl http://localhost:8000/api/signal/latest

# Signal history
curl http://localhost:8000/api/signal/history?limit=10

# Current geo score
curl http://localhost:8000/api/geo-score

# News (filtered)
curl http://localhost:8000/api/news?category=military&limit=20

# Force immediate scan
curl -X POST http://localhost:8000/api/force-scan

# Health check
curl http://localhost:8000/health
```

## Troubleshooting

**"ANTHROPIC_API_KEY not set"**  
→ Make sure `.env` is in the project root and contains your key.

**"No signals available" on /api/signal/latest**  
→ Run `main_loop.py` first — it needs at least one scoring cycle.

**Dashboard shows "DISCONNECTED"**  
→ The WebSocket endpoint `/ws` needs the backend running on port 8000.

**MT5 EA says "Signal file not found"**  
→ Check the `Signal Dir` input matches the `SIGNAL_OUTPUT_DIR` in `.env`.
   Default is `signals/` relative to MT5's `MQL5/Files/` directory.

---

**Need help?** Open an issue or contact @e49nana on GitHub.
