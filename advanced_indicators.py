"""
Advanced Smart Money / Price Action indicators — optimized.
FVG, Supply/Demand, Liquidity Sweeps, S/R Rejection, Structure Breaks, Fib.
"""
import pandas as pd
import numpy as np


# ═══════════════════════════════════════════════════════════════════
#  1. FAIR VALUE GAPS (FVG)
# ═══════════════════════════════════════════════════════════════════

def detect_fvg(df: pd.DataFrame, min_gap_pct: float = 0.03) -> pd.DataFrame:
    df = df.copy()
    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values
    n = len(df)

    fvg_bull = np.zeros(n, dtype=bool)
    fvg_bear = np.zeros(n, dtype=bool)
    fvg_bull_top = np.full(n, np.nan)
    fvg_bull_bot = np.full(n, np.nan)
    fvg_bear_top = np.full(n, np.nan)
    fvg_bear_bot = np.full(n, np.nan)

    for i in range(2, n):
        mid = closes[i - 1]
        if mid == 0:
            continue
        # Bullish FVG
        if lows[i] > highs[i - 2]:
            if (lows[i] - highs[i - 2]) / mid * 100 >= min_gap_pct:
                fvg_bull[i] = True
                fvg_bull_top[i] = lows[i]
                fvg_bull_bot[i] = highs[i - 2]
        # Bearish FVG
        if lows[i - 2] > highs[i]:
            if (lows[i - 2] - highs[i]) / mid * 100 >= min_gap_pct:
                fvg_bear[i] = True
                fvg_bear_top[i] = lows[i - 2]
                fvg_bear_bot[i] = highs[i]

    df["fvg_bull"] = fvg_bull
    df["fvg_bear"] = fvg_bear
    df["fvg_bull_top"] = fvg_bull_top
    df["fvg_bull_bottom"] = fvg_bull_bot
    df["fvg_bear_top"] = fvg_bear_top
    df["fvg_bear_bottom"] = fvg_bear_bot
    return df


def price_in_fvg(df: pd.DataFrame, lookback: int = 20) -> pd.DataFrame:
    df = df.copy()
    n = len(df)
    in_bull = np.zeros(n, dtype=bool)
    in_bear = np.zeros(n, dtype=bool)

    # Collect active FVG zones and check efficiently
    bull_zones = []  # (top, bot, expiry_idx)
    bear_zones = []

    for i in range(n):
        # Add new FVGs
        if df.iloc[i]["fvg_bull"]:
            bull_zones.append((df.iloc[i]["fvg_bull_top"], df.iloc[i]["fvg_bull_bottom"], i + lookback))
        if df.iloc[i]["fvg_bear"]:
            bear_zones.append((df.iloc[i]["fvg_bear_top"], df.iloc[i]["fvg_bear_bottom"], i + lookback))

        price = df.iloc[i]["close"]
        low = df.iloc[i]["low"]
        high = df.iloc[i]["high"]

        # Check bullish FVGs
        new_bull = []
        for top, bot, exp in bull_zones:
            if i > exp:
                continue
            new_bull.append((top, bot, exp))
            if bot <= low <= top or bot <= price <= top:
                in_bull[i] = True
        bull_zones = new_bull

        # Check bearish FVGs
        new_bear = []
        for top, bot, exp in bear_zones:
            if i > exp:
                continue
            new_bear.append((top, bot, exp))
            if bot <= high <= top or bot <= price <= top:
                in_bear[i] = True
        bear_zones = new_bear

    df["in_bull_fvg"] = in_bull
    df["in_bear_fvg"] = in_bear
    return df


# ═══════════════════════════════════════════════════════════════════
#  2. SUPPLY & DEMAND ZONES (optimized)
# ═══════════════════════════════════════════════════════════════════

