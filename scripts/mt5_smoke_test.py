"""
MT5 smoke test for connectivity + symbol + (optional) tiny trade.

Default behavior performs a safe "order_check" only (no execution).
Use --execute to place a minimal test order and immediately close it.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Load repo .env for convenience (same as the backend).
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:
    pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default=os.getenv("MT5_SYMBOL", "XAUUSD.s"))
    parser.add_argument("--volume", type=float, default=float(os.getenv("MT5_TEST_VOLUME", "0.01")))
    parser.add_argument("--side", choices=["BUY", "SELL"], default="BUY")
    parser.add_argument("--sl", type=float, default=0.0, help="Absolute SL price (0 = no SL).")
    parser.add_argument("--tp", type=float, default=0.0, help="Absolute TP price (0 = no TP).")
    parser.add_argument("--sl-points", type=float, default=0.0, help="SL distance in price units (e.g. 5.0).")
    parser.add_argument("--tp-points", type=float, default=0.0, help="TP distance in price units (e.g. 5.0).")
    parser.add_argument("--execute", action="store_true", help="Actually place and close a test order (REAL execution).")
    args = parser.parse_args()

    import MetaTrader5 as mt5

    login = os.getenv("MT5_LOGIN", "").strip()
    password = os.getenv("MT5_PASSWORD", "").strip()
    server = os.getenv("MT5_SERVER", "").strip()
    if not (login and password and server):
        raise SystemExit("Missing MT5_LOGIN/MT5_PASSWORD/MT5_SERVER in environment.")

    # On some setups, initialize() fails with authorization error unless credentials are
    # provided up front (or a terminal instance is already logged in).
    if not mt5.initialize(login=int(login), password=password, server=server):
        raise SystemExit(
            "mt5.initialize failed. Make sure the MetaTrader 5 terminal is installed, "
            "you can log in with these credentials in the terminal, and Algo Trading is enabled. "
            f"last_error={mt5.last_error()}"
        )

    try:
        # Extra login call is harmless and helps on some terminals.
        if not mt5.login(login=int(login), password=password, server=server):
            raise SystemExit(f"mt5.login failed: {mt5.last_error()}")

        acc = mt5.account_info()
        if not acc:
            raise SystemExit("mt5.account_info returned None")

        print(f"Connected: server={acc.server} login={acc.login} balance={acc.balance} equity={acc.equity}")

        sym = mt5.symbol_info(args.symbol)
        if not sym:
            raise SystemExit(f"Symbol not found in terminal: {args.symbol}")

        if not sym.visible:
            mt5.symbol_select(args.symbol, True)

        tick = mt5.symbol_info_tick(args.symbol)
        if not tick:
            raise SystemExit(f"No tick for symbol: {args.symbol}")

        order_type = mt5.ORDER_TYPE_BUY if args.side == "BUY" else mt5.ORDER_TYPE_SELL
        price = tick.ask if args.side == "BUY" else tick.bid
        digits = getattr(sym, "digits", 2) or 2

        # Determine SL/TP if requested.
        sl = float(args.sl or 0.0)
        tp = float(args.tp or 0.0)
        if not sl and args.sl_points:
            sl = price - float(args.sl_points) if args.side == "BUY" else price + float(args.sl_points)
        if not tp and args.tp_points:
            tp = price + float(args.tp_points) if args.side == "BUY" else price - float(args.tp_points)
        sl = round(sl, digits) if sl else 0.0
        tp = round(tp, digits) if tp else 0.0

        # Probe filling mode: JustMarkets XAUUSD.s accepts FOK only.
        sym_fill = getattr(sym, "filling_mode", None)
        preferred_fillings = [
            getattr(mt5, "ORDER_FILLING_FOK", None),
            sym_fill,
            getattr(mt5, "ORDER_FILLING_IOC", None),
            getattr(mt5, "ORDER_FILLING_RETURN", None),
        ]
        preferred_fillings = [f for f in preferred_fillings if f is not None]
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": args.symbol,
            "volume": float(args.volume),
            "type": order_type,
            "price": float(price),
            "sl": sl,
            "tp": tp,
            "deviation": 20,
            "magic": 123456,
            "comment": "ClubMillies smoke test",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": preferred_fillings[0],
        }

        check = None
        last = None
        for f in preferred_fillings:
            req = {**request, "type_filling": f}
            last = mt5.order_check(req)
            if last is not None and getattr(last, "retcode", None) == 0:
                check = last
                request = req
                break
        print("order_check:", check or last)
        if (check or last) is None:
            raise SystemExit(f"order_check returned None: {mt5.last_error()}")

        if not args.execute:
            print("OK: connectivity + symbol + order_check succeeded (no trade executed).")
            return

        print("EXECUTE enabled: placing test order...")
        result = mt5.order_send(request)
        print("order_send:", result)
        if result is None:
            raise SystemExit(f"order_send returned None: {mt5.last_error()}")
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            raise SystemExit(f"order_send failed retcode={result.retcode} comment={getattr(result,'comment',None)}")

        # Give terminal a moment to register position, then close it
        time.sleep(1.0)
        positions = mt5.positions_get(symbol=args.symbol)
        if not positions:
            print("Placed order but positions_get returned none; not closing.")
            return

        # Prefer the position that matches our magic + side + volume
        target_type = mt5.ORDER_TYPE_BUY if args.side == "BUY" else mt5.ORDER_TYPE_SELL
        candidates = [p for p in positions if getattr(p, "magic", None) == 123456 and abs(p.volume - float(args.volume)) < 1e-9]
        candidates = [p for p in candidates if getattr(p, "type", None) == target_type] or candidates
        pos = sorted(candidates or list(positions), key=lambda p: p.time, reverse=True)[0]
        close_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
        tick2 = mt5.symbol_info_tick(args.symbol)
        close_price = tick2.bid if pos.type == mt5.ORDER_TYPE_BUY else tick2.ask

        close_req_base = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": args.symbol,
            "position": pos.ticket,
            "volume": pos.volume,
            "type": close_type,
            "price": float(close_price),
            "deviation": 20,
            "magic": 123456,
            "comment": "ClubMillies smoke test close",
            "type_time": mt5.ORDER_TIME_GTC,
        }

        close_res = None
        close_last = None
        for f in preferred_fillings:
            close_req = {**close_req_base, "type_filling": f}
            close_last = mt5.order_check(close_req)
            if close_last is not None and getattr(close_last, "retcode", None) == 0:
                close_res = mt5.order_send(close_req)
                break

        if close_res is None:
            # Still attempt a send with the first filling for a clearer retcode/comment.
            close_res = mt5.order_send({**close_req_base, "type_filling": preferred_fillings[0]})

        print("close_check:", close_last)
        print("close_send:", close_res)
        print("OK: test trade placed and close attempted.")

    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()

