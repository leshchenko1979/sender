"""Message sending logic.

Replaced Telethon/tg with fast-mcp-telegram bridge for all Telegram operations.
Supports per-client bearer tokens.
"""

from __future__ import annotations

import re
from typing import Any

import telegram_bridge as bridge

from ..core.clients import Client
from ..core.settings import Setting
from ..scheduling.cron_utils import humanize_seconds
from ..utils.telegram_url_parser import parse_telegram_message_url
from ..utils.telegram_utils import parse_chat_and_topic
from .error_handlers import handle_slow_mode_error

# Known RPC error codes that map to user-facing messages
KNOWN_ERROR_MESSAGES: dict[str, str] = {
    "CHAT_WRITE_FORBIDDEN": "Нет прав для отправки сообщения",
    "CHAT_SEND_MEDIA_FORBIDDEN": "Нет прав для отправки изображений",
    "CHAT_SEND_PHOTOS_FORBIDDEN": "Нет прав для отправки изображений в этот чат",
    "CHAT_ADMIN_REQUIRED": "Это канал, а не группа",
    "INVITE_REQUEST_SENT": "До сих пор не принят запрос на вступление",
    "USERNAME_NOT_OCCUPIED": "Указанный чат не существует",
    "USERNAME_INVALID": "Указанный чат не существует",
}

_RPC_CODE_RE = re.compile(r"\b([A-Z][A-Z_]+[A-Z])\b")


def _extract_rpc_code(error_detail: str) -> str | None:
    m = _RPC_CODE_RE.search(error_detail)
    return m.group(1) if m else None


def _handle_bridge_error(exc: bridge.MtProtoError) -> str:
    detail = exc.detail
    code = _extract_rpc_code(detail)

    if code and "PAYMENT_REQUIRED" in code:
        m = re.search(r"ALLOW_PAYMENT_REQUIRED_(\d+)", detail)
        stars = m.group(1) if m else None
        if stars == "1":
            need_text = "нужна 1 звезда"
        elif stars:
            need_text = f"нужно {stars} звёзд"
        else:
            need_text = "нужны звёзды"
        return (
            f"Error: Требуется оплата: чтобы опубликовать в этом чате, {need_text}. "
            "Купите звезды и повторите попытку."
        )

    if code and ("FLOOD" in code or "SLOWMODE" in code or "SLOW_MODE" in code):
        seconds = None
        m = re.search(r"(\d+)\s*SEC", detail, re.IGNORECASE)
        if m:
            seconds = int(m.group(1))
        elif code:
            m2 = re.search(r"_WAIT_(\d+)", code)
            if m2:
                seconds = int(m2.group(1))
        if seconds:
            wait = humanize_seconds(seconds)
            return (
                f"Error: Слишком рано отправляется (подождать {wait}). "
                "Поставьте больше паузу после предыдущих отправок в расписании."
            )

    if code and code in KNOWN_ERROR_MESSAGES:
        return f"Error: {KNOWN_ERROR_MESSAGES[code]}"

    return f"Error sending message: {detail}"


def _bearer(client: Client | None) -> str | None:
    """Extract bearer token from client config."""
    return client.fast_mcp_bearer if client else None


def send_setting(
    setting: Setting, client: Client | None = None
) -> tuple[str, dict[str, Any] | None]:
    """Send or forward a message for the given setting.

    Uses the fast-mcp-telegram bridge instead of Telethon.
    Passes per-client bearer token when available.

    Args:
        setting: The setting to process.
        client: Optional client for bearer token and slow-mode handling.

    Returns:
        Tuple of (result_message, optional_message_info_dict).
    """
    token = _bearer(client)
    chat_id, topic_id = parse_chat_and_topic(setting.chat_id)

    clean_url = setting.text.split("?")[0] if "?" in setting.text else setting.text
    try:
        from_chat_id, message_id = parse_telegram_message_url(clean_url)
        forward_needed = True
    except Exception:
        forward_needed = False

    bridge._call("channels.JoinChannel", {"channel": chat_id}, bearer_token=token)

    try:
        if forward_needed:
            result_data = bridge.forward_messages(
                from_peer=from_chat_id,
                to_peer=chat_id,
                message_ids=[message_id],
                top_msg_id=topic_id,
                drop_author=True,
                bearer_token=token,
            )
            result_text = "Message forwarded successfully"
            message_ids = _extract_forwarded_ids(result_data)
            if message_ids:
                return result_text, {
                    "chat_id": chat_id,
                    "topic_id": topic_id,
                    "message_ids": message_ids,
                }
            return result_text, {"chat_id": chat_id, "topic_id": topic_id}
        else:
            result_data = bridge.send_message(
                peer=chat_id,
                text=setting.text,
                reply_to=topic_id,
                bearer_token=token,
            )
            result_text = "Message sent successfully"
            msg_id = _extract_message_id(result_data)
            if msg_id:
                return result_text, {
                    "chat_id": chat_id,
                    "topic_id": topic_id,
                    "message_ids": [msg_id],
                }
            return result_text, {"chat_id": chat_id, "topic_id": topic_id}

    except bridge.MtProtoError as exc:
        detail = exc.detail
        code = _extract_rpc_code(detail)
        if code and ("SLOWMODE" in code or "FLOOD_WAIT" in code or "SLOW_MODE" in code):
            seconds = None
            m = re.search(r"(\d+)", detail)
            if m:
                seconds = int(m.group(1))
            if seconds is not None and client is not None:
                result = handle_slow_mode_error(client, setting, seconds)
                return result, None
        return _handle_bridge_error(exc), None

    except ValueError as exc:
        msg = str(exc)
        if "Не удалось получить исходное сообщение" in msg:
            return "Error: Не удалось получить исходное сообщение", None
        if "Медиагруппа неполная или недоступна" in msg:
            return "Error: Медиагруппа неполная или недоступна", None
        return f"Error: {msg}", None


def _extract_forwarded_ids(result: dict) -> list[int]:
    ids: list[int] = []
    updates = result.get("updates", [])
    for upd in updates:
        msg = upd.get("message", {})
        mid = msg.get("id")
        if mid is not None:
            ids.append(mid)
    return ids


def _extract_message_id(result: dict) -> int | None:
    updates = result.get("updates", [])
    for upd in updates:
        msg = upd.get("message", {})
        mid = msg.get("id")
        if mid is not None:
            return mid
    return result.get("id")