def detect_supply_demand(df: pd.DataFrame, strength: int = 3,
                         zone_lookback: int = 40) -> pd.DataFrame:
    df = df.copy()
    n = len(df)
    in_demand = np.zeros(n, dtype=bool)
    in_supply = np.zeros(n, dtype=bool)

    opens = df["open"].values
    closes = df["close"].values
    highs = df["high"].values
    lows = df["low"].values

    demand_zones = []  # (top, bot, expiry)
    supply_zones = []

    for i in range(1, n - strength):
        # Check bullish impulse: next `strength` candles all bullish
        bullish = True
        for k in range(1, strength + 1):
            if closes[i + k] <= opens[i + k]:
                bullish = False
                break
        if bullish:
            zt = max(opens[i], closes[i])
            zb = lows[i]
            demand_zones.append((zt, zb, i + zone_lookback))

        # Check bearish impulse
        bearish = True
        for k in range(1, strength + 1):
            if closes[i + k] >= opens[i + k]:
                bearish = False
                break
        if bearish:
            zt = highs[i]
            zb = min(opens[i], closes[i])
            supply_zones.append((zt, zb, i + zone_lookback))

    # Now scan price against active zones
    for i in range(n):
        price = closes[i]
        low = lows[i]
        high = highs[i]

        for zt, zb, exp in demand_zones:
            if i <= exp and i > (exp - zone_lookback + strength) and low <= zt and price >= zb:
                in_demand[i] = True
                break

        for zt, zb, exp in supply_zones:
            if i <= exp and i > (exp - zone_lookback + strength) and high >= zb and price <= zt:
                in_supply[i] = True
                break

    df["in_demand"] = in_demand
    df["in_supply"] = in_supply
    return df


# ═══════════════════════════════════════════════════════════════════
#  3. LIQUIDITY SWEEP / STOP HUNT
# ═══════════════════════════════════════════════════════════════════

def detect_liquidity_sweep(df: pd.DataFrame, lookback: int = 20,
                           wick_ratio: float = 0.6) -> pd.DataFrame:
    df = df.copy()
    n = len(df)
    sweep_bull = np.zeros(n, dtype=bool)
    sweep_bear = np.zeros(n, dtype=bool)

    highs = df["high"].values
    lows = df["low"].values
    opens = df["open"].values
    closes = df["close"].values

    for i in range(lookback, n):
        cr = highs[i] - lows[i]
        if cr == 0:
            continue

        body_low = min(opens[i], closes[i])
        body_high = max(opens[i], closes[i])
        lower_wick = body_low - lows[i]
        upper_wick = highs[i] - body_high

        swing_low = lows[i - lookback:i].min()
        swing_high = highs[i - lookback:i].max()

        if lows[i] < swing_low and closes[i] > swing_low and lower_wick / cr >= wick_ratio:
            sweep_bull[i] = True
        if highs[i] > swing_high and closes[i] < swing_high and upper_wick / cr >= wick_ratio:
            sweep_bear[i] = True

    df["liq_sweep_bull"] = sweep_bull
    df["liq_sweep_bear"] = sweep_bear
    return df


# ═══════════════════════════════════════════════════════════════════
#  4. SUPPORT/RESISTANCE + REJECTION
# ═══════════════════════════════════════════════════════════════════

def detect_sr_rejection(df: pd.DataFrame, sr_lookback: int = 50,
                        touch_threshold: float = 0.15,
                        min_touches: int = 2,
                        proximity: float = 0.3,
                        wick_ratio: float = 0.5) -> pd.DataFrame:
    df = df.copy()
    n = len(df)
    reject_bull = np.zeros(n, dtype=bool)
    reject_bear = np.zeros(n, dtype=bool)

    highs = df["high"].values
    lows = df["low"].values
    opens = df["open"].values
    closes = df["close"].values

    for i in range(sr_lookback, n):
        cr = highs[i] - lows[i]
        if cr == 0:
            continue

        # Build S/R levels from recent window
        window_h = highs[i - sr_lookback:i]
        window_l = lows[i - sr_lookback:i]
        pivots = np.concatenate([window_h, window_l])
        pivots.sort()

        # Cluster pivots into levels
        levels = []
        used = set()
        for p in pivots:
            skip = False
            for u in used:
                if abs(p - u) < touch_threshold:
                    skip = True
                    break
            if skip:
                continue
            touches = np.sum(np.abs(pivots - p) <= touch_threshold)
            if touches >= min_touches:
                levels.append(p)
                used.add(p)
            if len(levels) >= 5:
                break

        body_low = min(opens[i], closes[i])
        body_high = max(opens[i], closes[i])
        lower_wick = body_low - lows[i]
        upper_wick = highs[i] - body_high

        for lp in levels:
            if abs(lows[i] - lp) <= proximity and lower_wick / cr >= wick_ratio and closes[i] > lp:
                reject_bull[i] = True
                break
            if abs(highs[i] - lp) <= proximity and upper_wick / cr >= wick_ratio and closes[i] < lp:
                reject_bear[i] = True
                break

    df["reject_bull"] = reject_bull
    df["reject_bear"] = reject_bear
    return df


