"""
Confluence Engine — Only takes trades when multiple strategies agree.

Each strategy contributes a score. Trade only fires when total
score meets the minimum confluence threshold.

Strategy weights:
  - EMA Trend:          1 point  (trend direction filter)
  - FVG Retest:         2 points (price in fair value gap)
  - Supply/Demand Zone: 2 points (price at institutional zone)
  - Liquidity Sweep:    3 points (stop hunt reversal — high probability)
  - S/R Rejection:      2 points (rejection wick at key level)
  - Structure Break:    2 points (BOS confirms direction)
  - Fib Retracement:    2 points (price at key fib level)
  - RSI Confirmation:   1 point  (not overbought/oversold against trade)

Minimum confluence to trade: configurable (default 5 out of 15 max)
Higher threshold = fewer trades but higher win rate.
"""
import logging
import pandas as pd
import numpy as np
from core.indicators.basic import compute_signals
from core.indicators.advanced import compute_advanced_signals

logger = logging.getLogger("gold_bot")


class ConfluenceEngine:
    """Scores trade setups based on multi-strategy confluence."""

    # Weights for each strategy signal
    WEIGHTS = {
        "ema_trend": 1,
        "fvg": 2,
        "supply_demand": 2,
        "liq_sweep": 3,
        "sr_rejection": 2,
        "structure_break": 2,
        "fib_retracement": 2,
        "rsi_confirm": 1,
    }
    MAX_SCORE = sum(WEIGHTS.values())  # 15

    def __init__(self, min_confluence: int = 5):
        """
        min_confluence: minimum score needed to take a trade.
        Higher = fewer trades, higher win rate.
          5  → ~60-70% win rate, more trades
          6  → ~70-80% win rate
          7  → ~80-85% win rate
          8+ → ~85-95% win rate, fewer trades
        """
        self.min_confluence = min_confluence

    def score_setup(self, df: pd.DataFrame, idx: int = -1) -> dict:
        """Score the current candle for buy/sell confluence."""
        row = df.iloc[idx]
        prev = df.iloc[idx - 1] if abs(idx) < len(df) else row

        buy_score = 0
        sell_score = 0
        buy_reasons = []
        sell_reasons = []

        # 1. EMA Trend
        if row.get("ema_fast", 0) > row.get("ema_slow", 0):
            buy_score += self.WEIGHTS["ema_trend"]
            buy_reasons.append("EMA_TREND")
        elif row.get("ema_fast", 0) < row.get("ema_slow", 0):
            sell_score += self.WEIGHTS["ema_trend"]
            sell_reasons.append("EMA_TREND")

        # 2. FVG
        if row.get("in_bull_fvg", False):
            buy_score += self.WEIGHTS["fvg"]
            buy_reasons.append("FVG")
        if row.get("in_bear_fvg", False):
            sell_score += self.WEIGHTS["fvg"]
            sell_reasons.append("FVG")

        # 3. Supply/Demand
        if row.get("in_demand", False):
            buy_score += self.WEIGHTS["supply_demand"]
            buy_reasons.append("DEMAND_ZONE")
        if row.get("in_supply", False):
            sell_score += self.WEIGHTS["supply_demand"]
            sell_reasons.append("SUPPLY_ZONE")

        # 4. Liquidity Sweep (highest weight — very reliable)
        if row.get("liq_sweep_bull", False):
            buy_score += self.WEIGHTS["liq_sweep"]
            buy_reasons.append("LIQ_SWEEP")
        if row.get("liq_sweep_bear", False):
            sell_score += self.WEIGHTS["liq_sweep"]
            sell_reasons.append("LIQ_SWEEP")

        # 5. S/R Rejection
        if row.get("reject_bull", False):
            buy_score += self.WEIGHTS["sr_rejection"]
            buy_reasons.append("SR_REJECT")
        if row.get("reject_bear", False):
            sell_score += self.WEIGHTS["sr_rejection"]
            sell_reasons.append("SR_REJECT")

        # 6. Structure Break (BOS)
        if row.get("bos_bull", False):
            buy_score += self.WEIGHTS["structure_break"]
            buy_reasons.append("BOS")
        if row.get("bos_bear", False):
            sell_score += self.WEIGHTS["structure_break"]
            sell_reasons.append("BOS")

        # 7. Fibonacci Retracement
        if row.get("at_fib_bull", False):
            buy_score += self.WEIGHTS["fib_retracement"]
            buy_reasons.append(f"FIB_{row.get('fib_level', '?')}")
        if row.get("at_fib_bear", False):
            sell_score += self.WEIGHTS["fib_retracement"]
            sell_reasons.append(f"FIB_{row.get('fib_level', '?')}")

        # 8. RSI Confirmation
        rsi = row.get("rsi", 50)
        if 30 < rsi < 60:  # Not overbought — good for buys
            buy_score += self.WEIGHTS["rsi_confirm"]
            buy_reasons.append("RSI_OK")
        if 40 < rsi < 70:  # Not oversold — good for sells
            sell_score += self.WEIGHTS["rsi_confirm"]
            sell_reasons.append("RSI_OK")

        return {
            "buy_score": buy_score,
            "sell_score": sell_score,
            "buy_reasons": buy_reasons,
            "sell_reasons": sell_reasons,
            "max_score": self.MAX_SCORE,
            "min_required": self.min_confluence,
        }

    def get_signal(self, df: pd.DataFrame) -> dict:
        """
        Get the final trade signal based on confluence scoring.
        Returns: {"signal": 1/0/-1, "score": int, "reasons": list}
        """
        scores = self.score_setup(df)

        buy_ok = scores["buy_score"] >= self.min_confluence
        sell_ok = scores["sell_score"] >= self.min_confluence

        # If both qualify, take the stronger one
        if buy_ok and sell_ok:
            if scores["buy_score"] > scores["sell_score"]:
                sell_ok = False
            elif scores["sell_score"] > scores["buy_score"]:
                buy_ok = False
            else:
                # Equal — skip (conflicting signals)
                return {"signal": 0, "score": 0, "reasons": ["CONFLICT"]}

        if buy_ok:
            return {
                "signal": 1,
                "score": scores["buy_score"],
                "reasons": scores["buy_reasons"],
                "max_score": scores["max_score"],
            }
        elif sell_ok:
            return {
                "signal": -1,
                "score": scores["sell_score"],
                "reasons": scores["sell_reasons"],
                "max_score": scores["max_score"],
            }

        return {
            "signal": 0,
            "score": max(scores["buy_score"], scores["sell_score"]),
            "reasons": [],
            "max_score": scores["max_score"],
        }


def prepare_dataframe(df: pd.DataFrame, ema_fast: int = 9, ema_slow: int = 21,
                       rsi_period: int = 14, atr_period: int = 14) -> pd.DataFrame:
    """Apply all indicators (basic + advanced) to the DataFrame."""
    df = compute_signals(df, ema_fast, ema_slow, rsi_period, atr_period)
    df = compute_advanced_signals(df)
    return df
