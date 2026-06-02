"""Message orchestration — processing settings, checking schedules, logging.

Previously used async Telethon via tg.account.Account and AccountCollection.
Now uses the synchronous fast-mcp-telegram bridge.
Supports per-client bearer tokens.
"""

from __future__ import annotations

import datetime
import logging
import traceback
from zoneinfo import ZoneInfo

from ..core.clients import Client
from ..core.settings import Setting
from ..utils.telegram_utils import _check_message_exists, _generate_message_link
from .sender import send_setting

logger = logging.getLogger(__name__)


def _client_token(client: Client | None) -> str | None:
    """Extract bearer token from client config."""
    return client.fast_mcp_bearer if client else None


def process_setting_outer(
    client_name: str,
    setting: Setting,
    errors: dict[str, str],
    client: Client | None = None,
    supabase_logs=None,
) -> tuple[bool, bool]:
    """Process a single setting: check schedule, forward/send, log.

    Returns (was_processed, was_successful).
    """
    was_processed = False
    was_successful = False
    token = _client_token(client)

    if setting.active:
        try:
            successful = (
                supabase_logs.get_last_successful_entry(setting)
                if supabase_logs
                else None
            )
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
                if setting.link:
                    message_exists = _check_message_exists(
                        setting.link, bearer_token=token
                    )
                    if not message_exists:
                        result = "Error: Предыдущее сообщение было удалено"
                        was_processed = True
                        was_successful = False

                if not result:
                    result, message_info = send_setting(setting, client)

        except Exception:
            result = f"Error: {traceback.format_exc()}"
    else:
        result = "Setting skipped"

    try:
        if supabase_logs:
            supabase_logs.add_log_entry(client_name, setting, result)
    except Exception:
        result = f"Logging error: {traceback.format_exc()}"

    if "error" in result.lower():
        errors[setting.get_hash()] = result
        setting.error = result
        setting.active = 0
        if was_processed:
            was_successful = False
    elif "successfully" in result.lower():
        moscow_tz = ZoneInfo("Europe/Moscow")
        timestamp = datetime.datetime.now(moscow_tz).strftime("%Y-%m-%d %H:%M:%S")
        setting.error = f"���: {timestamp}"
        setting.link = ""

        if (
            "message_info" in locals()
            and message_info
            and isinstance(message_info, dict)
            and "message_ids" in message_info
        ):
            try:
                first_msg_id = message_info["message_ids"][0]
                link = _generate_message_link(
                    chat_id=message_info["chat_id"],
                    message_id=first_msg_id,
                    topic_id=message_info.get("topic_id"),
                    bearer_token=token,
                )
                if link:
                    setting.link = link
            except Exception:
                pass

        was_successful = True

    return was_processed, was_successful
