"""
ClubMillies — Telegram Bot for trade alerts and management.
"""
import logging
import os
from telegram import Update, BotCommand
from telegram.ext import Application, CommandHandler, ContextTypes
from sqlalchemy import select, func

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
    # Performance summaries are verbose on Telegram — enable explicitly.
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
    await update.message.reply_html(
        "👑 <b>Welcome to ClubMillies</b>\n\n"
        "<i>Not the best you can get but the best there is</i>\n\n"
        "You're now subscribed to trade alerts! 🔔\n\n"
        "Commands:\n"
        "/status — Active accounts & balances\n"
        "/trades — Recent closed trades\n"
        "/accounts — Active accounts only\n"
        "/report — Today + all-time P&amp;L (EAT)\n"
        "/help — All commands\n\n"
        f"🌐 Dashboard: <a href=\"{dash}\">{dash}</a>"
    )


async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Account).where(Account.enabled == True))
        accounts = result.scalars().all()

    if not accounts:
        await update.message.reply_text("No active accounts. Add one via the dashboard.")
        return

    msg = "📊 <b>ACTIVE ACCOUNTS</b>\n\n"
    total_balance = 0
    for acc in accounts:
        msg += (
            f"🟢 <b>{acc.name}</b>\n"
            f"   💰 ${acc.balance:,.2f} | 📈 ${acc.equity:,.2f}\n"
            f"   🎯 {acc.profile} | 💱 {acc.symbol}\n\n"
        )
        total_balance += acc.balance

    msg += f"━━━━━━━━━━━━━━━━━━\n💰 Total balance: <b>${total_balance:,.2f}</b>"
    await update.message.reply_html(msg)


async def cmd_trades(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Trade).where(Trade.status == "CLOSED")
            .order_by(Trade.closed_at.desc()).limit(10)
        )
        trades = result.scalars().all()

    if not trades:
        await update.message.reply_text("No closed trades yet.")
        return

    msg = "📋 <b>RECENT CLOSED TRADES</b>\n\n"
    for t in trades:
        emoji = "✅" if (t.pnl or 0) > 0 else "❌"
        pnl_str = f"+${t.pnl:.2f}" if (t.pnl or 0) > 0 else f"-${abs(t.pnl or 0):.2f}"
        msg += (
            f"{emoji} {t.direction} | {pnl_str} | "
            f"Score: {t.confluence_score}/15 | {t.close_reason}\n"
        )

    await update.message.reply_html(msg)


async def cmd_accounts(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Account).where(Account.enabled == True))
        accounts = result.scalars().all()

    if not accounts:
        await update.message.reply_text("No active accounts.")
        return

    msg = "👥 <b>ACTIVE ACCOUNTS</b>\n\n"
    for acc in accounts:
        msg += (
            f"<b>#{acc.id} {acc.name}</b>\n"
            f"   🟢 {acc.broker_type.upper()} | {acc.profile}\n"
            f"   💰 ${acc.balance:,.2f} | {acc.symbol}\n\n"
        )
    await update.message.reply_html(msg)


async def cmd_report(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    start_today = period_start_utc_naive("today")
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Account).where(Account.enabled == True)
        )
        enabled = result.scalars().all()

        result = await session.execute(select(func.sum(Account.balance)).where(Account.enabled == True))
        total_balance = result.scalar() or 0

        result = await session.execute(select(Trade).where(Trade.status == "CLOSED"))
        all_closed = result.scalars().all()

        result = await session.execute(
            select(Trade).where(Trade.status == "OPEN")
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

    # Balance total only if we have enabled accounts; else 0
    bal = float(total_balance) if enabled else 0.0

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
        "/start — Subscribe to alerts\n"
        "/status — Active accounts & balances\n"
        "/trades — Last 10 closed trades\n"
        "/accounts — Active accounts only\n"
        "/report — Today + all-time realized P&amp;L (EAT day)\n"
        "/help — This message\n\n"
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

    # Register commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("trades", cmd_trades))
    app.add_handler(CommandHandler("accounts", cmd_accounts))
    app.add_handler(CommandHandler("report", cmd_report))
    app.add_handler(CommandHandler("help", cmd_help))

    # Subscribe to event bus
    bus.subscribe(TRADE_OPENED, on_trade_opened)
    bus.subscribe(TRADE_CLOSED, on_trade_closed)
    bus.subscribe(SIGNAL_GENERATED, on_signal)
    bus.subscribe(NEWS_EVENT, on_news)
    bus.subscribe(AI_ANALYSIS, on_ai_analysis)

    # Set bot commands menu
    await app.bot.set_my_commands([
        BotCommand("start", "Subscribe to trade alerts"),
        BotCommand("status", "Active accounts overview"),
        BotCommand("trades", "Recent closed trades"),
        BotCommand("accounts", "Active accounts"),
        BotCommand("report", "Today & all-time P/L"),
        BotCommand("help", "Show commands"),
    ])

    # Default: outbound-only (no polling) to avoid getUpdates conflicts.
    # Enable polling only when explicitly requested via TELEGRAM_ENABLE_POLLING=true.
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
