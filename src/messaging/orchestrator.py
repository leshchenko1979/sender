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
from ..utils.telegram_url_parser import parse_telegram_message_url
from ..utils.telegram_utils import _check_message_exists, _generate_message_link
from .sender import send_setting

logger = logging.getLogger(__name__)


def _is_url(text: str) -> bool:
    """Check if text is a Telegram message URL."""
    try:
        parse_telegram_message_url(text)
        return True
    except (ValueError, TypeError):
        return False


def _extract_title(setting: Setting) -> str | None:
    """Extract a short title from the setting for logging."""
    if not setting.text:
        return None
    if _is_url(setting.text):
        return "[Пересылка]"
    return setting.text[:100] if setting.text else None


def _client_token(client: Client | None) -> str | None:
    """Extract bearer token from client config."""
    return client.fast_mcp_bearer if client else None


def _run_setting(
    setting: Setting,
    supabase_logs,
    token: str | None,
    client: Client | None,
) -> tuple[str, bool, dict | None]:
    """Run the send pipeline for an active setting.

    Returns (result_text, was_processed, message_info_dict).
    """
    successful = (
        supabase_logs.get_last_successful_entry(setting) if supabase_logs else None
    )
    if not successful:
        return "Message was never sent before: logged successfully", True, None

    try:
        should_be_run = setting.should_be_run(successful)
    except Exception as e:
        return f"Error: Could not figure out the crontab setting: {e}", True, None

    if not should_be_run:
        return "Message already sent recently", False, None

    if setting.link:
        message_exists = _check_message_exists(setting.link, bearer_token=token)
        if not message_exists:
            return "Error: Предыдущее сообщение было удалено", True, None

    result, message_info = send_setting(setting, client)
    return result, True, message_info


def _apply_result(
    setting: Setting,
    result: str,
    message_info: dict | None,
    errors: dict[str, str],
    token: str | None,
) -> bool:
    """Update setting state from send result. Returns was_successful."""
    if "error" in result.lower():
        errors[setting.get_hash()] = result
        setting.error = result
        setting.active = 0
        return False

    if "successfully" in result.lower():
        moscow_tz = ZoneInfo("Europe/Moscow")
        timestamp = datetime.datetime.now(moscow_tz).strftime("%Y-%m-%d %H:%M:%S")
        setting.error = f"ОК: {timestamp}"
        setting.link = ""
        if (
            message_info
            and isinstance(message_info, dict)
            and message_info.get("message_ids")
        ):
            try:
                first_msg_id = message_info["message_ids"][0]
                if link := _generate_message_link(
                    chat_id=message_info["chat_id"],
                    message_id=first_msg_id,
                    topic_id=message_info.get("topic_id"),
                    bearer_token=token,
                ):
                    setting.link = link
            except Exception:
                pass
        return True

    return False


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
    message_info = None
    token = _client_token(client)

    if not setting.active:
        result = "Setting skipped"
    else:
        try:
            result, was_processed, message_info = _run_setting(
                setting, supabase_logs, token, client
            )
        except Exception:
            result = f"Error: {traceback.format_exc()}"
            was_processed = True

    was_successful = _apply_result(setting, result, message_info, errors, token)

    # Log entry — AFTER _apply_result so setting.link is populated
    if supabase_logs:
        try:
            supabase_logs.add_log_entry(
                client_name,
                setting,
                result,
                message_title=_extract_title(setting),
                source_link=setting.text if _is_url(setting.text) else None,
                message_link=setting.link or None,
            )
        except Exception:
            logger.warning(
                f"Failed to log entry for {setting.chat_id}: {traceback.format_exc()}"
            )

    return was_processed, was_successful
