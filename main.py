#!/usr/bin/env python3
"""
ClubMillies — Main entry point.
Starts: API server, trading engine, Telegram bot, news monitor, Twitter monitor.
"""
import asyncio
import logging
import sys
import signal
import uvicorn
from pathlib import Path
import os

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from core.database import init_db, init_db_sync, AsyncSessionLocal
from core.models import Account
from core.config import settings
from accounts.manager import AccountManager
from api.app import app
from sqlalchemy import select

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("clubmillies.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("clubmillies")

BANNER = r"""
   ╔═══════════════════════════════════════════════════════════╗
   ║                                                           ║
   ║       ██████╗██╗     ██╗   ██╗██████╗                     ║
   ║      ██╔════╝██║     ██║   ██║██╔══██╗                    ║
   ║      ██║     ██║     ██║   ██║██████╔╝                    ║
   ║      ██║     ██║     ██║   ██║██╔══██╗                    ║
   ║      ╚██████╗███████╗╚██████╔╝██████╔╝                   ║
   ║       ╚═════╝╚══════╝ ╚═════╝ ╚═════╝                    ║
   ║                                                           ║
   ║      ███╗   ███╗██╗██╗     ██╗     ██╗███████╗███████╗    ║
   ║      ████╗ ████║██║██║     ██║     ██║██╔════╝██╔════╝    ║
   ║      ██╔████╔██║██║██║     ██║     ██║█████╗  ███████╗    ║
   ║      ██║╚██╔╝██║██║██║     ██║     ██║██╔══╝  ╚════██║    ║
   ║      ██║ ╚═╝ ██║██║███████╗███████╗██║███████╗███████║    ║
   ║      ╚═╝     ╚═╝╚═╝╚══════╝╚══════╝╚═╝╚══════╝╚══════╝  ║
   ║                                                           ║
   ║      Not the best you can get but the best there is       ║
   ║                                                           ║
   ╚═══════════════════════════════════════════════════════════╝
"""


async def create_default_accounts():
    """Create default accounts if none exist."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Account))
        if not result.scalars().first():
            # Defaults are optional and must come from environment variables.
            # Never hardcode real credentials in source control.
            create_paper = (os.getenv("CREATE_PAPER_DEMO", "false").lower() == "true")
            if create_paper:
                session.add(Account(
                    name="Paper Demo",
                    broker_type="paper",
                    symbol=os.getenv("DEFAULT_SYMBOL", "XAUUSDm"),
                    profile=os.getenv("DEFAULT_PROFILE", "SNIPER"),
                    balance=float(os.getenv("PAPER_BALANCE", "10000")),
                    equity=float(os.getenv("PAPER_BALANCE", "10000")),
                    enabled=True,
                ))

            mt5_login = os.getenv("MT5_LOGIN", "").strip()
            mt5_password = os.getenv("MT5_PASSWORD", "").strip()
            mt5_server = os.getenv("MT5_SERVER", "").strip()
            if mt5_login and mt5_password and mt5_server:
                session.add(Account(
                    name=os.getenv("MT5_ACCOUNT_NAME", "MT5 Account"),
                    broker_type="mt5",
                    login=mt5_login,
                    password=mt5_password,
                    server=mt5_server,
                    symbol=os.getenv("MT5_SYMBOL", os.getenv("DEFAULT_SYMBOL", "XAUUSDm")),
                    timeframe=os.getenv("MT5_TIMEFRAME", "M15"),
                    profile=os.getenv("DEFAULT_PROFILE", "SNIPER"),
                    balance=0.0,
                    equity=0.0,
                    enabled=True,
                ))
            await session.commit()
            logger.info("Created default accounts from environment variables")


async def start_services():
    """Start all ClubMillies services."""
    print(BANNER)

    # Initialize database
    await init_db()
    await create_default_accounts()
    logger.info("Database initialized")

    # Start account manager (trading engine)
    manager = AccountManager()
    await manager.start_all()
    logger.info("Trading engine started")
    # Expose manager to API routes (create/toggle can start/stop runners)
    app.state.account_manager = manager

    # Start Telegram bot
    try:
        from notifications.telegram_bot import setup_telegram
        await setup_telegram()
    except ImportError as e:
        logger.warning(f"Telegram bot not available: {e}")
    except Exception as e:
        logger.warning(f"Telegram bot failed to start: {e}")

    # Start news monitor
    try:
        from intelligence.news_fetcher import news_monitor_loop
        asyncio.create_task(news_monitor_loop())
        logger.info("News monitor started")
    except Exception as e:
        logger.warning(f"News monitor failed: {e}")

    # Start AI analyzer (Claude) for news/tweets/market if configured
    try:
        from intelligence.claude_analyzer import ClaudeAnalyzer
        from core.events import NEWS_EVENT, bus

        analyzer = ClaudeAnalyzer()

        async def _on_news_for_ai(event):
            try:
                # event.data comes from bus.emit(NEWS_EVENT, ev)
                await analyzer.analyze_news(event.data)
            except Exception as e:
                logger.warning(f"AI news analysis failed: {e}")

        if analyzer.enabled:
            bus.subscribe(NEWS_EVENT, _on_news_for_ai)
            logger.info("AI analyzer enabled")
        else:
            logger.info("AI analyzer disabled (no ANTHROPIC_API_KEY)")
    except Exception as e:
        logger.warning(f"AI analyzer failed to start: {e}")

    # Start Twitter monitor
    try:
        from intelligence.twitter_monitor import TwitterMonitor
        twitter = TwitterMonitor()
        asyncio.create_task(twitter.monitor_loop())
    except Exception as e:
        logger.warning(f"Twitter monitor failed: {e}")

    # AI analyze tweet batches (if AI is enabled)
    try:
        from core.events import bus
        from intelligence.claude_analyzer import ClaudeAnalyzer

        analyzer = ClaudeAnalyzer()

        async def _on_tweets_for_ai(event):
            try:
                tweets = (event.data or {}).get("tweets") or []
                if tweets:
                    await analyzer.analyze_tweets(tweets)
            except Exception as e:
                logger.warning(f"AI tweet analysis failed: {e}")

        if analyzer.enabled:
            bus.subscribe("twitter.tweets", _on_tweets_for_ai)
    except Exception as e:
        logger.warning(f"AI tweet hook failed: {e}")

    # Start API server
    config = uvicorn.Config(
        app,
        host=settings.host,
        port=settings.port,
        log_level="info",
    )
    server = uvicorn.Server(config)

    logger.info(f"API server starting on http://{settings.host}:{settings.port}")
    logger.info(f"Dashboard: http://localhost:3000")
    logger.info("Press Ctrl+C to stop")

    await server.serve()


def main():
    try:
        asyncio.run(start_services())
    except KeyboardInterrupt:
        print("\n\nShutting down ClubMillies...")
        logger.info("ClubMillies stopped")


if __name__ == "__main__":
    main()
