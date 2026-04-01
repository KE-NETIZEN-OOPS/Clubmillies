"""
ClubMillies — Multi-Account async trading engine.
Each account runs its own independent trading loop.
"""
import asyncio
import logging
import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Optional

import numpy as np
import pandas as pd
from sqlalchemy import select, update, desc
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import AsyncSessionLocal
from core.models import Account, Trade, Signal, AIAnalysis
from core.events import bus, TRADE_OPENED, TRADE_CLOSED, SIGNAL_GENERATED, ACCOUNT_UPDATE
from core.engine.confluence import ConfluenceEngine, prepare_dataframe
from core.config import settings

logger = logging.getLogger("clubmillies.accounts")

# Gold: broker digits — match entry/SL/TP vs MT5 history within this (points)
_MT5_LEVEL_TOL = 0.12


def _price_match(a: Optional[float], b: Optional[float], tol: float = _MT5_LEVEL_TOL) -> bool:
    if a is None or b is None:
        return False
    return abs(float(a) - float(b)) <= tol


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


class MT5LiveBroker:
    """Real MT5 broker for live/demo trading."""

    TIMEFRAME_MAP = {}

    def __init__(self, symbol: str, timeframe: str):
        self.symbol = symbol
        self.timeframe = timeframe
        self.balance = 0.0
        self.equity = 0.0
        self.positions = []

        try:
            import MetaTrader5 as mt5
            self.mt5 = mt5
            self.TIMEFRAME_MAP = {
                "M1": mt5.TIMEFRAME_M1, "M5": mt5.TIMEFRAME_M5,
                "M15": mt5.TIMEFRAME_M15, "M30": mt5.TIMEFRAME_M30,
                "H1": mt5.TIMEFRAME_H1, "H4": mt5.TIMEFRAME_H4,
                "D1": mt5.TIMEFRAME_D1,
            }
            info = mt5.account_info()
            if info:
                self.balance = info.balance
        except ImportError:
            self.mt5 = None

    def tick(self):
        """Update balance and positions from MT5."""
        if not self.mt5:
            return
        # Ensure symbol is visible (e.g. XAUUSD.s on JustMarkets)
        try:
            si = self.mt5.symbol_info(self.symbol)
            if si is not None and not getattr(si, "visible", True):
                self.mt5.symbol_select(self.symbol, True)
        except Exception:
            pass
        info = self.mt5.account_info()
        if info:
            self.balance = info.balance
            self.equity = info.equity
        # Sync open positions
        pos = self.mt5.positions_get(symbol=self.symbol)
        self.positions = []
        if pos:
            for p in pos:
                self.positions.append({
                    "ticket": p.ticket,
                    "direction": "BUY" if p.type == 0 else "SELL",
                    "entry": p.price_open,
                    "lots": p.volume,
                    "sl": p.sl,
                    "tp": p.tp,
                    "profit": p.profit,
                })

    def get_candles(self, count=150):
        if not self.mt5:
            return pd.DataFrame()
        # TIMEFRAME constants are MetaTrader5 enums (not raw minutes).
        tf = self.TIMEFRAME_MAP.get(self.timeframe, self.mt5.TIMEFRAME_M15)
        rates = self.mt5.copy_rates_from_pos(self.symbol, tf, 0, count)
        if rates is None or len(rates) == 0:
            return pd.DataFrame()
        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        df.rename(columns={"tick_volume": "volume"}, inplace=True)
        return df[["time", "open", "high", "low", "close", "volume"]]

    def get_price(self):
        if not self.mt5:
            return 0
        tick = self.mt5.symbol_info_tick(self.symbol)
        return tick.bid if tick else 0

    def place_order(self, direction, lots, sl, tp):
        if not self.mt5:
            return None
        before = {
            p.ticket for p in (self.mt5.positions_get(symbol=self.symbol) or [])
        }
        tick = self.mt5.symbol_info_tick(self.symbol)
        if not tick:
            return None
        sym_info = self.mt5.symbol_info(self.symbol)
        digits = sym_info.digits if sym_info else 2

        if direction == "BUY":
            order_type = self.mt5.ORDER_TYPE_BUY
            price = tick.ask
        else:
            order_type = self.mt5.ORDER_TYPE_SELL
            price = tick.bid

        # Prefer symbol-specific filling mode (most reliable).
        sym_fill = getattr(sym_info, "filling_mode", None) if sym_info else None
        # For XAUUSD.s on JustMarkets, order_check passes only with FOK (0).
        # So we try FOK first, then fall back to symbol/defaults.
        preferred_fillings = [
            getattr(self.mt5, "ORDER_FILLING_FOK", None),
        ]
        if sym_fill is not None:
            preferred_fillings.append(sym_fill)
        preferred_fillings += [
            getattr(self.mt5, "ORDER_FILLING_RETURN", None),
            getattr(self.mt5, "ORDER_FILLING_IOC", None),
        ]
        preferred_fillings = [f for f in preferred_fillings if f is not None]

        base_request = {
            "action": self.mt5.TRADE_ACTION_DEAL,
            "symbol": self.symbol,
            "volume": lots,
            "type": order_type,
            "price": price,
            "sl": round(sl, digits),
            "tp": round(tp, digits),
            "deviation": 20,
            "magic": 123456,
            "comment": "ClubMillies",
            "type_time": self.mt5.ORDER_TIME_GTC,
        }

        last_result = None
        for filling in preferred_fillings:
            req = {**base_request, "type_filling": filling}
            result = self.mt5.order_send(req)
            last_result = result
            if result and result.retcode == self.mt5.TRADE_RETCODE_DONE:
                after_list = self.mt5.positions_get(symbol=self.symbol) or []
                after = {p.ticket for p in after_list}
                new_tickets = after - before
                pos_ticket = new_tickets.pop() if len(new_tickets) == 1 else None
                if pos_ticket is None and after_list:
                    for p in sorted(after_list, key=lambda x: getattr(x, "time_update", 0), reverse=True):
                        if getattr(p, "magic", 0) != 123456:
                            continue
                        if abs(float(p.volume) - float(lots)) > 0.01:
                            continue
                        want_buy = direction == "BUY"
                        if (want_buy and p.type == 0) or (not want_buy and p.type == 1):
                            pos_ticket = p.ticket
                            break
                return {"ticket": pos_ticket, "price": price}

        if last_result and getattr(last_result, "comment", ""):
            logger.error(f"MT5 order_send failed: {last_result.comment}")
        return None

    def close_position(self, ticket):
        if not self.mt5:
            return
        positions = self.mt5.positions_get(ticket=ticket)
        if not positions:
            return
        pos = positions[0]
        tick = self.mt5.symbol_info_tick(pos.symbol)
        close_type = self.mt5.ORDER_TYPE_SELL if pos.type == 0 else self.mt5.ORDER_TYPE_BUY
        price = tick.bid if pos.type == 0 else tick.ask
        sym_info = self.mt5.symbol_info(pos.symbol)
        sym_fill = getattr(sym_info, "filling_mode", None) if sym_info else None

        base_request = {
            "action": self.mt5.TRADE_ACTION_DEAL,
            "symbol": pos.symbol,
            "volume": pos.volume,
            "type": close_type,
            "position": ticket,
            "price": price,
            "deviation": 20,
            "magic": 123456,
            "comment": "ClubMillies close",
            "type_time": self.mt5.ORDER_TIME_GTC,
        }
        preferred_fillings = [
            getattr(self.mt5, "ORDER_FILLING_FOK", None),
        ]
        if sym_fill is not None:
            preferred_fillings.append(sym_fill)
        preferred_fillings += [
            getattr(self.mt5, "ORDER_FILLING_RETURN", None),
            getattr(self.mt5, "ORDER_FILLING_IOC", None),
        ]
        preferred_fillings = [f for f in preferred_fillings if f is not None]
        for filling in preferred_fillings:
            req = {**base_request, "type_filling": filling}
            res = self.mt5.order_send(req)
            if res and res.retcode == self.mt5.TRADE_RETCODE_DONE:
                return

    def match_db_trade_to_position(
        self, direction: str, entry_price: float, lots: float, tol: float = 2.0
    ) -> Optional[int]:
        if not self.mt5:
            return None
        pos_list = self.mt5.positions_get(symbol=self.symbol) or []
        for p in pos_list:
            if getattr(p, "magic", 0) != 123456:
                continue
            d = "BUY" if p.type == 0 else "SELL"
            if d != direction:
                continue
            if abs(float(p.volume) - float(lots)) > 0.02:
                continue
            if abs(float(p.price_open) - float(entry_price)) <= tol:
                return int(p.ticket)
        return None

    def fetch_closed_position_details(
        self, position_ticket: int, opened_at: datetime
    ) -> Optional[dict]:
        """Profit, exit price, and TP/SL reason from MT5 deal history.

        When a position just disappeared from the terminal, the closing deal may land in the
        history cache a tick later. We prime a **recent** time window (ending now), then pull
        deals for the position; retry briefly if empty.
        """
        if not self.mt5:
            return None
        start = opened_at
        if start.tzinfo is not None:
            start = start.replace(tzinfo=None)
        t1 = datetime.utcnow()
        day_floor = max(start - timedelta(days=1), t1 - timedelta(days=7))

        def _select_and_get() -> Optional[list]:
            mt5 = self.mt5
            # Refresh history around "now" first so the latest close is visible after disappearance
            try:
                mt5.history_deals_select(t1 - timedelta(hours=2), t1)
            except Exception:
                pass
            try:
                mt5.history_deals_select(day_floor, t1)
            except Exception:
                pass
            got = mt5.history_deals_get(day_floor, t1, position=position_ticket)
            if got is not None and len(got) > 0:
                return list(got)
            return None

        deals = _select_and_get()
        if not deals:
            time.sleep(0.35)
            t1 = datetime.utcnow()
            day_floor = max(start - timedelta(days=1), t1 - timedelta(days=7))
            deals = _select_and_get()
        if not deals:
            time.sleep(0.45)
            t1 = datetime.utcnow()
            try:
                self.mt5.history_deals_select(t1 - timedelta(days=1), t1)
            except Exception:
                pass
            got = self.mt5.history_deals_get(t1 - timedelta(days=1), t1, position=position_ticket)
            deals = list(got) if got else None
        if not deals:
            return None
        deals = sorted(deals, key=lambda d: int(getattr(d, "time", 0)))
        mt5 = self.mt5
        entry_out = int(getattr(mt5, "DEAL_ENTRY_OUT", 1))
        closing = [d for d in deals if int(getattr(d, "entry", -1)) == entry_out]
        exit_deal = closing[-1] if closing else deals[-1]
        exit_price = float(exit_deal.price)
        exit_reason = int(getattr(exit_deal, "reason", -1))
        total = 0.0
        for d in deals:
            total += float(d.profit) + float(d.swap) + float(d.commission)
        # MetaTrader5: DEAL_REASON_SL=4, DEAL_REASON_TP=5 (always use live enums)
        sl_code = int(getattr(mt5, "DEAL_REASON_SL", 4))
        tp_code = int(getattr(mt5, "DEAL_REASON_TP", 5))
        if exit_reason == sl_code:
            reason_str = "SL"
        elif exit_reason == tp_code:
            reason_str = "TP"
        else:
            reason_str = "CLIENT"
        closed_at = datetime.utcfromtimestamp(int(exit_deal.time))
        return {
            "exit_price": exit_price,
            "pnl": round(total, 2),
            "close_reason": reason_str,
            "closed_at": closed_at,
        }

    def get_mid_price(self) -> Optional[float]:
        """Broker bid/ask mid for charted symbol (matches open P/L context)."""
        if not self.mt5:
            return None
        t = self.mt5.symbol_info_tick(self.symbol)
        if t is None or not t.bid or not t.ask:
            return None
        return round((float(t.bid) + float(t.ask)) / 2.0, 2)

    def _sl_tp_from_orders(self, position_id: int, t0: datetime, t1: datetime) -> tuple[Optional[float], Optional[float]]:
        """Best-effort SL/TP from history orders for this position id."""
        if not self.mt5:
            return None, None
        try:
            orders = self.mt5.history_orders_get(t0, t1)
        except Exception:
            return None, None
        if not orders:
            return None, None
        for o in orders:
            op = getattr(o, "position_id", None)
            if op is None:
                op = getattr(o, "position", None)
            if op is not None and int(op) == int(position_id):
                sl = getattr(o, "sl", None)
                tp = getattr(o, "tp", None)
                if sl is not None and tp is not None:
                    return float(sl), float(tp)
        return None, None

    def list_closed_round_trips_from_history(self, days: int = 21) -> list[dict[str, Any]]:
        """
        Scan MT5 deal history for fully closed round-trips (our magic / ClubMillies comment)
        on this symbol. Used to backfill DB and verify closes vs terminal.
        """
        if not self.mt5:
            return []
        mt5 = self.mt5
        t1 = datetime.utcnow()
        t0 = t1 - timedelta(days=days)
        try:
            mt5.history_deals_select(t0, t1)
        except Exception:
            pass
        raw = mt5.history_deals_get(t0, t1)
        if not raw:
            return []
        entry_in = int(getattr(mt5, "DEAL_ENTRY_IN", 0))
        entry_out = int(getattr(mt5, "DEAL_ENTRY_OUT", 1))
        dt_buy = int(getattr(mt5, "DEAL_TYPE_BUY", 0))
        sl_code = int(getattr(mt5, "DEAL_REASON_SL", 4))
        tp_code = int(getattr(mt5, "DEAL_REASON_TP", 5))
        by_pos: dict[int, list] = defaultdict(list)
        for d in raw:
            if getattr(d, "symbol", None) != self.symbol:
                continue
            magic = int(getattr(d, "magic", 0) or 0)
            comment = (getattr(d, "comment", None) or "") + ""
            if magic != 123456 and "ClubMillies" not in comment:
                continue
            pid = getattr(d, "position_id", None)
            if pid is None:
                pid = getattr(d, "position", None)
            if pid is None or int(pid) == 0:
                continue
            by_pos[int(pid)].append(d)

        out: list[dict[str, Any]] = []
        for position_id, deals in by_pos.items():
            deals = sorted(deals, key=lambda x: int(getattr(x, "time", 0)))
            ins = [d for d in deals if int(getattr(d, "entry", -99)) == entry_in]
            outs = [d for d in deals if int(getattr(d, "entry", -99)) == entry_out]
            if not ins or not outs:
                continue
            vol_in = sum(float(d.volume) for d in ins)
            vol_out = sum(float(d.volume) for d in outs)
            if abs(vol_in - vol_out) > 0.02:
                continue
            d_in = ins[0]
            d_exit = outs[-1]
            direction = "BUY" if int(getattr(d_in, "type", -1)) == dt_buy else "SELL"
            entry = float(d_in.price)
            exit_px = float(d_exit.price)
            total = 0.0
            for d in deals:
                total += float(d.profit) + float(d.swap) + float(d.commission)
            er = int(getattr(d_exit, "reason", -1))
            if er == sl_code:
                reason = "SL"
            elif er == tp_code:
                reason = "TP"
            else:
                reason = "CLIENT"
            opened_at = datetime.utcfromtimestamp(int(d_in.time))
            closed_at = datetime.utcfromtimestamp(int(d_exit.time))
            sl_o, tp_o = self._sl_tp_from_orders(position_id, t0, t1)
            sl_f = sl_o if sl_o is not None else float(getattr(d_in, "sl", 0.0) or 0.0)
            tp_f = tp_o if tp_o is not None else float(getattr(d_in, "tp", 0.0) or 0.0)
            out.append(
                {
                    "position_id": position_id,
                    "direction": direction,
                    "entry": round(entry, 5),
                    "exit": round(exit_px, 5),
                    "lots": round(vol_in, 2),
                    "sl": round(sl_f, 5),
                    "tp": round(tp_f, 5),
                    "pnl": round(total, 2),
                    "close_reason": reason,
                    "opened_at": opened_at,
                    "closed_at": closed_at,
                }
            )
        out.sort(key=lambda r: r["closed_at"], reverse=True)
        return out


