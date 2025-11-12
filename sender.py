import asyncio
import datetime
import logging
import os
import re
import traceback
from math import ceil

import dotenv
import supabase
from telethon.errors import (
    ChatAdminRequiredError,
    ChatSendMediaForbiddenError,
    ChatWriteForbiddenError,
    InviteRequestSentError,
    RPCError,
    SlowModeWaitError,
    UsernameNotOccupiedError,
)
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import (
    ForwardMessagesRequest,
    ImportChatInviteRequest,
)
from tg.account import Account, AccountCollection, AccountStartFailed
from tg.supabasefs import SupabaseTableFileSystem
from tg.utils import parse_telegram_message_url

from clients import Client, load_clients
from cron_utils import adjust_cron_interval, format_schedule_change_message
from settings import Setting
from supabase_logs import SupabaseLogHandler


def parse_chat_and_topic(chat_id: str) -> tuple[str, int | None]:
    """
    Parse chat_id which may contain topic in format: chat_id/topic_id

    Examples:
        "@mychannel/123" -> ("@mychannel", 123)
        "-1001234567890/456" -> ("-1001234567890", 456)
        "1826486256/7832" -> ("-1001826486256", 7832)  # Auto-converts to supergroup format
        "@mychannel" -> ("@mychannel", None)

    Returns:
        Tuple of (chat_id, topic_id or None)
    """
    if "/" in chat_id:
        parts = chat_id.rsplit("/", 1)
        try:
            topic_id = int(parts[1])
            chat_part = parts[0]

            # Auto-convert numeric chat IDs to supergroup format if needed
            if chat_part.isdigit() and not chat_part.startswith("-100"):
                # Convert to supergroup format: add -100 prefix
                chat_part = f"-100{chat_part}"

            return chat_part, topic_id
        except ValueError:
            # Not a valid topic number, treat whole string as chat_id
            return chat_id, None
    return chat_id, None


# Set up standard Python logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


class SenderAccount(Account):
    """Defines methods for sending and forwarding messages
    with forced joining the group if the peer is not in the chat yet."""

    async def _get_grouped_message_ids(self, from_chat_id, message_id, grouped_id):
        """Retrieve all message IDs in a media group around the given message."""
        search_window = 20  # Search 20 messages before and after
        offsets_to_try = [message_id + search_window, message_id]

        for offset_id in offsets_to_try:
            grouped_messages = []
            try:
                async for msg in self.app.iter_messages(
                    from_chat_id,
                    offset_id=offset_id,
                    limit=search_window * 2,
                ):
                    if hasattr(msg, "grouped_id") and msg.grouped_id == grouped_id:
                        grouped_messages.append(msg.id)

                if grouped_messages:
                    return grouped_messages
            except ValueError:
                # Try next offset if this one fails
                continue

        return []

    async def _forward_grouped_or_single(
        self, chat_id, from_chat_id, message_id, reply_to_msg_id=None
    ):
        """Forward a message or entire media group if the message is part of one."""
        source_message = await self.app.get_messages(from_chat_id, ids=message_id)
        if not source_message:
            raise ValueError("Не удалось получить исходное сообщение")

        # Determine messages to forward
        if (
            hasattr(source_message, "grouped_id")
            and source_message.grouped_id is not None
        ):
            grouped_messages = await self._get_grouped_message_ids(
                from_chat_id, message_id, source_message.grouped_id
            )
            if not grouped_messages:
                raise ValueError("Медиагруппа неполная или недоступна")
            message_ids = sorted(grouped_messages)
        else:
            message_ids = [message_id]

        # Forward messages using MTProto ForwardMessagesRequest (supports both regular and forum topics)
        return await self.app(
            ForwardMessagesRequest(
                from_peer=from_chat_id,
                id=message_ids,
                to_peer=chat_id,
                top_msg_id=reply_to_msg_id,  # None for regular forwarding, topic ID for forum topics
                drop_author=True,
            )
        )

    async def _join_chat(self, chat_id):
        try:
            # If chat_id is an invite link, try importing invite first
            invite_hash = self._extract_invite_hash(str(chat_id))
            if invite_hash:
                try:
                    await self.app(ImportChatInviteRequest(invite_hash))
                    return
                except RPCError:
                    # fall back to channel join attempt below
                    pass

            # For public channels/supergroups this will work with username or id
            await self.app(JoinChannelRequest(chat_id))
        except RPCError:
            # Silently ignore join failures; send/forward will raise clearer error
            pass

    def _extract_invite_hash(self, text: str):
        # Supports t.me/joinchat/<hash> and t.me/+<hash>
        m = re.search(r"t\.me/(?:joinchat/|\+)([A-Za-z0-9_-]{16,})", text)
        return m.group(1) if m else None


async def main():
    dotenv.load_dotenv()
    fs = set_up_supabase()
    clients = load_clients()

    for client in clients:
        logger.info(f"Starting {client.name}")
        await process_client(fs, client)
        logger.info(f"Finished {client.name}")

    logger.info("Messages sent and logged successfully")


def set_up_supabase():
    global supabase_client, supabase_logs

    supabase_client = supabase.create_client(
        os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"]
    )

    supabase_logs = SupabaseLogHandler(supabase_client)

    return SupabaseTableFileSystem(supabase_client, "sessions")


