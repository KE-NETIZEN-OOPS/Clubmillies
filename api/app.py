"""
ClubMillies — FastAPI backend + WebSocket for the dashboard.
"""
import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import select, func, update, desc, delete
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.database import AsyncSessionLocal, get_session, init_db
from core.models import Account, Trade, Signal, NewsEvent, AIAnalysis, Tweet
from core.events import bus
from core.datetime_eat import period_start_utc_naive
from core.trade_metrics import directional_rr, aggregate_closed_stats

logger = logging.getLogger("clubmillies.api")


def _signal_list_min_score(requested: Optional[int] = None) -> int:
    """API lists: only directional signals with score strictly greater than 5 (integer ≥ 6)."""
    if requested is not None:
        return max(6, int(requested))
    return 6


@asynccontextmanager
async def _app_lifespan(app: FastAPI):
    try:
        from core.log_redaction import install_telegram_log_redaction

        install_telegram_log_redaction()
    except Exception:
        pass
    yield


app = FastAPI(title="ClubMillies", version="1.0.0", lifespan=_app_lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── WebSocket Manager ────────────────────────────────────────────────

class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        self.active.remove(ws)

    async def broadcast(self, data: dict):
        for ws in self.active[:]:
            try:
                await ws.send_json(data)
            except Exception:
                self.active.remove(ws)

ws_manager = ConnectionManager()


async def ws_event_forwarder(event):
    """Forward all events to WebSocket clients."""
    await ws_manager.broadcast({
        "type": event.type,
        "data": event.data,
        "timestamp": event.timestamp.isoformat(),
    })

bus.subscribe_all(ws_event_forwarder)


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws_manager.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(ws)


# ── Pydantic Models ──────────────────────────────────────────────────

class AccountCreate(BaseModel):
    name: str
    broker_type: str = "paper"
    login: str = ""
    password: str = ""
    server: str = ""
    symbol: str = "XAUUSDm"
    timeframe: str = "M15"
    profile: str = "SNIPER"
    risk_per_trade: float = 0.02
    max_open_trades: int = 3
    balance: float = 10000.0

class AccountUpdate(BaseModel):
    name: Optional[str] = None
    profile: Optional[str] = None
    risk_per_trade: Optional[float] = None
    max_open_trades: Optional[int] = None
    enabled: Optional[bool] = None
    symbol: Optional[str] = None


# ── Dashboard Overview ───────────────────────────────────────────────

@app.get("/api/dashboard")
async def get_dashboard(
    period: Optional[str] = Query(
        None,
        description="Filter P&L stats: all (default), today, week, month, 3m, 6m, year",
    ),
):
    from datetime import timezone
    from core.datetime_eat import EAT

    async with AsyncSessionLocal() as session:
        # Accounts
        result = await session.execute(select(Account))
        accounts = result.scalars().all()

        # Today (calendar day in East Africa Time)
        now_eat = datetime.now(EAT)
        today_start_eat = now_eat.replace(hour=0, minute=0, second=0, microsecond=0)
        today_start_utc = today_start_eat.astimezone(timezone.utc).replace(tzinfo=None)
        result = await session.execute(
            select(Trade).where(
                Trade.status == "CLOSED",
                Trade.closed_at >= today_start_utc,
            )
        )
        todays_trades = result.scalars().all()

        result = await session.execute(select(Trade).where(Trade.status == "CLOSED"))
        all_trades = result.scalars().all()

        eff = (period or "all").lower()
        start = period_start_utc_naive(eff if eff != "all" else None)
        if start:
            period_rows = [t for t in all_trades if t.closed_at and t.closed_at >= start]
        else:
            period_rows = list(all_trades)

        sig_min = _signal_list_min_score()
        result = await session.execute(
            select(Signal)
            .where(
                Signal.signal_type.in_(["BUY", "SELL"]),
                Signal.score >= sig_min,
            )
            .order_by(desc(Signal.created_at))
            .limit(8)
        )
        recent_signals = result.scalars().all()

    total_balance = sum(a.balance for a in accounts)
    total_equity = sum(a.equity for a in accounts)
    today_pnl = sum(t.pnl or 0 for t in todays_trades)
    total_pnl = sum(t.pnl or 0 for t in all_trades)
    period_pnl = sum(t.pnl or 0 for t in period_rows)
    wins = sum(1 for t in all_trades if (t.pnl or 0) > 0)
    win_rate = (wins / len(all_trades) * 100) if all_trades else 0
    pw = sum(1 for t in period_rows if (t.pnl or 0) > 0)
    period_win_rate = (pw / len(period_rows) * 100) if period_rows else 0.0

    return {
        "total_balance": round(total_balance, 2),
        "total_equity": round(total_equity, 2),
        "today_pnl": round(today_pnl, 2),
        "total_pnl": round(total_pnl, 2),
        "period": eff,
        "period_pnl": round(period_pnl, 2),
        "period_trade_count": len(period_rows),
        "period_win_rate": round(period_win_rate, 1),
        "total_trades": len(all_trades),
        "today_trades": len(todays_trades),
        "win_rate": round(win_rate, 1),
        "active_accounts": sum(1 for a in accounts if a.enabled),
        "total_accounts": len(accounts),
        "accounts": [
            {
                "id": a.id, "name": a.name, "balance": a.balance,
                "equity": a.equity, "profile": a.profile,
                "enabled": a.enabled, "broker_type": a.broker_type,
                "symbol": a.symbol,
            }
            for a in accounts
        ],
        "recent_signals": [
            {
                "signal": s.signal_type, "score": s.score,
                "reasons": s.reasons, "price": s.price,
                "sl": s.sl, "tp": s.tp,
                "risk_reward": directional_rr(s.price, s.sl, s.tp, s.signal_type),
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in recent_signals
        ],
    }


# ── Accounts ─────────────────────────────────────────────────────────

@app.get("/api/accounts")
async def list_accounts():
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Account))
        accounts = result.scalars().all()
    return [
        {
            "id": a.id, "name": a.name, "broker_type": a.broker_type,
            "login": a.login or "",
            "server": a.server or "",
            "symbol": a.symbol, "timeframe": a.timeframe, "profile": a.profile,
            "risk_per_trade": a.risk_per_trade, "max_open_trades": a.max_open_trades,
            "balance": a.balance, "equity": a.equity,
            "starting_balance": getattr(a, "starting_balance", None) or a.balance,
            "is_demo": getattr(a, "is_demo", None),
            "enabled": a.enabled,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in accounts
    ]


@app.get("/api/accounts/{account_id}")
async def get_account(
    account_id: int,
    period: Optional[str] = Query(
        None,
        description="Stats window: all, today, week, month, 3m, 6m, year",
    ),
):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Account).where(Account.id == account_id))
        account = result.scalar_one_or_none()
        if not account:
            raise HTTPException(404, "Account not found")

        closed_all_r = await session.execute(
            select(Trade)
            .where(Trade.account_id == account_id, Trade.status == "CLOSED")
            .order_by(desc(Trade.closed_at))
            .limit(500)
        )
        closed_all = closed_all_r.scalars().all()

        eff = (period or "all").lower()
        start = period_start_utc_naive(eff if eff != "all" else None)
        if start:
            closed_trades = [t for t in closed_all if t.closed_at and t.closed_at >= start][:200]
        else:
            closed_trades = list(closed_all)[:200]

        open_r = await session.execute(
            select(Trade).where(
                Trade.account_id == account_id,
                Trade.status == "OPEN",
            )
        )
        open_trades = open_r.scalars().all()

        ai_r = await session.execute(
            select(AIAnalysis)
            .where(
                AIAnalysis.account_id == account_id,
                AIAnalysis.source == "trade_close",
            )
            .order_by(desc(AIAnalysis.created_at))
            .limit(1)
        )
        latest_perf_ai = ai_r.scalar_one_or_none()

    total_realized_all = sum(t.pnl or 0 for t in closed_all)
    total_realized = sum(t.pnl or 0 for t in closed_trades)
    base = float(account.starting_balance or account.balance or 1)
    roi_pct = round((total_realized / base) * 100, 2) if base else 0.0
    wins = sum(1 for t in closed_trades if (t.pnl or 0) > 0)
    agg = aggregate_closed_stats(closed_trades)

    def _trade_row(t: Trade):
        return {
            "id": t.id,
            "direction": t.direction,
            "entry_price": t.entry_price,
            "exit_price": t.exit_price,
            "lots": t.lots,
            "sl": t.sl,
            "tp": t.tp,
            "pnl": t.pnl,
            "close_reason": t.close_reason,
            "status": t.status,
            "opened_at": t.opened_at.isoformat() if t.opened_at else None,
            "closed_at": t.closed_at.isoformat() if t.closed_at else None,
            "mt5_position_ticket": getattr(t, "mt5_position_ticket", None),
            "risk_reward": directional_rr(t.entry_price, t.sl, t.tp, t.direction),
        }

    is_demo = account.is_demo
    if is_demo is None and account.broker_type == "paper":
        is_demo = True

    return {
        "id": account.id,
        "name": account.name,
        "broker_type": account.broker_type,
        "login": account.login or "",
        "server": account.server or "",
        "is_demo": is_demo,
        "symbol": account.symbol,
        "timeframe": account.timeframe,
        "profile": account.profile,
        "risk_per_trade": account.risk_per_trade,
        "max_open_trades": account.max_open_trades,
        "balance": account.balance,
        "equity": account.equity,
        "starting_balance": getattr(account, "starting_balance", None) or account.balance,
        "enabled": account.enabled,
        "period": eff,
        "stats": {
            "total_realized_pnl": round(total_realized, 2),
            "total_realized_pnl_all_time": round(total_realized_all, 2),
            "closed_trade_count": agg["closed_trade_count"],
            "open_trade_count": len(open_trades),
            "win_count": agg["win_count"],
            "loss_count": agg["loss_count"],
            "win_rate_pct": agg["win_rate_pct"],
            "roi_vs_starting_balance_pct": roi_pct,
            "best_trade": agg["best_trade"],
            "worst_trade": agg["worst_trade"],
            "avg_risk_reward": agg["avg_rr"],
            "profit_factor": agg["profit_factor"],
        },
        "closed_trades": [_trade_row(t) for t in closed_trades],
        "open_trades": [_trade_row(t) for t in open_trades],
        "latest_performance_ai": (
            {
                "id": latest_perf_ai.id,
                "direction": latest_perf_ai.direction,
                "confidence": latest_perf_ai.confidence,
                "reasoning": latest_perf_ai.reasoning,
                "metrics": latest_perf_ai.metrics,
                "created_at": latest_perf_ai.created_at.isoformat()
                if latest_perf_ai.created_at
                else None,
            }
            if latest_perf_ai
            else None
        ),
    }


