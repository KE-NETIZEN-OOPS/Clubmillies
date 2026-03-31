"""
ClubMillies — Event bus for decoupled communication.
Trading engine emits events → Telegram, WebSocket, DB logger subscribe.
"""
import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Coroutine

logger = logging.getLogger("clubmillies.events")


@dataclass
class Event:
    type: str
    data: dict
    timestamp: datetime = field(default_factory=datetime.utcnow)


class EventBus:
    def __init__(self):
        self._subscribers: dict[str, list[Callable]] = {}
        self._global_subscribers: list[Callable] = []

    def subscribe(self, event_type: str, callback: Callable[[Event], Coroutine]):
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(callback)

    def subscribe_all(self, callback: Callable[[Event], Coroutine]):
        self._global_subscribers.append(callback)

    async def emit(self, event_type: str, data: dict = None):
        event = Event(type=event_type, data=data or {})
        handlers = self._subscribers.get(event_type, []) + self._global_subscribers

        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as e:
                logger.error(f"Event handler error for {event_type}: {e}")


# Event type constants
TRADE_OPENED = "trade.opened"
TRADE_CLOSED = "trade.closed"
SIGNAL_GENERATED = "signal.generated"
NEWS_EVENT = "news.event"
AI_ANALYSIS = "ai.analysis"
ACCOUNT_UPDATE = "account.update"
BOT_STATUS = "bot.status"

# Global event bus instance
bus = EventBus()
