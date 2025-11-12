import datetime
import logging
import re
import traceback
from math import ceil

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

from clients import Client
from cron_utils import adjust_cron_interval, format_schedule_change_message
from settings import Setting
from telegram_sender import SenderAccount
from telegram_utils import parse_chat_and_topic, _generate_message_link

logger = logging.getLogger(__name__)


async def process_setting_outer(
    client_name: str,
    setting: Setting,
    accounts,
    errors: list[str],
    client: Client = None,
    supabase_logs=None,
):
    was_processed = False
    was_successful = False

    if setting.active:
        try:
            successful = supabase_logs.get_last_successful_entry(setting)
            # Check the setting time to determine if a message should be sent based
            # on the last time it was sent.
            if not successful:
                result = "Message was never sent before: logged successfully"
                was_processed = True
                was_successful = True
            else:
                try:
                    should_be_run = setting.should_be_run(successful)
                    result = None if should_be_run else "Message already sent recently"
                    if should_be_run:
                        was_processed = True
                except Exception as e:
                    result = (
                        f"Error: Could not figure out the crontab setting: {str(e)}"
                    )
            if not result:
                result, message_info = await send_setting(setting, accounts, client)

        except Exception:
            result = f"Error: {traceback.format_exc()}"
    else:
        result = "Setting skipped"

    # add log entry
    try:
        supabase_logs.add_log_entry(client_name, setting, result)
    except Exception:
        result = f"Logging error: {traceback.format_exc()}"

    # add error to error list and setting
    if "error" in result.lower():
        errors[setting.get_hash()] = result
        setting.error = result
        setting.active = 0
        if was_processed:
            was_successful = False
    elif "successfully" in result.lower():
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        error_text = f"ОК: {timestamp}"

        # Try to generate link to the published message
        if (
            "message_info" in locals()
            and message_info
            and isinstance(message_info, dict)
            and "message_ids" in message_info
        ):
            try:
                # Get account app for entity resolution
                acc = accounts[setting.account]
                first_message_id = message_info["message_ids"][
                    0
                ]  # Use first message ID
                link = await _generate_message_link(
                    chat_id=message_info["chat_id"],
                    message_id=first_message_id,
                    topic_id=message_info.get("topic_id"),
                    account_app=acc.app,
                )
                if link:
                    error_text += f" - {link}"
            except Exception:
                # If link generation fails, just use timestamp
                pass

        setting.error = error_text
        was_successful = True

    return was_processed, was_successful


async def send_setting(setting: Setting, accounts, client: Client = None):
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
            message_ids = []
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
            from cron_utils import humanize_seconds

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


def handle_slow_mode_error(client: Client, setting: Setting, wait_seconds: int) -> str:
    """
    Handle SlowModeWaitError by adjusting schedules for all settings targeting the same chat.

    Args:
        client: Client containing all settings
        setting: The setting that triggered the slow mode error
        wait_seconds: Number of seconds to wait before next message

    Returns:
        Result message describing the changes made
    """
    # Step 1: Calculate required interval (round up to hours)
    # Handle edge cases where wait_seconds is 0 or negative
    if wait_seconds <= 0:
        wait_seconds = 3600  # Default to 1 hour minimum
    required_hours = ceil((wait_seconds * 1.2) / 3600)  # 20% buffer

    # Step 2: Find all active settings for same chat
    related_settings = [
        s for s in client.settings if s.chat_id == setting.chat_id and s.active
    ]

    if not related_settings:
        return "No active settings found for this chat"

    # Step 3: Adjust schedules for all related settings
    updated_count = 0
    for s in related_settings:
        old_schedule = s.schedule
        new_schedule = adjust_cron_interval(old_schedule, required_hours)

        if new_schedule != old_schedule:
            s.schedule = new_schedule
            s.error = format_schedule_change_message(
                wait_seconds,
                old_schedule,
                new_schedule,
                required_hours,
                len(related_settings),
            )
            updated_count += 1

    # Step 4: Update Google Sheets with new schedules and errors
    client.update_settings_in_gsheets(["schedule", "error"])

    if updated_count > 0:
        return (
            f"Schedule auto-adjusted to every {required_hours} hours "
            f"for {updated_count} settings in chat {setting.chat_id}"
        )
    else:
        return (
            f"No schedule adjustments needed - current intervals already sufficient "
            f"for {len(related_settings)} settings in chat {setting.chat_id}"
        )
