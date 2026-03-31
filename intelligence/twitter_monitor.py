"""
ClubMillies — Twitter/X monitor for gold market intelligence.
Supports two modes:
  1. Official API (if bearer token provided) — most reliable
  2. Free scraping via RSS bridges and syndication — no API key needed
"""
import asyncio
import logging
import re
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

from core.config import settings
from core.events import bus

logger = logging.getLogger("clubmillies.twitter")

# Key accounts for gold/forex intelligence
DEFAULT_ACCOUNTS = [
    "zaborhedge",
    "GoldTelegraph",
    "DeItaone",
    "ForexLive",
    "Faborhedge",
    "financialjuice",
    "IGSquawk",
]

TWITTER_API_BASE = "https://api.twitter.com/2"

# Free RSS/scraping sources to try (in order of reliability)
RSS_BRIDGES = [
    "https://nitter.privacydev.net/{username}/rss",
    "https://nitter.poast.org/{username}/rss",
    "https://nitter.1d4.us/{username}/rss",
    "https://rsshub.app/twitter/user/{username}",
]


class TwitterMonitor:
    def __init__(self, bearer_token: str = None, accounts: list[str] = None):
        self.bearer_token = bearer_token or settings.twitter_bearer_token
        self.accounts = accounts or DEFAULT_ACCOUNTS
        self.last_tweet_ids: dict[str, str] = {}
        self.use_api = bool(self.bearer_token)
        self._working_bridge: str | None = None
        self._seen_tweets: set[str] = set()

    # ── Official API Mode ────────────────────────────────────────────

    async def _api_get_user_id(self, username: str) -> str | None:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{TWITTER_API_BASE}/users/by/username/{username}",
                headers={"Authorization": f"Bearer {self.bearer_token}"},
            )
            if resp.status_code == 200:
                return resp.json()["data"]["id"]
        return None

    async def _api_fetch_tweets(self, username: str) -> list[dict]:
        try:
            user_id = await self._api_get_user_id(username)
            if not user_id:
                return []

            params = {
                "max_results": 10,
                "tweet.fields": "created_at,text,public_metrics",
            }
            since_id = self.last_tweet_ids.get(username)
            if since_id:
                params["since_id"] = since_id

            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{TWITTER_API_BASE}/users/{user_id}/tweets",
                    headers={"Authorization": f"Bearer {self.bearer_token}"},
                    params=params,
                )

            if resp.status_code != 200:
                return []

            data = resp.json()
            tweets = data.get("data", [])
            if tweets:
                self.last_tweet_ids[username] = tweets[0]["id"]

            return [
                {
                    "id": t["id"],
                    "text": t["text"],
                    "author": username,
                    "created_at": t.get("created_at", ""),
                    "source": "api",
                }
                for t in tweets
            ]
        except Exception as e:
            logger.error(f"Twitter API error for @{username}: {e}")
            return []

    # ── Free Scraping Mode ───────────────────────────────────────────

    async def _find_working_bridge(self) -> str | None:
        """Try each RSS bridge until one works."""
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            for bridge_template in RSS_BRIDGES:
                url = bridge_template.format(username="GoldTelegraph")
                try:
                    resp = await client.get(url, headers={
                        "User-Agent": "Mozilla/5.0 (compatible; ClubMillies/1.0)"
                    })
                    if resp.status_code == 200 and ("<item" in resp.text or "<entry" in resp.text):
                        logger.info(f"Found working RSS bridge: {bridge_template}")
                        return bridge_template
                except Exception:
                    continue
        return None

    async def _scrape_rss(self, username: str) -> list[dict]:
        """Fetch tweets via RSS bridge."""
        if not self._working_bridge:
            return []

        url = self._working_bridge.format(username=username)
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                resp = await client.get(url, headers={
                    "User-Agent": "Mozilla/5.0 (compatible; ClubMillies/1.0)"
                })
                if resp.status_code != 200:
                    return []

            soup = BeautifulSoup(resp.text, "xml")
            tweets = []

            # RSS format (Nitter)
            items = soup.find_all("item") or soup.find_all("entry")
            for item in items[:10]:
                title = item.find("title")
                desc = item.find("description") or item.find("content")
                link = item.find("link")
                pub_date = item.find("pubDate") or item.find("published")

                text = ""
                if desc:
                    # Strip HTML from description
                    text = BeautifulSoup(desc.get_text(), "html.parser").get_text()
                elif title:
                    text = title.get_text()

                if not text:
                    continue

                # Create unique ID from text hash
                tweet_id = f"{username}_{hash(text[:100])}"
                if tweet_id in self._seen_tweets:
                    continue
                self._seen_tweets.add(tweet_id)

                tweets.append({
                    "id": tweet_id,
                    "text": text.strip()[:500],
                    "author": username,
                    "created_at": pub_date.get_text() if pub_date else "",
                    "source": "rss",
                })

            return tweets

        except Exception as e:
            logger.debug(f"RSS scrape error for @{username}: {e}")
            return []

    async def _scrape_syndication(self, username: str) -> list[dict]:
        """Fallback: try Twitter's syndication endpoint."""
        try:
            url = f"https://syndication.twitter.com/srv/timeline-profile/screen-name/{username}"
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                resp = await client.get(url, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                })
                if resp.status_code != 200:
                    return []

            soup = BeautifulSoup(resp.text, "html.parser")
            tweets = []

            # Find tweet text elements
            for tweet_el in soup.select("[data-tweet-id]")[:10]:
                tweet_id = tweet_el.get("data-tweet-id", "")
                text_el = tweet_el.select_one(".timeline-Tweet-text")
                if not text_el:
                    continue

                text = text_el.get_text(strip=True)
                full_id = f"{username}_{tweet_id}"

                if full_id in self._seen_tweets:
                    continue
                self._seen_tweets.add(full_id)

                tweets.append({
                    "id": full_id,
                    "text": text[:500],
                    "author": username,
                    "created_at": "",
                    "source": "syndication",
                })

            return tweets

        except Exception as e:
            logger.debug(f"Syndication scrape error for @{username}: {e}")
            return []

    # ── Main Interface ───────────────────────────────────────────────

    async def fetch_user_tweets(self, username: str) -> list[dict]:
        """Fetch tweets using the best available method."""
        if self.use_api:
            return await self._api_fetch_tweets(username)

        # Try RSS first, then syndication
        tweets = await self._scrape_rss(username)
        if not tweets:
            tweets = await self._scrape_syndication(username)
        return tweets

    async def fetch_all_accounts(self) -> list[dict]:
        """Fetch recent tweets from all monitored accounts."""
        all_tweets = []
        for account in self.accounts:
            tweets = await self.fetch_user_tweets(account)
            all_tweets.extend(tweets)
            await asyncio.sleep(2)  # Be polite with rate limiting
        return all_tweets

    async def monitor_loop(self):
        """Continuously monitor Twitter every 5 minutes."""
        mode = "API" if self.use_api else "free scraping"
        logger.info(f"Twitter monitor started — {mode} mode — watching {len(self.accounts)} accounts")

        # Find a working RSS bridge if not using API
        if not self.use_api:
            self._working_bridge = await self._find_working_bridge()
            if self._working_bridge:
                logger.info(f"Using RSS bridge for Twitter monitoring")
            else:
                logger.warning("No RSS bridges available — will try syndication fallback")

        while True:
            try:
                tweets = await self.fetch_all_accounts()
                if tweets:
                    logger.info(f"Fetched {len(tweets)} tweets from {len(self.accounts)} accounts")
                    for tweet in tweets:
                        await bus.emit("twitter.tweet", tweet)

                    # Keep seen tweets cache manageable
                    if len(self._seen_tweets) > 5000:
                        self._seen_tweets = set(list(self._seen_tweets)[-2000:])
            except Exception as e:
                logger.error(f"Twitter monitor error: {e}")

            await asyncio.sleep(300)  # 5 minutes
