"""
ClubMillies — Telegram Bot for trade alerts and management.

Commands use the same SQLite DB as the trading engine. Scope is configurable so
/stats do not mix paper backtests with live MT5 (see TELEGRAM_* env vars).
Balances are refreshed from the running MT5 connector when possible.
"""
import asyncio
import logging
import os
from typing import List, Optional

from telegram import Update, BotCommand
from telegram.ext import Application, CommandHandler, ContextTypes
from sqlalchemy import select, func, update

from core.config import settings
from core.database import AsyncSessionLocal
from core.models import Account, Trade, TelegramChat
from core.events import bus, TRADE_OPENED, TRADE_CLOSED, SIGNAL_GENERATED, NEWS_EVENT, AI_ANALYSIS
from core.datetime_eat import period_start_utc_naive
from notifications.messages import (
    trade_opened_msg, trade_closed_msg, signal_msg,
    news_alert_msg, ai_analysis_msg, daily_report_msg,
)

logger = logging.getLogger("clubmillies.telegram")

app: Application = None


def _dashboard_url() -> str:
    return (settings.dashboard_public_url or "https://clubmillies.vercel.app").rstrip("/")


def _parse_telegram_account_ids() -> Optional[List[int]]:
    raw = (settings.telegram_stats_account_ids or "").strip()
    if not raw:
        return None
    out: List[int] = []
    for x in raw.split(","):
        x = x.strip()
        if x.isdigit():
            out.append(int(x))
    return out if out else None


async def _sync_mt5_balances_from_engine() -> None:
    """Push latest MT5 terminal balance/equity into DB before /status and similar."""
    try:
        from api.app import app as api_app
    except Exception as e:
        logger.debug(f"No api.app for MT5 sync: {e}")
        return
    mgr = getattr(api_app.state, "account_manager", None)
    if not mgr or not getattr(mgr, "runners", None):
        return
    for aid, runner in list(mgr.runners.items()):
        if runner.broker_type != "mt5" or not runner.broker:
            continue
        try:
            await asyncio.to_thread(runner.broker.tick)
        except Exception as e:
            logger.warning(f"MT5 tick for Telegram sync failed acc {aid}: {e}")
            continue
        b = float(getattr(runner.broker, "balance", 0) or 0)
        e_bal = float(getattr(runner.broker, "equity", b) or b)
        async with AsyncSessionLocal() as session:
            await session.execute(
                update(Account)
                .where(Account.id == aid)
                .values(balance=round(b, 2), equity=round(e_bal, 2))
            )
            await session.commit()


async def _scoped_accounts(session) -> List[Account]:
    """Enabled accounts matching TELEGRAM_* filters."""
    ids = _parse_telegram_account_ids()
    q = select(Account).where(Account.enabled == True)
    if ids is not None:
        q = q.where(Account.id.in_(ids))
    else:
        if settings.telegram_mt5_only:
            q = q.where(Account.broker_type == "mt5")
        elif settings.telegram_exclude_paper:
            q = q.where(Account.broker_type != "paper")
        if settings.telegram_mt5_live_only:
            q = q.where(Account.broker_type == "mt5").where(Account.is_demo == False)
    result = await session.execute(q.order_by(Account.id))
    return list(result.scalars().all())


def _account_label(acc: Account) -> str:
    if acc.broker_type == "mt5":
        demo = acc.is_demo
        tag = "MT5 demo" if demo else "MT5 live"
    elif acc.broker_type == "paper":
        tag = "Paper"
    else:
        tag = acc.broker_type.upper()
    return tag