@app.post("/api/accounts")
async def create_account(data: AccountCreate):
    async with AsyncSessionLocal() as session:
        account = Account(
            name=data.name,
            broker_type=data.broker_type,
            login=data.login,
            password=data.password,
            server=data.server,
            symbol=data.symbol,
            timeframe=data.timeframe,
            profile=data.profile,
            risk_per_trade=data.risk_per_trade,
            max_open_trades=data.max_open_trades,
            balance=data.balance,
            equity=data.balance,
            starting_balance=data.balance,
            is_demo=True if data.broker_type == "paper" else None,
        )
        session.add(account)
        await session.commit()
        await session.refresh(account)

    # If the trading engine is running, start this account immediately.
    mgr = getattr(app.state, "account_manager", None)
    if mgr and getattr(account, "enabled", False):
        try:
            await mgr.start_account(account.id)
        except Exception as e:
            logger.error(f"Failed to start account runner {account.id}: {e}")

    return {"id": account.id, "name": account.name, "status": "created"}


@app.patch("/api/accounts/{account_id}")
async def update_account(account_id: int, data: AccountUpdate):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Account).where(Account.id == account_id))
        account = result.scalar_one_or_none()
        if not account:
            raise HTTPException(404, "Account not found")

        update_data = data.dict(exclude_unset=True)
        for key, value in update_data.items():
            setattr(account, key, value)
        await session.commit()
        return {"id": account_id, "status": "updated"}


