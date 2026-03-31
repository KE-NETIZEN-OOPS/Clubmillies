"""
Tuning to maximize win rate above 85%.
Key insight: tighter TP (closer to entry) = more wins but smaller wins.
Combined with high confluence = only take the best setups.
"""
import numpy as np
import pandas as pd
from confluence_engine import ConfluenceEngine, prepare_dataframe
import config


def generate_data(n_candles=2000, seed=None):
    if seed is not None:
        np.random.seed(seed)
    base = 2650.0
    prices = [base]
    regime_len = np.random.randint(15, 40)
    trend = np.random.choice([-1.0, 0.5, 1.0, -0.5])
    counter = 0
    vol = 2.0
    for _ in range(n_candles - 1):
        counter += 1
        if counter >= regime_len:
            trend = np.random.choice([-1.2, -0.6, 0.0, 0.6, 1.2])
            regime_len = np.random.randint(12, 35)
            counter = 0
            vol = np.random.uniform(1.5, 4.0)
        prices.append(prices[-1] + trend + np.random.normal(0, vol))
    data = []
    for close in prices:
        sp = abs(np.random.normal(0, vol * 0.6))
        o = close + np.random.normal(0, vol * 0.3)
        data.append({"time": "t", "open": round(o, 2),
                      "high": round(max(o, close) + sp, 2),
                      "low": round(min(o, close) - sp, 2),
                      "close": round(close, 2), "volume": 500})
    return pd.DataFrame(data)


def run_bt(df, balance=10000, min_conf=7, sl_mult=1.5, tp_mult=2.5, cs=100):
    df = prepare_dataframe(df, config.EMA_FAST, config.EMA_SLOW, config.RSI_PERIOD, config.ATR_PERIOD)
    engine = ConfluenceEngine(min_confluence=min_conf)
    pos = 0; ep = 0; sl = 0; tp = 0; ls = 0
    trades = []; start = max(config.EMA_SLOW + 30, 50)

    for i in range(start, len(df)):
        row = df.iloc[i]
        p, h, l, atr = row["close"], row["high"], row["low"], row["atr"]

        if pos > 0:
            if l <= sl:
                trades.append((sl - ep) * ls * cs)
                pos = 0
            elif h >= tp:
                trades.append((tp - ep) * ls * cs)
                pos = 0
        elif pos < 0:
            if h >= sl:
                trades.append((ep - sl) * ls * cs)
                pos = 0
            elif l <= tp:
                trades.append((ep - tp) * ls * cs)
                pos = 0

        if pd.isna(atr) or atr == 0:
            continue

        sub = df.iloc[max(0, i - config.CANDLE_COUNT):i + 1].copy().reset_index(drop=True)
        if len(sub) < start:
            continue
        result = engine.get_signal(sub)
        sig = result["signal"]

        if sig == 0:
            continue

        if pos > 0 and sig == -1:
            trades.append((p - ep) * ls * cs); pos = 0
        elif pos < 0 and sig == 1:
            trades.append((ep - p) * ls * cs); pos = 0

        if pos == 0:
            sd = atr * sl_mult; td = atr * tp_mult
            risk = balance * config.RISK_PER_TRADE
            ls = max(0.01, min(round(risk / (cs * sd), 2), 5.0))
            if sig == 1:
                pos = 1; ep = p; sl = p - sd; tp = p + td
            elif sig == -1:
                pos = -1; ep = p; sl = p + sd; tp = p - td

    if not trades:
        return 0, 0, 0, 0
    wins = sum(1 for t in trades if t > 0)
    wr = wins / len(trades) * 100
    total = sum(trades)
    ret = total / balance * 100
    w = [t for t in trades if t > 0]
    l = [t for t in trades if t <= 0]
    pf = sum(w) / abs(sum(l)) if l and sum(l) != 0 else 99
    return wr, ret, len(trades), pf


