#!/usr/bin/env python3
"""Send a one-off test message using TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID from .env."""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

# Avoid httpx INFO lines that would echo the request URL (token in path).
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


async def main() -> None:
    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    chat_id = (os.getenv("TELEGRAM_CHAT_ID") or "").strip()
    if not token or not chat_id:
        print("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID in .env", file=sys.stderr)
        sys.exit(1)

    import httpx

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": "<b>ClubMillies test</b>\nIf you see this, outbound Telegram is working.",
        "parse_mode": "HTML",
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(url, json=payload)
    try:
        body = r.json()
    except Exception:
        print("Failed: invalid JSON from Telegram", file=sys.stderr)
        sys.exit(1)

    ok = r.status_code == 200 and isinstance(body, dict) and body.get("ok") is True
    if ok:
        print("OK: Telegram accepted the message (open the chat with this bot to read it).")
        mid = (body.get("result") or {}).get("message_id")
        if mid is not None:
            print(f"message_id={mid}")
        return

    print(f"Failed: HTTP {r.status_code}", file=sys.stderr)
    err = body.get("description") if isinstance(body, dict) else None
    if err:
        print(err, file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
