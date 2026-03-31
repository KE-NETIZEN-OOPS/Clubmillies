"""
OANDA REST API v20 client for the Gold bot.
"""
import requests
import logging
from typing import Optional

logger = logging.getLogger("gold_bot")

BASE_URLS = {
    "practice": "https://api-fxpractice.oanda.com",
    "live": "https://api-fxtrade.oanda.com",
}


class OandaClient:
    def __init__(self, api_key: str, account_id: str, env: str = "practice"):
        self.api_key = api_key
        self.account_id = account_id
        self.base_url = BASE_URLS[env]
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        })

    def _get(self, path: str, params: Optional[dict] = None) -> dict:
        url = f"{self.base_url}{path}"
        resp = self.session.get(url, params=params)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, data: dict) -> dict:
        url = f"{self.base_url}{path}"
        resp = self.session.post(url, json=data)
        resp.raise_for_status()
        return resp.json()

    def get_account(self) -> dict:
        return self._get(f"/v3/accounts/{self.account_id}")

    def get_balance(self) -> float:
        acct = self.get_account()
        return float(acct["account"]["balance"])

    def get_candles(self, instrument: str, granularity: str, count: int) -> list[dict]:
        data = self._get(f"/v3/instruments/{instrument}/candles", params={
            "granularity": granularity,
            "count": count,
            "price": "M",  # mid prices
        })
        candles = []
        for c in data.get("candles", []):
            if c["complete"]:
                mid = c["mid"]
                candles.append({
                    "time": c["time"],
                    "open": float(mid["o"]),
                    "high": float(mid["h"]),
                    "low": float(mid["l"]),
                    "close": float(mid["c"]),
                    "volume": int(c["volume"]),
                })
        return candles

    def get_open_trades(self, instrument: str = None) -> list[dict]:
        data = self._get(f"/v3/accounts/{self.account_id}/openTrades")
        trades = data.get("trades", [])
        if instrument:
            trades = [t for t in trades if t["instrument"] == instrument]
        return trades

    def get_price(self, instrument: str) -> dict:
        data = self._get(f"/v3/accounts/{self.account_id}/pricing", params={
            "instruments": instrument,
        })
        price = data["prices"][0]
        return {
            "bid": float(price["bids"][0]["price"]),
            "ask": float(price["asks"][0]["price"]),
            "spread": float(price["asks"][0]["price"]) - float(price["bids"][0]["price"]),
        }

    def place_market_order(self, instrument: str, units: int,
                           sl_price: float = None, tp_price: float = None) -> dict:
        """Place a market order. units > 0 = BUY, units < 0 = SELL."""
        order = {
            "type": "MARKET",
            "instrument": instrument,
            "units": str(units),
            "timeInForce": "FOK",
        }
        if sl_price:
            order["stopLossOnFill"] = {"price": f"{sl_price:.2f}"}
        if tp_price:
            order["takeProfitOnFill"] = {"price": f"{tp_price:.2f}"}

        data = self._post(f"/v3/accounts/{self.account_id}/orders", {"order": order})
        logger.info(f"Order placed: {units} units of {instrument} | SL={sl_price} TP={tp_price}")
        return data

    def close_trade(self, trade_id: str) -> dict:
        url = f"{self.base_url}/v3/accounts/{self.account_id}/trades/{trade_id}/close"
        resp = self.session.put(url, json={"units": "ALL"})
        resp.raise_for_status()
        logger.info(f"Closed trade {trade_id}")
        return resp.json()
