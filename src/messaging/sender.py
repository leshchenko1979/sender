from __future__ import annotations

import re
from typing import Any

from telethon.errors import (
    ChatAdminRequiredError,
    ChatSendMediaForbiddenError,
    ChatWriteForbiddenError,
    InviteRequestSentError,
    RPCError,
    SlowModeWaitError,
    UsernameNotOccupiedError,
)
from tg.utils import parse_telegram_message_url

from ..core.clients import Client
from ..core.settings import Setting
from ..scheduling.cron_utils import humanize_seconds
from ..utils.telegram_utils import parse_chat_and_topic
from .error_handlers import handle_slow_mode_error
from .telegram_sender import SenderAccount


async def send_setting(
    setting: Setting, accounts: Any, client: Client | None = None
) -> tuple[str, dict[str, Any] | None]:
    # Parse chat_id to extract optional topic
    chat_id, topic_id = parse_chat_and_topic(setting.chat_id)

    try:
        # Strip query parameters from URL before parsing to handle ?single and other params
        clean_url = setting.text.split("?")[0] if "?" in setting.text else setting.text
        from_chat_id, message_id = parse_telegram_message_url(clean_url)
        forward_needed = True
    except Exception:  # not a valid telegram url
        forward_needed = False

    acc: SenderAccount = accounts[setting.account]

    try:
        # Try to join the destination chat first to reduce resolution and permission issues
        await acc._join_chat(chat_id)

        if forward_needed:
            forwarded_messages = await acc._forward_grouped_or_single(
                chat_id=chat_id,
                from_chat_id=from_chat_id,
                message_id=message_id,
                reply_to_msg_id=topic_id,
            )
            result = "Message forwarded successfully"
            # Extract message IDs from forwarded messages
            message_ids: list[int] = []
            if hasattr(forwarded_messages, "updates"):
                for update in forwarded_messages.updates:
                    if hasattr(update, "message") and hasattr(update.message, "id"):
                        message_ids.append(update.message.id)
            elif hasattr(forwarded_messages, "messages"):
                for msg in forwarded_messages.messages:
                    if hasattr(msg, "id"):
                        message_ids.append(msg.id)
            # If we can't extract IDs, return basic success info
            if not message_ids:
                return result, {"chat_id": chat_id, "topic_id": topic_id}

            return result, {
                "chat_id": chat_id,
                "topic_id": topic_id,
                "message_ids": message_ids,
            }

        else:
            sent_message = await acc.app.send_message(
                chat_id=chat_id,
                text=setting.text,
                reply_to=topic_id,
            )
            result = "Message sent successfully"
            message_id = getattr(sent_message, "id", None)
            if message_id:
                return result, {
                    "chat_id": chat_id,
                    "topic_id": topic_id,
                    "message_ids": [message_id],
                }
            else:
                return result, {"chat_id": chat_id, "topic_id": topic_id}

    except ChatWriteForbiddenError:
        result = "Error: Нет прав для отправки сообщения"
        return result, None

    except ChatSendMediaForbiddenError:
        result = "Error: Нет прав для отправки изображений"
        return result, None

    except ChatAdminRequiredError:
        result = "Error: Это канал, а не группа"
        return result, None

    except InviteRequestSentError:
        result = "Error: До сих пор не принят запрос на вступление"
        return result, None

    except UsernameNotOccupiedError:
        result = "Error: Указанный чат не существует"
        return result, None

    except SlowModeWaitError as e:
        # Telethon exposes .seconds on Flood/SlowMode waits; fallback to str(e)
        seconds = getattr(e, "seconds", None)
        if seconds is not None and client is not None:
            # Auto-adjust schedule for all settings in this chat
            result = handle_slow_mode_error(client, setting, seconds)
        else:
            # Fallback to old behavior if we can't extract seconds or client not available
            wait_text = humanize_seconds(seconds) if seconds is not None else str(e)
            result = (
                f"Error: Слишком рано отправляется (подождать {wait_text}). "
                "Поставьте больше паузу после предыдущих отправок в расписании."
            )
        return result, None

    except ValueError as e:
        # Handle media group errors and other ValueError cases
        if "Не удалось получить исходное сообщение" in str(e):
            result = "Error: Не удалось получить исходное сообщение"
        elif "Медиагруппа неполная или недоступна" in str(e):
            result = "Error: Медиагруппа неполная или недоступна"
        elif "No user has" in str(e) and "as username" in str(e):
            result = "Error: Указанный чат не существует"
        else:
            result = f"Error: {e}"
        return result, None

    except RPCError as e:
        # Handle cases where Telegram requires Stars to post/forward into the target chat
        err_text = str(e)
        message_text = getattr(e, "message", "") or err_text
        m = re.search(r"ALLOW_PAYMENT_REQUIRED_(\\d+)", message_text)
        if getattr(e, "code", None) == 403 and (
            "ALLOW_PAYMENT_REQUIRED" in message_text
            or "PAYMENT_REQUIRED" in message_text
            or m is not None
        ):
            stars = m.group(1) if m else None
            if stars == "1":
                need_text = "нужна 1 звезда"
            elif stars:
                need_text = f"нужно {stars} звёзд"
            else:
                need_text = "нужны звёзды"
            result = (
                f"Error: Требуется оплата: чтобы опубликовать в этом чате, {need_text}. "
                "Купите звезды и повторите попытку."
            )
        elif (
            getattr(e, "code", None) == 403
            and "CHAT_SEND_PHOTOS_FORBIDDEN" in message_text
        ):
            result = "Error: Нет прав для отправки изображений в этот чат"
        else:
            result = f"Error sending message: {e}"
        return result, None

    return result, None
