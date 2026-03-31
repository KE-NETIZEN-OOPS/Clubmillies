#!/usr/bin/env python3
"""
Forex Gold Trading Bot — JustMarkets / MetaTrader 5

Usage:
  python bot.py live       # Live/demo trading via MT5 (requires MT5 + credentials)
  python bot.py paper      # Paper trading simulation (no MT5 needed)
  python bot.py backtest   # Backtest on historical data (requires MT5)
"""
import sys
import time
import signal
import logging
from datetime import datetime

import config

# ── Logging setup ────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(config.LOG_FILE),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("gold_bot")

running = True


def handle_exit(signum, frame):
    global running
    print("\n\nShutting down gracefully...")
    running = False


signal.signal(signal.SIGINT, handle_exit)
signal.signal(signal.SIGTERM, handle_exit)


def run_live():
    from mt5_client import MT5Client
    from strategy import GoldStrategy

    if not config.MT5_LOGIN or not config.MT5_PASSWORD:
        print("\n  ERROR: Set your MT5 credentials in config.py first!")
        print("  1. Open a demo account at https://justmarkets.com/")
        print("  2. Fill in MT5_LOGIN, MT5_PASSWORD, MT5_SERVER in config.py")
        sys.exit(1)

    client = MT5Client()
    if not client.connect():
        print("\n  ERROR: Could not connect to MetaTrader 5.")
        print("  Make sure MT5 is installed, running, and logged in.")
        sys.exit(1)

    strategy = GoldStrategy(client)
    info = client.get_account_info()

    print(f"\n  Connected to {info['server']}")
    print(f"  Account:         {info['login']}")
    print(f"  Balance:         ${info['balance']:.2f}")
    print(f"  Leverage:        1:{info['leverage']}")
    print(f"  Symbol:          {config.SYMBOL}")
    print(f"  Timeframe:       {config.TIMEFRAME}")
    print(f"  Strategy:        EMA({config.EMA_FAST}/{config.EMA_SLOW}) + RSI({config.RSI_PERIOD})")
    print(f"  Risk per trade:  {config.RISK_PER_TRADE*100:.0f}%")
    print(f"  Polling every:   {config.POLL_INTERVAL}s")
    print(f"\n  Bot is running... Press Ctrl+C to stop.\n")

    try:
        while running:
            try:
                result = strategy.run()
                action = result.get("action", "NONE")

                if action in ("BUY", "SELL"):
                    logger.info(f"=== {action} {result['lots']} lots @ {result['price']:.2f} | "
                               f"SL: {result['sl']:.2f} | TP: {result['tp']:.2f} ===")
                elif action == "HOLD":
                    logger.debug(f"Holding | Price: {result['price']:.2f} | RSI: {result['rsi']:.1f}")
                elif action == "BLOCKED":
                    logger.warning(f"Blocked: {result['reason']}")

                time.sleep(config.POLL_INTERVAL)
            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"Error: {e}", exc_info=True)
                time.sleep(30)
    finally:
        client.disconnect()
        print("  MT5 disconnected. Goodbye.")


def run_paper():
    from paper_trader import PaperTrader

    trader = PaperTrader(starting_balance=10000.0)

    print("\n" + "=" * 50)
    print("  GOLD BOT — Paper Trading Mode")
    print("=" * 50)
    print(f"  Starting Balance: $10,000.00")
    print(f"  Strategy: EMA({config.EMA_FAST}/{config.EMA_SLOW}) + RSI({config.RSI_PERIOD})")
    print(f"  Risk per trade: {config.RISK_PER_TRADE*100:.0f}%")
    print(f"  Polling every {config.POLL_INTERVAL}s — Press Ctrl+C to stop.\n")

    while running:
        try:
            trader.run_once()
            time.sleep(config.POLL_INTERVAL)
        except KeyboardInterrupt:
            break
        except Exception as e:
            logger.error(f"Error: {e}", exc_info=True)
            time.sleep(10)

    trader.print_summary()


def run_backtest():
    from mt5_client import MT5Client
    from backtester import backtest

    if not config.MT5_LOGIN:
        print("\n  ERROR: Set your MT5 credentials in config.py first!")
        sys.exit(1)

    client = MT5Client()
    if not client.connect():
        print("  ERROR: Could not connect to MT5.")
        sys.exit(1)

    try:
        print(f"\n  Running backtest on {config.SYMBOL} ({config.TIMEFRAME})...")
        backtest(client, candle_count=500)
    finally:
        client.disconnect()


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "paper"

    print(r"""
   ██████╗  ██████╗ ██╗     ██████╗     ██████╗  ██████╗ ████████╗
  ██╔════╝ ██╔═══██╗██║     ██╔══██╗    ██╔══██╗██╔═══██╗╚══██╔══╝
  ██║  ███╗██║   ██║██║     ██║  ██║    ██████╔╝██║   ██║   ██║
  ██║   ██║██║   ██║██║     ██║  ██║    ██╔══██╗██║   ██║   ██║
  ╚██████╔╝╚██████╔╝███████╗██████╔╝    ██████╔╝╚██████╔╝   ██║
   ╚═════╝  ╚═════╝ ╚══════╝╚═════╝     ╚═════╝  ╚═════╝    ╚═╝
                    JustMarkets / MT5 Edition
    """)

    if mode == "live":
        run_live()
    elif mode == "paper":
        run_paper()
    elif mode == "backtest":
        run_backtest()
    else:
        print(f"Unknown mode: {mode}")
        print("Usage: python bot.py [live|paper|backtest]")
        sys.exit(1)


if __name__ == "__main__":
    main()
