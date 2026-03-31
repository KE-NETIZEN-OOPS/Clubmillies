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


async def create_default_account():
    """Create a default paper trading account if none exist."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Account))
        if not result.scalars().first():
            account = Account(
                name="Paper Demo",
                broker_type="paper",
                symbol="XAUUSDm",
                profile="SNIPER",
                balance=10000.0,
                equity=10000.0,
                enabled=True,
            )
            session.add(account)
            await session.commit()
            logger.info("Created default paper trading account")


async def start_services():
    """Start all ClubMillies services."""
    print(BANNER)

    # Initialize database
    await init_db()
    await create_default_account()
    logger.info("Database initialized")

    # Start account manager (trading engine)
    manager = AccountManager()
    await manager.start_all()
    logger.info("Trading engine started")

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

    # Start Twitter monitor
    try:
        from intelligence.twitter_monitor import TwitterMonitor
        twitter = TwitterMonitor()
        asyncio.create_task(twitter.monitor_loop())
    except Exception as e:
        logger.warning(f"Twitter monitor failed: {e}")

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
