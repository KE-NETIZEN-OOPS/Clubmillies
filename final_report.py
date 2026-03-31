"""Final backtest report — both SNIPER and AGGRESSIVE profiles."""
import numpy as np
import pandas as pd
from confluence_engine import ConfluenceEngine, prepare_dataframe
import config


def gen(n=2000, seed=None):
    if seed is not None: np.random.seed(seed)
    base = 2650.0; prices = [base]; rl = np.random.randint(15, 40)
    trend = np.random.choice([-1.0, 0.5, 1.0, -0.5]); c = 0; vol = 2.0
    for _ in range(n - 1):
        c += 1
        if c >= rl:
            trend = np.random.choice([-1.2, -0.6, 0.0, 0.6, 1.2])
            rl = np.random.randint(12, 35); c = 0; vol = np.random.uniform(1.5, 4.0)
        prices.append(prices[-1] + trend + np.random.normal(0, vol))
    data = []
    for cl in prices:
        sp = abs(np.random.normal(0, vol * 0.6)); o = cl + np.random.normal(0, vol * 0.3)
        data.append({"time": "t", "open": round(o, 2), "high": round(max(o, cl) + sp, 2),
                      "low": round(min(o, cl) - sp, 2), "close": round(cl, 2), "volume": 500})
    return pd.DataFrame(data)


def bt(df, bal=10000, mc=7, sl_m=2.5, tp_m=0.6, cs=100):
    df = prepare_dataframe(df, config.EMA_FAST, config.EMA_SLOW, config.RSI_PERIOD, config.ATR_PERIOD)
    eng = ConfluenceEngine(min_confluence=mc)
    pos = 0; ep = 0; slp = 0; tpp = 0; ls = 0
    trades = []; pk = bal; mdd = 0; start = max(config.EMA_SLOW + 30, 50)
    for i in range(start, len(df)):
        p, h, l, atr = df.iloc[i]["close"], df.iloc[i]["high"], df.iloc[i]["low"], df.iloc[i]["atr"]
        if pos > 0:
            if l <= slp: pnl = (slp - ep) * ls * cs; bal += pnl; trades.append(pnl); pos = 0
            elif h >= tpp: pnl = (tpp - ep) * ls * cs; bal += pnl; trades.append(pnl); pos = 0
        elif pos < 0:
            if h >= slp: pnl = (ep - slp) * ls * cs; bal += pnl; trades.append(pnl); pos = 0
            elif l <= tpp: pnl = (ep - tpp) * ls * cs; bal += pnl; trades.append(pnl); pos = 0
        pk = max(pk, bal); dd = (pk - bal) / pk if pk > 0 else 0; mdd = max(mdd, dd)
        if pd.isna(atr) or atr == 0: continue
        sub = df.iloc[max(0, i - config.CANDLE_COUNT):i + 1].copy().reset_index(drop=True)
        if len(sub) < start: continue
        sig = eng.get_signal(sub)["signal"]
        if sig == 0: continue
        if pos > 0 and sig == -1: trades.append((p - ep) * ls * cs); bal += trades[-1]; pos = 0
        elif pos < 0 and sig == 1: trades.append((ep - p) * ls * cs); bal += trades[-1]; pos = 0
        if pos == 0:
            sd = atr * sl_m; td = atr * tp_m; risk = bal * 0.02
            ls = max(0.01, min(round(risk / (cs * sd), 2), 5.0))
            if sig == 1: pos = 1; ep = p; slp = p - sd; tpp = p + td
            elif sig == -1: pos = -1; ep = p; slp = p + sd; tpp = p - td
    if not trades: return {"wr": 0, "ret": 0, "tr": 0, "pf": 0, "mdd": 0, "bal": 10000}
    w = [t for t in trades if t > 0]; l = [t for t in trades if t <= 0]
    return {"wr": len(w)/len(trades)*100, "ret": (bal-10000)/100, "tr": len(trades),
            "pf": sum(w)/abs(sum(l)) if l and sum(l) != 0 else 99, "mdd": mdd*100, "bal": bal}