@app.delete("/api/accounts/{account_id}")
async def delete_account(account_id: int):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Account).where(Account.id == account_id))
        account = result.scalar_one_or_none()
        if not account:
            raise HTTPException(404, "Account not found")

        # Stop runner if trading engine is running
        mgr = getattr(app.state, "account_manager", None)
        if mgr:
            try:
                await mgr.stop_account(account_id)
            except Exception as e:
                logger.error(f"Failed to stop runner for account {account_id}: {e}")

        # Clean up dependent rows (SQLite FK constraints are strict).
        # Commit the deletes before removing the account to avoid SQLAlchemy trying
        # to NULL out FK columns on flush.
        await session.execute(delete(AIAnalysis).where(AIAnalysis.account_id == account_id))
        await session.execute(delete(Trade).where(Trade.account_id == account_id))
        await session.execute(delete(Signal).where(Signal.account_id == account_id))
        await session.execute(delete(Account).where(Account.id == account_id))
        await session.commit()

        return {"id": account_id, "status": "deleted"}


@app.post("/api/accounts/{account_id}/toggle")
async def toggle_account(account_id: int):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Account).where(Account.id == account_id))
        account = result.scalar_one_or_none()
        if not account:
            raise HTTPException(404, "Account not found")
        account.enabled = not account.enabled
        await session.commit()

    mgr = getattr(app.state, "account_manager", None)
    if mgr:
        try:
            if account.enabled:
                await mgr.start_account(account_id)
            else:
                await mgr.stop_account(account_id)
        except Exception as e:
            logger.error(f"Failed to toggle runner for account {account_id}: {e}")

    return {"id": account_id, "enabled": account.enabled}


