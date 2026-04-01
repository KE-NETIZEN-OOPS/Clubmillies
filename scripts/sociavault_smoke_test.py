#!/usr/bin/env python3
"""
Quick SociaVault connectivity test (reads SOCIAVAULT_API_KEY from environment).
Do not pass keys on the command line.

  set SOCIAVAULT_API_KEY=sk_live_...
  python scripts/sociavault_smoke_test.py
"""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from intelligence.sociavault import fetch_twitter_search


async def main():
    key = (os.getenv("SOCIAVAULT_API_KEY") or "").strip()
    if not key:
        print("Set SOCIAVAULT_API_KEY in the environment.")
        sys.exit(1)
    q = os.getenv("SOCIAVAULT_TEST_QUERY", "XAUUSD gold")
    rows = await fetch_twitter_search(key, q)
    print(f"Query: {q!r}")
    print(f"Parsed tweets: {len(rows)}")
    for t in rows[:5]:
        print(f"  @{t['author']}: {t['text'][:120]}...")


if __name__ == "__main__":
    asyncio.run(main())
