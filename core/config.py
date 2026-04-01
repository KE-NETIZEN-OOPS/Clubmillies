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
    # Stats commands: exclude paper bots; narrow to MT5 and/or live (see .env.example)
    telegram_exclude_paper: bool = True
    telegram_mt5_only: bool = False
    telegram_mt5_live_only: bool = False
    # Comma-separated account ids — if set, only these (enabled) rows are used for /status /report /trades
    telegram_stats_account_ids: str = ""

    # Anthropic
    anthropic_api_key: str = ""

    # Twitter / intel (comma-separated)
    twitter_bearer_token: str = ""
    twitter_search_queries: str = ""  # API v2 recent search, e.g. "gold OR XAUUSD OR DXY"
    google_news_queries: str = "gold price,XAUUSD,DXY US Dollar"

    # SociaVault (optional — X search via api.sociavault.com; key in .env only)
    sociavault_api_key: str = ""
    sociavault_base_url: str = "https://api.sociavault.com"
    # Comma-separated Twitter search queries; falls back to twitter_search_queries if empty
    sociavault_search_queries: str = ""
    # Default X search for manual "Fetch new tweets" button (SociaVault, 1 credit per click)
    intel_default_query: str = 'gold OR XAUUSD OR DXY OR war OR "us dollar index"'

    # API
    api_secret_key: str = "change-me"
    host: str = "0.0.0.0"
    port: int = 8000
    # Telegram / links (production dashboard URL, not localhost)
    dashboard_public_url: str = "https://clubmillies.vercel.app"

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

    # Hard floor for directional trades / signals (profiles cannot go below this).
    min_confluence_floor: int = 5

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
            twitter_search_queries=os.getenv("TWITTER_SEARCH_QUERIES", ""),
            google_news_queries=os.getenv("GOOGLE_NEWS_QUERIES", "gold price,XAUUSD,DXY US Dollar"),
            sociavault_api_key=os.getenv("SOCIAVAULT_API_KEY", ""),
            sociavault_base_url=os.getenv("SOCIAVAULT_BASE_URL", "https://api.sociavault.com"),
            sociavault_search_queries=os.getenv("SOCIAVAULT_SEARCH_QUERIES", ""),
            intel_default_query=os.getenv(
                "INTEL_DEFAULT_QUERY",
                'gold OR XAUUSD OR DXY OR war OR "us dollar index"',
            ),
            api_secret_key=os.getenv("API_SECRET_KEY", "change-me"),
            host=os.getenv("HOST", "0.0.0.0"),
            port=int(os.getenv("PORT", "8000")),
            min_confluence_floor=int(os.getenv("MIN_CONFLUENCE_FLOOR", "5")),
            dashboard_public_url=os.getenv(
                "DASHBOARD_PUBLIC_URL", "https://clubmillies.vercel.app"
            ).rstrip("/"),
            telegram_exclude_paper=os.getenv("TELEGRAM_EXCLUDE_PAPER", "true").lower()
            in ("1", "true", "yes"),
            telegram_mt5_only=os.getenv("TELEGRAM_MT5_ONLY", "false").lower()
            in ("1", "true", "yes"),
            telegram_mt5_live_only=os.getenv("TELEGRAM_MT5_LIVE_ONLY", "false").lower()
            in ("1", "true", "yes"),
            telegram_stats_account_ids=os.getenv("TELEGRAM_STATS_ACCOUNT_IDS", "").strip(),
        )


settings = Settings.from_env()
