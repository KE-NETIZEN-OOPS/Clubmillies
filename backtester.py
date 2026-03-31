"""
Backtester — validates the strategy on MT5 historical data.
"""
import pandas as pd
import logging
from indicators import compute_signals
from mt5_client import MT5Client
import config

logger = logging.getLogger("gold_bot")


def backtest(client: MT5Client, candle_count: int = 500) -> dict:
    """Run backtest on historical data and return performance stats."""
    df = client.get_candles(count=candle_count)

    if len(df) < config.EMA_SLOW + 10:
        print("Not enough data for backtest.")
        return {}

    df = compute_signals(
        df, config.EMA_FAST, config.EMA_SLOW,
        config.RSI_PERIOD, config.ATR_PERIOD
    )

    initial_balance = 10000.0
    balance = initial_balance
    position = 0     # +lots = long, -lots = short
    entry_price = 0.0
    sl_price = 0.0
    tp_price = 0.0
    lot_size = 0.0
    trades = []

    # Get contract size for P&L calc
    sym_info = client.get_symbol_info()
    contract_size = sym_info.get("trade_contract_size", 100)

    for i in range(config.EMA_SLOW + 5, len(df)):
        row = df.iloc[i]
        signal = int(row["signal"])
        price = row["close"]
        high = row["high"]
        low = row["low"]
        current_atr = row["atr"]

        # Check SL/TP hits on open position
        if position > 0:  # long
            if low <= sl_price:
                pnl = (sl_price - entry_price) * lot_size * contract_size
                balance += pnl
                trades.append({"type": "BUY", "entry": entry_price, "exit": sl_price, "pnl": pnl, "reason": "SL"})
                position = 0
            elif high >= tp_price:
                pnl = (tp_price - entry_price) * lot_size * contract_size
                balance += pnl
                trades.append({"type": "BUY", "entry": entry_price, "exit": tp_price, "pnl": pnl, "reason": "TP"})
                position = 0
        elif position < 0:  # short
            if high >= sl_price:
                pnl = (entry_price - sl_price) * lot_size * contract_size
                balance += pnl
                trades.append({"type": "SELL", "entry": entry_price, "exit": sl_price, "pnl": pnl, "reason": "SL"})
                position = 0
            elif low <= tp_price:
                pnl = (entry_price - tp_price) * lot_size * contract_size
                balance += pnl
                trades.append({"type": "SELL", "entry": entry_price, "exit": tp_price, "pnl": pnl, "reason": "TP"})
                position = 0

        if signal == 0 or pd.isna(current_atr) or current_atr == 0:
            continue

        # Close opposite position on signal
        if position > 0 and signal == -1:
            pnl = (price - entry_price) * lot_size * contract_size
            balance += pnl
            trades.append({"type": "BUY", "entry": entry_price, "exit": price, "pnl": pnl, "reason": "SIGNAL"})
            position = 0
        elif position < 0 and signal == 1:
            pnl = (entry_price - price) * lot_size * contract_size
            balance += pnl
            trades.append({"type": "SELL", "entry": entry_price, "exit": price, "pnl": pnl, "reason": "SIGNAL"})
            position = 0

        # Open new position
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

    # Close remaining position
    if position != 0:
        last_price = df.iloc[-1]["close"]
        if position > 0:
            pnl = (last_price - entry_price) * lot_size * contract_size
        else:
            pnl = (entry_price - last_price) * lot_size * contract_size
        balance += pnl
        trades.append({"type": "OPEN", "entry": entry_price, "exit": last_price, "pnl": pnl, "reason": "END"})

    if not trades:
        print("No trades generated.")
        return {}

    trade_df = pd.DataFrame(trades)
    winners = trade_df[trade_df["pnl"] > 0]
    losers = trade_df[trade_df["pnl"] <= 0]
    total_pnl = balance - initial_balance

    stats = {
        "initial_balance": initial_balance,
        "final_balance": round(balance, 2),
        "total_pnl": round(total_pnl, 2),
        "return_pct": round((total_pnl / initial_balance) * 100, 2),
        "total_trades": len(trades),
        "winners": len(winners),
        "losers": len(losers),
        "win_rate": round(len(winners) / len(trades) * 100, 1),
        "avg_win": round(winners["pnl"].mean(), 2) if len(winners) > 0 else 0,
        "avg_loss": round(losers["pnl"].mean(), 2) if len(losers) > 0 else 0,
        "largest_win": round(trade_df["pnl"].max(), 2),
        "largest_loss": round(trade_df["pnl"].min(), 2),
    }

    if stats["avg_loss"] != 0 and stats["losers"] > 0:
        stats["profit_factor"] = round(abs(stats["avg_win"] * stats["winners"]) /
                                        abs(stats["avg_loss"] * stats["losers"]), 2)
    else:
        stats["profit_factor"] = float("inf")

    print("\n" + "=" * 50)
    print("  BACKTEST RESULTS")
    print("=" * 50)
    for k, v in stats.items():
        label = k.replace("_", " ").title()
        print(f"  {label:.<30} {v}")
    print("=" * 50)

    return stats
