"""
Gold Multi-Confluence Strategy — JustMarkets / MT5

Only trades when multiple strategies align:
  - EMA trend direction
  - Fair Value Gap retest
  - Supply/Demand zone
  - Liquidity sweep (stop hunt)
  - S/R rejection candles
  - Break of Structure (BOS)
  - Fibonacci retracement
  - RSI confirmation

Minimum confluence score required before entering a trade.
"""
import logging
import pandas as pd
from confluence_engine import ConfluenceEngine, prepare_dataframe
from mt5_client import MT5Client
import config

logger = logging.getLogger("gold_bot")


class GoldStrategy:
    def __init__(self, client: MT5Client):
        self.client = client
        self.starting_balance = None
        self.engine = ConfluenceEngine(min_confluence=config.MIN_CONFLUENCE)

    def calc_lot_size(self, balance: float, atr_value: float, price: float) -> float:
        """Calculate lot size based on risk percentage and ATR."""
        risk_amount = balance * config.RISK_PER_TRADE
        sl_distance = atr_value * config.ATR_SL_MULTIPLIER

        if sl_distance == 0:
            return config.LOT_SIZE_MIN

        sym_info = self.client.get_symbol_info()
        contract_size = sym_info.get("trade_contract_size", 100)
        volume_step = sym_info.get("volume_step", 0.01)

        lots = risk_amount / (contract_size * sl_distance)
        lots = round(lots / volume_step) * volume_step
        lots = max(config.LOT_SIZE_MIN, min(lots, config.LOT_SIZE_MAX))
        return round(lots, 2)

    def check_daily_loss_limit(self, balance: float) -> bool:
        if self.starting_balance is None:
            self.starting_balance = balance
            return False
        loss_pct = (self.starting_balance - balance) / self.starting_balance
        if loss_pct >= config.MAX_DAILY_LOSS:
            logger.warning(f"Daily loss limit hit: {loss_pct:.1%}")
            return True
        return False

    def run(self) -> dict:
        """Run one iteration of the multi-confluence strategy."""
        balance = self.client.get_balance()

        if self.check_daily_loss_limit(balance):
            return {"action": "BLOCKED", "reason": "daily loss limit"}

        open_positions = self.client.get_open_positions()
        if len(open_positions) >= config.MAX_OPEN_TRADES:
            return {"action": "SKIP", "reason": f"max open trades ({config.MAX_OPEN_TRADES})"}

        df = self.client.get_candles()
        if len(df) < config.EMA_SLOW + 30:
            return {"action": "SKIP", "reason": "not enough candle data"}

        # Apply all indicators
        df = prepare_dataframe(
            df, config.EMA_FAST, config.EMA_SLOW,
            config.RSI_PERIOD, config.ATR_PERIOD
        )

        last = df.iloc[-1]
        current_atr = last["atr"]
        current_price = last["close"]

        # Get confluence signal
        result = self.engine.get_signal(df)
        signal = result["signal"]
        score = result["score"]
        reasons = result["reasons"]

        logger.info(
            f"Price={current_price:.2f} | Score={score}/{result['max_score']} | "
            f"Signal={'BUY' if signal == 1 else 'SELL' if signal == -1 else 'NONE'} | "
            f"Reasons={', '.join(reasons) if reasons else 'none'}"
        )

        if signal == 0:
            return {"action": "HOLD", "price": current_price, "score": score,
                    "reasons": reasons, "rsi": last["rsi"]}

        # Close opposite positions
        for pos in open_positions:
            if (signal == 1 and pos["type"] == "SELL") or \
               (signal == -1 and pos["type"] == "BUY"):
                self.client.close_position(pos["ticket"])
                logger.info(f"Closed opposite position {pos['ticket']}")

        open_positions = self.client.get_open_positions()
        if len(open_positions) >= config.MAX_OPEN_TRADES:
            return {"action": "SKIP", "reason": "max trades after close"}

        tick = self.client.get_price()
        lot_size = self.calc_lot_size(balance, current_atr, current_price)
        sl_distance = current_atr * config.ATR_SL_MULTIPLIER
        tp_distance = current_atr * config.ATR_TP_MULTIPLIER

        if signal == 1:
            entry = tick["ask"]
            sl = entry - sl_distance
            tp = entry + tp_distance
            order_result = self.client.place_order("BUY", lot_size, sl, tp)
            return {"action": "BUY", "lots": lot_size, "sl": sl, "tp": tp,
                    "price": entry, "score": score, "reasons": reasons,
                    "result": order_result}

        elif signal == -1:
            entry = tick["bid"]
            sl = entry + sl_distance
            tp = entry - tp_distance
            order_result = self.client.place_order("SELL", lot_size, sl, tp)
            return {"action": "SELL", "lots": lot_size, "sl": sl, "tp": tp,
                    "price": entry, "score": score, "reasons": reasons,
                    "result": order_result}

        return {"action": "NONE"}
