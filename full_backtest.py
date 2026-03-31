"""
Comprehensive backtest for the Multi-Confluence Gold Bot.
Tests different confluence thresholds, account sizes, and market conditions.
"""
import numpy as np
import pandas as pd
from confluence_engine import ConfluenceEngine, prepare_dataframe
import config


def generate_realistic_gold_data(n_candles: int = 2000, seed: int = None) -> pd.DataFrame:
    """Generate realistic gold price data with trends, ranges, and volatility clusters."""
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

        noise = np.random.normal(0, vol)
        prices.append(prices[-1] + trend + noise)

    data = []
    for close in prices:
        spread = abs(np.random.normal(0, vol * 0.6))
        o = close + np.random.normal(0, vol * 0.3)
        data.append({
            "time": "t",
            "open": round(o, 2),
            "high": round(max(o, close) + spread, 2),
            "low": round(min(o, close) - spread, 2),
            "close": round(close, 2),
            "volume": int(np.random.uniform(100, 1000)),
        })
    return pd.DataFrame(data)


def run_backtest(df: pd.DataFrame, initial_balance: float = 10000.0,
                 min_confluence: int = 7, contract_size: float = 100.0) -> dict:
    """Run full backtest with confluence engine."""
    df = prepare_dataframe(
        df, config.EMA_FAST, config.EMA_SLOW,
        config.RSI_PERIOD, config.ATR_PERIOD
    )

    engine = ConfluenceEngine(min_confluence=min_confluence)

    balance = initial_balance
    peak_balance = initial_balance
    max_drawdown = 0.0
    position = 0
    entry_price = 0.0
    sl_price = 0.0
    tp_price = 0.0
    lot_size = 0.0
    trades = []
    consecutive_losses = 0
    max_consecutive_losses = 0
    start_idx = max(config.EMA_SLOW + 30, 50)

    for i in range(start_idx, len(df)):
        row = df.iloc[i]
        price = row["close"]
        high = row["high"]
        low = row["low"]
        current_atr = row["atr"]

        # Check SL/TP
        if position > 0:
            if low <= sl_price:
                pnl = (sl_price - entry_price) * lot_size * contract_size
                balance += pnl
                trades.append({"pnl": pnl, "reason": "SL", "type": "BUY"})
                position = 0
                if pnl <= 0:
                    consecutive_losses += 1
                    max_consecutive_losses = max(max_consecutive_losses, consecutive_losses)
                else:
                    consecutive_losses = 0
            elif high >= tp_price:
                pnl = (tp_price - entry_price) * lot_size * contract_size
                balance += pnl
                trades.append({"pnl": pnl, "reason": "TP", "type": "BUY"})
                position = 0
                consecutive_losses = 0
        elif position < 0:
            if high >= sl_price:
                pnl = (entry_price - sl_price) * lot_size * contract_size
                balance += pnl
                trades.append({"pnl": pnl, "reason": "SL", "type": "SELL"})
                position = 0
                if pnl <= 0:
                    consecutive_losses += 1
                    max_consecutive_losses = max(max_consecutive_losses, consecutive_losses)
                else:
                    consecutive_losses = 0
            elif low <= tp_price:
                pnl = (entry_price - tp_price) * lot_size * contract_size
                balance += pnl
                trades.append({"pnl": pnl, "reason": "TP", "type": "SELL"})
                position = 0
                consecutive_losses = 0

        peak_balance = max(peak_balance, balance)
        dd = (peak_balance - balance) / peak_balance if peak_balance > 0 else 0
        max_drawdown = max(max_drawdown, dd)

        if pd.isna(current_atr) or current_atr == 0:
            continue

        # Get confluence signal (use slice up to current candle)
        sub_df = df.iloc[max(0, i - config.CANDLE_COUNT):i + 1].copy().reset_index(drop=True)
        if len(sub_df) < start_idx:
            continue

        result = engine.get_signal(sub_df)
        signal = result["signal"]

        if signal == 0:
            continue

        # Close opposite
        if position > 0 and signal == -1:
            pnl = (price - entry_price) * lot_size * contract_size
            balance += pnl
            trades.append({"pnl": pnl, "reason": "SIGNAL", "type": "BUY"})
            position = 0
        elif position < 0 and signal == 1:
            pnl = (entry_price - price) * lot_size * contract_size
            balance += pnl
            trades.append({"pnl": pnl, "reason": "SIGNAL", "type": "SELL"})
            position = 0

        # Open new
        if position == 0:
            sl_dist = current_atr * config.ATR_SL_MULTIPLIER
            tp_dist = current_atr * config.ATR_TP_MULTIPLIER
            risk_amount = balance * config.RISK_PER_TRADE
            lot_size = risk_amount / (contract_size * sl_dist)
            lot_size = max(0.01, min(round(lot_size, 2), 5.0))

            if signal == 1:
                position = 1
                entry_price = price
                sl_price = price - sl_dist
                tp_price = price + tp_dist
            elif signal == -1:
                position = -1
                entry_price = price
                sl_price = price + sl_dist
                tp_price = price - tp_dist

    # Close remaining
    if position != 0:
        last_price = df.iloc[-1]["close"]
        if position > 0:
            pnl = (last_price - entry_price) * lot_size * contract_size
        else:
            pnl = (entry_price - last_price) * lot_size * contract_size
        balance += pnl
        trades.append({"pnl": pnl, "reason": "END", "type": "OPEN"})

    if not trades:
        return {"total_trades": 0, "win_rate": 0, "return_pct": 0,
                "profit_factor": 0, "max_drawdown_pct": 0, "final_balance": initial_balance}

    trade_df = pd.DataFrame(trades)
    winners = trade_df[trade_df["pnl"] > 0]
    losers = trade_df[trade_df["pnl"] <= 0]
    total_pnl = balance - initial_balance
    avg_win = winners["pnl"].mean() if len(winners) > 0 else 0
    avg_loss = abs(losers["pnl"].mean()) if len(losers) > 0 else 0

    pf = (winners["pnl"].sum() / abs(losers["pnl"].sum())) if len(losers) > 0 and losers["pnl"].sum() != 0 else 99.0

    return {
        "initial_balance": initial_balance,
        "final_balance": round(balance, 2),
        "total_pnl": round(total_pnl, 2),
        "return_pct": round((total_pnl / initial_balance) * 100, 2),
        "total_trades": len(trades),
        "winners": len(winners),
        "losers": len(losers),
        "win_rate": round(len(winners) / len(trades) * 100, 1) if trades else 0,
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "reward_risk": round(avg_win / avg_loss, 2) if avg_loss > 0 else 99,
        "profit_factor": round(pf, 2),
        "max_drawdown_pct": round(max_drawdown * 100, 2),
        "max_consec_losses": max_consecutive_losses,
    }


