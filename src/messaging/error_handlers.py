from math import ceil
from typing import Iterable

from ..core.clients import Client
from ..core.settings import Setting
from ..scheduling.cron_utils import adjust_cron_interval, format_schedule_change_message


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
    related_settings = _related_active_settings(client.settings, setting.chat_id)

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


def _related_active_settings(
    settings: Iterable[Setting], chat_id: str
) -> list[Setting]:
    return [s for s in settings if s.chat_id == chat_id and s.active]