# ── Trades ───────────────────────────────────────────────────────────

def _analysis_is_garbage_row(a) -> bool:
    """Hide rows saved when the API server was misconfigured (e.g. missing anthropic)."""
    r = (getattr(a, "reasoning", None) or "") + ""
    low = r.lower()
    return "no module named" in low and "anthropic" in low


@app.get("/api/trades")
async def list_trades(status: str = None, account_id: int = None, limit: int = 200):
    """
    Recent activity first: uses last activity time (close time if closed, else open time).
    Avoids hiding closed trades behind a long run of open positions (old bug: sort by opened_at only).
    """
    async with AsyncSessionLocal() as session:
        last_activity = func.coalesce(Trade.closed_at, Trade.opened_at)
        query = select(Trade)
        if account_id:
            query = query.where(Trade.account_id == account_id)
        if status:
            query = query.where(Trade.status == status)
            if status.upper() == "CLOSED":
                query = query.order_by(desc(Trade.closed_at))
            else:
                query = query.order_by(desc(Trade.opened_at))
        else:
            query = query.order_by(desc(last_activity))
        query = query.limit(limit)
        result = await session.execute(query)
        trades = result.scalars().all()

    return [
        {
            "id": t.id, "account_id": t.account_id, "direction": t.direction,
            "entry_price": t.entry_price, "exit_price": t.exit_price,
            "lots": t.lots, "sl": t.sl, "tp": t.tp, "pnl": t.pnl,
            "confluence_score": t.confluence_score,
            "confluence_reasons": t.confluence_reasons,
            "status": t.status, "close_reason": t.close_reason,
            "opened_at": t.opened_at.isoformat() if t.opened_at else None,
            "closed_at": t.closed_at.isoformat() if t.closed_at else None,
            "mt5_position_ticket": getattr(t, "mt5_position_ticket", None),
        }
        for t in trades
    ]


