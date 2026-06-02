"""Sender CLI — entry point for the cron job.

Dispatches to clients, processes settings, reports to Gatus.
Now synchronous — uses fast-mcp-telegram bridge instead of Telethon.
"""

from __future__ import annotations

import logging
import traceback

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
    gatus_reporter: GatusReporter | None = None,
) -> None:
    """Process all clients and log their progress."""
    clients = load_clients()

    for client in clients:
        logger.info(f"Starting {client.name}")
        try:
            process_client(app_settings, supabase_logs, client)
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

    process_all_clients(app_settings, supabase_logs, gatus_reporter)


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


def process_client(
    app_settings: AppSettings,
    supabase_logs: SupabaseLogHandler,
    client: Client,
) -> None:
    """Process a single client."""
    errors: dict[str, str] = {}
    processed_count = 0
    successful_count = 0

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

    except Exception as exc:
        raise ProcessingError(f"Unexpected error: {traceback.format_exc()}") from exc
    finally:
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
