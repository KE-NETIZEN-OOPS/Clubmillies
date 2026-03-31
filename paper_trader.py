"""
Paper trading mode with multi-confluence engine.
Simulates trades without connecting to MT5/broker.
"""
import time
import logging
import numpy as np
import pandas as pd
from datetime import datetime
from confluence_engine import ConfluenceEngine, prepare_dataframe
import config

logger = logging.getLogger("gold_bot")


class PaperTrader:
    def __init__(self, starting_balance: float = 10000.0):
        self.balance = starting_balance
        self.starting_balance = starting_balance
        self.positions = []
        self.trade_history = []
        self.price_history = []
        self.engine = ConfluenceEngine(min_confluence=config.MIN_CONFLUENCE)
        self._init_price_history()

    def _init_price_history(self):
        np.random.seed(None)
        base = 2650.0
        n = config.CANDLE_COUNT
        prices = [base]
        regime_len = np.random.randint(15, 40)
        trend = np.random.choice([-1.0, 0.5, 1.0, -0.5])
        counter = 0

        for _ in range(n - 1):
            counter += 1
            if counter >= regime_len:
                trend = np.random.choice([-1.2, -0.6, 0.0, 0.6, 1.2])
                regime_len = np.random.randint(12, 25)
                counter = 0
            noise = np.random.normal(0, 1.5)
            prices.append(prices[-1] + trend + noise)

        for i, close in enumerate(prices):
            spread = abs(np.random.normal(0, 1.2))
            self.price_history.append({
                "time": datetime.now().isoformat(),
                "open": round(close + np.random.normal(0, 0.8), 2),
                "high": round(close + spread, 2),
                "low": round(close - spread, 2),
                "close": round(close, 2),
                "volume": int(np.random.uniform(100, 1000)),
            })

    def _tick(self):
        last_close = self.price_history[-1]["close"]
        if np.random.random() < 0.08:
            move = np.random.normal(0, 5.0)
        else:
            move = np.random.normal(0, 2.0)
        new_close = last_close + move
        spread = abs(np.random.normal(0, 1.2))
        self.price_history.append({
            "time": datetime.now().isoformat(),
            "open": round(last_close + np.random.normal(0, 0.5), 2),
            "high": round(max(last_close, new_close) + spread, 2),
            "low": round(min(last_close, new_close) - spread, 2),
            "close": round(new_close, 2),
            "volume": int(np.random.uniform(100, 1000)),
        })
        if len(self.price_history) > config.CANDLE_COUNT + 50:
            self.price_history = self.price_history[-(config.CANDLE_COUNT + 50):]

    def _get_df(self) -> pd.DataFrame:
        return pd.DataFrame(self.price_history[-config.CANDLE_COUNT:])

    def calc_lot_size(self, atr_value: float) -> float:
        risk_amount = self.balance * config.RISK_PER_TRADE
        sl_distance = atr_value * config.ATR_SL_MULTIPLIER
        if sl_distance == 0:
            return config.LOT_SIZE_MIN
        lots = risk_amount / (100 * sl_distance)
        return max(config.LOT_SIZE_MIN, min(round(lots, 2), config.LOT_SIZE_MAX))

    def close_position(self, pos: dict, price: float, reason: str):
        contract_size = 100
        if pos["direction"] == "BUY":
            pnl = (price - pos["entry"]) * pos["lots"] * contract_size
        else:
            pnl = (pos["entry"] - price) * pos["lots"] * contract_size
        self.balance += pnl
        self.trade_history.append({
            "direction": pos["direction"],
            "entry": pos["entry"],
            "exit": price,
            "lots": pos["lots"],
            "pnl": round(pnl, 2),
            "reason": reason,
            "score": pos.get("score", 0),
            "confluence": pos.get("reasons", []),
            "time": datetime.now().isoformat(),
        })
        logger.info(f"[PAPER] Closed {pos['direction']} {pos['lots']} lots @ {price:.2f} | "
                     f"PnL: ${pnl:.2f} ({reason})")
        print(f"  <<< CLOSED {pos['direction']} {pos['lots']}L @ ${price:.2f} | "
              f"PnL: ${pnl:.2f} ({reason})")
        return pnl

    def run_once(self) -> dict:
        self._tick()
        df = self._get_df()
        df = prepare_dataframe(
            df, config.EMA_FAST, config.EMA_SLOW,
            config.RSI_PERIOD, config.ATR_PERIOD
        )

        last = df.iloc[-1]
        price = last["close"]
        current_atr = last["atr"]

        # Get confluence signal
        result = self.engine.get_signal(df)
        signal = result["signal"]
        score = result["score"]
        reasons = result["reasons"]

        signal_str = {1: "BUY", -1: "SELL", 0: "---"}[signal]
        reasons_str = ", ".join(reasons) if reasons else "none"

        print(f"\n  [{datetime.now().strftime('%H:%M:%S')}] "
              f"${price:.2f} | RSI: {last['rsi']:.1f} | "
              f"Score: {score}/{result['max_score']} | "
              f"Signal: {signal_str} | {reasons_str}")

        # Check SL/TP
        remaining = []
        for pos in self.positions:
            hit = False
            if pos["direction"] == "BUY":
                if price <= pos["sl"]:
                    self.close_position(pos, pos["sl"], "STOP LOSS")
                    hit = True
                elif price >= pos["tp"]:
                    self.close_position(pos, pos["tp"], "TAKE PROFIT")
                    hit = True
            else:
                if price >= pos["sl"]:
                    self.close_position(pos, pos["sl"], "STOP LOSS")
                    hit = True
                elif price <= pos["tp"]:
                    self.close_position(pos, pos["tp"], "TAKE PROFIT")
                    hit = True
            if not hit:
                remaining.append(pos)
        self.positions = remaining

        if signal != 0:
            still_open = []
            for pos in self.positions:
                if (signal == 1 and pos["direction"] == "SELL") or \
                   (signal == -1 and pos["direction"] == "BUY"):
                    self.close_position(pos, price, "REVERSAL")
                else:
                    still_open.append(pos)
            self.positions = still_open

            if len(self.positions) < config.MAX_OPEN_TRADES:
                lots = self.calc_lot_size(current_atr)
                sl_dist = current_atr * config.ATR_SL_MULTIPLIER
                tp_dist = current_atr * config.ATR_TP_MULTIPLIER
                direction = "BUY" if signal == 1 else "SELL"

                if signal == 1:
                    sl, tp = price - sl_dist, price + tp_dist
                else:
                    sl, tp = price + sl_dist, price - tp_dist

                pos = {"direction": direction, "entry": price, "lots": lots,
                       "sl": round(sl, 2), "tp": round(tp, 2),
                       "score": score, "reasons": reasons}
                self.positions.append(pos)
                print(f"  >>> {direction} {lots}L @ ${price:.2f} | "
                      f"SL=${sl:.2f} | TP=${tp:.2f} | "
                      f"Confluence: {score}/{result['max_score']} [{reasons_str}]")
        else:
            if self.positions:
                for pos in self.positions:
                    if pos["direction"] == "BUY":
                        unr = (price - pos["entry"]) * pos["lots"] * 100
                    else:
                        unr = (pos["entry"] - price) * pos["lots"] * 100
                    print(f"      Holding {pos['direction']} {pos['lots']}L | "
                          f"Unrealized: ${unr:.2f}")

        unrealized = sum(
            ((price - p["entry"]) if p["direction"] == "BUY" else (p["entry"] - price))
            * p["lots"] * 100 for p in self.positions
        )
        equity = self.balance + unrealized
        print(f"  Balance: ${self.balance:.2f} | Equity: ${equity:.2f} | "
              f"Open: {len(self.positions)} | Closed: {len(self.trade_history)}")

        return {"signal": signal, "price": price, "balance": self.balance, "score": score}

    def print_summary(self):
        total_pnl = self.balance - self.starting_balance
        print("\n" + "=" * 60)
        print("  PAPER TRADING SUMMARY (CONFLUENCE ENGINE)")
        print("=" * 60)
        print(f"  Min Confluence:    {config.MIN_CONFLUENCE}/{self.engine.MAX_SCORE}")
        print(f"  Starting Balance:  ${self.starting_balance:>10,.2f}")
        print(f"  Final Balance:     ${self.balance:>10,.2f}")
        print(f"  Total P&L:         ${total_pnl:>10,.2f} ({total_pnl/self.starting_balance*100:+.1f}%)")
        print(f"  Total Trades:      {len(self.trade_history):>10}")
        if self.trade_history:
            wins = [t for t in self.trade_history if t["pnl"] > 0]
            losses = [t for t in self.trade_history if t["pnl"] <= 0]
            print(f"  Winners:           {len(wins):>10}")
            print(f"  Losers:            {len(losses):>10}")
            print(f"  Win Rate:          {len(wins)/len(self.trade_history)*100:>9.1f}%")
            if wins:
                print(f"  Avg Win:           ${sum(t['pnl'] for t in wins)/len(wins):>10,.2f}")
            if losses:
                print(f"  Avg Loss:          ${sum(t['pnl'] for t in losses)/len(losses):>10,.2f}")
        print("=" * 60)
