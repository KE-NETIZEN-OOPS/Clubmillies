"""
ClubMillies — Message templates and encouraging messages.
"""
import random

# ── Trade Alerts ─────────────────────────────────────────────────────

def trade_opened_msg(data: dict) -> str:
    direction = data["direction"]
    emoji = "🟢" if direction == "BUY" else "🔴"
    score = data.get("score", 0)
    bar = _power_bar(score)
    return (
        f"{emoji} <b>NEW {direction} TRADE</b>\n\n"
        f"💰 Entry: <code>${data['price']:.2f}</code>\n"
        f"📊 Lots: <code>{data['lots']}</code>\n"
        f"🛑 Stop Loss: <code>${data['sl']:.2f}</code>\n"
        f"🎯 Take Profit: <code>${data['tp']:.2f}</code>\n\n"
        f"⚡ Power: {bar} <b>{score}/15</b>\n\n"
        f"<i>ClubMillies — Not the best you can get but the best there is</i>"
    )


def trade_closed_msg(data: dict) -> str:
    pnl = data["pnl"]
    reason = data["reason"]
    direction = data["direction"]

    if reason == "TAKE PROFIT":
        emoji = "🎯💰"
        header = "TAKE PROFIT HIT!"
    elif reason == "STOP LOSS":
        emoji = "🛑"
        header = "STOP LOSS HIT"
    else:
        emoji = "🔄"
        header = f"TRADE CLOSED ({reason})"

    pnl_emoji = "✅" if pnl > 0 else "❌"
    pnl_str = f"+${pnl:.2f}" if pnl > 0 else f"-${abs(pnl):.2f}"

    msg = (
        f"{emoji} <b>{header}</b>\n\n"
        f"📊 {direction} closed\n"
        f"📍 Entry: <code>${data['entry']:.2f}</code>\n"
        f"📍 Exit: <code>${data['exit']:.2f}</code>\n"
        f"{pnl_emoji} P&L: <code>{pnl_str}</code>\n"
    )

    # Add encouraging message
    if pnl > 0:
        msg += f"\n💪 {random.choice(WIN_MESSAGES)}"
    else:
        msg += f"\n🧠 {random.choice(LOSS_MESSAGES)}"

    return msg


def _power_bar(score: int, max_score: int = 15) -> str:
    """Generate a visual power bar for confluence score."""
    filled = round(score / max_score * 10)
    empty = 10 - filled
    if score >= 7:
        bar = "🟩" * filled + "⬜" * empty
    elif score >= 5:
        bar = "🟨" * filled + "⬜" * empty
    else:
        bar = "🟧" * filled + "⬜" * empty
    return bar


def signal_msg(data: dict) -> str:
    signal = data["signal"]
    emoji = "🟢" if signal == "BUY" else "🔴" if signal == "SELL" else "⚪"
    sl = data.get("sl")
    tp = data.get("tp")
    score = data.get("score", 0)
    bar = _power_bar(score)

    msg = (
        f"{emoji} <b>SIGNAL: {signal}</b>\n\n"
        f"💲 Price: <code>${data['price']:.2f}</code>\n"
    )
    if sl is not None:
        msg += f"🛑 Stop Loss: <code>${sl:.2f}</code>\n"
    if tp is not None:
        msg += f"🎯 Take Profit: <code>${tp:.2f}</code>\n"
    msg += (
        f"\n⚡ Power: {bar} <b>{score}/15</b>\n\n"
        f"<i>ClubMillies — Not the best you can get but the best there is</i>"
    )
    return msg


def news_alert_msg(data: dict) -> str:
    impact_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(data.get("impact", ""), "⚪")
    return (
        f"📰 <b>NEWS ALERT</b> {impact_emoji}\n\n"
        f"📋 {data['title']}\n"
        f"💱 Currency: {data.get('currency', 'USD')}\n"
        f"📊 Impact: {data.get('impact', 'unknown').upper()}\n"
        f"📈 Forecast: {data.get('forecast', 'N/A')}\n"
        f"📉 Previous: {data.get('previous', 'N/A')}\n"
    )


def ai_analysis_msg(data: dict) -> str:
    direction = data.get("direction", "neutral")
    confidence = data.get("confidence", 0)
    emoji = "🟢" if direction == "bullish" else "🔴" if direction == "bearish" else "⚪"
    bar = "█" * (confidence // 10) + "░" * (10 - confidence // 10)
    return (
        f"🤖 <b>AI ANALYSIS</b>\n\n"
        f"{emoji} Direction: <b>{direction.upper()}</b>\n"
        f"📊 Confidence: [{bar}] {confidence}%\n"
        f"💡 {data.get('reasoning', 'N/A')}\n\n"
        f"<i>Source: {data.get('source', 'Claude AI')}</i>"
    )


def daily_report_msg(stats: dict) -> str:
    return (
        f"📊 <b>DAILY REPORT — ClubMillies</b>\n\n"
        f"💰 Balance: <code>${stats.get('balance', 0):,.2f}</code>\n"
        f"📈 Today P&L: <code>{'+' if stats.get('pnl', 0) >= 0 else ''}"
        f"${stats.get('pnl', 0):,.2f}</code>\n"
        f"🎯 Trades: <code>{stats.get('trades', 0)}</code>\n"
        f"✅ Win Rate: <code>{stats.get('win_rate', 0):.1f}%</code>\n"
        f"📊 Open Positions: <code>{stats.get('open_positions', 0)}</code>\n\n"
        f"💪 {random.choice(DAILY_MESSAGES)}"
    )


# ── Encouraging Messages ────────────────────────────────────────────

WIN_MESSAGES = [
    "Money moves! The strategy is printing! 💸",
    "Another one in the bag! Consistency is key 🔑",
    "ClubMillies doesn't miss! Let's keep stacking 📈",
    "That's how winners trade. Calculated and precise 🎯",
    "The confluence never lies! Great setup 🔥",
    "Trust the process, collect the profits 💰",
    "Smart money concepts doing their thing! 🧠",
    "Patience paid off. This is what discipline looks like 👑",
    "We don't gamble, we calculate. And we WIN 🏆",
    "The market respects our strategy. Another clean trade ✨",
    "Gold keeps giving! Stay focused, stay profitable 💛",
    "That entry was *chef's kiss* — perfect confluence 👨‍🍳",
]

LOSS_MESSAGES = [
    "One loss doesn't define us. The win rate is on our side 📊",
    "Even the best strategies have losing trades. Stay disciplined 🧠",
    "This is the cost of doing business. The math still works 📐",
    "Small loss, big lessons. We live to trade another day 💪",
    "Remember: 85% win rate means 15% losses. This was one of them 📉",
    "Risk managed perfectly. That's why we use stop losses 🛑",
    "The market owes us nothing. But our edge will pay us back 🔄",
    "Shake it off. The next high-confluence setup is around the corner 🎯",
    "Losses are tuition. And we're almost done paying 🎓",
    "This is why we risk only 2%. Small loss, strategy intact ✅",
]

DAILY_MESSAGES = [
    "Another day of disciplined trading. Keep grinding! 💪",
    "The markets never sleep, and neither does ClubMillies 🌙",
    "Every day is a step closer to financial freedom 🏆",
    "Trust the confluence, trust the process 🔥",
    "Not the best you can get but the best there is 👑",
    "Building wealth one smart trade at a time 📈",
]
