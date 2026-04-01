"""
ClubMillies — Message templates, wealth motivation, and SL humor.
"""
import random


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
        f"👑 <b>ClubMillies Master Signals</b> — execution locked in.\n"
        f"<i>{random.choice(WEALTH_MOTIVATION)}</i>"
    )


def trade_closed_msg(data: dict) -> str:
    pnl = data.get("pnl") or 0
    reason = (data.get("reason") or "").upper()
    direction = data.get("direction", "")

    is_tp = reason in ("TP", "TAKE PROFIT", "TAKE_PROFIT")
    is_sl = reason in ("SL", "STOP LOSS", "STOP_LOSS")

    if is_tp:
        header = "🎯🏆 <b>TAKE PROFIT — ClubMillies Master Signals</b>"
        extra = random.choice(TP_CELEBRATION)
        emoji_line = "✨💰🥂 " + random.choice(WEALTH_MOTIVATION)
    elif is_sl:
        header = "🛑 <b>STOP LOSS FILLED</b> — plan respected"
        extra = random.choice(SL_FUNNY)
        emoji_line = random.choice(SL_MEME_LINES)
    else:
        header = f"🔄 <b>TRADE CLOSED</b> ({reason})"
        extra = random.choice(LOSS_MESSAGES) if pnl <= 0 else random.choice(WIN_MESSAGES)
        emoji_line = ""

    pnl_emoji = "✅" if pnl > 0 else "❌"
    pnl_str = f"+${pnl:.2f}" if pnl > 0 else f"-${abs(pnl):.2f}"

    msg = (
        f"{header}\n\n"
        f"📊 {direction} closed\n"
        f"📍 Entry: <code>${data.get('entry', 0):.2f}</code>\n"
        f"📍 Exit: <code>${data.get('exit', 0):.2f}</code>\n"
        f"{pnl_emoji} P&amp;L: <code>{pnl_str}</code>\n\n"
        f"{extra}\n"
    )
    if emoji_line:
        msg += f"\n<i>{emoji_line}</i>\n"
    if is_tp and pnl > 0:
        msg += f"\n{random.choice(WEALTH_MOTIVATION)}"
    elif not is_tp and not is_sl and pnl > 0:
        msg += f"\n💪 {random.choice(WIN_MESSAGES)}"
    elif not is_tp and not is_sl and pnl <= 0:
        msg += f"\n🧠 {random.choice(LOSS_MESSAGES)}"
    return msg