async def _broadcast(text: str):
    """Send message to all subscribed chats."""
    if not app:
        return
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(TelegramChat).where(TelegramChat.subscribed == True))
        chats = result.scalars().all()

    for chat in chats:
        try:
            await app.bot.send_message(
                chat_id=chat.chat_id, text=text, parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Telegram send error to {chat.chat_id}: {e}")


# ── Event Handlers (subscribe to event bus) ──────────────────────────

async def on_trade_opened(event):
    if event.data.get("score", 0) < int(settings.min_confluence_floor):
        return
    await _broadcast(trade_opened_msg(event.data))

async def on_trade_closed(event):
    await _broadcast(trade_closed_msg(event.data))

async def on_signal(event):
    signal = event.data.get("signal")
    if signal in ("BUY", "SELL") and event.data.get("score", 0) >= int(settings.min_confluence_floor):
        await _broadcast(signal_msg(event.data))

async def on_news(event):
    if event.data.get("impact") == "high":
        await _broadcast(news_alert_msg(event.data))

async def on_ai_analysis(event):
    data = event.data or {}
    src = data.get("source", "")
    conf = data.get("confidence", 0)
    if src == "trade_close":
        if (os.getenv("TELEGRAM_TRADE_CLOSE_AI", "false").lower() != "true"):
            return
        await _broadcast(ai_analysis_msg(data))
        return
    if conf >= 70:
        await _broadcast(ai_analysis_msg(data))


# ── Command Handlers ────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    username = update.effective_user.username or "Unknown"

    async with AsyncSessionLocal() as session:
        existing = await session.execute(
            select(TelegramChat).where(TelegramChat.chat_id == chat_id)
        )
        if not existing.scalar_one_or_none():
            session.add(TelegramChat(chat_id=chat_id, username=username))
            await session.commit()

    dash = _dashboard_url()
    scope_hint = ""
    if settings.telegram_stats_account_ids:
        scope_hint = f"\n<i>Stats scope: account id(s) {settings.telegram_stats_account_ids}</i>\n"
    elif settings.telegram_mt5_only or settings.telegram_mt5_live_only or settings.telegram_exclude_paper:
        scope_hint = "\n<i>Stats exclude paper / optional MT5 filters — see TELEGRAM_* in .env</i>\n"

    await update.message.reply_html(
        "👑 <b>Welcome to ClubMillies</b>\n\n"
        "<i>Not the best you can get but the best there is</i>\n\n"
        "You're now subscribed to trade alerts! 🔔\n\n"
        "Commands:\n"
        "/status — Balances (scoped accounts)\n"
        "/trades — Recent closed trades (scoped)\n"
        "/accounts — Scoped active accounts\n"
        "/report — Today + all-time P&amp;L (scoped)\n"
        "/help — All commands\n\n"
        f"{scope_hint}"
        f"🌐 Dashboard: <a href=\"{dash}\">{dash}</a>"
    )


async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await _sync_mt5_balances_from_engine()
    async with AsyncSessionLocal() as session:
        accounts = await _scoped_accounts(session)

    if not accounts:
        await update.message.reply_html(
            "<b>No accounts in scope.</b>\n"
            "Enable an account or set <code>TELEGRAM_STATS_ACCOUNT_IDS</code> (e.g. your MT5 row id).\n"
            "Paper accounts are hidden when <code>TELEGRAM_EXCLUDE_PAPER=true</code>."
        )
        return

    msg = "📊 <b>ACCOUNT STATUS</b> <i>(scoped)</i>\n\n"
    total_balance = 0.0
    total_equity = 0.0
    for acc in accounts:
        tag = _account_label(acc)
        msg += (
            f"🟢 <b>{acc.name}</b> <code>#{acc.id}</code> · {tag}\n"
            f"   💰 ${acc.balance:,.2f} | 📈 ${acc.equity:,.2f}\n"
            f"   🎯 {acc.profile} | 💱 {acc.symbol}\n\n"
        )
        total_balance += float(acc.balance or 0)
        total_equity += float(acc.equity or 0)

    msg += (
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💰 Total balance: <b>${total_balance:,.2f}</b>\n"
        f"📈 Total equity: <b>${total_equity:,.2f}</b>"
    )
    await update.message.reply_html(msg)


async def cmd_trades(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await _sync_mt5_balances_from_engine()
    async with AsyncSessionLocal() as session:
        accounts = await _scoped_accounts(session)
        ids = [a.id for a in accounts]

    if not ids:
        await update.message.reply_text(
            "No accounts in scope for trades. Check TELEGRAM_STATS_ACCOUNT_IDS or disable paper filter."
        )
        return

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Trade)
            .where(Trade.status == "CLOSED", Trade.account_id.in_(ids))
            .order_by(Trade.closed_at.desc())
            .limit(15)
        )
        trades = result.scalars().all()

    if not trades:
        await update.message.reply_text("No closed trades yet for scoped accounts.")
        return

    id_to_name = {a.id: a.name for a in accounts}
    msg = "📋 <b>RECENT CLOSED TRADES</b> <i>(newest first · scoped)</i>\n\n"
    for t in trades:
        emoji = "✅" if (t.pnl or 0) > 0 else "❌"
        pnl_str = f"+${t.pnl:.2f}" if (t.pnl or 0) > 0 else f"-${abs(t.pnl or 0):.2f}"
        who = id_to_name.get(t.account_id, f"#{t.account_id}")
        reason = (t.close_reason or "—").upper()
        entry = t.entry_price if t.entry_price is not None else 0.0
        exit_p = t.exit_price if t.exit_price is not None else 0.0
        msg += (
            f"{emoji} <b>{who}</b> · {t.direction} · <code>{reason}</code>\n"
            f"   {pnl_str} · in {entry:.2f} → out {exit_p:.2f} · score {t.confluence_score}/15\n\n"
        )

    await update.message.reply_html(msg)


