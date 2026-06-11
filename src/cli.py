"""Sender CLI — entry point for the cron job.

Dispatches to clients, processes settings, reports to Gatus.
Now synchronous — uses fast-mcp-telegram bridge instead of Telethon.
"""

from __future__ import annotations

import logging
import traceback
from datetime import datetime, timezone

import supabase

from .core.clients import Client, load_clients
from .core.config import AppSettings, get_settings
from .infrastructure.supabase_logs import SupabaseLogHandler
from .monitoring.gatus_reporter import GatusReporter
from .monitoring.logging_config import setup_logging
from .monitoring.stats_publisher import publish_stats

logger = logging.getLogger(__name__)


class ClientProcessingError(Exception):
    """Base exception for client processing errors."""

    pass


class ProcessingError(ClientProcessingError):
    """Raised when message processing fails."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def process_all_clients(
    app_settings: AppSettings,
    supabase_logs: SupabaseLogHandler,
    supabase_client: supabase.Client,
    gatus_reporter: GatusReporter | None = None,
) -> None:
    """Process all clients and log their progress."""
    clients = load_clients()

    for client in clients:
        logger.info(f"Starting {client.name}")
        try:
            process_client(app_settings, supabase_logs, supabase_client, client)
            logger.info(f"Finished {client.name}")
            _report_to_gatus(gatus_reporter, client.name, success=True)
        except ClientProcessingError as exc:
            logger.exception(f"Client {client.name} processing failed: {exc}")
            _report_to_gatus(gatus_reporter, client.name, success=False, error=str(exc))
        except Exception as exc:
            logger.exception(f"Unexpected error processing client {client.name}: {exc}")
            _report_to_gatus(gatus_reporter, client.name, success=False, error=str(exc))

    logger.info("Messages sent and logged successfully")


def _report_to_gatus(
    reporter: GatusReporter | None,
    client_name: str,
    success: bool,
    error: str | None = None,
) -> None:
    if reporter:
        reporter.report(client_name, success, error)


def main() -> None:
    """Main application entry point."""
    app_settings = get_settings()
    setup_logging(app_settings)

    # Supabase client for log persistence
    supabase_client = supabase.create_client(
        app_settings.supabase_url,
        app_settings.supabase_key,
    )
    supabase_logs = SupabaseLogHandler(supabase_client)

    gatus_reporter = None
    if app_settings.gatus_url and app_settings.gatus_token:
        gatus_reporter = GatusReporter(app_settings.gatus_url, app_settings.gatus_token)

    process_all_clients(app_settings, supabase_logs, supabase_client, gatus_reporter)


def process_client_settings(
    client: Client,
    supabase_logs: SupabaseLogHandler,
    errors: dict[str, str],
) -> tuple[int, int]:
    """Process all settings for a client and return statistics.

    Synchronous — uses fast-mcp-telegram bridge for Telegram operations.
    """
    processed_count = 0
    successful_count = 0

    from .messaging.orchestrator import process_setting_outer

    for setting in client.load_settings():
        if not setting.active:
            continue
        try:
            result = process_setting_outer(
                client.name,
                setting,
                errors,
                client,
                supabase_logs,
            )
            if isinstance(result, tuple) and len(result) == 2:
                was_processed, was_successful = result
                if was_processed:
                    processed_count += 1
                    if was_successful:
                        successful_count += 1
        except Exception as exc:
            logger.error(f"Setting processing failed: {exc}")
            errors[""] = f"Processing error: {str(exc)}"

    return processed_count, successful_count


def _bridge_call(method: str, params: dict, bearer_token: str | None = None) -> dict:
    """Call the MTProto bridge directly (bypasses _call's ok/error check).

    The bridge returns raw TL results without the ok/result wrapper
    that bridge._call() expects.
    """
    import json as _json
    import os
    import urllib.error
    import urllib.request

    base = os.environ.get("FAST_MCP_BASE", "http://fast-mcp-telegram:8000/mtproto-api")
    url = f"{base.rstrip('/')}/{method.lstrip('/')}"
    body = _json.dumps({"params": params}).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    token = bearer_token or os.environ.get("FAST_MCP_BEARER", "")
    if token:
        req.add_header("Authorization", f"Bearer {token}")

    with urllib.request.urlopen(req, timeout=15) as resp:
        return _json.loads(resp.read().decode("utf-8"))


def _fetch_group_stats(
    client: Client,
    settings: list,
    supabase_client: supabase.Client,
) -> None:
    """Fetch member/online counts for unique groups and upsert to Supabase."""
    token = client.fast_mcp_bearer if client else None
    unique_chat_ids = list({s.chat_id.split("/")[0] for s in settings if s.active})
    if not unique_chat_ids:
        return

    rows = []
    for chat_id in unique_chat_ids:
        members = None
        online = None
        name = None
        try:
            full = _bridge_call(
                "channels.GetFullChannel",
                {"channel": chat_id},
                bearer_token=token,
            )
            full_chat = full.get("full_chat", {})
            members = full_chat.get("participants_count")
            chats = full.get("chats", [])
            if chats:
                name = chats[0].get("title")
        except Exception as exc:
            logger.warning(f"Failed to get full channel for {chat_id}: {exc}")

        try:
            onlines = _bridge_call(
                "messages.GetOnlines",
                {"peer": chat_id},
                bearer_token=token,
            )
            online = onlines.get("onlines")
        except Exception as exc:
            logger.warning(f"Failed to get onlines for {chat_id}: {exc}")

        rows.append(
            {
                "chat_id": chat_id,
                "client_name": client.name,
                "members": members,
                "online": online,
                "name": name,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    try:
        supabase_client.table("group_stats").upsert(
            rows, on_conflict="chat_id,client_name"
        ).execute()
        logger.info(f"Updated group_stats for {len(rows)} groups in {client.name}")
    except Exception as exc:
        logger.warning(f"Failed to upsert group_stats for {client.name}: {exc}")

    # Fetch message history to count total posts per day per group
    _fetch_group_daily_stats(client, unique_chat_ids, token, supabase_client)


def _fetch_group_daily_stats(
    client: Client,
    chat_ids: list[str],
    token: str | None,
    supabase_client: supabase.Client,
) -> None:
    """Fetch recent messages from each group and count posts per day."""

    daily_rows = []
    for chat_id in chat_ids:
        try:
            history = _bridge_call(
                "messages.GetHistory",
                {
                    "peer": chat_id,
                    "limit": 100,
                    "offset_id": 0,
                    "offset_date": None,
                    "add_offset": 0,
                    "max_id": 0,
                    "min_id": 0,
                    "hash": 0,
                },
                bearer_token=token,
            )
            messages = history.get("messages", [])
            # Count posts by day (last 7 days)
            day_counts: dict[str, int] = {}
            for msg in messages:
                date_str = msg.get("date", "")
                if not date_str or len(date_str) < 10:
                    continue
                day = date_str[:10]  # YYYY-MM-DD
                day_counts[day] = day_counts.get(day, 0) + 1

            for day, count in day_counts.items():
                daily_rows.append(
                    {
                        "chat_id": chat_id,
                        "client_name": client.name,
                        "date": day,
                        "post_count": count,
                    }
                )
        except Exception as exc:
            logger.warning(f"Failed to get history for {chat_id}: {exc}")

    if daily_rows:
        try:
            supabase_client.table("group_daily_stats").upsert(
                daily_rows, on_conflict="chat_id,client_name,date"
            ).execute()
            logger.info(
                f"Updated daily stats for {len(chat_ids)} groups in {client.name}"
            )
        except Exception as exc:
            logger.warning(f"Failed to upsert daily stats for {client.name}: {exc}")


def _mirror_settings(
    client: Client,
    settings: list,
    supabase_client: supabase.Client,
) -> None:
    """Write current settings to settings_mirror for the dashboard.

    Called in the finally block after processing, so error/link/active
    values reflect the final state.
    """
    rows = []
    for i, setting in enumerate(settings):
        rows.append(
            {
                "client_name": client.name,
                "row_index": i,
                "active": bool(setting.active),
                "schedule": setting.schedule,
                "chat_id": setting.chat_id,
                "text": setting.text,
                "error": setting.error,
                "link": setting.link,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    try:
        supabase_client.table("settings_mirror").upsert(
            rows, on_conflict="client_name,row_index"
        ).execute()
        logger.info(f"Mirrored {len(rows)} settings for {client.name}")
    except Exception as exc:
        logger.warning(f"Failed to mirror settings for {client.name}: {exc}")


def process_client(
    app_settings: AppSettings,
    supabase_logs: SupabaseLogHandler,
    supabase_client: supabase.Client,
    client: Client,
) -> None:
    """Process a single client."""
    errors: dict[str, str] = {}
    processed_count = 0
    successful_count = 0
    settings = []

    try:
        try:
            settings = client.load_settings()
        except Exception as exc:
            errors[""] = f"Не удалось загрузить настройки: {str(exc)}"
            raise ProcessingError(
                f"Settings loading failed: {traceback.format_exc()}"
            ) from exc

        if not any(s.active for s in settings):
            logger.warning(f"No active settings for {client.name}")
            return

        supabase_logs.load_results_for_client(client.name)
        processed_count, successful_count = process_client_settings(
            client, supabase_logs, errors
        )

        # Fetch group stats after all settings are processed
        _fetch_group_stats(client, settings, supabase_client)

    except Exception as exc:
        raise ProcessingError(f"Unexpected error: {traceback.format_exc()}") from exc
    finally:
        # Mirror settings to Supabase (final state with error/link/active)
        if settings:
            _mirror_settings(client, settings, supabase_client)

        try:
            publish_stats(
                errors,
                None,  # fs no longer needed
                client,
                processed_count,
                successful_count,
                app_settings,
            )
            client.update_settings_in_gsheets(["active", "error", "link"])
        except Exception as exc:
            logger.error(f"Failed to publish stats for {client.name}: {exc}")


if __name__ == "__main__":
    main()
