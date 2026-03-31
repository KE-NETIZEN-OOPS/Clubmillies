"""
ClubMillies — Forexfactory economic calendar scraper.
Fetches high-impact news events that affect gold (XAU/USD).
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select

from core.database import AsyncSessionLocal
from core.models import NewsEvent
from core.events import bus, NEWS_EVENT

logger = logging.getLogger("clubmillies.news")

FOREX_FACTORY_URL = "https://www.forexfactory.com/calendar"
GOLD_CURRENCIES = ["USD", "EUR", "CNY"]  # Currencies that impact gold


async def fetch_forexfactory_calendar() -> list[dict]:
    """Scrape Forexfactory calendar for today's events."""
    events = []
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(FOREX_FACTORY_URL, headers=headers)
            if resp.status_code != 200:
                logger.warning(f"Forexfactory returned {resp.status_code}")
                return events

        soup = BeautifulSoup(resp.text, "html.parser")
        rows = soup.select("tr.calendar__row")

        current_date = datetime.utcnow().date()
        for row in rows:
            try:
                currency_el = row.select_one("td.calendar__currency")
                if not currency_el:
                    continue
                currency = currency_el.get_text(strip=True)
                if currency not in GOLD_CURRENCIES:
                    continue

                impact_el = row.select_one("td.calendar__impact span")
                impact = "low"
                if impact_el:
                    classes = impact_el.get("class", [])
                    if any("high" in c for c in classes):
                        impact = "high"
                    elif any("medium" in c for c in classes):
                        impact = "medium"

                title_el = row.select_one("td.calendar__event span")
                title = title_el.get_text(strip=True) if title_el else "Unknown"

                time_el = row.select_one("td.calendar__time")
                time_str = time_el.get_text(strip=True) if time_el else ""

                forecast_el = row.select_one("td.calendar__forecast span")
                forecast = forecast_el.get_text(strip=True) if forecast_el else ""

                previous_el = row.select_one("td.calendar__previous span")
                previous = previous_el.get_text(strip=True) if previous_el else ""

                actual_el = row.select_one("td.calendar__actual span")
                actual = actual_el.get_text(strip=True) if actual_el else ""

                # Parse time
                event_time = datetime.utcnow()
                if time_str and ":" in time_str:
                    try:
                        t = datetime.strptime(time_str.replace("am", " AM").replace("pm", " PM"), "%I:%M %p")
                        event_time = datetime.combine(current_date, t.time())
                    except ValueError:
                        pass

                events.append({
                    "title": title,
                    "currency": currency,
                    "impact": impact,
                    "forecast": forecast,
                    "previous": previous,
                    "actual": actual,
                    "event_time": event_time,
                })
            except Exception as e:
                continue

    except Exception as e:
        logger.error(f"Forexfactory scrape error: {e}")

    return events


async def save_news_events(events: list[dict]):
    """Save events to database and emit high-impact alerts."""
    async with AsyncSessionLocal() as session:
        for ev in events:
            # Check if already exists
            existing = await session.execute(
                select(NewsEvent).where(
                    NewsEvent.title == ev["title"],
                    NewsEvent.event_time == ev["event_time"],
                )
            )
            if existing.scalar_one_or_none():
                continue

            news = NewsEvent(
                title=ev["title"],
                currency=ev["currency"],
                impact=ev["impact"],
                forecast=ev["forecast"],
                previous=ev["previous"],
                actual=ev["actual"],
                event_time=ev["event_time"],
            )
            session.add(news)

            # Emit event for high-impact news
            if ev["impact"] == "high":
                await bus.emit(NEWS_EVENT, ev)

        await session.commit()


def is_news_window(events: list[dict], minutes_before: int = 30) -> bool:
    """Check if any high-impact news is within the danger window."""
    now = datetime.utcnow()
    for ev in events:
        if ev["impact"] != "high":
            continue
        time_diff = (ev["event_time"] - now).total_seconds() / 60
        if -5 <= time_diff <= minutes_before:
            return True
    return False


async def news_monitor_loop():
    """Continuously monitor news every 15 minutes."""
    logger.info("News monitor started")
    while True:
        try:
            events = await fetch_forexfactory_calendar()
            if events:
                await save_news_events(events)
                logger.info(f"Fetched {len(events)} news events")
        except Exception as e:
            logger.error(f"News monitor error: {e}")

        await asyncio.sleep(900)  # 15 minutes