# ── Signals ──────────────────────────────────────────────────────────

@app.get("/api/signals")
async def list_signals(
    account_id: Optional[int] = None,
    limit: int = 50,
    min_score: Optional[int] = None,
):
    sig_min = _signal_list_min_score(min_score)
    async with AsyncSessionLocal() as session:
        query = (
            select(Signal)
            .where(
                Signal.signal_type.in_(["BUY", "SELL"]),
                Signal.score >= sig_min,
            )
            .order_by(desc(Signal.created_at))
            .limit(limit)
        )
        if account_id:
            query = query.where(Signal.account_id == account_id)
        result = await session.execute(query)
        signals = result.scalars().all()

    return [
        {
            "id": s.id, "account_id": s.account_id, "signal": s.signal_type,
            "score": s.score, "max_score": s.max_score, "reasons": s.reasons,
            "price": s.price, "sl": s.sl, "tp": s.tp,
            "risk_reward": directional_rr(s.price, s.sl, s.tp, s.signal_type),
            "rsi": s.rsi, "atr": s.atr,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s in signals
    ]


class IntelFetchBody(BaseModel):
    """One SociaVault twitter/search request per button click."""
    query: Optional[str] = None


@app.get("/api/intel/config")
async def intel_config():
    return {
        "default_query": settings.intel_default_query,
        "sociavault_configured": bool((settings.sociavault_api_key or "").strip()),
    }


@app.post("/api/intel/fetch-tweets")
async def intel_fetch_tweets(body: IntelFetchBody):
    """
    Manual only: one SociaVault search (1 credit) + persist tweets + Claude analysis.
    """
    key = (settings.sociavault_api_key or "").strip()
    if not key:
        raise HTTPException(
            503,
            "SOCIAVAULT_API_KEY is not set — add it to .env on the API server.",
        )
    q = (body.query or "").strip() or (settings.intel_default_query or "").strip()
    if not q:
        raise HTTPException(400, "Provide a non-empty query or set INTEL_DEFAULT_QUERY in .env")

    from intelligence.sociavault import fetch_twitter_search
    from intelligence.tweet_persist import persist_tweet_dicts
    from intelligence.claude_analyzer import ClaudeAnalyzer

    base = (settings.sociavault_base_url or "https://api.sociavault.com").strip()
    tweets = await fetch_twitter_search(key, q, base_url=base)
    inserted = await persist_tweet_dicts(tweets) if tweets else 0

    analyzer = ClaudeAnalyzer()
    analysis: dict
    if tweets and analyzer.enabled:
        uni_summary, per_post = await analyzer.analyze_intel_fetch_unified(tweets, search_query=q)
        if uni_summary is not None:
            analysis = uni_summary
            if per_post:
                async with AsyncSessionLocal() as session:
                    for row in per_post:
                        tid = row.get("tweet_id")
                        if not tid:
                            continue
                        await session.execute(
                            update(Tweet)
                            .where(Tweet.tweet_id == str(tid))
                            .values(
                                ai_direction=row.get("direction"),
                                ai_confidence=row.get("confidence"),
                                ai_reasoning=row.get("market_impact"),
                            )
                        )
                    await session.commit()
            tw_snip = "\n".join((t.get("text") or "")[:120] for t in tweets[:8])
            await analyzer._save_analysis(
                "twitter",
                tw_snip[:500],
                analysis,
                metrics={
                    "search_query": q,
                    "tweet_count": len(tweets),
                    "per_post_intel_count": len(per_post or []),
                },
            )
        else:
            analysis = await analyzer.analyze_tweets(tweets, search_query=q)
    elif tweets:
        analysis = {
            "direction": "neutral",
            "confidence": 0,
            "reasoning": "ANTHROPIC_API_KEY not set — tweets saved without AI summary.",
        }
    else:
        analysis = {
            "direction": "neutral",
            "confidence": 0,
            "reasoning": "No posts returned for this query (try different keywords).",
        }

    serialized = [
        {
            "tweet_id": str(t.get("id", "")),
            "author": t.get("author", ""),
            "text": t.get("text", ""),
            "url": t.get("url"),
            "source": t.get("source", "sociavault"),
        }
        for t in tweets
    ]

    return {
        "query": q,
        "sociavault_requests": 1,
        "tweets_found": len(tweets),
        "tweets_new_rows": inserted,
        "tweets": serialized,
        "analysis": analysis,
    }


@app.get("/api/intel/summary")
async def intel_summary(limit: int = Query(200, le=500, description="Max posts to load for counts + list")):
    """
    Aggregate intel: per-direction counts, net bias line, latest batch Claude summary, and tweet rows.
    """
    async with AsyncSessionLocal() as session:
        tr = await session.execute(
            select(Tweet).order_by(desc(Tweet.fetched_at)).limit(limit)
        )
        tweets = list(tr.scalars().all())
        ar = await session.execute(
            select(AIAnalysis)
            .where(AIAnalysis.source == "twitter")
            .order_by(desc(AIAnalysis.created_at))
            .limit(1)
        )
        batch = ar.scalar_one_or_none()

    counts = {"bullish": 0, "bearish": 0, "neutral": 0, "unknown": 0}
    for t in tweets:
        d = (getattr(t, "ai_direction", None) or "").strip().lower()
        if d == "bullish":
            counts["bullish"] += 1
        elif d == "bearish":
            counts["bearish"] += 1
        elif d == "neutral":
            counts["neutral"] += 1
        else:
            counts["unknown"] += 1

    tagged = counts["bullish"] + counts["bearish"] + counts["neutral"]
    if tagged == 0:
        net_bias = "unknown"
        net_summary_line = (
            "No posts have per-post AI tags yet. Run Fetch intel on the Market intel page "
            "with ANTHROPIC_API_KEY set on the API server."
        )
    else:
        b, br, n = counts["bullish"], counts["bearish"], counts["neutral"]
        if b > br and b > n:
            net_bias = "bullish"
        elif br > b and br > n:
            net_bias = "bearish"
        elif n >= b and n >= br:
            net_bias = "neutral"
        else:
            net_bias = "mixed"
        net_summary_line = (
            f"In this list, {b} post(s) lean bullish, {br} bearish, {n} neutral "
            f"(among {tagged} with tags). Net: {net_bias}."
        )

    batch_payload = None
    if batch:
        batch_payload = {
            "direction": batch.direction,
            "confidence": batch.confidence,
            "reasoning": batch.reasoning,
            "created_at": batch.created_at.isoformat() if batch.created_at else None,
        }

    return {
        "counts": counts,
        "total_posts": len(tweets),
        "tagged_posts": tagged,
        "net_bias": net_bias,
        "net_summary_line": net_summary_line,
        "batch_analysis": batch_payload,
        "tweets": [
            {
                "id": t.id,
                "tweet_id": t.tweet_id,
                "author": t.author,
                "text": t.text,
                "url": t.url,
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "fetched_at": t.fetched_at.isoformat() if t.fetched_at else None,
                "ai_direction": getattr(t, "ai_direction", None),
                "ai_confidence": getattr(t, "ai_confidence", None),
                "ai_reasoning": getattr(t, "ai_reasoning", None),
            }
            for t in tweets
        ],
    }


# ── Live snapshot (open trades + spot) ───────────────────────────────

@app.get("/api/live")
async def live_snapshot():
    """Open positions: MT5 terminal profit when engine is running; else DB + Yahoo spot estimate."""
    from intelligence.spot_price import estimate_open_pnl, fetch_xau_usd_spot

    contract_size = 100.0
    mgr = getattr(app.state, "account_manager", None)
    open_trades = []
    total_unrealized = 0.0
    used_mt5 = False
    spot: Optional[float] = None
    spot_source: Optional[str] = None

    # Prefer broker tick mid (same symbol as positions) over Yahoo for displayed spot
    if mgr and getattr(mgr, "runners", None):
        for _aid, runner in mgr.runners.items():
            if runner.broker_type != "mt5" or not runner.broker:
                continue
            await asyncio.to_thread(runner.broker.tick)
            if hasattr(runner.broker, "get_mid_price"):
                mid = await asyncio.to_thread(runner.broker.get_mid_price)
                if mid:
                    spot = float(mid)
                    spot_source = "mt5"
                    break
    if spot is None:
        spot = await fetch_xau_usd_spot()
        if spot is not None:
            spot_source = "yahoo"

    if mgr and getattr(mgr, "runners", None):
        async with AsyncSessionLocal() as session:
            acc_r = await session.execute(select(Account))
            acc_by_id = {a.id: a for a in acc_r.scalars().all()}
        for aid, runner in mgr.runners.items():
            if runner.broker_type != "mt5" or not runner.broker:
                continue
            await asyncio.to_thread(runner.broker.tick)
            sym = getattr(runner.broker, "symbol", "") or ""
            aname = acc_by_id.get(aid)
            name = aname.name if aname else f"#{aid}"
            for p in runner.broker.positions or []:
                used_mt5 = True
                profit = float(p.get("profit", 0) or 0)
                total_unrealized += profit
                open_trades.append({
                    "id": int(p.get("ticket", 0)),
                    "account_id": aid,
                    "account_name": name,
                    "direction": p.get("direction"),
                    "entry_price": p.get("entry"),
                    "lots": p.get("lots"),
                    "sl": p.get("sl"),
                    "tp": p.get("tp"),
                    "confluence_score": None,
                    "unrealized_pnl": round(profit, 2),
                    "opened_at": None,
                    "mt5_position_ticket": int(p.get("ticket", 0)),
                    "symbol": sym,
                    "source": "mt5",
                })

    if not used_mt5:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Trade)
                .where(Trade.status == "OPEN")
                .order_by(desc(Trade.opened_at))
                .limit(40)
            )
            rows = result.scalars().all()
        for t in rows:
            u = None
            if spot and t.entry_price and t.direction:
                u = estimate_open_pnl(
                    t.direction,
                    float(t.entry_price),
                    float(t.lots or 0),
                    contract_size,
                    float(spot),
                )
                u = round(u, 2)
                total_unrealized += u
            open_trades.append({
                "id": t.id,
                "account_id": t.account_id,
                "account_name": None,
                "direction": t.direction,
                "entry_price": t.entry_price,
                "lots": t.lots,
                "sl": t.sl,
                "tp": t.tp,
                "confluence_score": t.confluence_score,
                "unrealized_pnl": u,
                "opened_at": t.opened_at.isoformat() if t.opened_at else None,
                "mt5_position_ticket": getattr(t, "mt5_position_ticket", None),
                "symbol": None,
                "source": "db_estimate",
            })

    return {
        "spot_xauusd": spot,
        "spot_source": spot_source,
        "open_trades": open_trades,
        "total_unrealized_pnl": round(total_unrealized, 2),
        "updated_at": datetime.utcnow().isoformat(),
        "source": "mt5" if used_mt5 else "db_estimate",
    }


