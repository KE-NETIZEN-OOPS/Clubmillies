"""
ClubMillies — Multi-Account async trading engine.
Each account runs its own independent trading loop.
"""
import asyncio
import logging
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import AsyncSessionLocal
from core.models import Account, Trade, Signal
from core.events import bus, TRADE_OPENED, TRADE_CLOSED, SIGNAL_GENERATED, ACCOUNT_UPDATE
from core.engine.confluence import ConfluenceEngine, prepare_dataframe
from core.config import settings

logger = logging.getLogger("clubmillies.accounts")


class PaperBroker:
    """Simulated broker for paper trading."""

    def __init__(self, balance: float = 10000.0):
        self.balance = balance
        self.positions = []
        self.price_history = []
        self._init_prices()

    def _init_prices(self):
        np.random.seed(None)
        base = 2650.0
        prices = [base]
        rl = np.random.randint(15, 40)
        trend = np.random.choice([-1.0, 0.5, 1.0, -0.5])
        c = 0
        for _ in range(149):
            c += 1
            if c >= rl:
                trend = np.random.choice([-1.2, -0.6, 0.0, 0.6, 1.2])
                rl = np.random.randint(12, 25)
                c = 0
            prices.append(prices[-1] + trend + np.random.normal(0, 1.5))

        for close in prices:
            sp = abs(np.random.normal(0, 1.2))
            self.price_history.append({
                "time": datetime.now().isoformat(),
                "open": round(close + np.random.normal(0, 0.8), 2),
                "high": round(close + sp, 2),
                "low": round(close - sp, 2),
                "close": round(close, 2),
                "volume": int(np.random.uniform(100, 1000)),
            })

    def tick(self):
        last = self.price_history[-1]["close"]
        move = np.random.normal(0, 5.0) if np.random.random() < 0.08 else np.random.normal(0, 2.0)
        c = last + move
        sp = abs(np.random.normal(0, 1.2))
        self.price_history.append({
            "time": datetime.now().isoformat(),
            "open": round(last + np.random.normal(0, 0.5), 2),
            "high": round(max(last, c) + sp, 2),
            "low": round(min(last, c) - sp, 2),
            "close": round(c, 2),
            "volume": int(np.random.uniform(100, 1000)),
        })
        if len(self.price_history) > 200:
            self.price_history = self.price_history[-200:]

    def get_candles(self, count=150):
        return pd.DataFrame(self.price_history[-count:])

    def get_price(self):
        return self.price_history[-1]["close"]


