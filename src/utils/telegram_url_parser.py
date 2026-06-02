"""Telegram message URL parser. Vendored from tg.utils (no Telethon dependency).

Parses t.me/... links into (chat_identifier, message_id) tuples.
"""

from __future__ import annotations

import re


def parse_telegram_message_url(url: str) -> tuple[str, int]:
    """Parse a Telegram message URL into (chat_id_or_username, message_id).

    Supports formats:
      https://t.me/username/123          -> ("@username", 123)
      https://t.me/c/123456789/123       -> ("-100123456789", 123)
      https://t.me/username/100/123      -> ("@username", 123)   (topic/thread)
      https://t.me/c/123456789/100/123   -> ("-100123456789", 123)

    Raises ValueError if the URL cannot be parsed.
    """
    if not url:
        raise ValueError("Empty URL")

    # Strip protocol / www
    cleaned = url.strip()
    for prefix in ("https://", "http://", "www.", "t.me/"):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix) :]

    # Remove query params
    cleaned = cleaned.split("?")[0].rstrip("/")

    # t.me/c/CHANNEL_ID[/TOPIC_ID/]MESSAGE_ID
    m = re.match(r"c/(\d+)(?:/\d+)?/(\d+)$", cleaned)
    if m:
        channel_id = int(m.group(1))
        msg_id = int(m.group(2))
        return (f"-100{channel_id}", msg_id)

    # t.me/USERNAME[/TOPIC_ID/]MESSAGE_ID
    m = re.match(r"([a-zA-Z][a-zA-Z0-9_]+)(?:/\d+)?/(\d+)$", cleaned)
    if m:
        username = m.group(1)
        msg_id = int(m.group(2))
        return (f"@{username}", msg_id)

    raise ValueError(f"Cannot parse Telegram URL: {url}")
