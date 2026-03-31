"""
Technical indicators for the Gold trading strategy.
"""
import pandas as pd
import numpy as np


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, min_periods=period).mean()


def compute_signals(df: pd.DataFrame, fast: int, slow: int,
                    rsi_period: int, atr_period: int) -> pd.DataFrame:
    """Add all indicator columns and generate raw signals."""
    df = df.copy()
    df["ema_fast"] = ema(df["close"], fast)
    df["ema_slow"] = ema(df["close"], slow)
    df["rsi"] = rsi(df["close"], rsi_period)
    df["atr"] = atr(df, atr_period)

    # Crossover detection
    df["ema_cross_up"] = (df["ema_fast"] > df["ema_slow"]) & (df["ema_fast"].shift() <= df["ema_slow"].shift())
    df["ema_cross_down"] = (df["ema_fast"] < df["ema_slow"]) & (df["ema_fast"].shift() >= df["ema_slow"].shift())

    # Signal: 1 = BUY, -1 = SELL, 0 = no action
    df["signal"] = 0
    df.loc[df["ema_cross_up"] & (df["rsi"] < 70), "signal"] = 1
    df.loc[df["ema_cross_down"] & (df["rsi"] > 30), "signal"] = -1

    return df