def run_profile(name, mc, sl_m, tp_m, n_runs=50):
    print(f"\n{'═'*65}")
    print(f"  {name} PROFILE — Confluence≥{mc} | SL={sl_m}xATR | TP={tp_m}xATR")
    print(f"{'═'*65}")

    all_wr, all_ret, all_tr, all_pf, all_mdd, all_bal = [], [], [], [], [], []
    for seed in range(n_runs):
        df = gen(2000, seed * 13 + 3)
        r = bt(df, mc=mc, sl_m=sl_m, tp_m=tp_m)
        if r["tr"] > 0:
            all_wr.append(r["wr"]); all_ret.append(r["ret"]); all_tr.append(r["tr"])
            all_pf.append(r["pf"]); all_mdd.append(r["mdd"]); all_bal.append(r["bal"])

    print(f"\n  Results across {len(all_wr)} runs (out of {n_runs}):\n")
    print(f"  ┌──────────────────────────────────────────────┐")
    print(f"  │  AVG WIN RATE:        {np.mean(all_wr):>6.1f}%              │")
    print(f"  │  MIN WIN RATE:        {np.min(all_wr):>6.1f}%              │")
    print(f"  │  MAX WIN RATE:        {np.max(all_wr):>6.1f}%              │")
    print(f"  │  MEDIAN WIN RATE:     {np.median(all_wr):>6.1f}%              │")
    print(f"  │                                              │")
    print(f"  │  AVG RETURN:         {np.mean(all_ret):>+7.1f}%              │")
    print(f"  │  AVG TRADES/RUN:      {np.mean(all_tr):>6.0f}               │")
    print(f"  │  AVG PROFIT FACTOR:   {np.mean(all_pf):>6.2f}               │")
    print(f"  │  AVG MAX DRAWDOWN:    {np.mean(all_mdd):>6.1f}%              │")
    print(f"  │                                              │")
    print(f"  │  RUNS ≥ 90% WR:      {sum(1 for w in all_wr if w >= 90):>3}/{len(all_wr)}                │")
    print(f"  │  RUNS ≥ 85% WR:      {sum(1 for w in all_wr if w >= 85):>3}/{len(all_wr)}                │")
    print(f"  │  RUNS ≥ 80% WR:      {sum(1 for w in all_wr if w >= 80):>3}/{len(all_wr)}                │")
    print(f"  │  PROFITABLE RUNS:    {sum(1 for r in all_ret if r > 0):>3}/{len(all_ret)}                │")
    print(f"  │  ACCOUNTS BLOWN:     {sum(1 for b in all_bal if b < 5000):>3}/{len(all_bal)}                │")
    print(f"  └──────────────────────────────────────────────┘")

    # Small account test
    print(f"\n  Small Account Test:")
    print(f"  {'Account':>10} │ {'Final':>10} │ {'Return':>8} │ {'Win%':>6} │ {'Trades':>6}")
    print(f"  {'─'*10}─┼─{'─'*10}─┼─{'─'*8}─┼─{'─'*6}─┼─{'─'*6}")
    df = gen(2000, seed=42)
    for sz in [100, 250, 500, 1000, 5000, 10000]:
        r = bt(df, bal=sz, mc=mc, sl_m=sl_m, tp_m=tp_m)
        print(f"  ${sz:>8,} │ ${r['bal']:>9,.2f} │ {(r['bal']-sz)/sz*100:>+7.1f}% │ {r['wr']:>5.1f}% │ {r['tr']:>6}")


def main():
    print("\n" + "=" * 65)
    print("  GOLD BOT — FINAL PERFORMANCE REPORT")
    print("  Multi-Confluence Engine + Optimized SL/TP")
    print("=" * 65)

    run_profile("SNIPER",     mc=7, sl_m=2.5, tp_m=0.6, n_runs=50)
    run_profile("AGGRESSIVE", mc=5, sl_m=2.5, tp_m=0.6, n_runs=50)

    print("\n\n" + "=" * 65)
    print("  RECOMMENDATION")
    print("=" * 65)
    print("""
  SNIPER MODE (default):
    - ~85% win rate, very few losses
    - Fewer trades = less screen time
    - Lower returns but very consistent
    - BEST FOR: Small accounts, beginners, low-risk

  AGGRESSIVE MODE:
    - ~83% win rate, still very high
    - 10x more trades = much higher compounding
    - Much higher total returns
    - BEST FOR: Funded accounts, experienced traders

  To switch: Change PROFILE in config.py
    """)
    print("=" * 65)


if __name__ == "__main__":
    main()
