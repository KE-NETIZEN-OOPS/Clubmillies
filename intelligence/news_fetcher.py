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
                # Forexfactory often blocks server-like traffic. Try a read-proxy fallback.
                logger.warning(f"Forexfactory returned {resp.status_code} — trying fallback fetch")
                fallback_url = f"https://r.jina.ai/http://{FOREX_FACTORY_URL}"
                resp = await client.get(fallback_url, headers=headers)
                if resp.status_code != 200:
                    logger.warning(f"Forexfactory fallback returned {resp.status_code}")
                    return events

        # The fallback fetch returns a markdown rendering, not HTML.
        if "Markdown Content:" in resp.text:
            return _parse_forexfactory_markdown(resp.text)

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


def _parse_forexfactory_markdown(text: str) -> list[dict]:
    """Parse the Jina markdown proxy output into event dicts."""
    events: list[dict] = []
    current_date: datetime.date | None = None
    now_date = datetime.utcnow().date()

    # Extract only the table section
    lines = [ln.strip() for ln in text.splitlines() if ln.strip().startswith("|")]
    if not lines:
        return events

    # Skip header rows (first two lines are table header + separator)
    for ln in lines[2:]:
        # Split markdown row into cells
        parts = [p.strip() for p in ln.strip("|").split("|")]
        if len(parts) < 10:
            continue

        # Heuristic: Date column sometimes contains "Mon Mar 30"
        date_cell = parts[0]
        time_cell = parts[1] if len(parts) > 1 else ""
        currency = parts[2] if len(parts) > 2 else ""
        impact_cell = parts[3] if len(parts) > 3 else ""
        title = parts[4] if len(parts) > 4 else "Unknown"
        actual = parts[7] if len(parts) > 7 else ""
        forecast = parts[8] if len(parts) > 8 else ""
        previous = parts[9] if len(parts) > 9 else ""

        # Update current_date if present
        # Examples: "Mon Mar 30", "Sun Mar 29"
        if date_cell and any(m in date_cell for m in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")) and "All Day" not in date_cell:
            try:
                # date_cell may include markdown link, keep plain tokens
                tokens = date_cell.replace("[", "").replace("]", "").split()
                if len(tokens) >= 3:
                    # Assume current year if not provided
                    dt = datetime.strptime(f"{tokens[1]} {tokens[2]} {datetime.utcnow().year}", "%b %d %Y")
                    current_date = dt.date()
            except Exception:
                current_date = current_date or now_date
        if current_date is None:
            current_date = now_date

        if not currency or currency not in GOLD_CURRENCIES:
            continue

        impact = "low"
        impact_lower = impact_cell.lower()
        if "impact-red" in impact_lower or "ff-impact-red" in impact_lower:
            impact = "high"
        elif "impact-ora" in impact_lower or "ff-impact-ora" in impact_lower:
            impact = "medium"
        elif "impact-yel" in impact_lower or "ff-impact-yel" in impact_lower:
            impact = "low"

        # Parse time (may be "All Day" or "7:50pm")
        event_time = datetime.combine(current_date, datetime.utcnow().time())
        if time_cell and ":" in time_cell:
            try:
                t = datetime.strptime(time_cell.replace("am", " AM").replace("pm", " PM"), "%I:%M %p")
                event_time = datetime.combine(current_date, t.time())
            except Exception:
                pass
        elif time_cell.lower() == "all day":
            event_time = datetime.combine(current_date, datetime.min.time())

        events.append({
            "title": title,
            "currency": currency,
            "impact": impact,
            "forecast": forecast,
            "previous": previous,
            "actual": actual,
            "event_time": event_time,
        })

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