class AccountRunner:
    """Runs the trading strategy for a single account."""

    def __init__(self, account_id: int):
        self.account_id = account_id
        self.broker = None
        self.broker_type = "paper"
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

        # Setup broker based on account type
        self.broker_type = account.broker_type
        if account.broker_type == "mt5":
            try:
                self.broker = await self._connect_mt5(account)
                if not self.broker:
                    logger.error(f"MT5 connection failed for {account.name} — disabling account")
                    await self._disable_account(account.id, reason="MT5 connection failed")
                    return
            except Exception as e:
                logger.error(f"MT5 error: {e} — disabling account")
                await self._disable_account(account.id, reason=f"MT5 error: {e}")
                return
        else:
            self.broker = PaperBroker(balance=account.balance)

        # Setup confluence engine (never below global floor)
        profile = settings.sniper if account.profile == "SNIPER" else settings.aggressive
        eff_min = max(
            int(profile["min_confluence"]),
            int(settings.min_confluence_floor),
        )
        self.engine = ConfluenceEngine(min_confluence=eff_min)
        self.sl_mult = profile["atr_sl"]
        self.tp_mult = profile["atr_tp"]
        self.risk_pct = account.risk_per_trade

        broker_label = "MT5 LIVE" if self.broker_type == "mt5" else "PAPER"
        logger.info(f"Account {account.name} (#{account.id}) started — {account.profile} mode [{broker_label}]")
        await bus.emit(ACCOUNT_UPDATE, {
            "account_id": account.id, "name": account.name,
            "status": "running", "balance": self.broker.balance,
            "broker": broker_label,
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

    async def _connect_mt5(self, account):
        """Connect to MetaTrader 5 — only works on Windows."""
        try:
            import MetaTrader5 as mt5
        except ImportError:
            logger.warning("MetaTrader5 package not installed — pip install MetaTrader5 (Windows only)")
            return None

        success = await asyncio.to_thread(mt5.initialize)
        if not success:
            logger.error(f"MT5 init failed: {mt5.last_error()}")
            return None

        authorized = await asyncio.to_thread(
            mt5.login,
            login=int(account.login),
            password=account.password,
            server=account.server,
        )
        if not authorized:
            logger.error(f"MT5 login failed: {mt5.last_error()}")
            await asyncio.to_thread(mt5.shutdown)
            return None

        info = await asyncio.to_thread(mt5.account_info)
        logger.info(f"MT5 connected: {info.server} | Account: {info.login} | Balance: ${info.balance:.2f}")

        trade_mode = int(getattr(info, "trade_mode", 2))
        is_demo = trade_mode in (0, 1)

        async with AsyncSessionLocal() as session:
            result = await session.execute(select(Account).where(Account.id == account.id))
            acc_row = result.scalar_one_or_none()
            extras = {}
            if acc_row and (
                acc_row.starting_balance is None or float(acc_row.starting_balance) <= 0
            ):
                extras["starting_balance"] = float(info.balance)
            await session.execute(
                update(Account).where(Account.id == account.id).values(
                    balance=info.balance,
                    equity=info.equity,
                    is_demo=is_demo,
                    **extras,
                )
            )
            await session.commit()

        return MT5LiveBroker(account.symbol or "XAUUSDm", account.timeframe or "M15")

    async def _disable_account(self, account_id: int, reason: str):
        async with AsyncSessionLocal() as session:
            await session.execute(
                update(Account).where(Account.id == account_id).values(enabled=False)
            )
            await session.commit()
        await bus.emit(ACCOUNT_UPDATE, {
            "account_id": account_id,
            "status": "disabled",
            "reason": reason,
        })

    async def stop(self):
        self.running = False
        if self._task:
            self._task.cancel()

    async def _sync_mt5_closed_trades(self, account: Account):
        """Detect MT5 positions closed by TP/SL (or externally) and persist to DB."""
        if self.broker_type != "mt5" or not self.broker or not getattr(self.broker, "mt5", None):
            return
        current = {p["ticket"] for p in self.broker.positions}
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Trade).where(
                    Trade.account_id == self.account_id,
                    Trade.status == "OPEN",
                )
            )
            open_rows = list(result.scalars().all())

        for t in open_rows:
            tid = t.mt5_position_ticket
            if tid and tid not in current:
                detail = await asyncio.to_thread(
                    self.broker.fetch_closed_position_details, tid, t.opened_at
                )
                if not detail:
                    logger.warning(
                        f"MT5 position {tid} gone but no history — closing trade {t.id} as CLIENT"
                    )
                    detail = {
                        "exit_price": t.tp or t.sl or t.entry_price,
                        "pnl": 0.0,
                        "close_reason": "CLIENT",
                        "closed_at": None,
                    }
                await self._save_closed_trade(
                    {
                        "trade_id": t.id,
                        "mt5_ticket": tid,
                        "direction": t.direction,
                        "entry": t.entry_price,
                        "lots": t.lots,
                        "exit": detail["exit_price"],
                        "pnl": detail["pnl"],
                        "reason": detail["close_reason"],
                        "closed_at": detail.get("closed_at"),
                    }
                )
                continue
            if not tid:
                match = await asyncio.to_thread(
                    self.broker.match_db_trade_to_position,
                    t.direction,
                    float(t.entry_price or 0),
                    float(t.lots or 0),
                )
                if match:
                    async with AsyncSessionLocal() as session:
                        await session.execute(
                            update(Trade)
                            .where(Trade.id == t.id)
                            .values(mt5_position_ticket=match)
                        )
                        await session.commit()

    async def _align_open_trades_with_terminal(self, account: Account):
        """Keep DB entry / SL / TP in sync with live MT5 positions (exact broker levels)."""
        if self.broker_type != "mt5" or not self.broker or not getattr(self.broker, "positions", None):
            return
        by_ticket = {int(p["ticket"]): p for p in self.broker.positions}
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Trade).where(
                    Trade.account_id == self.account_id,
                    Trade.status == "OPEN",
                )
            )
            rows = list(result.scalars().all())
        for t in rows:
            tid = t.mt5_position_ticket
            if not tid or int(tid) not in by_ticket:
                continue
            p = by_ticket[int(tid)]
            e, sl, tp = float(p["entry"]), float(p["sl"]), float(p["tp"])
            if not (
                _price_match(t.entry_price, e, _MT5_LEVEL_TOL)
                and _price_match(t.sl, sl, _MT5_LEVEL_TOL)
                and _price_match(t.tp, tp, _MT5_LEVEL_TOL)
            ):
                async with AsyncSessionLocal() as session:
                    await session.execute(
                        update(Trade)
                        .where(Trade.id == t.id)
                        .values(entry_price=e, sl=sl, tp=tp)
                    )
                    await session.commit()
                logger.info(
                    f"Aligned OPEN trade {t.id} with MT5 #{tid}: entry={e} sl={sl} tp={tp}"
                )

    async def _insert_closed_from_history_import(self, r: dict) -> None:
        """Persist a closed round-trip seen in MT5 history but missing in DB (no Telegram/AI)."""
        async with AsyncSessionLocal() as session:
            ex = await session.execute(
                select(Trade).where(
                    Trade.account_id == self.account_id,
                    Trade.mt5_position_ticket == r["position_id"],
                )
            )
            if ex.scalar_one_or_none():
                return
            session.add(
                Trade(
                    account_id=self.account_id,
                    direction=r["direction"],
                    entry_price=r["entry"],
                    exit_price=r["exit"],
                    lots=r["lots"],
                    sl=r["sl"],
                    tp=r["tp"],
                    pnl=r["pnl"],
                    confluence_score=0,
                    confluence_reasons=[],
                    status="CLOSED",
                    close_reason=r["close_reason"],
                    mt5_position_ticket=r["position_id"],
                    opened_at=r["opened_at"],
                    closed_at=r["closed_at"],
                )
            )
            await session.commit()

    async def _reconcile_mt5_history_import(self, account: Account):
        """
        Backfill CLOSED rows from MT5 deal history; close dangling OPEN rows when history shows exit.
        Throttled — full scan is heavier than a single-position fetch.
        """
        if self.broker_type != "mt5" or not self.broker or not getattr(self.broker, "mt5", None):
            return
        now_m = time.monotonic()
        if now_m - getattr(self, "_last_mt5_hist_reconcile", 0.0) < 50.0:
            return
        self._last_mt5_hist_reconcile = now_m

        rounds = await asyncio.to_thread(self.broker.list_closed_round_trips_from_history, 21)
        for r in rounds:
            async with AsyncSessionLocal() as session:
                ex = await session.execute(
                    select(Trade).where(
                        Trade.account_id == self.account_id,
                        Trade.mt5_position_ticket == r["position_id"],
                    )
                )
                row = ex.scalar_one_or_none()
            if row and row.status == "CLOSED":
                continue
            if row and row.status == "OPEN":
                if not (
                    _price_match(row.entry_price, r["entry"])
                    and _price_match(row.sl, r["sl"])
                    and _price_match(row.tp, r["tp"])
                ):
                    logger.warning(
                        f"Trade {row.id} MT5 #{r['position_id']}: DB levels differ from history "
                        f"(DB entry={row.entry_price} sl={row.sl} tp={row.tp} vs "
                        f"hist entry={r['entry']} sl={r['sl']} tp={r['tp']}) — closing with MT5 history"
                    )
                await self._save_closed_trade(
                    {
                        "trade_id": row.id,
                        "mt5_ticket": r["position_id"],
                        "direction": r["direction"],
                        "entry": r["entry"],
                        "lots": r["lots"],
                        "sl": r["sl"],
                        "tp": r["tp"],
                        "exit": r["exit"],
                        "pnl": r["pnl"],
                        "reason": r["close_reason"],
                        "closed_at": r["closed_at"],
                    },
                    emit_event=False,
                    run_post_close_ai=False,
                )
                continue
            await self._insert_closed_from_history_import(r)

    async def _on_trade_closed_ai(self, trade_id: int):
        try:
            from intelligence.claude_analyzer import get_analyzer

            await get_analyzer().analyze_after_trade_close(self.account_id, trade_id)
        except Exception as e:
            logger.warning(f"Post-close AI analysis failed: {e}")

    async def _macro_sentiment_blocks(self, signal: int, score: int) -> bool:
        """
        If recent AI (twitter/market) strongly disagrees with direction and
        confluence is not very high, skip the trade for this bar.
        """
        if signal == 0 or score >= 9:
            return False
        try:
            async with AsyncSessionLocal() as session:
                r = await session.execute(
                    select(AIAnalysis)
                    .where(AIAnalysis.source.in_(["twitter", "market", "news"]))
                    .order_by(desc(AIAnalysis.created_at))
                    .limit(1)
                )
                a = r.scalar_one_or_none()
            if not a or not a.created_at:
                return False
            age = (datetime.utcnow() - a.created_at).total_seconds()
            if age > 4 * 3600:
                return False
            d = (a.direction or "").lower()
            if signal == 1 and d == "bearish" and score < 8:
                return True
            if signal == -1 and d == "bullish" and score < 8:
                return True
        except Exception as e:
            logger.debug(f"Sentiment check skipped: {e}")
        return False

    async def _tick(self, account: Account):
        self.broker.tick()
        if self.broker_type == "mt5":
            await self._sync_mt5_closed_trades(account)
            await self._align_open_trades_with_terminal(account)
            await self._reconcile_mt5_history_import(account)
        df = self.broker.get_candles()
        if df is None or getattr(df, "empty", True) or "close" not in df.columns:
            logger.warning(
                f"Account {self.account_id}: no candle data for {getattr(self.broker, 'symbol', '')} "
                f"({getattr(self.broker, 'timeframe', '')})"
            )
            return

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
        reasons = list(result["reasons"])

        if await self._macro_sentiment_blocks(signal, score):
            signal = 0
            reasons.append("MACRO_SENTIMENT")

        contract_size = 100
        if self.broker_type != "mt5":
            # Paper-mode SL/TP simulation
            closed_trades = []
            remaining = []
            for pos in self.broker.positions:
                hit = False
                if pos["direction"] == "BUY":
                    if price <= pos["sl"]:
                        pnl = (pos["sl"] - pos["entry"]) * pos["lots"] * contract_size
                        self.broker.balance += pnl
                        closed_trades.append({**pos, "exit": pos["sl"], "pnl": round(pnl, 2), "reason": "SL"})
                        hit = True
                    elif price >= pos["tp"]:
                        pnl = (pos["tp"] - pos["entry"]) * pos["lots"] * contract_size
                        self.broker.balance += pnl
                        closed_trades.append({**pos, "exit": pos["tp"], "pnl": round(pnl, 2), "reason": "TP"})
                        hit = True
                else:
                    if price >= pos["sl"]:
                        pnl = (pos["entry"] - pos["sl"]) * pos["lots"] * contract_size
                        self.broker.balance += pnl
                        closed_trades.append({**pos, "exit": pos["sl"], "pnl": round(pnl, 2), "reason": "SL"})
                        hit = True
                    elif price <= pos["tp"]:
                        pnl = (pos["entry"] - pos["tp"]) * pos["lots"] * contract_size
                        self.broker.balance += pnl
                        closed_trades.append({**pos, "exit": pos["tp"], "pnl": round(pnl, 2), "reason": "TP"})
                        hit = True
                if not hit:
                    remaining.append(pos)
            self.broker.positions = remaining

            for ct in closed_trades:
                await self._save_closed_trade(ct)

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

        max_open = getattr(account, "max_open_trades", 3) or 3
        if signal != 0 and len(self.broker.positions) < max_open:
            # Close opposite
            if self.broker_type == "mt5":
                # For MT5, close opposite positions via the terminal (no PnL simulation).
                for pos in list(self.broker.positions):
                    if (signal == 1 and pos["direction"] == "SELL") or (signal == -1 and pos["direction"] == "BUY"):
                        ticket = pos.get("ticket")
                        if ticket:
                            await asyncio.to_thread(self.broker.close_position, ticket)
                            await self._save_closed_trade({
                                "mt5_ticket": ticket,
                                "direction": pos["direction"],
                                "entry": pos["entry"],
                                "lots": pos["lots"],
                                "exit": price,
                                "pnl": round(float(pos.get("profit", 0.0) or 0.0), 2),
                                "reason": "REVERSAL",
                            })
                # Refresh positions after closes
                self.broker.tick()
            else:
                still_open = []
                for pos in self.broker.positions:
                    if (signal == 1 and pos["direction"] == "SELL") or (signal == -1 and pos["direction"] == "BUY"):
                        pnl_dir = 1 if pos["direction"] == "BUY" else -1
                        pnl = (price - pos["entry"]) * pnl_dir * pos["lots"] * contract_size
                        self.broker.balance += pnl
                        await self._save_closed_trade({**pos, "exit": price, "pnl": round(pnl, 2), "reason": "REVERSAL"})
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

                mt5_ticket = None
                if self.broker_type == "mt5" and hasattr(self.broker, "place_order"):
                    order_result = await asyncio.to_thread(
                        self.broker.place_order, direction, lots, sl, tp
                    )
                    if order_result:
                        price = order_result.get("price", price)
                        mt5_ticket = order_result.get("ticket")
                        logger.info(f"MT5 order placed: {direction} {lots} lots @ ${price:.2f}")
                    else:
                        logger.error("MT5 order failed — skipping")
                        return
                else:
                    pos = {"direction": direction, "entry": price, "lots": lots,
                           "sl": sl, "tp": tp, "score": score, "reasons": reasons}
                    self.broker.positions.append(pos)

                await self._save_open_trade(
                    {"direction": direction, "entry": price, "lots": lots, "sl": sl, "tp": tp},
                    score,
                    reasons,
                    mt5_ticket=mt5_ticket,
                )
                await bus.emit(TRADE_OPENED, {
                    "account_id": self.account_id, "direction": direction,
                    "price": price, "lots": lots, "sl": sl, "tp": tp,
                    "score": score, "reasons": reasons,
                })

        # Update account balance/equity in DB
        async with AsyncSessionLocal() as session:
            if self.broker_type == "mt5":
                bal = round(float(getattr(self.broker, "balance", 0.0) or 0.0), 2)
                eq = round(float(getattr(self.broker, "equity", bal) or bal), 2)
                await session.execute(
                    update(Account).where(Account.id == self.account_id).values(balance=bal, equity=eq)
                )
            else:
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

    async def _save_open_trade(self, pos, score, reasons, mt5_ticket: Optional[int] = None):
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
                mt5_position_ticket=mt5_ticket,
            )
            session.add(trade)
            await session.commit()

    async def _save_closed_trade(
        self,
        ct: dict,
        *,
        emit_event: bool = True,
        run_post_close_ai: bool = True,
    ):
        closed_id = None
        emit_direction = ct.get("direction")
        emit_entry = ct.get("entry")
        emit_lots = ct.get("lots")
        async with AsyncSessionLocal() as session:
            trade = None
            if ct.get("trade_id"):
                result = await session.execute(
                    select(Trade).where(
                        Trade.id == ct["trade_id"],
                        Trade.account_id == self.account_id,
                        Trade.status == "OPEN",
                    )
                )
                trade = result.scalar_one_or_none()
            elif ct.get("mt5_ticket"):
                result = await session.execute(
                    select(Trade).where(
                        Trade.account_id == self.account_id,
                        Trade.status == "OPEN",
                        Trade.mt5_position_ticket == ct["mt5_ticket"],
                    )
                )
                trade = result.scalar_one_or_none()
            if not trade:
                result = await session.execute(
                    select(Trade)
                    .where(
                        Trade.account_id == self.account_id,
                        Trade.status == "OPEN",
                        Trade.direction == ct["direction"],
                    )
                    .order_by(Trade.opened_at.desc())
                    .limit(1)
                )
                trade = result.scalar_one_or_none()
            if trade:
                if ct.get("entry") is not None:
                    trade.entry_price = float(ct["entry"])
                if ct.get("sl") is not None:
                    trade.sl = float(ct["sl"])
                if ct.get("tp") is not None:
                    trade.tp = float(ct["tp"])
                trade.exit_price = ct["exit"]
                trade.pnl = ct["pnl"]
                trade.status = "CLOSED"
                trade.close_reason = ct["reason"]
                trade.closed_at = ct.get("closed_at") or datetime.utcnow()
                closed_id = trade.id
                emit_direction = trade.direction
                emit_entry = trade.entry_price
                emit_lots = trade.lots
                await session.commit()

        if closed_id and emit_event:
            await bus.emit(
                TRADE_CLOSED,
                {
                    "account_id": self.account_id,
                    "direction": emit_direction,
                    "entry": emit_entry,
                    "exit": ct["exit"],
                    "pnl": ct["pnl"],
                    "reason": ct["reason"],
                    "lots": emit_lots,
                    "trade_id": closed_id,
                },
            )
        if closed_id and run_post_close_ai:
            asyncio.create_task(self._on_trade_closed_ai(closed_id))

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

        floor = int(settings.min_confluence_floor)
        rr = None
        if sl is not None and tp is not None and price and sig_type in ("BUY", "SELL"):
            from core.trade_metrics import directional_rr

            rr = directional_rr(float(price), float(sl), float(tp), sig_type)
        if (
            signal != 0
            and score >= floor
            and sig_type in ("BUY", "SELL")
        ):
            await bus.emit(SIGNAL_GENERATED, {
                "account_id": self.account_id, "signal": sig_type,
                "score": score, "reasons": reasons, "price": price,
                "sl": sl, "tp": tp,
                "risk_reward": rr,
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
