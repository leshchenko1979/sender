import datetime
import logging
import traceback
from typing import Any
from zoneinfo import ZoneInfo

from ..core.clients import Client
from ..core.settings import Setting
from ..utils.telegram_utils import _generate_message_link
from .sender import send_setting

logger = logging.getLogger(__name__)


async def process_setting_outer(
    client_name: str,
    setting: Setting,
    accounts: Any,
    errors: dict[str, str],
    client: Client | None = None,
    supabase_logs: Any = None,
) -> tuple[bool, bool]:
    was_processed = False
    was_successful = False

    if setting.active:
        try:
            successful = (
                supabase_logs.get_last_successful_entry(setting)
                if supabase_logs
                else None
            )
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
        if supabase_logs:
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
        moscow_tz = ZoneInfo("Europe/Moscow")
        timestamp = datetime.datetime.now(moscow_tz).strftime("%Y-%m-%d %H:%M:%S")
        setting.error = f"ОК: {timestamp}"
        setting.link = ""

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
                    setting.link = link
            except Exception:
                # If link generation fails, leave link empty
                pass

        was_successful = True

    return was_processed, was_successful
