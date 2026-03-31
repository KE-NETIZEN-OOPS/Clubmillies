"""
MetaTrader 5 client for JustMarkets Gold bot.
Wraps the MetaTrader5 Python package.

Requirements:
  - Windows OS (or Wine on Linux)
  - MetaTrader 5 terminal installed & logged in
  - pip install MetaTrader5
"""
import logging
from datetime import datetime

import MetaTrader5 as mt5
import pandas as pd

import config

logger = logging.getLogger("gold_bot")

TIMEFRAME_MAP = {
    "M1": mt5.TIMEFRAME_M1,
    "M5": mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "M30": mt5.TIMEFRAME_M30,
    "H1": mt5.TIMEFRAME_H1,
    "H4": mt5.TIMEFRAME_H4,
    "D1": mt5.TIMEFRAME_D1,
    "W1": mt5.TIMEFRAME_W1,
}


class MT5Client:
    def __init__(self):
        self.connected = False

    def connect(self) -> bool:
        """Initialize MT5 and log in to JustMarkets."""
        if not mt5.initialize():
            logger.error(f"MT5 init failed: {mt5.last_error()}")
            return False

        if config.MT5_LOGIN:
            authorized = mt5.login(
                login=config.MT5_LOGIN,
                password=config.MT5_PASSWORD,
                server=config.MT5_SERVER,
            )
            if not authorized:
                logger.error(f"MT5 login failed: {mt5.last_error()}")
                mt5.shutdown()
                return False

        self.connected = True
        info = mt5.account_info()
        logger.info(f"Connected to {info.server} | Account: {info.login} | "
                     f"Balance: ${info.balance:.2f} | Leverage: 1:{info.leverage}")
        return True

    def disconnect(self):
        mt5.shutdown()
        self.connected = False

    def get_account_info(self) -> dict:
        info = mt5.account_info()
        return {
            "login": info.login,
            "balance": info.balance,
            "equity": info.equity,
            "margin": info.margin,
            "free_margin": info.margin_free,
            "leverage": info.leverage,
            "profit": info.profit,
            "server": info.server,
        }

    def get_balance(self) -> float:
        return mt5.account_info().balance

    def get_candles(self, symbol: str = None, timeframe: str = None,
                    count: int = None) -> pd.DataFrame:
        symbol = symbol or config.SYMBOL
        timeframe = timeframe or config.TIMEFRAME
        count = count or config.CANDLE_COUNT

        tf = TIMEFRAME_MAP.get(timeframe, mt5.TIMEFRAME_M15)
        rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)

        if rates is None or len(rates) == 0:
            logger.error(f"No candle data for {symbol}: {mt5.last_error()}")
            return pd.DataFrame()

        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        df.rename(columns={
            "open": "open", "high": "high", "low": "low",
            "close": "close", "tick_volume": "volume",
        }, inplace=True)
        return df[["time", "open", "high", "low", "close", "volume"]]

    def get_price(self, symbol: str = None) -> dict:
        symbol = symbol or config.SYMBOL
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            logger.error(f"No tick data for {symbol}")
            return {}
        return {
            "bid": tick.bid,
            "ask": tick.ask,
            "spread": round(tick.ask - tick.bid, 2),
            "time": datetime.fromtimestamp(tick.time),
        }

    def get_symbol_info(self, symbol: str = None) -> dict:
        symbol = symbol or config.SYMBOL
        info = mt5.symbol_info(symbol)
        if info is None:
            logger.error(f"Symbol {symbol} not found. Check Market Watch.")
            return {}
        return {
            "name": info.name,
            "point": info.point,
            "digits": info.digits,
            "trade_contract_size": info.trade_contract_size,
            "volume_min": info.volume_min,
            "volume_max": info.volume_max,
            "volume_step": info.volume_step,
        }

    def get_open_positions(self, symbol: str = None) -> list:
        symbol = symbol or config.SYMBOL
        positions = mt5.positions_get(symbol=symbol)
        if positions is None:
            return []
        return [
            {
                "ticket": p.ticket,
                "type": "BUY" if p.type == mt5.ORDER_TYPE_BUY else "SELL",
                "volume": p.volume,
                "price_open": p.price_open,
                "sl": p.sl,
                "tp": p.tp,
                "profit": p.profit,
                "symbol": p.symbol,
            }
            for p in positions
        ]

    def place_order(self, order_type: str, volume: float,
                    sl: float = 0.0, tp: float = 0.0,
                    symbol: str = None) -> dict:
        """Place a market order. order_type: 'BUY' or 'SELL'."""
        symbol = symbol or config.SYMBOL
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return {"error": f"No tick for {symbol}"}

        if order_type == "BUY":
            mt5_type = mt5.ORDER_TYPE_BUY
            price = tick.ask
        else:
            mt5_type = mt5.ORDER_TYPE_SELL
            price = tick.bid

        # Get symbol info for digits
        sym_info = mt5.symbol_info(symbol)
        digits = sym_info.digits if sym_info else 2

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": mt5_type,
            "price": price,
            "sl": round(sl, digits),
            "tp": round(tp, digits),
            "deviation": 20,  # max slippage in points
            "magic": 123456,  # bot identifier
            "comment": "GoldBot",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(f"Order failed: {result.retcode} — {result.comment}")
            return {"error": result.comment, "retcode": result.retcode}

        logger.info(f"Order placed: {order_type} {volume} lots {symbol} @ {price:.2f} "
                     f"| SL={sl:.2f} TP={tp:.2f} | Ticket: {result.order}")
        return {
            "ticket": result.order,
            "price": price,
            "volume": volume,
            "type": order_type,
        }

    def close_position(self, ticket: int) -> dict:
        """Close a position by ticket number."""
        positions = mt5.positions_get(ticket=ticket)
        if not positions:
            return {"error": f"Position {ticket} not found"}

        pos = positions[0]
        symbol = pos.symbol
        tick = mt5.symbol_info_tick(symbol)

        if pos.type == mt5.ORDER_TYPE_BUY:
            close_type = mt5.ORDER_TYPE_SELL
            price = tick.bid
        else:
            close_type = mt5.ORDER_TYPE_BUY
            price = tick.ask

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": pos.volume,
            "type": close_type,
            "position": ticket,
            "price": price,
            "deviation": 20,
            "magic": 123456,
            "comment": "GoldBot close",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(f"Close failed: {result.retcode} — {result.comment}")
            return {"error": result.comment}

        logger.info(f"Closed position {ticket} @ {price:.2f}")
        return {"ticket": ticket, "close_price": price}
