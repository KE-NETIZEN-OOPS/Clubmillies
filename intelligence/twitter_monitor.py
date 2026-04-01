"""
ClubMillies — Twitter/X monitor for gold market intelligence.
Supports two modes:
  1. Official API (if bearer token provided) — most reliable
  2. Free scraping via RSS bridges and syndication — no API key needed
Plus: Google News RSS headlines (no Twitter login; configurable queries).
"""
import asyncio
import hashlib
import logging
import re
import time
import urllib.parse
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import httpx
from bs4 import BeautifulSoup

from core.config import settings
from intelligence.tweet_persist import persist_tweet_dicts
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
        self._api_blocked = False
        self._working_bridge: str | None = None
        self._seen_tweets: set[str] = set()
        self._rss_cache: dict[str, tuple[float, list]] = {}

    # ── Official API Mode ────────────────────────────────────────────

    async def _api_get_user_id(self, username: str) -> str | None:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{TWITTER_API_BASE}/users/by/username/{username}",
                headers={"Authorization": f"Bearer {self.bearer_token}"},
            )
            if resp.status_code == 402:
                self._api_blocked = True
                logger.warning("Twitter API returned 402 (plan restriction) — falling back to scraping mode")
                return None
            if resp.status_code == 200:
                return resp.json()["data"]["id"]
        return None

    async def _api_fetch_tweets(self, username: str) -> list[dict]:
        try:
            if self._api_blocked:
                return []
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
                if resp.status_code == 402:
                    self._api_blocked = True
                    logger.warning("Twitter API returned 402 (plan restriction) — falling back to scraping mode")
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
        if self.use_api and not self._api_blocked:
            tweets = await self._api_fetch_tweets(username)
            if tweets:
                return tweets

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

    async def _fetch_google_news_rss(self) -> list[dict]:
        """Headlines from Google News RSS (keyword intel — not X login)."""
        raw = (settings.google_news_queries or "").strip()
        if not raw:
            return []
        queries = [q.strip() for q in raw.split(",") if q.strip()][:5]
        out: list[dict] = []
        headers = {"User-Agent": "Mozilla/5.0 ClubMillies/1.0"}
        async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers=headers) as client:
            for q in queries:
                cache_key = f"gn:{q}"
                now = time.time()
                if cache_key in self._rss_cache and now - self._rss_cache[cache_key][0] < 300:
                    out.extend(self._rss_cache[cache_key][1])
                    continue
                url = (
                    "https://news.google.com/rss/search?"
                    + urllib.parse.urlencode({"q": q, "hl": "en-US", "gl": "US", "ceid": "US:en"})
                )
                try:
                    resp = await client.get(url)
                    if resp.status_code != 200:
                        continue
                    soup = BeautifulSoup(resp.text, "xml")
                    batch = []
                    for item in soup.find_all("item")[:15]:
                        title_el = item.find("title")
                        link_el = item.find("link")
                        pub = item.find("pubDate")
                        title = title_el.get_text(strip=True) if title_el else ""
                        link = link_el.get_text(strip=True) if link_el else ""
                        if not title:
                            continue
                        created_at = None
                        if pub:
                            try:
                                created_at = parsedate_to_datetime(pub.get_text())
                                if created_at.tzinfo:
                                    created_at = created_at.astimezone(timezone.utc).replace(tzinfo=None)
                            except Exception:
                                created_at = datetime.utcnow()
                        else:
                            created_at = datetime.utcnow()
                        tid = "gn_" + hashlib.sha256((link + title).encode()).hexdigest()[:20]
                        batch.append({
                            "id": tid,
                            "text": f"[News] {title}",
                            "author": "News",
                            "created_at": created_at.isoformat() + "Z",
                            "source": "google_news",
                            "url": link or None,
                        })
                    self._rss_cache[cache_key] = (now, batch)
                    out.extend(batch)
                except Exception as e:
                    logger.debug(f"Google News RSS error for {q!r}: {e}")
        return out

    async def _fetch_twitter_recent_search(self) -> list[dict]:
        """Twitter API v2 recent search (needs Elevated access for most projects)."""
        if not self.bearer_token or self._api_blocked:
            return []
        raw = (settings.twitter_search_queries or "").strip()
        if not raw:
            return []
        queries = [q.strip() for q in raw.split(",") if q.strip()][:4]
        out: list[dict] = []
        headers = {"Authorization": f"Bearer {self.bearer_token}"}
        async with httpx.AsyncClient(timeout=25, headers=headers) as client:
            for q in queries:
                try:
                    resp = await client.get(
                        "https://api.twitter.com/2/tweets/search/recent",
                        params={
                            "query": q,
                            "max_results": 10,
                            "tweet.fields": "created_at,author_id,text",
                        },
                    )
                    if resp.status_code == 402:
                        self._api_blocked = True
                        logger.warning("Twitter API search blocked (plan) — use account RSS only")
                        return out
                    if resp.status_code != 200:
                        logger.warning(f"Twitter search HTTP {resp.status_code} for query snippet")
                        continue
                    data = resp.json()
                    for t in data.get("data", []) or []:
                        ts = t.get("created_at", "")
                        out.append({
                            "id": t.get("id", ""),
                            "text": t.get("text", ""),
                            "author": "search",
                            "created_at": ts,
                            "source": "twitter_search",
                            "url": f"https://x.com/i/web/status/{t.get('id','')}",
                        })
                except Exception as e:
                    logger.debug(f"Twitter search error: {e}")
        return out

    @staticmethod
    def _tweet_age_seconds(tweet: dict) -> float:
        ca = tweet.get("created_at") or ""
        if not ca:
            return 0.0
        try:
            dt = datetime.fromisoformat(ca.replace("Z", "+00:00"))
            if dt.tzinfo:
                dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
            return (datetime.utcnow() - dt).total_seconds()
        except Exception:
            return 0.0

    def _filter_fresh_for_ai(self, tweets: list[dict], max_age_sec: int = 600) -> list[dict]:
        """Prefer items under max_age_sec for Claude batching."""
        fresh = [t for t in tweets if self._tweet_age_seconds(t) <= max_age_sec]
        return fresh if fresh else tweets[:25]

    def _dedupe(self, tweets: list[dict]) -> list[dict]:
        seen: set[str] = set()
        out: list[dict] = []
        for t in tweets:
            tid = str(t.get("id", ""))
            if not tid or tid in seen:
                continue
            seen.add(tid)
            out.append(t)
        return out

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
                tw = await self.fetch_all_accounts()
                tw.extend(await self._fetch_google_news_rss())
                tw.extend(await self._fetch_twitter_recent_search())
                tw = self._dedupe(tw)
                if tw:
                    logger.info(
                        f"Intel batch: {len(tw)} items (accounts + News + X API; SociaVault is manual)"
                    )
                    await self._save_tweets(tw)
                    for tweet in tw:
                        await bus.emit("twitter.tweet", tweet)
                    fresh = self._filter_fresh_for_ai(tw, max_age_sec=600)
                    await bus.emit("twitter.tweets", {"tweets": fresh})

                    if len(self._seen_tweets) > 5000:
                        self._seen_tweets = set(list(self._seen_tweets)[-2000:])
            except Exception as e:
                logger.error(f"Twitter monitor error: {e}")

            await asyncio.sleep(300)  # 5 minutes

    async def _save_tweets(self, tweets: list[dict]):
        await persist_tweet_dicts(tweets)