def main():
    print("=" * 70)
    print("  GOLD BOT — MULTI-CONFLUENCE BACKTEST REPORT")
    print("=" * 70)

    # ── Test 1: Find optimal confluence threshold ───────────────────
    print("\n┌────────────────────────────────────────────────────────────────┐")
    print("│  TEST 1: CONFLUENCE THRESHOLD COMPARISON (20 runs each)      │")
    print("└────────────────────────────────────────────────────────────────┘")

    for threshold in [5, 6, 7, 8, 9]:
        results = []
        for seed in range(20):
            df = generate_realistic_gold_data(2000, seed=seed * 42 + 7)
            r = run_backtest(df, 10000, min_confluence=threshold)
            if r["total_trades"] > 0:
                results.append(r)

        if not results:
            print(f"\n  Threshold {threshold}: No trades generated")
            continue

        avg_wr = np.mean([r["win_rate"] for r in results])
        avg_ret = np.mean([r["return_pct"] for r in results])
        avg_trades = np.mean([r["total_trades"] for r in results])
        avg_pf = np.mean([r["profit_factor"] for r in results])
        avg_dd = np.mean([r["max_drawdown_pct"] for r in results])
        profitable = sum(1 for r in results if r["return_pct"] > 0)

        print(f"\n  ── Confluence ≥ {threshold} (of 15) ──")
        print(f"     Win Rate:       {avg_wr:>6.1f}%")
        print(f"     Avg Return:     {avg_ret:>+6.1f}%")
        print(f"     Avg Trades:     {avg_trades:>6.0f}")
        print(f"     Profit Factor:  {avg_pf:>6.2f}")
        print(f"     Max Drawdown:   {avg_dd:>6.1f}%")
        print(f"     Profitable:     {profitable}/{len(results)}")

    # ── Test 2: Deep dive on threshold 7 and 8 ──────────────────────
    print("\n\n┌────────────────────────────────────────────────────────────────┐")
    print("│  TEST 2: DETAILED RUNS AT CONFLUENCE 7 & 8 (30 runs each)   │")
    print("└────────────────────────────────────────────────────────────────┘")

    for threshold in [7, 8]:
        print(f"\n  ═══ CONFLUENCE ≥ {threshold} ═══")
        print(f"  {'Run':>4} │ {'Return':>8} │ {'Trades':>6} │ {'Win%':>6} │ {'PF':>6} │ {'MaxDD':>6} │ {'MaxLoss':>8}")
        print(f"  {'─'*4}─┼─{'─'*8}─┼─{'─'*6}─┼─{'─'*6}─┼─{'─'*6}─┼─{'─'*6}─┼─{'─'*8}")

        all_r = []
        for seed in range(30):
            df = generate_realistic_gold_data(2000, seed=seed * 17 + 5)
            r = run_backtest(df, 10000, min_confluence=threshold)
            all_r.append(r)
            status = "+" if r["return_pct"] > 0 else "-"
            print(f"  {seed+1:>3}{status} │ {r['return_pct']:>+7.1f}% │ {r['total_trades']:>6} │ "
                  f"{r['win_rate']:>5.1f}% │ {r['profit_factor']:>6.2f} │ "
                  f"{r['max_drawdown_pct']:>5.1f}% │ {r['max_consec_losses']:>8}")

        valid = [r for r in all_r if r["total_trades"] > 0]
        if valid:
            print(f"\n  AVERAGE:")
            print(f"    Win Rate:       {np.mean([r['win_rate'] for r in valid]):>6.1f}%")
            print(f"    Return:         {np.mean([r['return_pct'] for r in valid]):>+6.1f}%")
            print(f"    Trades:         {np.mean([r['total_trades'] for r in valid]):>6.0f}")
            print(f"    Profit Factor:  {np.mean([r['profit_factor'] for r in valid]):>6.2f}")
            print(f"    Profitable:     {sum(1 for r in valid if r['return_pct'] > 0)}/{len(valid)}")

    # ── Test 3: Small account test ──────────────────────────────────
    print("\n\n┌────────────────────────────────────────────────────────────────┐")
    print("│  TEST 3: SMALL ACCOUNT VIABILITY (Confluence ≥ 7)           │")
    print("└────────────────────────────────────────────────────────────────┘")

    df = generate_realistic_gold_data(2000, seed=99)
    print(f"\n  {'Account':>10} │ {'Final':>10} │ {'Return':>8} │ {'Trades':>6} │ {'Win%':>6} │ {'PF':>6}")
    print(f"  {'─'*10}─┼─{'─'*10}─┼─{'─'*8}─┼─{'─'*6}─┼─{'─'*6}─┼─{'─'*6}")

    for size in [100, 250, 500, 1000, 2000, 5000, 10000]:
        r = run_backtest(df, float(size), min_confluence=7)
        print(f"  ${size:>8,} │ ${r['final_balance']:>9,.2f} │ {r['return_pct']:>+7.1f}% │ "
              f"{r['total_trades']:>6} │ {r['win_rate']:>5.1f}% │ {r['profit_factor']:>6.2f}")

    # ── Test 4: Extended run ────────────────────────────────────────
    print("\n\n┌────────────────────────────────────────────────────────────────┐")
    print("│  TEST 4: EXTENDED RUN — 5000 CANDLES (Confluence ≥ 7)       │")
    print("└────────────────────────────────────────────────────────────────┘")

    df_long = generate_realistic_gold_data(5000, seed=777)
    r = run_backtest(df_long, 10000, min_confluence=7)

    print(f"\n  Initial Balance:       ${r['initial_balance']:>10,.2f}")
    print(f"  Final Balance:         ${r['final_balance']:>10,.2f}")
    print(f"  Total P&L:             ${r['total_pnl']:>10,.2f}")
    print(f"  Return:                {r['return_pct']:>+9.2f}%")
    print(f"  Total Trades:          {r['total_trades']:>10}")
    print(f"  Winners:               {r['winners']:>10}")
    print(f"  Losers:                {r['losers']:>10}")
    print(f"  Win Rate:              {r['win_rate']:>9.1f}%")
    print(f"  Avg Win:               ${r['avg_win']:>10,.2f}")
    print(f"  Avg Loss:              ${r['avg_loss']:>10,.2f}")
    print(f"  Reward:Risk Ratio:     {r['reward_risk']:>10.2f}")
    print(f"  Profit Factor:         {r['profit_factor']:>10.2f}")
    print(f"  Max Drawdown:          {r['max_drawdown_pct']:>9.1f}%")
    print(f"  Max Consec. Losses:    {r['max_consec_losses']:>10}")

    # ── Test 5: Stress test ─────────────────────────────────────────
    print("\n\n┌────────────────────────────────────────────────────────────────┐")
    print("│  TEST 5: STRESS TEST — 50 RUNS (Confluence ≥ 7)            │")
    print("└────────────────────────────────────────────────────────────────┘")

    worst = {"return_pct": 999}
    best = {"return_pct": -999}
    blown = 0
    all_wr = []

    for i in range(50):
        df = generate_realistic_gold_data(2000, seed=i * 13 + 3)
        r = run_backtest(df, 10000, min_confluence=7)
        if r["total_trades"] == 0:
            continue
        all_wr.append(r["win_rate"])
        if r["return_pct"] < worst["return_pct"]:
            worst = r
        if r["return_pct"] > best["return_pct"]:
            best = r
        if r["return_pct"] < -50:
            blown += 1

    print(f"\n  Best run:     {best['return_pct']:>+7.1f}% | {best['total_trades']} trades | {best['win_rate']}% win rate")
    print(f"  Worst run:    {worst['return_pct']:>+7.1f}% | {worst['total_trades']} trades | {worst['win_rate']}% win rate")
    print(f"  Avg win rate: {np.mean(all_wr):>7.1f}%")
    print(f"  Min win rate: {np.min(all_wr):>7.1f}%")
    print(f"  Max win rate: {np.max(all_wr):>7.1f}%")
    print(f"  Accounts blown (>50% loss): {blown}/50")

    print("\n" + "=" * 70)
    print("  BACKTEST COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
