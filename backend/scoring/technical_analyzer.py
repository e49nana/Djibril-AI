"""
Djibril AI — Technical Analyzer

Fetches WTI OHLCV data via yfinance (fallback: Alpha Vantage) and computes:
RSI(14), ATR(14), EMA(20/50), SuperTrend, Volume ratio.
Produces a normalized technical_score between -1.0 and +1.0.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import numpy as np

try:
    from ..utils.config import get_settings
    from ..utils.logger import get_logger, timed
    from ..utils.models import TechnicalScore
except ImportError:
    from utils.config import get_settings
    from utils.logger import get_logger, timed
    from utils.models import TechnicalScore

logger = get_logger(__name__)

# Default WTI futures symbol
_WTI_SYMBOL = "CL=F"
_BRENT_SYMBOL = "BZ=F"


class TechnicalAnalyzer:
    """WTI crude oil technical analysis engine.

    Fetches price data and computes key indicators to produce
    a normalized technical score for the signal pipeline.
    """

    def __init__(self, symbol: str = _WTI_SYMBOL) -> None:
        self._settings = get_settings()
        self._symbol = symbol

    @timed
    def analyze(self) -> TechnicalScore:
        """Fetch data and compute all technical indicators.

        Returns:
            TechnicalScore with all indicators populated.
        """
        df = self._fetch_data()
        if df is None or len(df) < 60:
            logger.warning("technical_insufficient_data", symbol=self._symbol)
            return TechnicalScore(symbol=self._symbol)

        try:
            close = df["Close"].values.astype(float)
            high = df["High"].values.astype(float)
            low = df["Low"].values.astype(float)
            volume = df["Volume"].values.astype(float)

            rsi = self._compute_rsi(close, period=14)
            atr = self._compute_atr(high, low, close, period=14)
            ema_20 = self._compute_ema(close, period=20)
            ema_50 = self._compute_ema(close, period=50)
            st_dir = self._compute_supertrend(high, low, close, atr, period=10, multiplier=3.0)
            vol_ratio = self._compute_volume_ratio(volume, period=20)
            current_price = float(close[-1])

            # Compute composite technical score
            score = self._compute_score(
                rsi=rsi,
                ema_20=ema_20,
                ema_50=ema_50,
                supertrend_dir=st_dir,
                vol_ratio=vol_ratio,
                current_price=current_price,
            )

            result = TechnicalScore(
                score=round(score, 4),
                rsi_14=round(rsi, 2),
                atr_14=round(atr, 4),
                ema_20=round(ema_20, 4),
                ema_50=round(ema_50, 4),
                supertrend_direction=st_dir,
                volume_ratio=round(vol_ratio, 2),
                current_price=round(current_price, 4),
                symbol=self._symbol,
                timeframe="4H",
                computed_at=datetime.now(timezone.utc),
            )

            logger.info(
                "technical_analysis_complete",
                symbol=self._symbol,
                price=current_price,
                score=score,
                rsi=rsi,
                atr=atr,
            )
            return result

        except Exception as exc:
            logger.error("technical_analysis_error", error=str(exc))
            return TechnicalScore(symbol=self._symbol)

    def _fetch_data(self) -> Optional[object]:
        """Fetch OHLCV data from yfinance, fallback to Alpha Vantage.

        Returns:
            pandas DataFrame with OHLCV columns or None on failure.
        """
        # Try yfinance
        try:
            import yfinance as yf
            ticker = yf.Ticker(self._symbol)
            df = ticker.history(period="3mo", interval="1d")
            if df is not None and len(df) >= 20:
                logger.debug("technical_yfinance_ok", rows=len(df))
                return df
        except Exception as exc:
            logger.warning("technical_yfinance_failed", error=str(exc))

        # Fallback: Alpha Vantage
        try:
            return self._fetch_alphavantage()
        except Exception as exc:
            logger.warning("technical_alphavantage_failed", error=str(exc))

        return None

    def _fetch_alphavantage(self) -> Optional[object]:
        """Fetch daily OHLCV from Alpha Vantage API.

        Returns:
            pandas-like DataFrame or None.
        """
        import requests
        api_key = os.environ.get("ALPHAVANTAGE_API_KEY", "")
        if not api_key:
            return None

        url = "https://www.alphavantage.co/query"
        params = {
            "function": "TIME_SERIES_DAILY",
            "symbol": "CL",
            "apikey": api_key,
            "outputsize": "compact",
        }
        resp = requests.get(url, params=params, timeout=15)
        if resp.status_code != 200:
            return None

        data = resp.json()
        ts = data.get("Time Series (Daily)", {})
        if not ts:
            return None

        import pandas as pd
        records = []
        for date_str, values in sorted(ts.items()):
            records.append({
                "Date": date_str,
                "Open": float(values["1. open"]),
                "High": float(values["2. high"]),
                "Low": float(values["3. low"]),
                "Close": float(values["4. close"]),
                "Volume": float(values["5. volume"]),
            })

        df = pd.DataFrame(records)
        df["Date"] = pd.to_datetime(df["Date"])
        df = df.set_index("Date").sort_index()
        return df

    @staticmethod
    def _compute_rsi(close: np.ndarray, period: int = 14) -> float:
        """Compute Relative Strength Index.

        Args:
            close: Array of closing prices.
            period: RSI period.

        Returns:
            Current RSI value (0–100).
        """
        if len(close) < period + 1:
            return 50.0

        deltas = np.diff(close)
        gains = np.where(deltas > 0, deltas, 0.0)
        losses = np.where(deltas < 0, -deltas, 0.0)

        avg_gain = np.mean(gains[:period])
        avg_loss = np.mean(losses[:period])

        for i in range(period, len(gains)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period

        if avg_loss == 0:
            return 100.0

        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))

    @staticmethod
    def _compute_atr(
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray,
        period: int = 14,
    ) -> float:
        """Compute Average True Range.

        Args:
            high: High prices.
            low: Low prices.
            close: Close prices.
            period: ATR period.

        Returns:
            Current ATR value in USD/barrel.
        """
        if len(close) < period + 1:
            return 0.0

        tr_values = []
        for i in range(1, len(close)):
            hl = high[i] - low[i]
            hc = abs(high[i] - close[i - 1])
            lc = abs(low[i] - close[i - 1])
            tr_values.append(max(hl, hc, lc))

        tr = np.array(tr_values)

        # Wilder's smoothing
        atr = np.mean(tr[:period])
        for i in range(period, len(tr)):
            atr = (atr * (period - 1) + tr[i]) / period

        return float(atr)

    @staticmethod
    def _compute_ema(close: np.ndarray, period: int) -> float:
        """Compute Exponential Moving Average.

        Args:
            close: Closing prices.
            period: EMA period.

        Returns:
            Current EMA value.
        """
        if len(close) < period:
            return float(close[-1]) if len(close) > 0 else 0.0

        multiplier = 2.0 / (period + 1)
        ema = float(np.mean(close[:period]))

        for i in range(period, len(close)):
            ema = (close[i] - ema) * multiplier + ema

        return ema

    @staticmethod
    def _compute_supertrend(
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray,
        atr_value: float,
        period: int = 10,
        multiplier: float = 3.0,
    ) -> str:
        """Compute SuperTrend direction.

        Args:
            high: High prices.
            low: Low prices.
            close: Close prices.
            atr_value: Pre-computed ATR.
            period: SuperTrend period.
            multiplier: ATR multiplier for bands.

        Returns:
            "bullish", "bearish", or "neutral".
        """
        if len(close) < period + 1 or atr_value == 0:
            return "neutral"

        # Use last N bars for SuperTrend
        n = min(len(close), 50)
        hl2 = (high[-n:] + low[-n:]) / 2.0

        upper_band = hl2 + multiplier * atr_value
        lower_band = hl2 - multiplier * atr_value

        supertrend = np.zeros(n)
        direction = np.ones(n)  # 1 = bullish, -1 = bearish

        supertrend[0] = upper_band[0]

        for i in range(1, n):
            if close[-n + i] > supertrend[i - 1]:
                supertrend[i] = max(lower_band[i], supertrend[i - 1] if direction[i - 1] == 1 else lower_band[i])
                direction[i] = 1
            else:
                supertrend[i] = min(upper_band[i], supertrend[i - 1] if direction[i - 1] == -1 else upper_band[i])
                direction[i] = -1

        last_dir = direction[-1]
        if last_dir == 1:
            return "bullish"
        elif last_dir == -1:
            return "bearish"
        return "neutral"

    @staticmethod
    def _compute_volume_ratio(volume: np.ndarray, period: int = 20) -> float:
        """Compute volume ratio (current vs N-period average).

        Args:
            volume: Volume array.
            period: Averaging period.

        Returns:
            Ratio (1.0 = average, >1 = above average).
        """
        if len(volume) < period + 1:
            return 1.0

        avg_vol = np.mean(volume[-period - 1:-1])
        if avg_vol == 0:
            return 1.0

        return float(volume[-1] / avg_vol)

    @staticmethod
    def _compute_score(
        rsi: float,
        ema_20: float,
        ema_50: float,
        supertrend_dir: str,
        vol_ratio: float,
        current_price: float,
    ) -> float:
        """Compute composite technical score from indicators.

        Args:
            rsi: RSI(14) value.
            ema_20: EMA(20) value.
            ema_50: EMA(50) value.
            supertrend_dir: SuperTrend direction string.
            vol_ratio: Volume ratio.
            current_price: Latest close price.

        Returns:
            Score between -1.0 (bearish) and +1.0 (bullish).
        """
        signals: list[float] = []
        weights: list[float] = []

        # RSI signal (25% weight)
        if rsi > 70:
            signals.append(-0.5)  # Overbought = bearish signal
        elif rsi > 60:
            signals.append(0.3)
        elif rsi < 30:
            signals.append(0.5)  # Oversold = bullish signal
        elif rsi < 40:
            signals.append(-0.3)
        else:
            signals.append(0.0)
        weights.append(0.25)

        # EMA crossover (30% weight)
        if ema_20 > 0 and ema_50 > 0:
            if current_price > ema_20 > ema_50:
                signals.append(0.8)  # Strong bullish
            elif current_price > ema_20:
                signals.append(0.4)
            elif current_price < ema_20 < ema_50:
                signals.append(-0.8)  # Strong bearish
            elif current_price < ema_20:
                signals.append(-0.4)
            else:
                signals.append(0.0)
        else:
            signals.append(0.0)
        weights.append(0.30)

        # SuperTrend (30% weight)
        if supertrend_dir == "bullish":
            signals.append(0.7)
        elif supertrend_dir == "bearish":
            signals.append(-0.7)
        else:
            signals.append(0.0)
        weights.append(0.30)

        # Volume confirmation (15% weight)
        if vol_ratio > 1.5:
            # High volume confirms the trend
            signals.append(0.3 if signals[-1] > 0 else -0.3)
        elif vol_ratio < 0.5:
            signals.append(0.0)  # Low volume = weak signal
        else:
            signals.append(0.1 if signals[-1] > 0 else -0.1)
        weights.append(0.15)

        total_weight = sum(weights)
        composite = sum(s * w for s, w in zip(signals, weights)) / total_weight
        return max(-1.0, min(1.0, composite))


# Need this import for Alpha Vantage fallback
import os
