"""
ClubMillies — Central configuration via environment variables.
"""
import os
from dataclasses import dataclass, field
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "clubmillies.db"


@dataclass
class Settings:
    # Telegram
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # Anthropic
    anthropic_api_key: str = ""

    # Twitter
    twitter_bearer_token: str = ""

    # API
    api_secret_key: str = "change-me"
    host: str = "0.0.0.0"
    port: int = 8000

    # Database
    db_url: str = f"sqlite+aiosqlite:///{DB_PATH}"
    db_sync_url: str = f"sqlite:///{DB_PATH}"

    # Trading defaults
    default_symbol: str = "XAUUSDm"
    default_timeframe: str = "M15"
    default_candle_count: int = 150
    default_poll_interval: int = 60

    # Strategy defaults
    ema_fast: int = 9
    ema_slow: int = 21
    rsi_period: int = 14
    atr_period: int = 14

    # Profiles
    sniper: dict = field(default_factory=lambda: {
        "min_confluence": 7, "atr_sl": 2.5, "atr_tp": 0.6,
        "risk_per_trade": 0.02, "max_open_trades": 3, "max_daily_loss": 0.05,
    })
    aggressive: dict = field(default_factory=lambda: {
        "min_confluence": 5, "atr_sl": 2.5, "atr_tp": 0.6,
        "risk_per_trade": 0.02, "max_open_trades": 3, "max_daily_loss": 0.05,
    })

    @classmethod
    def from_env(cls):
        return cls(
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
            telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            twitter_bearer_token=os.getenv("TWITTER_BEARER_TOKEN", ""),
            api_secret_key=os.getenv("API_SECRET_KEY", "change-me"),
            host=os.getenv("HOST", "0.0.0.0"),
            port=int(os.getenv("PORT", "8000")),
        )


settings = Settings.from_env()