class AccountRunner:
    """Runs the trading strategy for a single account."""

    def __init__(self, account_id: int):
        self.account_id = account_id
        self.broker: Optional[PaperBroker] = None
        self.engine: Optional[ConfluenceEngine] = None
        self.running = False
        self._task: Optional[asyncio.Task] = None

    async def _load_account(self) -> Optional[Account]:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(Account).where(Account.id == self.account_id))
            return result.scalar_one_or_none()

    async def start(self):
        self.running = True
        account = await self._load_account()
        if not account:
            logger.error(f"Account {self.account_id} not found")
            return

        # Setup broker
        self.broker = PaperBroker(balance=account.balance)

        # Setup confluence engine
        profile = settings.sniper if account.profile == "SNIPER" else settings.aggressive
        self.engine = ConfluenceEngine(min_confluence=profile["min_confluence"])
        self.sl_mult = profile["atr_sl"]
        self.tp_mult = profile["atr_tp"]
        self.risk_pct = account.risk_per_trade

        logger.info(f"Account {account.name} (#{account.id}) started — {account.profile} mode")
        await bus.emit(ACCOUNT_UPDATE, {
            "account_id": account.id, "name": account.name,
            "status": "running", "balance": account.balance
        })

        while self.running:
            try:
                await self._tick(account)
                await asyncio.sleep(settings.default_poll_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Account {self.account_id} error: {e}", exc_info=True)
                await asyncio.sleep(30)

    async def stop(self):
        self.running = False
        if self._task:
            self._task.cancel()

    async def _tick(self, account: Account):
        self.broker.tick()
        df = self.broker.get_candles()

        df = prepare_dataframe(
            df, settings.ema_fast, settings.ema_slow,
            settings.rsi_period, settings.atr_period
        )

        last = df.iloc[-1]
        price = last["close"]
        atr = last["atr"]

        result = self.engine.get_signal(df)
        signal = result["signal"]
        score = result["score"]
        reasons = result["reasons"]

        # Check SL/TP on open positions
        contract_size = 100
        closed_trades = []
        remaining = []
        for pos in self.broker.positions:
            hit = False
            if pos["direction"] == "BUY":
                if price <= pos["sl"]:
                    pnl = (pos["sl"] - pos["entry"]) * pos["lots"] * contract_size
                    self.broker.balance += pnl
                    closed_trades.append({**pos, "exit": pos["sl"], "pnl": round(pnl, 2), "reason": "STOP LOSS"})
                    hit = True
                elif price >= pos["tp"]:
                    pnl = (pos["tp"] - pos["entry"]) * pos["lots"] * contract_size
                    self.broker.balance += pnl
                    closed_trades.append({**pos, "exit": pos["tp"], "pnl": round(pnl, 2), "reason": "TAKE PROFIT"})
                    hit = True
            else:
                if price >= pos["sl"]:
                    pnl = (pos["entry"] - pos["sl"]) * pos["lots"] * contract_size
                    self.broker.balance += pnl
                    closed_trades.append({**pos, "exit": pos["sl"], "pnl": round(pnl, 2), "reason": "STOP LOSS"})
                    hit = True
                elif price <= pos["tp"]:
                    pnl = (pos["entry"] - pos["tp"]) * pos["lots"] * contract_size
                    self.broker.balance += pnl
                    closed_trades.append({**pos, "exit": pos["tp"], "pnl": round(pnl, 2), "reason": "TAKE PROFIT"})
                    hit = True
            if not hit:
                remaining.append(pos)
        self.broker.positions = remaining

        # Emit closed trade events and save to DB
        for ct in closed_trades:
            await self._save_closed_trade(ct)
            await bus.emit(TRADE_CLOSED, {
                "account_id": self.account_id, "direction": ct["direction"],
                "entry": ct["entry"], "exit": ct["exit"], "pnl": ct["pnl"],
                "reason": ct["reason"], "lots": ct["lots"],
            })

        # Calculate SL/TP for the signal (even if we don't trade)
        sig_sl, sig_tp = None, None
        if signal != 0 and pd.notna(atr) and atr > 0:
            sl_dist = atr * self.sl_mult
            tp_dist = atr * self.tp_mult
            if signal == 1:
                sig_sl, sig_tp = round(price - sl_dist, 2), round(price + tp_dist, 2)
            else:
                sig_sl, sig_tp = round(price + sl_dist, 2), round(price - tp_dist, 2)

        # Save signal
        await self._save_signal(signal, score, result.get("max_score", 15), reasons, price, last.get("rsi"), atr, sig_sl, sig_tp)

        if signal != 0 and len(self.broker.positions) < 3:
            # Close opposite
            still_open = []
            for pos in self.broker.positions:
                if (signal == 1 and pos["direction"] == "SELL") or (signal == -1 and pos["direction"] == "BUY"):
                    pnl_dir = 1 if pos["direction"] == "BUY" else -1
                    pnl = (price - pos["entry"]) * pnl_dir * pos["lots"] * contract_size
                    self.broker.balance += pnl
                    await self._save_closed_trade({**pos, "exit": price, "pnl": round(pnl, 2), "reason": "REVERSAL"})
                    await bus.emit(TRADE_CLOSED, {
                        "account_id": self.account_id, "direction": pos["direction"],
                        "entry": pos["entry"], "exit": price, "pnl": round(pnl, 2),
                        "reason": "REVERSAL", "lots": pos["lots"],
                    })
                else:
                    still_open.append(pos)
            self.broker.positions = still_open

            # Open new position
            if pd.notna(atr) and atr > 0:
                sl_dist = atr * self.sl_mult
                tp_dist = atr * self.tp_mult
                risk_amount = self.broker.balance * self.risk_pct
                lots = max(0.01, min(round(risk_amount / (contract_size * sl_dist), 2), 5.0))
                direction = "BUY" if signal == 1 else "SELL"

                if signal == 1:
                    sl, tp = round(price - sl_dist, 2), round(price + tp_dist, 2)
                else:
                    sl, tp = round(price + sl_dist, 2), round(price - tp_dist, 2)

                pos = {"direction": direction, "entry": price, "lots": lots,
                       "sl": sl, "tp": tp, "score": score, "reasons": reasons}
                self.broker.positions.append(pos)

                await self._save_open_trade(pos, score, reasons)
                await bus.emit(TRADE_OPENED, {
                    "account_id": self.account_id, "direction": direction,
                    "price": price, "lots": lots, "sl": sl, "tp": tp,
                    "score": score, "reasons": reasons,
                })

        # Update account balance in DB
        async with AsyncSessionLocal() as session:
            await session.execute(
                update(Account).where(Account.id == self.account_id).values(
                    balance=round(self.broker.balance, 2),
                    equity=round(self.broker.balance + sum(
                        ((price - p["entry"]) if p["direction"] == "BUY" else (p["entry"] - price))
                        * p["lots"] * contract_size for p in self.broker.positions
                    ), 2)
                )
            )
            await session.commit()

    async def _save_open_trade(self, pos, score, reasons):
        async with AsyncSessionLocal() as session:
            trade = Trade(
                account_id=self.account_id,
                direction=pos["direction"],
                entry_price=pos["entry"],
                lots=pos["lots"],
                sl=pos["sl"],
                tp=pos["tp"],
                confluence_score=score,
                confluence_reasons=reasons,
                status="OPEN",
            )
            session.add(trade)
            await session.commit()

    async def _save_closed_trade(self, ct):
        async with AsyncSessionLocal() as session:
            # Find the open trade and close it
            result = await session.execute(
                select(Trade).where(
                    Trade.account_id == self.account_id,
                    Trade.status == "OPEN",
                    Trade.direction == ct["direction"],
                ).order_by(Trade.opened_at.desc()).limit(1)
            )
            trade = result.scalar_one_or_none()
            if trade:
                trade.exit_price = ct["exit"]
                trade.pnl = ct["pnl"]
                trade.status = "CLOSED"
                trade.close_reason = ct["reason"]
                trade.closed_at = datetime.utcnow()
                await session.commit()

    async def _save_signal(self, signal, score, max_score, reasons, price, rsi, atr, sl=None, tp=None):
        sig_type = "BUY" if signal == 1 else "SELL" if signal == -1 else "HOLD"
        async with AsyncSessionLocal() as session:
            s = Signal(
                account_id=self.account_id,
                signal_type=sig_type,
                score=score,
                max_score=max_score,
                reasons=reasons,
                price=price,
                sl=sl,
                tp=tp,
                rsi=float(rsi) if pd.notna(rsi) else None,
                atr=float(atr) if pd.notna(atr) else None,
            )
            session.add(s)
            await session.commit()

        if signal != 0:
            await bus.emit(SIGNAL_GENERATED, {
                "account_id": self.account_id, "signal": sig_type,
                "score": score, "reasons": reasons, "price": price,
                "sl": sl, "tp": tp,
            })


class AccountManager:
    """Manages all trading accounts, each running concurrently."""

    def __init__(self):
        self.runners: dict[int, AccountRunner] = {}

    async def start_all(self):
        """Start all enabled accounts from the database."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(Account).where(Account.enabled == True))
            accounts = result.scalars().all()

        for account in accounts:
            await self.start_account(account.id)

        logger.info(f"Started {len(accounts)} accounts")

    async def start_account(self, account_id: int):
        if account_id in self.runners:
            return
        runner = AccountRunner(account_id)
        self.runners[account_id] = runner
        runner._task = asyncio.create_task(runner.start())

    async def stop_account(self, account_id: int):
        runner = self.runners.pop(account_id, None)
        if runner:
            await runner.stop()

    async def stop_all(self):
        for aid in list(self.runners.keys()):
            await self.stop_account(aid)

    def get_status(self) -> dict:
        return {
            aid: {
                "running": r.running,
                "positions": len(r.broker.positions) if r.broker else 0,
                "balance": r.broker.balance if r.broker else 0,
            }
            for aid, r in self.runners.items()
        }
