"""
ClubMillies — AI analysis using Anthropic Claude API.
Analyzes news, tweets, and market conditions for trading insights.
"""
import asyncio
import logging
import json
from datetime import datetime

from core.config import settings
from core.database import AsyncSessionLocal
from core.models import AIAnalysis
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

    async def _call_claude(self, system: str, prompt: str) -> dict:
        """Call Claude API and parse structured response."""
        if not self.enabled:
            return {"direction": "neutral", "confidence": 0, "reasoning": "AI analysis disabled — no API key"}

        try:
            client = self._get_client()
            response = await asyncio.to_thread(
                client.messages.create,
                model="claude-sonnet-4-20250514",
                max_tokens=500,
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

    async def analyze_tweets(self, tweets: list[dict]) -> dict:
        """Analyze a batch of tweets for gold market sentiment."""
        if not tweets:
            return {"direction": "neutral", "confidence": 0, "reasoning": "No tweets to analyze"}

        system = (
            "You are a professional gold (XAU/USD) market analyst. "
            "Analyze tweets from financial accounts for gold market impact. "
            "Respond ONLY with a JSON object: "
            '{"direction": "bullish"|"bearish"|"neutral", "confidence": 0-100, "reasoning": "brief analysis"}'
        )

        tweet_text = "\n".join([
            f"@{t['author']}: {t['text']}" for t in tweets[:10]
        ])

        prompt = (
            f"Analyze these recent tweets from financial accounts. "
            f"What is the sentiment for gold (XAU/USD)?\n\n{tweet_text}"
        )

        result = await self._call_claude(system, prompt)
        await self._save_analysis("twitter", tweet_text[:500], result)
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

    async def _save_analysis(self, source: str, input_summary: str, result: dict):
        """Save analysis to database and emit event."""
        async with AsyncSessionLocal() as session:
            analysis = AIAnalysis(
                source=source,
                input_summary=input_summary[:500],
                direction=result.get("direction", "neutral"),
                confidence=result.get("confidence", 0),
                reasoning=result.get("reasoning", "")[:1000],
                raw_response=result.get("raw", "")[:2000],
            )
            session.add(analysis)
            await session.commit()

        await bus.emit(AI_ANALYSIS, {
            "source": source,
            "direction": result["direction"],
            "confidence": result["confidence"],
            "reasoning": result["reasoning"],
        })