# ── News & AI ────────────────────────────────────────────────────────

@app.get("/api/news")
async def list_news(limit: int = 20):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(NewsEvent).order_by(desc(NewsEvent.event_time)).limit(limit)
        )
        events = result.scalars().all()

    return [
        {
            "id": n.id, "title": n.title, "currency": n.currency,
            "impact": n.impact, "forecast": n.forecast,
            "previous": n.previous, "actual": n.actual,
            "event_time": n.event_time.isoformat() if n.event_time else None,
        }
        for n in events
    ]


@app.post("/api/news/{news_id}/analyze")
async def analyze_news_item(news_id: int):
    """On-demand Claude analysis for one calendar row + surrounding events (XAU/USD focus)."""
    from intelligence.claude_analyzer import ClaudeAnalyzer

    async with AsyncSessionLocal() as session:
        r = await session.execute(select(NewsEvent).where(NewsEvent.id == news_id))
        row = r.scalar_one_or_none()
        if not row:
            raise HTTPException(404, "News event not found")
        cal_r = await session.execute(
            select(NewsEvent).order_by(NewsEvent.event_time).limit(40)
        )
        cal = cal_r.scalars().all()

    ev = {
        "id": row.id,
        "title": row.title,
        "currency": row.currency,
        "impact": row.impact,
        "forecast": row.forecast,
        "previous": row.previous,
        "actual": row.actual,
        "event_time": row.event_time.isoformat() if row.event_time else None,
    }
    cal_dicts = [
        {
            "id": n.id,
            "title": n.title,
            "currency": n.currency,
            "impact": n.impact,
            "forecast": n.forecast,
            "previous": n.previous,
            "actual": n.actual,
            "event_time": n.event_time.isoformat() if n.event_time else None,
        }
        for n in cal
    ]
    analyzer = ClaudeAnalyzer()
    if not analyzer.enabled:
        raise HTTPException(503, "ANTHROPIC_API_KEY is not set on the API server.")
    result = await analyzer.analyze_news_item_with_calendar(ev, cal_dicts)
    return {"analysis": result, "event": ev}


