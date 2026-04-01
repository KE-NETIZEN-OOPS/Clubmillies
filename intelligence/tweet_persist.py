"""Persist intel tweet dicts into the Tweet table (shared by monitor + manual fetch)."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from core.database import AsyncSessionLocal
from core.models import Tweet


async def persist_tweet_dicts(tweets: list[dict]) -> int:
    """Insert new tweets; skip duplicates. Returns number of rows inserted."""
    inserted = 0
    async with AsyncSessionLocal() as session:
        for t in tweets:
            tweet_id = str(t.get("id", "")).strip()
            if not tweet_id:
                continue

            existing = await session.execute(
                select(Tweet).where(Tweet.tweet_id == tweet_id)
            )
            if existing.scalar_one_or_none():
                continue

            created_at = None
            try:
                ca = t.get("created_at")
                if ca:
                    ca2 = (
                        ca.replace("Z", "+00:00")
                        if isinstance(ca, str) and ca.endswith("Z")
                        else ca
                    )
                    created_at = datetime.fromisoformat(ca2)
                    if created_at.tzinfo:
                        created_at = created_at.astimezone(timezone.utc).replace(tzinfo=None)
            except Exception:
                created_at = None

            url = t.get("url")
            if not url:
                author = t.get("author", "")
                url = (
                    f"https://x.com/{author}/status/{tweet_id}"
                    if author and tweet_id.isdigit()
                    else None
                )

            session.add(
                Tweet(
                    tweet_id=tweet_id,
                    author=t.get("author", ""),
                    text=t.get("text", ""),
                    url=url,
                    created_at=created_at,
                )
            )
            inserted += 1

        await session.commit()
    return inserted