async def process_client(fs, client: Client):
    try:
        errors = {}
        processed_count = 0
        successful_count = 0

        settings = client.load_settings()

        if any(s.active for s in settings):
            accounts = set_up_accounts(fs, settings)
            supabase_logs.load_results_for_client(client.name)

            async with accounts.session():
                results = await asyncio.gather(
                    *[
                        process_setting_outer(
                            client.name, setting, accounts, errors, client
                        )
                        for setting in settings
                    ]
                )

                # Подсчет статистики из результатов
                for was_processed, was_successful in results:
                    if was_processed:
                        processed_count += 1
                        if was_successful:
                            successful_count += 1
        else:
            logger.warning(f"No active settings for {client.name}")

    except AccountStartFailed as exc:
        errors[""] = f"Телефон {exc.phone} не был инициализирован."
    except Exception:
        errors[""] = f"Error: {traceback.format_exc()}"

    await publish_stats(errors, fs, client, processed_count, successful_count)

    client.update_settings_in_gsheets(["active", "error"])


def set_up_accounts(fs, settings: list[Setting]):
    return AccountCollection(
        {
            setting.account: SenderAccount(fs, setting.account)
            for setting in settings
            if setting.active
        },
        fs,
        invalid="raise",
    )


async def process_setting_outer(
    client_name: str,
    setting: Setting,
    accounts: AccountCollection,
    errors: list[str],
    client: Client = None,
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


async def send_setting(
    setting: Setting, accounts: AccountCollection, client: Client = None
):
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


def _normalize_channel_id(channel_id: str) -> str:
    """Normalize channel ID by removing -100 prefix for private channels."""
    return channel_id[4:] if channel_id.startswith("-100") else channel_id


def _build_query_string(
    thread_id: int | None = None,
    comment_id: int | None = None,
) -> str:
    """Build query string for Telegram links."""
    query_params = []
    if thread_id:
        query_params.append(f"thread={thread_id}")

    query_string = "&".join(query_params)
    return "?" + query_string if query_string else ""


async def _generate_message_link(
    chat_id: str,
    message_id: int,
    topic_id: int | None = None,
    account_app=None,
) -> str | None:
    """
    Generate Telegram message link.

    Returns link string or None if cannot generate.
    """
    try:
        # Try to resolve entity to get username
        entity = None
        if account_app:
            try:
                entity = await account_app.get_entity(chat_id)
            except Exception:
                pass

        if entity and hasattr(entity, "username") and entity.username:
            # Public chat with username
            clean_username = entity.username.lstrip("@")
            if topic_id:
                return f"https://t.me/{clean_username}/{topic_id}/{message_id}"
            else:
                return f"https://t.me/{clean_username}/{message_id}"
        else:
            # Private chat - use numeric ID
            channel_id = _normalize_channel_id(str(chat_id))
            if topic_id:
                return f"https://t.me/c/{channel_id}/{topic_id}/{message_id}"
            else:
                return f"https://t.me/c/{channel_id}/{message_id}"
    except Exception as e:
        logger.warning(f"Failed to generate message link: {e}")
        return None


ALERT_HEADING = "Результаты последней рассылки:"


async def publish_stats(
    errors: dict, fs, client: Client, processed_count: int, successful_count: int
):
    alert_acc = SenderAccount(fs, client.alert_account)

    async with alert_acc.session(revalidate=False):
        app = alert_acc.app

        # Delete last message if it contains alert heading
        msgs = await app.get_messages(client.alert_chat, limit=1)
        if msgs:
            last_msg = msgs[0]
            if getattr(last_msg, "message", None) and ALERT_HEADING in last_msg.message:
                await app.delete_messages(client.alert_chat, [last_msg.id])

        text = f"{ALERT_HEADING}\n\n"

        # If there are critical errors (like authorization failure), show only them
        if "" in errors:
            text += f"❌ {errors['']}\n\n"
            text += f"Подробности в файле настроек: {client.spreadsheet_url}."
        else:
            # Добавляем статистику обработанных и успешных отправок
            if processed_count > 0:
                text += f"Наступило время для: {processed_count} рассылок\n"
                text += (
                    f"Успешных отправок: {successful_count} из {processed_count}\n\n"
                )
            else:
                text += "Наступило время для: 0 рассылок\n\n"

            # Calculate error stats from client.settings:
            # turned off with errors, active with errors
            turned_off_with_errors = len(
                [s for s in client.settings if not s.active and s.error]
            )
            turned_off_no_errors = len(
                [s for s in client.settings if not s.active and not s.error]
            )

            if turned_off_with_errors:
                text += (
                    f"{turned_off_with_errors} рассылок отключены из-за ошибок. "
                    "Исправьте и включите заново.\n\n"
                )

            if turned_off_no_errors:
                text += (
                    f"{turned_off_no_errors} отключенных рассылок без ошибок. "
                    "Почему отключены?\n\n"
                )

            text += (
                f"{len([s for s in client.settings if s.active])} "
                f"(из {len(client.settings)} всего) активных рассылок.\n\n"
                f"Подробности в файле настроек: {client.spreadsheet_url}."
            )

        await app.send_message(client.alert_chat, text)

        if errors:
            logger.warning("Alert message sent", extra={"errors": errors})
        else:
            logger.info("Alert message sent with success statistics")


if __name__ == "__main__":
    asyncio.run(main())
