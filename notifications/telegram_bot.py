"""
ClubMillies — Telegram Bot for trade alerts and management.
"""
import logging
from datetime import datetime
from telegram import Update, BotCommand
from telegram.ext import Application, CommandHandler, ContextTypes
from sqlalchemy import select, func

from core.config import settings
from core.database import AsyncSessionLocal
from core.models import Account, Trade, Signal, TelegramChat
from core.events import bus, TRADE_OPENED, TRADE_CLOSED, SIGNAL_GENERATED, NEWS_EVENT, AI_ANALYSIS
from notifications.messages import (
    trade_opened_msg, trade_closed_msg, signal_msg,
    news_alert_msg, ai_analysis_msg, daily_report_msg,
)

logger = logging.getLogger("clubmillies.telegram")

app: Application = None


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
    await _broadcast(trade_opened_msg(event.data))

async def on_trade_closed(event):
    await _broadcast(trade_closed_msg(event.data))

async def on_signal(event):
    # Only send BUY/SELL signals that meet trading threshold (5+)
    signal = event.data.get("signal")
    if signal in ("BUY", "SELL") and event.data.get("score", 0) >= 5:
        await _broadcast(signal_msg(event.data))

async def on_news(event):
    if event.data.get("impact") == "high":
        await _broadcast(news_alert_msg(event.data))

async def on_ai_analysis(event):
    if event.data.get("confidence", 0) >= 70:
        await _broadcast(ai_analysis_msg(event.data))


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

    await update.message.reply_html(
        "👑 <b>Welcome to ClubMillies</b>\n\n"
        "<i>Not the best you can get but the best there is</i>\n\n"
        "You're now subscribed to trade alerts! 🔔\n\n"
        "Commands:\n"
        "/status — Account overview\n"
        "/trades — Recent trades\n"
        "/accounts — All accounts\n"
        "/report — Performance report\n"
        "/help — All commands"
    )


async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Account).where(Account.enabled == True))
        accounts = result.scalars().all()

    if not accounts:
        await update.message.reply_text("No active accounts. Add one via the dashboard.")
        return

    msg = "📊 <b>ACCOUNT STATUS</b>\n\n"
    total_balance = 0
    for acc in accounts:
        status = "🟢" if acc.enabled else "🔴"
        msg += (
            f"{status} <b>{acc.name}</b>\n"
            f"   💰 ${acc.balance:,.2f} | 📈 ${acc.equity:,.2f}\n"
            f"   🎯 {acc.profile} | 💱 {acc.symbol}\n\n"
        )
        total_balance += acc.balance

    msg += f"━━━━━━━━━━━━━━━━━━\n💰 Total: <b>${total_balance:,.2f}</b>"
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

    msg = "📋 <b>RECENT TRADES</b>\n\n"
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
        result = await session.execute(select(Account))
        accounts = result.scalars().all()

    if not accounts:
        await update.message.reply_text("No accounts configured.")
        return

    msg = "👥 <b>ALL ACCOUNTS</b>\n\n"
    for acc in accounts:
        status = "🟢 Active" if acc.enabled else "🔴 Paused"
        msg += (
            f"<b>#{acc.id} {acc.name}</b>\n"
            f"   {status} | {acc.broker_type.upper()} | {acc.profile}\n"
            f"   💰 ${acc.balance:,.2f} | {acc.symbol}\n\n"
        )
    await update.message.reply_html(msg)


async def cmd_report(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    today = datetime.utcnow().date()
    async with AsyncSessionLocal() as session:
        # Total balance
        result = await session.execute(select(func.sum(Account.balance)))
        total_balance = result.scalar() or 0

        # Today's trades
        result = await session.execute(
            select(Trade).where(
                Trade.status == "CLOSED",
                func.date(Trade.closed_at) == today,
            )
        )
        todays_trades = result.scalars().all()

    pnl = sum(t.pnl or 0 for t in todays_trades)
    wins = sum(1 for t in todays_trades if (t.pnl or 0) > 0)
    wr = (wins / len(todays_trades) * 100) if todays_trades else 0

    await update.message.reply_html(daily_report_msg({
        "balance": total_balance,
        "pnl": pnl,
        "trades": len(todays_trades),
        "win_rate": wr,
        "open_positions": 0,
    }))


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_html(
        "👑 <b>ClubMillies Commands</b>\n\n"
        "/start — Subscribe to alerts\n"
        "/status — Account balances & equity\n"
        "/trades — Last 10 closed trades\n"
        "/accounts — All accounts overview\n"
        "/report — Today's performance\n"
        "/help — This message\n\n"
        "🌐 Dashboard: <code>http://your-server:3000</code>"
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
        BotCommand("status", "Account overview"),
        BotCommand("trades", "Recent trades"),
        BotCommand("accounts", "All accounts"),
        BotCommand("report", "Performance report"),
        BotCommand("help", "Show commands"),
    ])

    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)
    logger.info("Telegram bot started")


async def stop_telegram():
    global app
    if app:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()