async def cmd_accounts(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await _sync_mt5_balances_from_engine()
    async with AsyncSessionLocal() as session:
        accounts = await _scoped_accounts(session)

    if not accounts:
        await update.message.reply_text("No accounts in scope.")
        return

    msg = "👥 <b>ACTIVE ACCOUNTS</b> <i>(scoped)</i>\n\n"
    for acc in accounts:
        tag = _account_label(acc)
        msg += (
            f"<b>#{acc.id} {acc.name}</b> · {tag}\n"
            f"   💰 ${acc.balance:,.2f} | 📈 ${acc.equity:,.2f} | {acc.symbol}\n"
            f"   🎯 {acc.profile}\n\n"
        )
    await update.message.reply_html(msg)


async def cmd_report(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await _sync_mt5_balances_from_engine()
    start_today = period_start_utc_naive("today")
    async with AsyncSessionLocal() as session:
        accounts = await _scoped_accounts(session)
        ids = [a.id for a in accounts]

    if not ids:
        await update.message.reply_text("No accounts in scope for report.")
        return

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(func.sum(Account.balance)).where(
                Account.enabled == True,
                Account.id.in_(ids),
            )
        )
        total_balance = result.scalar() or 0

        result = await session.execute(
            select(Trade).where(
                Trade.status == "CLOSED",
                Trade.account_id.in_(ids),
            )
        )
        all_closed = result.scalars().all()

        result = await session.execute(
            select(Trade).where(
                Trade.status == "OPEN",
                Trade.account_id.in_(ids),
            )
        )
        open_rows = result.scalars().all()

    today_closed = [
        t for t in all_closed
        if t.closed_at and start_today and t.closed_at >= start_today
    ]

    pnl_today = sum(t.pnl or 0 for t in today_closed)
    all_time = sum(t.pnl or 0 for t in all_closed)
    wins = sum(1 for t in today_closed if (t.pnl or 0) > 0)
    wr = (wins / len(today_closed) * 100) if today_closed else 0

    bal = float(total_balance or 0)

    await update.message.reply_html(daily_report_msg({
        "balance": bal,
        "today_pnl": pnl_today,
        "all_time_pnl": all_time,
        "pnl": pnl_today,
        "trades": len(today_closed),
        "win_rate": wr,
        "open_positions": len(open_rows),
    }))


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    dash = _dashboard_url()
    await update.message.reply_html(
        "👑 <b>ClubMillies Commands</b>\n\n"
        "/status — Scoped balances & equity\n"
        "/trades — Last 10 closed (scoped accounts)\n"
        "/accounts — Scoped active accounts\n"
        "/report — Today + all-time realized P&amp;L (scoped)\n"
        "/help — This message\n\n"
        "<i>Scope: TELEGRAM_STATS_ACCOUNT_IDS, or TELEGRAM_EXCLUDE_PAPER / "
        "TELEGRAM_MT5_ONLY / TELEGRAM_MT5_LIVE_ONLY</i>\n\n"
        f"🌐 Dashboard: <a href=\"{dash}\">{dash}</a>"
    )


# ── Bot Setup ────────────────────────────────────────────────────────

async def setup_telegram():
    """Initialize and start the Telegram bot."""
    global app

    token = settings.telegram_bot_token
    if not token:
        logger.warning("No TELEGRAM_BOT_TOKEN set — Telegram bot disabled")
        return

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("trades", cmd_trades))
    app.add_handler(CommandHandler("accounts", cmd_accounts))
    app.add_handler(CommandHandler("report", cmd_report))
    app.add_handler(CommandHandler("help", cmd_help))

    bus.subscribe(TRADE_OPENED, on_trade_opened)
    bus.subscribe(TRADE_CLOSED, on_trade_closed)
    bus.subscribe(SIGNAL_GENERATED, on_signal)
    bus.subscribe(NEWS_EVENT, on_news)
    bus.subscribe(AI_ANALYSIS, on_ai_analysis)

    await app.bot.set_my_commands([
        BotCommand("start", "Subscribe to trade alerts"),
        BotCommand("status", "Scoped balances"),
        BotCommand("trades", "Scoped closed trades"),
        BotCommand("accounts", "Scoped accounts"),
        BotCommand("report", "Today & all-time P/L"),
        BotCommand("help", "Show commands"),
    ])

    enable_polling = (os.getenv("TELEGRAM_ENABLE_POLLING", "false").lower() == "true")
    chat_id = (settings.telegram_chat_id or "").strip()
    if chat_id:
        async with AsyncSessionLocal() as session:
            existing = await session.execute(select(TelegramChat).where(TelegramChat.chat_id == chat_id))
            if not existing.scalar_one_or_none():
                session.add(TelegramChat(chat_id=chat_id, username="env", subscribed=True))
                await session.commit()

    await app.initialize()
    await app.start()
    if enable_polling:
        await app.updater.start_polling(drop_pending_updates=True)
        logger.info("Telegram bot started (polling enabled)")
    else:
        logger.info("Telegram bot started (outbound-only; polling disabled)")


async def stop_telegram():
    global app
    if app:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()
