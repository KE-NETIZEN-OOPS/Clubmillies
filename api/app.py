"""
ClubMillies — FastAPI backend + WebSocket for the dashboard.
"""
import asyncio
import json
import logging
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import select, func, update, desc, delete
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.database import AsyncSessionLocal, get_session, init_db
from core.models import Account, Trade, Signal, NewsEvent, AIAnalysis, Tweet
from core.events import bus

logger = logging.getLogger("clubmillies.api")

app = FastAPI(title="ClubMillies", version="1.0.0")

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
async def get_dashboard():
    async with AsyncSessionLocal() as session:
        # Accounts
        result = await session.execute(select(Account))
        accounts = result.scalars().all()

        # Today's trades
        today = datetime.utcnow().date()
        result = await session.execute(
            select(Trade).where(
                Trade.status == "CLOSED",
                func.date(Trade.closed_at) == today,
            )
        )
        todays_trades = result.scalars().all()

        # Total stats
        result = await session.execute(
            select(Trade).where(Trade.status == "CLOSED")
        )
        all_trades = result.scalars().all()

        # Recent signals
        result = await session.execute(
            select(Signal).order_by(desc(Signal.created_at)).limit(5)
        )
        recent_signals = result.scalars().all()

    total_balance = sum(a.balance for a in accounts)
    total_equity = sum(a.equity for a in accounts)
    today_pnl = sum(t.pnl or 0 for t in todays_trades)
    total_pnl = sum(t.pnl or 0 for t in all_trades)
    wins = sum(1 for t in all_trades if (t.pnl or 0) > 0)
    win_rate = (wins / len(all_trades) * 100) if all_trades else 0

    return {
        "total_balance": round(total_balance, 2),
        "total_equity": round(total_equity, 2),
        "today_pnl": round(today_pnl, 2),
        "total_pnl": round(total_pnl, 2),
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
            "symbol": a.symbol, "timeframe": a.timeframe, "profile": a.profile,
            "risk_per_trade": a.risk_per_trade, "max_open_trades": a.max_open_trades,
            "balance": a.balance, "equity": a.equity, "enabled": a.enabled,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in accounts
    ]


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

@app.get("/api/trades")
async def list_trades(status: str = None, account_id: int = None, limit: int = 50):
    async with AsyncSessionLocal() as session:
        query = select(Trade).order_by(desc(Trade.opened_at)).limit(limit)
        if status:
            query = query.where(Trade.status == status)
        if account_id:
            query = query.where(Trade.account_id == account_id)
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
        }
        for t in trades
    ]


# ── Signals ──────────────────────────────────────────────────────────

@app.get("/api/signals")
async def list_signals(account_id: int = None, limit: int = 50):
    async with AsyncSessionLocal() as session:
        query = select(Signal).order_by(desc(Signal.created_at)).limit(limit)
        if account_id:
            query = query.where(Signal.account_id == account_id)
        result = await session.execute(query)
        signals = result.scalars().all()

    return [
        {
            "id": s.id, "account_id": s.account_id, "signal": s.signal_type,
            "score": s.score, "max_score": s.max_score, "reasons": s.reasons,
            "price": s.price, "sl": s.sl, "tp": s.tp,
            "rsi": s.rsi, "atr": s.atr,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s in signals
    ]


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


@app.get("/api/ai-analyses")
async def list_analyses(limit: int = 20):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(AIAnalysis).order_by(desc(AIAnalysis.created_at)).limit(limit)
        )
        analyses = result.scalars().all()

    return [
        {
            "id": a.id, "source": a.source, "direction": a.direction,
            "confidence": a.confidence, "reasoning": a.reasoning,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in analyses
    ]


@app.get("/api/tweets")
async def list_tweets(limit: int = 30):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Tweet).order_by(desc(Tweet.created_at)).limit(limit)
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