@app.get("/api/ai-analyses")
async def list_analyses(limit: int = 20, account_id: Optional[int] = None):
    async with AsyncSessionLocal() as session:
        query = (
            select(AIAnalysis)
            .order_by(desc(AIAnalysis.created_at))
            .limit(max(limit * 4, 40))
        )
        if account_id is not None:
            query = query.where(AIAnalysis.account_id == account_id)
        result = await session.execute(query)
        raw = result.scalars().all()
        analyses = [a for a in raw if not _analysis_is_garbage_row(a)][:limit]

    return [
        {
            "id": a.id,
            "source": a.source,
            "account_id": getattr(a, "account_id", None),
            "trade_id": getattr(a, "trade_id", None),
            "direction": a.direction,
            "confidence": a.confidence,
            "reasoning": a.reasoning,
            "metrics": getattr(a, "metrics", None),
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in analyses
    ]


@app.get("/api/tweets")
async def list_tweets(limit: int = 30):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Tweet).order_by(desc(Tweet.fetched_at)).limit(limit)
        )
        tweets = result.scalars().all()

    return [
        {
            "id": t.id,
            "tweet_id": t.tweet_id,
            "author": t.author,
            "text": t.text,
            "url": t.url,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "fetched_at": t.fetched_at.isoformat() if t.fetched_at else None,
            "ai_direction": getattr(t, "ai_direction", None),
            "ai_confidence": getattr(t, "ai_confidence", None),
            "ai_reasoning": getattr(t, "ai_reasoning", None),
        }
        for t in tweets
    ]


# ── Stats ────────────────────────────────────────────────────────────

@app.get("/api/stats")
async def get_stats():
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Trade).where(Trade.status == "CLOSED"))
        trades = result.scalars().all()

    if not trades:
        return {"total_trades": 0, "win_rate": 0, "total_pnl": 0, "profit_factor": 0}

    wins = [t for t in trades if (t.pnl or 0) > 0]
    losses = [t for t in trades if (t.pnl or 0) <= 0]
    total_wins = sum(t.pnl or 0 for t in wins)
    total_losses = abs(sum(t.pnl or 0 for t in losses))

    return {
        "total_trades": len(trades),
        "winners": len(wins),
        "losers": len(losses),
        "win_rate": round(len(wins) / len(trades) * 100, 1),
        "total_pnl": round(sum(t.pnl or 0 for t in trades), 2),
        "avg_win": round(total_wins / len(wins), 2) if wins else 0,
        "avg_loss": round(total_losses / len(losses), 2) if losses else 0,
        "profit_factor": round(total_wins / total_losses, 2) if total_losses > 0 else 99,
        "best_trade": round(max((t.pnl or 0) for t in trades), 2),
        "worst_trade": round(min((t.pnl or 0) for t in trades), 2),
    }