def main():
    print("=" * 75)
    print("  WIN RATE OPTIMIZATION — Testing SL/TP combos × Confluence levels")
    print("=" * 75)

    configs = [
        # (name, min_conf, sl_mult, tp_mult)
        ("Baseline",                   7, 1.5, 2.5),
        ("Tight TP",                   7, 1.5, 1.0),
        ("Very tight TP",             7, 1.5, 0.7),
        ("Wide SL + Tight TP",        7, 2.0, 1.0),
        ("Wide SL + Very tight TP",   7, 2.5, 0.8),
        ("Conf8 + Tight TP",          8, 1.5, 1.0),
        ("Conf8 + Very tight TP",     8, 1.5, 0.7),
        ("Conf8 + Wide SL tight TP",  8, 2.0, 0.8),
        ("Conf6 + Tight TP",          6, 1.5, 1.0),
        ("Conf6 + Very tight TP",     6, 1.5, 0.7),
        ("Conf7 + SL2 TP0.5",         7, 2.0, 0.5),
        ("Conf7 + SL2.5 TP0.6",       7, 2.5, 0.6),
        ("Conf7 + SL3 TP0.7",         7, 3.0, 0.7),
        ("Conf8 + SL2.5 TP0.5",       8, 2.5, 0.5),
        ("Conf8 + SL3 TP0.6",         8, 3.0, 0.6),
        ("Conf5 + SL2 TP0.5",         5, 2.0, 0.5),
        ("Conf5 + SL2.5 TP0.6",       5, 2.5, 0.6),
        ("Conf5 + SL3 TP0.7",         5, 3.0, 0.7),
        ("Conf5 + SL2 TP0.7",         5, 2.0, 0.7),
    ]

    print(f"\n  {'Config':<30} │ {'Win%':>6} │ {'Return':>8} │ {'Trades':>6} │ {'PF':>6}")
    print(f"  {'─'*30}─┼─{'─'*6}─┼─{'─'*8}─┼─{'─'*6}─┼─{'─'*6}")

    best_config = None
    best_wr = 0

    for name, mc, sl_m, tp_m in configs:
        wrs, rets, trs, pfs = [], [], [], []
        for seed in range(20):
            df = generate_data(2000, seed * 42 + 7)
            wr, ret, tr, pf = run_bt(df, min_conf=mc, sl_mult=sl_m, tp_mult=tp_m)
            if tr > 0:
                wrs.append(wr); rets.append(ret); trs.append(tr); pfs.append(pf)

        if wrs:
            avg_wr = np.mean(wrs)
            avg_ret = np.mean(rets)
            avg_tr = np.mean(trs)
            avg_pf = np.mean(pfs)
            print(f"  {name:<30} │ {avg_wr:>5.1f}% │ {avg_ret:>+7.1f}% │ {avg_tr:>6.0f} │ {avg_pf:>6.2f}")
            if avg_wr > best_wr:
                best_wr = avg_wr
                best_config = (name, mc, sl_m, tp_m)
        else:
            print(f"  {name:<30} │   N/A  │     N/A  │    N/A │   N/A")

    print(f"\n  BEST CONFIG: {best_config[0]} → {best_wr:.1f}% win rate")
    print(f"  Settings: MIN_CONFLUENCE={best_config[1]}, ATR_SL={best_config[2]}, ATR_TP={best_config[3]}")

    # Deep test the best config
    print(f"\n\n  ── DEEP TEST: {best_config[0]} (50 runs) ──")
    _, mc, sl_m, tp_m = best_config
    all_wr, all_ret, all_tr = [], [], []
    for seed in range(50):
        df = generate_data(2000, seed * 13 + 3)
        wr, ret, tr, pf = run_bt(df, min_conf=mc, sl_mult=sl_m, tp_mult=tp_m)
        if tr > 0:
            all_wr.append(wr); all_ret.append(ret); all_tr.append(tr)

    print(f"  Avg Win Rate:  {np.mean(all_wr):.1f}%")
    print(f"  Min Win Rate:  {np.min(all_wr):.1f}%")
    print(f"  Max Win Rate:  {np.max(all_wr):.1f}%")
    print(f"  Avg Return:    {np.mean(all_ret):+.1f}%")
    print(f"  Avg Trades:    {np.mean(all_tr):.0f}")
    print(f"  Runs ≥85% WR:  {sum(1 for w in all_wr if w >= 85)}/{len(all_wr)}")
    print(f"  Runs ≥80% WR:  {sum(1 for w in all_wr if w >= 80)}/{len(all_wr)}")
    print(f"  Profitable:    {sum(1 for r in all_ret if r > 0)}/{len(all_ret)}")

    # Also deep-test top 3
    print("\n\n  ── DEEP TEST: Top configs with highest WR (50 runs each) ──\n")
    top_configs = [
        ("Conf5 + SL3 TP0.7",   5, 3.0, 0.7),
        ("Conf5 + SL2.5 TP0.6", 5, 2.5, 0.6),
        ("Conf5 + SL2 TP0.7",   5, 2.0, 0.7),
        ("Conf5 + SL2 TP0.5",   5, 2.0, 0.5),
        ("Conf7 + SL3 TP0.7",   7, 3.0, 0.7),
        ("Conf7 + SL2.5 TP0.6", 7, 2.5, 0.6),
    ]

    for name, mc, sl_m, tp_m in top_configs:
        all_wr, all_ret, all_tr = [], [], []
        for seed in range(50):
            df = generate_data(2000, seed * 13 + 3)
            wr, ret, tr, pf = run_bt(df, min_conf=mc, sl_mult=sl_m, tp_mult=tp_m)
            if tr > 0:
                all_wr.append(wr); all_ret.append(ret); all_tr.append(tr)

        if all_wr:
            print(f"  {name:<25} │ WR: {np.mean(all_wr):>5.1f}% (min {np.min(all_wr):.0f}%) │ "
                  f"Ret: {np.mean(all_ret):>+7.1f}% │ Trades: {np.mean(all_tr):>4.0f} │ "
                  f"≥85%: {sum(1 for w in all_wr if w >= 85)}/{len(all_wr)} │ "
                  f"Profitable: {sum(1 for r in all_ret if r > 0)}/{len(all_ret)}")

    print("\n" + "=" * 75)


if __name__ == "__main__":
    main()
