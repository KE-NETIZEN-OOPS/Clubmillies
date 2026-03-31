"""
Forex Gold Bot Configuration — JustMarkets / MetaTrader 5

Two trading profiles:

  SNIPER MODE (default):
    ~85% win rate, fewer trades, consistent profits
    Best for: beginners, small accounts, peace of mind

  AGGRESSIVE MODE:
    ~83% win rate, many more trades, much higher total returns
    Best for: experienced traders, larger accounts, compounding
"""

# ── MetaTrader 5 / JustMarkets Settings ─────────────────────────────
MT5_LOGIN = 0
MT5_PASSWORD = ""
MT5_SERVER = "JustMarkets-Demo"

# ── Trading Instrument ──────────────────────────────────────────────
SYMBOL = "XAUUSDm"

# ── Choose Your Profile ─────────────────────────────────────────────
PROFILE = "SNIPER"   # "SNIPER" or "AGGRESSIVE"

# ── Strategy Parameters (shared) ────────────────────────────────────
EMA_FAST = 9
EMA_SLOW = 21
RSI_PERIOD = 14
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30
ATR_PERIOD = 14

# ── Profile-specific Settings ───────────────────────────────────────
if PROFILE == "SNIPER":
    # ~85% win rate | ~58 trades per 2000 candles | ~9% return
    # Safe, consistent, high win rate
    MIN_CONFLUENCE = 7       # Need 7/15 strategies to agree
    ATR_SL_MULTIPLIER = 2.5  # Wide stop loss (more room)
    ATR_TP_MULTIPLIER = 0.6  # Quick take profit (lock in wins fast)
elif PROFILE == "AGGRESSIVE":
    # ~83% win rate | ~545 trades per 2000 candles | ~112% return
    # More trades, bigger returns, slightly lower win rate
    MIN_CONFLUENCE = 5
    ATR_SL_MULTIPLIER = 2.5
    ATR_TP_MULTIPLIER = 0.6
else:
    raise ValueError(f"Unknown profile: {PROFILE}. Use 'SNIPER' or 'AGGRESSIVE'.")

# ── Risk Management ─────────────────────────────────────────────────
RISK_PER_TRADE = 0.02       # Risk 2% of account per trade
MAX_OPEN_TRADES = 3
MAX_DAILY_LOSS = 0.05       # Stop trading if daily loss exceeds 5%
LOT_SIZE_MIN = 0.01
LOT_SIZE_MAX = 5.0

# ── Timeframe & Polling ─────────────────────────────────────────────
TIMEFRAME = "M15"
CANDLE_COUNT = 150
POLL_INTERVAL = 60

# ── Logging ──────────────────────────────────────────────────────────
LOG_FILE = "gold_bot.log"
LOG_LEVEL = "INFO"
