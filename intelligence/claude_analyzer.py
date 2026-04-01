"""
ClubMillies — AI analysis using Anthropic Claude API.
Analyzes news, tweets, and market conditions for trading insights.
"""
import asyncio
import logging
import json
from datetime import datetime
from typing import Optional

from sqlalchemy import select, desc

from core.config import settings
from core.database import AsyncSessionLocal
from core.models import AIAnalysis, NewsEvent
from core.events import bus, AI_ANALYSIS

logger = logging.getLogger("clubmillies.ai")


class ClaudeAnalyzer:
    def __init__(self, api_key: str = None):
        self.api_key = api_key or settings.anthropic_api_key
        self.enabled = bool(self.api_key)
        self._client = None

    def _get_client(self):
        if self._client is None and self.enabled:
            import anthropic
            self._client = anthropic.Anthropic(api_key=self.api_key)
        return self._client

    async def _call_claude(self, system: str, prompt: str, max_tokens: int = 500) -> dict:
        """Call Claude API and parse structured response."""
        if not self.enabled:
            return {"direction": "neutral", "confidence": 0, "reasoning": "AI analysis disabled — no API key"}

        try:
            client = self._get_client()
            response = await asyncio.to_thread(
                client.messages.create,
                model="claude-sonnet-4-20250514",
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": prompt}],
            )

            text = response.content[0].text

            # Try to parse JSON response
            try:
                # Find JSON in response
                start = text.find("{")
                end = text.rfind("}") + 1
                if start >= 0 and end > start:
                    result = json.loads(text[start:end])
                    return {
                        "direction": result.get("direction", "neutral"),
                        "confidence": int(result.get("confidence", 50)),
                        "reasoning": result.get("reasoning", text),
                        "raw": text,
                    }
            except json.JSONDecodeError:
                pass

            # Fallback: extract from text
            direction = "neutral"
            if "bullish" in text.lower():
                direction = "bullish"
            elif "bearish" in text.lower():
                direction = "bearish"

            return {
                "direction": direction,
                "confidence": 50,
                "reasoning": text[:300],
                "raw": text,
            }

        except Exception as e:
            logger.error(f"Claude API error: {e}")
            return {"direction": "neutral", "confidence": 0, "reasoning": str(e)}

    async def analyze_news(self, event: dict) -> dict:
        """Analyze a news event's impact on gold."""
        system = (
            "You are a professional gold (XAU/USD) market analyst. "
            "Respond ONLY with a JSON object: "
            '{"direction": "bullish"|"bearish"|"neutral", "confidence": 0-100, "reasoning": "brief explanation"}'
        )
        prompt = (
            f"Analyze this economic event's impact on gold (XAU/USD) price:\n\n"
            f"Event: {event.get('title', 'Unknown')}\n"
            f"Currency: {event.get('currency', 'USD')}\n"
            f"Impact: {event.get('impact', 'unknown')}\n"
            f"Forecast: {event.get('forecast', 'N/A')}\n"
            f"Previous: {event.get('previous', 'N/A')}\n"
            f"Actual: {event.get('actual', 'N/A')}\n\n"
            f"What direction will gold move? How confident are you?"
        )

        result = await self._call_claude(system, prompt)
        await self._save_analysis("news", str(event), result)
        return result

    async def analyze_tweets(
        self, tweets: list[dict], *, search_query: str = ""
    ) -> dict:
        """Analyze a batch of tweets for gold market sentiment (uses all passed tweets, capped)."""
        if not tweets:
            return {"direction": "neutral", "confidence": 0, "reasoning": "No tweets to analyze"}

        system = (
            "You are a professional gold (XAU/USD) market analyst. "
            "Analyze ALL provided posts for impact on gold vs the US dollar. "
            "Respond ONLY with a JSON object: "
            '{"direction": "bullish"|"bearish"|"neutral", "confidence": 0-100, '
            '"reasoning": "structured: (1) key themes (2) XAU/DXY/geopolitics (3) trading implication)"}'
        )

        chunks = []
        for t in tweets[:45]:
            txt = (t.get("text") or "").replace("\n", " ").strip()[:420]
            chunks.append(f"@{t.get('author', '?')}: {txt}")
        tweet_text = "\n".join(chunks)

        cal_snip = ""
        try:
            async with AsyncSessionLocal() as session:
                nr = await session.execute(
                    select(NewsEvent).order_by(desc(NewsEvent.event_time)).limit(18)
                )
                evs = nr.scalars().all()
            if evs:
                lines = [
                    f"- {e.title} ({e.currency}, {e.impact})"
                    for e in evs
                ]
                cal_snip = "\n\nRecent economic calendar (cross-check with headlines):\n" + "\n".join(
                    lines
                )
        except Exception as e:
            logger.debug(f"Calendar snippet skipped: {e}")

        prompt = (
            f"Search context: {search_query or 'manual fetch'}\n\n"
            f"Analyze these posts for gold (XAU/USD), USD/DXY, geopolitical risk, and risk sentiment.\n\n"
            f"{tweet_text}{cal_snip}"
        )

        result = await self._call_claude(system, prompt, max_tokens=1400)
        metrics = {
            "search_query": search_query,
            "tweet_count": len(tweets),
            "analyzed_posts": min(len(tweets), 45),
        }
        await self._save_analysis(
            "twitter", tweet_text[:500], result, metrics=metrics
        )
        return result

    async def analyze_market(self, price: float, rsi: float, atr: float,
                             trend: str, confluence_score: int,
                             news_events: list = None) -> dict:
        """Comprehensive market analysis combining technical + fundamental."""
        system = (
            "You are a professional gold (XAU/USD) market analyst at ClubMillies. "
            "Provide a concise market outlook combining technical and fundamental factors. "
            "Respond ONLY with a JSON object: "
            '{"direction": "bullish"|"bearish"|"neutral", "confidence": 0-100, '
            '"reasoning": "2-3 sentence analysis", "key_levels": {"support": price, "resistance": price}}'
        )

        news_str = ""
        if news_events:
            news_str = "\nRecent news:\n" + "\n".join([
                f"- {n.get('title', '')} ({n.get('impact', '')})" for n in news_events[:5]
            ])

        prompt = (
            f"Current gold market state:\n"
            f"Price: ${price:.2f}\n"
            f"RSI(14): {rsi:.1f}\n"
            f"ATR(14): {atr:.2f}\n"
            f"Trend: {trend}\n"
            f"Confluence Score: {confluence_score}/15\n"
            f"{news_str}\n\n"
            f"What is your outlook for gold in the next 1-4 hours?"
        )

        result = await self._call_claude(system, prompt)
        await self._save_analysis("market", prompt[:500], result)
        return result

    async def analyze_news_item_with_calendar(
        self,
        event: dict,
        calendar_events: list[dict],
    ) -> dict:
        """
        Deep analysis for a single calendar/news row + surrounding economic context.
        """
        system = (
            "You are a professional gold (XAU/USD) strategist. "
            "Given one economic release and nearby calendar context, assess likely direction for gold "
            "over the next sessions. Respond ONLY with JSON: "
            '{"direction":"bullish"|"bearish"|"neutral", "confidence":0-100, '
            '"verdict":"1-2 sentence where gold could head", '
            '"reasoning":"2-5 sentences: link the event, surprise vs forecast, USD real yields/DXY angle, '
            "and how nearby calendar risks could amplify or fade the move.\"}"
        )
        cal_lines = []
        for c in calendar_events[:25]:
            cal_lines.append(
                f"- {c.get('title', '')} | {c.get('currency', '')} | "
                f"{c.get('impact', '')} | t={c.get('event_time', '')}"
            )
        prompt = (
            f"PRIMARY EVENT (analyze this in depth):\n"
            f"Title: {event.get('title')}\n"
            f"Currency: {event.get('currency')}\n"
            f"Impact: {event.get('impact')}\n"
            f"Forecast: {event.get('forecast')}\n"
            f"Previous: {event.get('previous')}\n"
            f"Actual: {event.get('actual')}\n"
            f"Event time: {event.get('event_time')}\n\n"
            f"RELATED ECONOMIC CALENDAR (context — not all need equal weight):\n"
            + "\n".join(cal_lines)
        )
        result = await self._call_claude(system, prompt, max_tokens=900)
        v = result.get("verdict")
        rs = result.get("reasoning") or ""
        if v and isinstance(rs, str) and str(v) not in rs:
            result["reasoning"] = f"{v}\n\n{rs}"
        metrics = {
            "focus_event_id": event.get("id"),
            "calendar_context_count": len(calendar_events),
        }
        await self._save_analysis(
            "news_calendar",
            str(event.get("title", ""))[:500],
            result,
            metrics=metrics,
        )
        return result

    async def _save_analysis(
        self,
        source: str,
        input_summary: str,
        result: dict,
        account_id: Optional[int] = None,
        trade_id: Optional[int] = None,
        metrics: Optional[dict] = None,
    ):
        """Save analysis to database and emit event."""
        async with AsyncSessionLocal() as session:
            analysis = AIAnalysis(
                source=source,
                account_id=account_id,
                trade_id=trade_id,
                input_summary=input_summary[:500],
                direction=result.get("direction", "neutral"),
                confidence=result.get("confidence", 0),
                reasoning=result.get("reasoning", "")[:1000],
                raw_response=result.get("raw", "")[:2000],
                metrics=metrics,
            )
            session.add(analysis)
            await session.commit()

        await bus.emit(AI_ANALYSIS, {
            "source": source,
            "direction": result["direction"],
            "confidence": result["confidence"],
            "reasoning": result["reasoning"],
            "account_id": account_id,
            "trade_id": trade_id,
            "metrics": metrics,
        })

    async def analyze_after_trade_close(self, account_id: int, trigger_trade_id: int):
        """Summarize realized performance and ROI after each closed trade (refreshes every close)."""
        from sqlalchemy import select
        from core.models import Account, Trade

        metrics: dict = {}
        trigger = None
        account = None
        async with AsyncSessionLocal() as session:
            acc_r = await session.execute(select(Account).where(Account.id == account_id))
            account = acc_r.scalar_one_or_none()
            t_r = await session.execute(select(Trade).where(Trade.id == trigger_trade_id))
            trigger = t_r.scalar_one_or_none()
            closed_r = await session.execute(
                select(Trade).where(
                    Trade.account_id == account_id,
                    Trade.status == "CLOSED",
                )
            )
            closed = list(closed_r.scalars().all())

        if not account or not trigger:
            return

        total_realized = sum(float(t.pnl or 0) for t in closed)
        wins = [t for t in closed if (t.pnl or 0) > 0]
        losses = [t for t in closed if (t.pnl or 0) <= 0]
        base = float(account.starting_balance or account.balance or 1)
        roi_pct = round((total_realized / base) * 100, 2) if base else 0.0

        metrics = {
            "total_realized_pnl": round(total_realized, 2),
            "closed_trade_count": len(closed),
            "win_count": len(wins),
            "loss_count": len(losses),
            "win_rate_pct": round(len(wins) / len(closed) * 100, 1) if closed else 0.0,
            "roi_vs_starting_balance_pct": roi_pct,
            "starting_balance": round(base, 2),
            "current_balance": round(float(account.balance or 0), 2),
            "trigger_trade_id": trigger_trade_id,
            "trigger_close_reason": trigger.close_reason,
            "trigger_pnl": float(trigger.pnl or 0),
        }

        summary = (
            f"Closed trade #{trigger_trade_id} {trigger.direction} "
            f"P/L ${trigger.pnl:.2f} ({trigger.close_reason}). "
            f"Account total realized: ${total_realized:.2f} over {len(closed)} trades, "
            f"ROI vs starting ${base:.2f}: {roi_pct}%."
        )

        if not self.enabled:
            await self._save_analysis(
                "trade_close",
                summary,
                {
                    "direction": "neutral",
                    "confidence": 0,
                    "reasoning": "AI disabled — metrics only (set ANTHROPIC_API_KEY for commentary).",
                },
                account_id=account_id,
                trade_id=trigger_trade_id,
                metrics=metrics,
            )
            return

        system = (
            "You are a trading coach for a gold (XAU) systematic trader. "
            "Respond ONLY JSON: "
            '{"direction":"bullish"|"bearish"|"neutral", "confidence":0-100, '
            '"reasoning":"2-4 sentences: comment on the latest closed trade, cumulative P/L, ROI vs starting balance, and discipline."}'
        )
        prompt = summary + f"\n\nFull metrics JSON:\n{json.dumps(metrics)}"
        result = await self._call_claude(system, prompt)
        await self._save_analysis(
            "trade_close",
            summary,
            result,
            account_id=account_id,
            trade_id=trigger_trade_id,
            metrics=metrics,
        )


_analyzer_instance: Optional[ClaudeAnalyzer] = None


def get_analyzer() -> ClaudeAnalyzer:
    global _analyzer_instance
    if _analyzer_instance is None:
        _analyzer_instance = ClaudeAnalyzer()
    return _analyzer_instance