def _power_bar(score: int, max_score: int = 15) -> str:
    """Generate a visual power bar for confluence score."""
    filled = max(0, min(10, round(score / max_score * 10)))
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
    rr = data.get("risk_reward")
    bar = _power_bar(score)

    msg = (
        f"{emoji} <b>SIGNAL: {signal}</b>\n\n"
        f"💲 Price: <code>${data['price']:.2f}</code>\n"
    )
    if sl is not None:
        msg += f"🛑 Stop Loss: <code>${sl:.2f}</code>\n"
    if tp is not None:
        msg += f"🎯 Take Profit: <code>${tp:.2f}</code>\n"
    if rr is not None:
        msg += f"⚖️ Risk:Reward (TP vs SL): <b>1 : {float(rr):.2f}</b>\n"
    msg += (
        f"\n⚡ Power: {bar} <b>{score}/15</b>\n\n"
        f"<i>ClubMillies Master Signals — {random.choice(WEALTH_MOTIVATION)}</i>"
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
    bar = "█" * max(0, min(10, confidence // 10)) + "░" * max(0, 10 - confidence // 10)
    src = data.get("source", "claude")
    label = {
        "news": "News AI",
        "twitter": "Twitter AI",
        "market": "Market AI",
        "trade_close": "Performance AI",
    }.get(src, src or "Claude")
    return (
        f"🤖 <b>AI — {label}</b>\n\n"
        f"{emoji} Direction: <b>{direction.upper()}</b>\n"
        f"📊 Confidence: [{bar}] {confidence}%\n"
        f"💡 {data.get('reasoning', 'N/A')}\n\n"
        f"<i>ClubMillies intelligence layer</i>"
    )


def daily_report_msg(stats: dict) -> str:
    tp = stats.get("today_pnl", stats.get("pnl", 0))
    ap = stats.get("all_time_pnl", 0)
    return (
        f"📊 <b>PERFORMANCE — ClubMillies</b>\n\n"
        f"💰 Active accounts balance (sum): <code>${stats.get('balance', 0):,.2f}</code>\n"
        f"📈 Today P&L (closed, EAT day): <code>{'+' if tp >= 0 else ''}${tp:,.2f}</code>\n"
        f"🏛 All-time realized P&L: <code>{'+' if ap >= 0 else ''}${ap:,.2f}</code>\n"
        f"🎯 Closed trades today: <code>{stats.get('trades', 0)}</code>\n"
        f"✅ Today win rate: <code>{stats.get('win_rate', 0):.1f}%</code>\n"
        f"📊 Open positions (DB): <code>{stats.get('open_positions', 0)}</code>\n\n"
        f"💪 {random.choice(DAILY_MESSAGES)}"
    )


# ── Motivation & humor pools (shuffled via random.choice) ────────────

TP_CELEBRATION = [
    "👑 ClubMillies Master Signals — the target was always the plan. Discipline pays.",
    "🥂 Target vaporized. Wealth favors the systematic.",
    "🏆 Confluence delivered. This is what edge looks like.",
    "✨ TP secured — your process beat the noise.",
    "💎 Precision beats prediction. Another clean harvest.",
    "🚀 Risk defined, reward collected. Trading is a business — you just closed a solid invoice.",
]

SL_FUNNY = [
    "The market said ‘not today’ — your stop said ‘I’ve got you’. 🧱",
    "Stop loss: the bouncer that keeps your account from doing karaoke after midnight. 🎤🚫",
    "That wasn’t a loss — it was tuition with a receipt. 🧾😅",
    "Even legends eat stop hunts for breakfast sometimes. 🥞📉",
    "Risk management flex: small L, account still standing. 💪🛑",
    "Plot twist: the SL was the hero all along. 🦸‍♂️📉",
    "Market: ‘surprise!’ You: ‘capped.’ That’s professionalism. 🎩",
    "Stop hit — ego didn’t. That’s the real win. 🏅",
    "Like a seatbelt: annoying until it saves you. 🚗🛑",
    "The trade ghosted you — your stop didn’t ghost your account. 👻✅",
]

SL_MEME_LINES = [
    "📉 Speed bump, not a cliff.",
    "🎰 House edge is time + discipline — you kept both.",
    "🧠 Stop = ‘wrong fast’ — cheaper than ‘wrong forever’.",
]

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

WEALTH_MOTIVATION = [
    "Wealth is built in boring repetition — not one lucky spike.",
    "Discipline is the bridge between goals and gold.",
    "Patience turns setups into stacks.",
    "Risk small, think big, compound quietly.",
    "The chart doesn’t care about your feelings — your system does.",
    "Freedom is funded by process, not hope.",
    "Every tick is a vote — vote with your plan.",
    "Liquidity rewards the prepared mind.",
    "Capital preservation is the first profit.",
    "Consistency beats intensity in trading and in life.",
    "Your edge is your routine on display.",
    "Master the pause between signal and click.",
    "Fortunes favor the patient and the precise.",
    "Trade the plan — let the market do the drama.",
    "Small edges, large time horizon — that’s wealth.",
    "Calm execution beats loud prediction.",
    "Protect downside — upside handles itself.",
    "Journal the trade, not just the P/L.",
    "Systems scale — emotions don’t.",
    "The best trade is often the one you skip.",
    "Risk is a dial — never a hammer.",
    "Clarity beats confidence.",
    "Stack evidence, not opinions.",
    "Your future self funds today’s discipline.",
    "Markets echo: preparation pays compound interest.",
    "Stay liquid in mind and in account.",
    "Precision is a habit, not a mood.",
    "Win quietly. Improve loudly.",
    "Measure twice — click once.",
    "Volatility is the price of opportunity.",
    "Sleep comes easier with defined risk.",
    "Wealth whispers — hype screams.",
    "Trade like an owner, not a gambler.",
    "The trend rewards those who survive the chop.",
    "Macro patience, micro execution.",
    "Your rules are your real leverage.",
    "Capital compounds when ego doesn’t.",
    "Good traders love being bored.",
    "Every stop is a boundary — boundaries build empires.",
    "Focus on the next right action.",
    "The scoreboard is long-term.",
    "Liquidity, volatility, discipline — pick two to respect.",
    "Plan the trade — trade the plan.",
    "Confidence follows evidence.",
    "Let winners breathe — cut doubts fast.",
    "The market is a teacher — pay attention.",
    "Wealth is what you keep after the storm.",
    "Risk defines your runway.",
    "Slow is smooth — smooth is profitable.",
    "Build habits that pay rent.",
    "Data over drama.",
    "Your edge is boring on purpose.",
    "Trade small enough to think clearly.",
    "Protect the stack — opportunities recycle.",
    "Consistency is the real alpha.",
    "Mind the spread — and the ego spread too.",
    "Every session is practice for the big one.",
    "Stay humble — the market humbles for free.",
    "Fortune favors funded discipline.",
    "Think in distributions, not single trades.",
    "Keep powder dry for high conviction.",
    "Process first — outcomes follow.",
    "Quiet accounts grow loud results.",
    "Measure risk in sleep hours saved.",
    "Trade to live — don’t live to trade recklessly.",
    "The best risk manager is a rested mind.",
    "Wealth: delayed gratification with a spreadsheet.",
    "Your playbook beats your mood.",
    "Signals are invitations — risk management is RSVP.",
    "Stack skills — gold follows.",
    "Precision is respect for capital.",
    "The market rewards adults.",
    "Build the machine — then let it run.",
    "Survive first — thrive second.",
    "Risk is rented — never marry it.",
    "Keep losses boring — let wins surprise you.",
    "Macro calm, micro sharp.",
    "Your journal is your edge file.",
    "Wealth whispers when discipline speaks.",
    "Trade clean — live free.",
    "Capital is confidence with a limit order.",
    "The line between pro and amateur is process.",
    "Let math lead — let noise fade.",
    "Opportunity is infinite — capital is not.",
    "Protect the downside — celebrate the upside.",
    "Stillness before entries — speed after risk is defined.",
    "Wealth is a series of good nos.",
    "Trade the odds — sleep the calm.",
    "Discipline is the interest rate on skill.",
    "Small steps, large arcs.",
    "Your system is your shield.",
    "Markets test patience — pass quietly.",
    "Risk smart — stack long.",
    "The chart is a mirror — your rules are the light.",
    "Wealth compounds where fear is managed.",
    "Stay mechanical on entries — human on review.",
    "Profit is the applause — process is the rehearsal.",
    "Keep score weekly — not tick-by-tick emotionally.",
    "Liquidity is opportunity wearing a mask.",
    "Trade like you’ll trade forever.",
    "The best revenge on chaos is a checklist.",
    "Wealth: boring days, exciting years.",
    "Risk small — dream big — repeat.",
    "Your future portfolio thanks today’s pause.",
    "Precision beats prediction — always.",
    "Markets reward the consistent, not the clever.",
    "Stay green in mind when red on a trade.",
    "Wealth is built in the hours nobody claps for.",
]

DAILY_MESSAGES = [
    "Another day of disciplined trading. Keep grinding! 💪",
    "The markets never sleep, and neither does ClubMillies 🌙",
    "Every day is a step closer to financial freedom 🏆",
    "Trust the confluence, trust the process 🔥",
    "Not the best you can get but the best there is 👑",
    "Building wealth one smart trade at a time 📈",
]
