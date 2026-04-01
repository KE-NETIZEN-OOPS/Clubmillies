"""
SociaVault API — Twitter/X search (server-side scrape; uses X-API-Key only).

Docs: https://docs.sociavault.com/api-reference/twitter/search
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

import httpx

logger = logging.getLogger("clubmillies.sociavault")

DEFAULT_BASE = "https://api.sociavault.com"


def _walk_collect_tweet_nodes(obj: Any, acc: list[dict]) -> None:
    """Find TweetWithVisibilityResults-shaped nodes (rest_id + legacy.full_text)."""
    if isinstance(obj, dict):
        leg = obj.get("legacy")
        tid = obj.get("rest_id")
        if isinstance(leg, dict) and tid:
            text = leg.get("full_text")
            if text and isinstance(text, str) and text.strip():
                acc.append(obj)
        for v in obj.values():
            _walk_collect_tweet_nodes(v, acc)
    elif isinstance(obj, list):
        for x in obj:
            _walk_collect_tweet_nodes(x, acc)


def _parse_created_at(s: str | None) -> Optional[str]:
    if not s:
        return None
    try:
        # e.g. "Wed Oct 10 20:19:24 +0000 2018"
        dt = datetime.strptime(s, "%a %b %d %H:%M:%S %z %Y")
        return dt.isoformat()
    except Exception:
        return None


def normalize_search_response(data: dict) -> list[dict]:
    """Turn SociaVault twitter/search JSON into ClubMillies tweet dicts."""
    root = data.get("data") or data
    if isinstance(root, dict) and root.get("error"):
        logger.warning(f"SociaVault response error: {root.get('error')}")
        return []

    nodes: list[dict] = []
    _walk_collect_tweet_nodes(data, nodes)
    seen: set[str] = set()
    out: list[dict] = []

    for node in nodes:
        tid = str(node.get("rest_id", "")).strip()
        leg = node.get("legacy") or {}
        text = (leg.get("full_text") or "").strip()
        if not tid or not text or tid in seen:
            continue
        seen.add(tid)
        author = (leg.get("screen_name") or "unknown").strip()
        created = _parse_created_at(leg.get("created_at"))

        out.append({
            "id": tid,
            "text": text[:2000],
            "author": author,
            "created_at": created or "",
            "source": "sociavault",
            "url": f"https://x.com/{author}/status/{tid}",
        })
    return out


async def fetch_twitter_search(
    api_key: str,
    query: str,
    *,
    search_type: str = "Latest",
    base_url: str = DEFAULT_BASE,
) -> list[dict]:
    """
    GET /v1/scrape/twitter/search — 1 credit per request.
    Use type=Latest for chronological posts.
    """
    if not api_key or not query.strip():
        return []
    url = f"{base_url.rstrip('/')}/v1/scrape/twitter/search"
    headers = {"X-API-Key": api_key}
    params = {"query": query.strip(), "type": search_type}
    try:
        async with httpx.AsyncClient(timeout=45) as client:
            resp = await client.get(url, headers=headers, params=params)
        if resp.status_code == 401:
            logger.error("SociaVault: invalid API key (401)")
            return []
        if resp.status_code == 402:
            logger.warning("SociaVault: insufficient credits (402)")
            return []
        if resp.status_code != 200:
            logger.warning(f"SociaVault search HTTP {resp.status_code}: {resp.text[:200]}")
            return []
        data = resp.json()
        if data.get("success") is False:
            logger.warning(f"SociaVault: success=false {str(data)[:300]}")
            return []
        inner = data.get("data", data)
        if isinstance(inner, dict) and inner.get("error"):
            logger.warning(f"SociaVault data error: {inner.get('error')}")
            return []
        tweets = normalize_search_response(data)
        logger.info(f"SociaVault: {len(tweets)} tweets for query={query[:40]!r}")
        return tweets
    except Exception as e:
        logger.error(f"SociaVault search failed: {e}")
        return []


async def fetch_all_queries(
    api_key: str,
    queries: list[str],
    *,
    base_url: str = DEFAULT_BASE,
) -> list[dict]:
    merged: list[dict] = []
    seen: set[str] = set()
    for q in queries[:6]:
        batch = await fetch_twitter_search(api_key, q, base_url=base_url)
        for t in batch:
            tid = str(t.get("id", ""))
            if tid and tid not in seen:
                seen.add(tid)
                merged.append(t)
    return merged
