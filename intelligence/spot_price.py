"""
Best-effort XAU/USD spot for dashboard live P/L estimates (no API key).
"""
from __future__ import annotations

import logging
from typing import Optional

import httpx

logger = logging.getLogger("clubmillies.spot")


async def fetch_xau_usd_spot() -> Optional[float]:
    """Yahoo Finance chart API for GC=F (gold futures ~ spot)."""
    url = "https://query1.finance.yahoo.com/v8/finance/chart/GC=F?interval=1m&range=1d"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ClubMillies/1.0",
        "Accept": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=12, headers=headers) as client:
            r = await client.get(url)
            if r.status_code != 200:
                return None
            data = r.json()
            res = data.get("chart", {}).get("result")
            if not res:
                return None
            meta = res[0].get("meta", {})
            price = meta.get("regularMarketPrice") or meta.get("previousClose")
            return float(price) if price is not None else None
    except Exception as e:
        logger.debug(f"Spot price fetch failed: {e}")
        return None


def estimate_open_pnl(
    direction: str,
    entry: float,
    lots: float,
    contract_size: float,
    spot: float,
) -> float:
    """Unrealized P/L in account currency (approximate for XAU CFD)."""
    if spot <= 0 or entry <= 0:
        return 0.0
    if direction == "BUY":
        return (spot - entry) * lots * contract_size
    return (entry - spot) * lots * contract_size
