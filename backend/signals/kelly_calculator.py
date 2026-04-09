"""
Djibril AI — Kelly Criterion Calculator

Implements the Half-Kelly position sizing strategy adapted for oil futures.
Calculates optimal lot size based on win rate, win/loss ratio, account balance,
and risk limits.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

try:
    from ..utils.config import get_settings
    from ..utils.logger import get_logger, timed
except ImportError:
    from utils.config import get_settings
    from utils.logger import get_logger, timed

logger = get_logger(__name__)


@dataclass
class PositionSize:
    """Result of a Kelly position sizing calculation."""

    kelly_fraction: float      # Full Kelly fraction
    half_kelly: float          # Half-Kelly (used for trading)
    risk_amount_usd: float     # Dollar amount risked
    lot_size: float            # Lot size for the broker
    lot_type: str              # "standard", "mini", or "micro"
    contracts: int             # Number of contracts (for futures)
    risk_percent: float        # Actual risk as % of account
    capped: bool               # Whether max_risk cap was applied


class KellyCalculator:
    """Half-Kelly position sizing calculator for WTI/Brent trading.

    Uses the Kelly Criterion formula with a 50% reduction (Half-Kelly)
    for safety, capped by max_risk_per_trade.
    """

    # Lot value constants for WTI crude oil
    # 1 standard lot = 1000 barrels, pip value depends on broker
    _STANDARD_LOT_BARRELS = 1000
    _MINI_LOT_BARRELS = 100
    _MICRO_LOT_BARRELS = 10

    # Typical pip value (point value) for WTI
    # 1 point = $0.01 per barrel, so:
    # Standard: $0.01 × 1000 = $10 per point
    # Mini: $0.01 × 100 = $1 per point
    # Micro: $0.01 × 10 = $0.10 per point
    _PIP_VALUE_STANDARD = 10.0
    _PIP_VALUE_MINI = 1.0
    _PIP_VALUE_MICRO = 0.10

    def __init__(self) -> None:
        self._settings = get_settings()

    @timed
    def calculate(
        self,
        sl_pips: float,
        confidence: float = 1.0,
        win_rate: Optional[float] = None,
        avg_wl_ratio: Optional[float] = None,
        account_balance: Optional[float] = None,
        max_risk: Optional[float] = None,
    ) -> PositionSize:
        """Calculate position size using Half-Kelly criterion.

        Args:
            sl_pips: Stop loss distance in pips/points.
            confidence: Signal confidence [0, 1] — scales the Kelly fraction.
            win_rate: Historical win rate [0, 1]. Default from config.
            avg_wl_ratio: Average win/loss ratio. Default from config.
            account_balance: Account balance in USD. Default from config.
            max_risk: Maximum risk per trade as fraction [0, 1]. Default from config.

        Returns:
            PositionSize with all calculated fields.
        """
        cfg = self._settings.trading
        wr = win_rate if win_rate is not None else cfg.default_win_rate
        wl = avg_wl_ratio if avg_wl_ratio is not None else cfg.avg_win_loss_ratio
        balance = account_balance if account_balance is not None else cfg.account_balance
        max_r = max_risk if max_risk is not None else cfg.max_risk_per_trade

        if sl_pips <= 0:
            logger.warning("kelly_invalid_sl", sl_pips=sl_pips)
            return self._zero_position()

        if not (0 < wr < 1):
            logger.warning("kelly_invalid_win_rate", win_rate=wr)
            return self._zero_position()

        # ── Kelly Criterion formula ──
        # K = W - (1-W)/R
        # W = win rate, R = avg win/loss ratio
        kelly_full = wr - (1.0 - wr) / wl

        if kelly_full <= 0:
            logger.info("kelly_negative", kelly=kelly_full, win_rate=wr, wl_ratio=wl)
            return self._zero_position()

        # Half-Kelly for safety, scaled by confidence
        kelly_half = (kelly_full / 2.0) * confidence

        # Risk amount in USD
        risk_amount = balance * kelly_half

        # Cap at max risk per trade
        max_risk_amount = balance * max_r
        capped = risk_amount > max_risk_amount
        if capped:
            risk_amount = max_risk_amount
            kelly_half = max_r

        # ── Lot size calculation ──
        lot_size, lot_type, contracts = self._calculate_lots(
            risk_amount, sl_pips
        )

        # Actual risk percent
        risk_percent = risk_amount / balance if balance > 0 else 0.0

        result = PositionSize(
            kelly_fraction=round(kelly_full, 6),
            half_kelly=round(kelly_half, 6),
            risk_amount_usd=round(risk_amount, 2),
            lot_size=lot_size,
            lot_type=lot_type,
            contracts=contracts,
            risk_percent=round(risk_percent, 4),
            capped=capped,
        )

        logger.info(
            "kelly_calculated",
            kelly_full=kelly_full,
            half_kelly=kelly_half,
            risk_usd=risk_amount,
            lots=lot_size,
            lot_type=lot_type,
            capped=capped,
        )
        return result

    def _calculate_lots(
        self,
        risk_amount_usd: float,
        sl_pips: float,
    ) -> tuple[float, str, int]:
        """Convert USD risk into lot size based on SL distance.

        Tries standard lots first, then mini, then micro.
        Returns the largest lot type that fits within the risk budget.

        Args:
            risk_amount_usd: Total risk in USD.
            sl_pips: Stop loss in pips/points.

        Returns:
            Tuple of (lot_size, lot_type, contracts).
        """
        if sl_pips <= 0:
            return 0.0, "micro", 0

        # Risk per lot = SL_pips × pip_value_per_lot
        risk_per_standard = sl_pips * self._PIP_VALUE_STANDARD
        risk_per_mini = sl_pips * self._PIP_VALUE_MINI
        risk_per_micro = sl_pips * self._PIP_VALUE_MICRO

        # Try standard lots first
        if risk_per_standard > 0 and risk_amount_usd >= risk_per_standard:
            lots = risk_amount_usd / risk_per_standard
            if lots >= 0.01:
                contracts = max(1, int(lots))
                return round(lots, 2), "standard", contracts

        # Try mini lots
        if risk_per_mini > 0 and risk_amount_usd >= risk_per_mini:
            lots = risk_amount_usd / risk_per_mini
            if lots >= 0.01:
                contracts = max(1, int(lots))
                return round(lots, 2), "mini", contracts

        # Micro lots
        if risk_per_micro > 0 and risk_amount_usd >= risk_per_micro:
            lots = risk_amount_usd / risk_per_micro
            contracts = max(1, int(lots))
            return round(max(0.01, lots), 2), "micro", contracts

        return 0.01, "micro", 1

    @staticmethod
    def _zero_position() -> PositionSize:
        """Return a zero-risk position (no trade)."""
        return PositionSize(
            kelly_fraction=0.0,
            half_kelly=0.0,
            risk_amount_usd=0.0,
            lot_size=0.0,
            lot_type="micro",
            contracts=0,
            risk_percent=0.0,
            capped=False,
        )