# ═══════════════════════════════════════════════════════════════════
#  5. MARKET STRUCTURE (BOS)
# ═══════════════════════════════════════════════════════════════════

def detect_structure_break(df: pd.DataFrame, left: int = 3, right: int = 3) -> pd.DataFrame:
    df = df.copy()
    n = len(df)
    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values

    swing_h = np.full(n, np.nan)
    swing_l = np.full(n, np.nan)
    bos_bull = np.zeros(n, dtype=bool)
    bos_bear = np.zeros(n, dtype=bool)

    for i in range(left, n - right):
        is_high = all(highs[i] > highs[i - j] for j in range(1, left + 1))
        if is_high:
            is_high = all(highs[i] > highs[i + j] for j in range(1, min(right + 1, n - i)))
        if is_high:
            swing_h[i] = highs[i]

        is_low = all(lows[i] < lows[i - j] for j in range(1, left + 1))
        if is_low:
            is_low = all(lows[i] < lows[i + j] for j in range(1, min(right + 1, n - i)))
        if is_low:
            swing_l[i] = lows[i]

    last_sh = np.nan
    last_sl = np.nan
    for i in range(n):
        if not np.isnan(swing_h[i]):
            last_sh = swing_h[i]
        if not np.isnan(swing_l[i]):
            last_sl = swing_l[i]
        if not np.isnan(last_sh) and closes[i] > last_sh:
            bos_bull[i] = True
        if not np.isnan(last_sl) and closes[i] < last_sl:
            bos_bear[i] = True

    df["bos_bull"] = bos_bull
    df["bos_bear"] = bos_bear
    return df


# ═══════════════════════════════════════════════════════════════════
#  6. FIBONACCI RETRACEMENT
# ═══════════════════════════════════════════════════════════════════

def detect_fib_retracement(df: pd.DataFrame, lookback: int = 30,
                            tolerance: float = 0.3) -> pd.DataFrame:
    fib_levels = [0.382, 0.5, 0.618, 0.705, 0.786]
    df = df.copy()
    n = len(df)
    at_fib_bull = np.zeros(n, dtype=bool)
    at_fib_bear = np.zeros(n, dtype=bool)
    fib_val = np.full(n, np.nan)

    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values

    for i in range(lookback, n):
        window_h = highs[i - lookback:i]
        window_l = lows[i - lookback:i]
        sh_idx = np.argmax(window_h)
        sl_idx = np.argmin(window_l)
        sh = window_h[sh_idx]
        sl = window_l[sl_idx]
        sr = sh - sl
        if sr == 0:
            continue

        price = closes[i]
        if sl_idx < sh_idx:  # uptrend → bull fib
            for fib in fib_levels:
                fp = sh - sr * fib
                if abs(price - fp) <= tolerance:
                    at_fib_bull[i] = True
                    fib_val[i] = fib
                    break
        else:  # downtrend → bear fib
            for fib in fib_levels:
                fp = sl + sr * fib
                if abs(price - fp) <= tolerance:
                    at_fib_bear[i] = True
                    fib_val[i] = fib
                    break

    df["at_fib_bull"] = at_fib_bull
    df["at_fib_bear"] = at_fib_bear
    df["fib_level"] = fib_val
    return df


# ═══════════════════════════════════════════════════════════════════
#  MASTER
# ═══════════════════════════════════════════════════════════════════

def compute_advanced_signals(df: pd.DataFrame) -> pd.DataFrame:
    df = detect_fvg(df)
    df = price_in_fvg(df)
    df = detect_supply_demand(df)
    df = detect_liquidity_sweep(df)
    df = detect_structure_break(df)
    df = detect_fib_retracement(df)
    df = detect_sr_rejection(df)
    return df
