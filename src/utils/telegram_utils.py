"""Telegram utility functions — chat parsing, link generation, message checks.

Previously used Telethon get_entity / get_messages.
Now uses the fast-mcp-telegram bridge for all API calls.
Supports per-client bearer tokens.
"""

from __future__ import annotations

import logging
import re

import telegram_bridge as bridge

logger = logging.getLogger(__name__)


def parse_chat_and_topic(chat_id: str) -> tuple[str, int | None]:
    """Parse chat_id which may contain topic in format: chat_id/topic_id."""
    if "/" in chat_id:
        parts = chat_id.rsplit("/", 1)
        try:
            topic_id = int(parts[1])
            chat_part = parts[0]
            if chat_part.isdigit() and not chat_part.startswith("-100"):
                chat_part = f"-100{chat_part}"
            return chat_part, topic_id
        except ValueError:
            return chat_id, None
    return chat_id, None


def _normalize_channel_id(channel_id: str) -> str:
    return channel_id[4:] if channel_id.startswith("-100") else channel_id


def _build_query_string(
    thread_id: int | None = None,
    comment_id: int | None = None,
) -> str:
    query_params = []
    if thread_id:
        query_params.append(f"thread={thread_id}")
    qs = "&".join(query_params)
    return f"?{qs}" if qs else ""


def _generate_message_link(
    chat_id: str,
    message_id: int,
    topic_id: int | None = None,
    account_app=None,
    bearer_token: str | None = None,
) -> str | None:
    """Generate a Telegram message link.

    Args:
        bearer_token: Per-client bridge token (optional).
    """
    try:
        entity = _resolve_peer(chat_id, bearer_token=bearer_token)
    except Exception:
        entity = None

    if entity and entity.get("username"):
        username = entity["username"].lstrip("@")
        if topic_id:
            return f"https://t.me/{username}/{topic_id}/{message_id}"
        return f"https://t.me/{username}/{message_id}"

    clean = _normalize_channel_id(chat_id.lstrip("@"))
    if "/" in clean:
        clean = clean.split("/")[0]
    if topic_id:
        return f"https://t.me/c/{clean}/{topic_id}/{message_id}"
    return f"https://t.me/c/{clean}/{message_id}"


def _resolve_peer(peer: str, bearer_token: str | None = None) -> dict | None:
    """Resolve a peer (@username or numeric ID) via the bridge."""
    s = peer.lstrip("@")
    if s.lstrip("-").isdigit():
        try:
            chat_id = int(s[4:]) if s.startswith("-100") and len(s) > 4 else int(s)
            return bridge._call(
                "messages.GetChats", {"id": [chat_id]}, bearer_token=bearer_token
            )
        except bridge.MtProtoError:
            return None
    try:
        return bridge._call(
            "contacts.ResolveUsername", {"username": s}, bearer_token=bearer_token
        )
    except bridge.MtProtoError:
        return None


def _parse_message_link(link: str) -> tuple[str | None, int | None, int | None]:
    """Parse a Telegram message link.

    Returns (chat_identifier, message_id, topic_id).
    """
    if not link or not isinstance(link, str):
        return None, None, None

    link = link.replace("https://", "").replace("http://", "").replace("www.", "")

    patterns = [
        r"t\.me/c/(\d+)/(\d+)/(\d+)",
        r"t\.me/c/(\d+)/(\d+)",
        r"t\.me/([a-zA-Z0-9_]+)/(\d+)/(\d+)",
        r"t\.me/([a-zA-Z0-9_]+)/(\d+)",
    ]

    for pattern in patterns:
        if m := re.match(pattern, link):
            groups = m.groups()
            if len(groups) == 3:
                if "c/" in link:
                    cid, tid, mid = groups
                    return f"-100{cid}", int(mid), int(tid)
                else:
                    uname, tid, mid = groups
                    return f"@{uname}", int(mid), int(tid)
            elif len(groups) == 2:
                if "c/" in link:
                    cid, mid = groups
                    return f"-100{cid}", int(mid), None
                else:
                    uname, mid = groups
                    return f"@{uname}", int(mid), None

    return None, None, None


def _check_message_exists(
    link: str, account_app=None, bearer_token: str | None = None
) -> bool:
    """Check if a Telegram message still exists.

    Args:
        bearer_token: Per-client bridge token (optional).
    """
    if not link:
        return False

    chat_id, message_id, topic_id = _parse_message_link(link)
    if not chat_id or not message_id:
        logger.warning(f"Could not parse message link: {link}")
        return False

    try:
        result = bridge.get_messages(chat_id, [message_id], bearer_token=bearer_token)
        msgs = result.get("messages", [])
        return bool(msgs and msgs[0] is not None)
    except bridge.MtProtoError as e:
        logger.warning(f"Error checking message existence for link {link}: {e}")
        return False
