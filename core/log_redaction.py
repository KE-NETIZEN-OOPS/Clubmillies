"""
Redact Telegram Bot API tokens from log output (e.g. httpx INFO lines with full request URLs).
"""
from __future__ import annotations

import logging
import re

# Path form: .../bot<digits>:<secret>/method
_BOT_IN_URL = re.compile(r"(/bot)([0-9]{6,}:[A-Za-z0-9_-]{20,})(/)")
# Same token appearing outside URLs (e.g. copied into messages)
_BOT_TOKEN_STANDALONE = re.compile(r"\b([0-9]{6,}:[A-Za-z0-9_-]{25,})\b")


def redact_telegram_secrets(text: str) -> str:
    if not text or not isinstance(text, str):
        return text
    s = _BOT_IN_URL.sub(r"\1***REDACTED***\3", text)
    s = _BOT_TOKEN_STANDALONE.sub("***REDACTED***", s)
    return s


class RedactTelegramSecretsFilter(logging.Filter):
    """Apply to handlers or loggers that may emit Telegram API URLs."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact_telegram_secrets(record.msg)
        if record.args:
            record.args = tuple(
                redact_telegram_secrets(a) if isinstance(a, str) else a for a in record.args
            )
        return True


_installed = False


def install_telegram_log_redaction() -> None:
    """Attach redaction to root handlers and noisy HTTP/Telegram loggers. Safe to call once at startup."""
    global _installed
    if _installed:
        return
    _installed = True
    f = RedactTelegramSecretsFilter()
    root = logging.getLogger()
    for h in root.handlers:
        h.addFilter(f)
    for name in ("httpx", "httpcore", "telegram", "telegram.ext"):
        logging.getLogger(name).addFilter(f)
