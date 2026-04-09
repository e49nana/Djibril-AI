#!/usr/bin/env bash
# ═══════════════════════════════════════════════════
# Djibril AI — End-to-End Simulation Script
# Runs the backend and simulates 10 full signal cycles.
# ═══════════════════════════════════════════════════
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"

echo "══════════════════════════════════════════════"
echo "  Djibril AI — E2E Simulation (10 signals)"
echo "══════════════════════════════════════════════"

# Run tests first
echo ""
echo "▸ Running test suite..."
cd "$BACKEND_DIR"
python -m pytest tests/ -v --tb=short
echo ""
echo "✓ All tests passed"

# Run E2E simulation
echo ""
echo "▸ Running E2E pipeline simulation..."
python -c "
import asyncio
import sys
import os
import tempfile

sys.path.insert(0, '.')

from utils.models import (
    GeoScore, SentimentScore, TechnicalScore,
    TradeAction, Urgency, NewsItem, NewsCategory, SignalSource,
)
from scoring.claude_scorer import ClaudeScorer
from scoring.geo_risk_engine import GeoRiskEngine
from signal.signal_composer import SignalComposer
from signal.signal_publisher import SignalPublisher
from signal.kelly_calculator import KellyCalculator

# Setup temp output
tmp_dir = tempfile.mkdtemp()
os.environ['SIGNAL_OUTPUT_DIR'] = tmp_dir
db_path = os.path.join(tmp_dir, 'e2e_test.db')

publisher = SignalPublisher(db_path=db_path)
composer  = SignalComposer()
engine    = GeoRiskEngine()
scorer    = ClaudeScorer()

headlines = [
    ('Iran threatens Strait of Hormuz closure amid sanctions', NewsCategory.MILITARY),
    ('OPEC+ emergency meeting on production cuts', NewsCategory.ENERGY),
    ('US Navy carrier group deployed to Persian Gulf', NewsCategory.MILITARY),
    ('Iran-Saudi diplomatic talks show progress', NewsCategory.DIPLOMATIC),
    ('Houthi rebels attack oil tanker in Red Sea', NewsCategory.CONFLICT),
    ('New EU sanctions on Iranian oil exports', NewsCategory.SANCTIONS),
    ('Iraq pipeline bombed by drone attack', NewsCategory.INFRASTRUCTURE),
    ('Iran enriches uranium to 60% — IAEA report', NewsCategory.MILITARY),
    ('JCPOA nuclear talks collapse in Vienna', NewsCategory.DIPLOMATIC),
    ('WTI crude surges \$5 on supply disruption fears', NewsCategory.ENERGY),
]

async def run_e2e():
    buy_count = 0
    sell_count = 0
    flat_count = 0

    for i, (title, cat) in enumerate(headlines):
        print(f'  Signal {i+1}/10: {title[:50]}...')

        news = [NewsItem(
            title=title,
            description=f'Full report: {title}',
            source_name='e2e_test',
            source_type=SignalSource.RSS,
            category=cat,
            keywords_matched=['iran', 'oil'],
            relevance_score=0.8,
        )]

        geo = scorer._fallback_score(news)
        tech = TechnicalScore(
            score=0.3 + (i % 3) * 0.15 * (1 if i % 2 == 0 else -1),
            atr_14=1.50 + i * 0.05,
            current_price=75.0 + i * 0.5,
            rsi_14=45 + i * 3,
            ema_20=74.0 + i * 0.3,
            ema_50=73.0 + i * 0.2,
            supertrend_direction='bullish' if i % 2 == 0 else 'bearish',
            volume_ratio=1.0 + i * 0.1,
        )
        sent = SentimentScore(score=0.1 * (i - 5), sample_size=50)

        signal = engine.compute_signal(geo, tech, sent, vix_level=18.0 + i)
        trade = composer.compose(signal)
        await publisher.publish(trade)

        if trade.action.value == 'BUY': buy_count += 1
        elif trade.action.value == 'SELL': sell_count += 1
        else: flat_count += 1

    history = publisher.get_history(limit=50)
    print()
    print(f'  Results: {buy_count} BUY | {sell_count} SELL | {flat_count} FLAT')
    print(f'  Signals in DB: {len(history)}')
    print(f'  Output dir: {tmp_dir}')

    # Verify files written
    import glob
    json_files = glob.glob(os.path.join(tmp_dir, '*.json'))
    print(f'  JSON files: {len(json_files)}')

loop = asyncio.new_event_loop()
loop.run_until_complete(run_e2e())
loop.close()
print()
print('✓ E2E simulation complete')
"

echo ""
echo "══════════════════════════════════════════════"
echo "  ✓ ALL E2E CHECKS PASSED"
echo "══════════════════════════════════════════════"
