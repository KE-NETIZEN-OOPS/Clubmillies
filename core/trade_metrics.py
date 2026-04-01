"""Trade-level risk/reward and aggregate stats from closed trades."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.models import Trade


def directional_rr(
    price: float | None,
    sl: float | None,
    tp: float | None,
    direction: str | None,
) -> float | None:
    """Reward/risk ratio from entry vs SL and TP (same units as price)."""
    if price is None or sl is None or tp is None or not direction:
        return None
    d = direction.upper()
    try:
        p, s, t = float(price), float(sl), float(tp)
    except (TypeError, ValueError):
        return None
    if d == "BUY":
        risk = abs(p - s)
        reward = abs(t - p)
    elif d == "SELL":
        risk = abs(s - p)
        reward = abs(p - t)
    else:
        return None
    if risk < 1e-9:
        return None
    return round(reward / risk, 2)


def aggregate_closed_stats(closed: list[Any]) -> dict:
    """closed: iterable of objects with pnl, entry_price, sl, tp, direction."""
    if not closed:
        return {
            "total_realized_pnl": 0.0,
            "closed_trade_count": 0,
            "win_count": 0,
            "loss_count": 0,
            "win_rate_pct": 0.0,
            "best_trade": 0.0,
            "worst_trade": 0.0,
            "avg_rr": None,
            "profit_factor": None,
        }
    pnls = [float(getattr(t, "pnl", 0) or 0) for t in closed]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    total_win = sum(wins)
    total_loss = abs(sum(losses))
    rr_vals = []
    for t in closed:
        rr = directional_rr(
            getattr(t, "entry_price", None),
            getattr(t, "sl", None),
            getattr(t, "tp", None),
            getattr(t, "direction", None),
        )
        if rr is not None:
            rr_vals.append(rr)
    return {
        "total_realized_pnl": round(sum(pnls), 2),
        "closed_trade_count": len(closed),
        "win_count": len(wins),
        "loss_count": len(losses),
        "win_rate_pct": round(len(wins) / len(closed) * 100, 1) if closed else 0.0,
        "best_trade": round(max(pnls), 2),
        "worst_trade": round(min(pnls), 2),
        "avg_rr": round(sum(rr_vals) / len(rr_vals), 2) if rr_vals else None,
        "profit_factor": round(total_win / total_loss, 2) if total_loss > 0 else None,
    }
