import asyncio
import logging
import traceback
from dataclasses import dataclass
from typing import Optional

import supabase
from tg.account import AccountCollection, AccountStartFailed
from tg.supabasefs import SupabaseTableFileSystem

from .core.clients import Client, load_clients
from .core.config import AppSettings, get_settings
from .core.settings import Setting
from .infrastructure.supabase_logs import SupabaseLogHandler
from .messaging.orchestrator import process_setting_outer
from .messaging.telegram_sender import SenderAccount
from .monitoring.logging_config import setup_logging
from .monitoring.stats_publisher import publish_stats

# Initialize logger (logging config will be set up in setup_logging function)
logger = logging.getLogger(__name__)


class ClientProcessingError(Exception):
    """Base exception for client processing errors."""

    pass


class AccountInitializationError(ClientProcessingError):
    """Raised when account initialization fails."""

    def __init__(self, phone: str, message: str):
        self.phone = phone
        self.message = message
        super().__init__(f"Account {phone}: {message}")


class ProcessingError(ClientProcessingError):
    """Raised when message processing fails."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


@dataclass
class AppContext:
    """Application context containing shared dependencies."""

    supabase_client: supabase.Client
    supabase_logs: SupabaseLogHandler
    filesystem: SupabaseTableFileSystem


async def process_all_clients(app_settings: AppSettings, context: AppContext) -> None:
    """Process all clients and log their progress."""
    clients = load_clients()

    for client in clients:
        logger.info(f"Starting {client.name}")
        try:
            await process_client(app_settings, context, client)
            logger.info(f"Finished {client.name}")
        except ClientProcessingError as exc:
            logger.exception(f"Client {client.name} processing failed: {exc}")
        except Exception as exc:
            logger.exception(f"Unexpected error processing client {client.name}: {exc}")

    logger.info("Messages sent and logged successfully")


async def main() -> None:
    """Main application entry point."""
    app_settings = get_settings()
    setup_logging(app_settings)

    context = set_up_supabase(app_settings)
    await process_all_clients(app_settings, context)


def set_up_supabase(app_settings: AppSettings) -> AppContext:
    """Set up Supabase client, logging, and filesystem."""
    supabase_client = supabase.create_client(
        app_settings.supabase_url,
        app_settings.supabase_key,
    )

    supabase_logs = SupabaseLogHandler(supabase_client)
    filesystem = SupabaseTableFileSystem(supabase_client, "sessions")

    return AppContext(
        supabase_client=supabase_client,
        supabase_logs=supabase_logs,
        filesystem=filesystem,
    )


async def process_client_settings(
    client: Client,
    accounts: AccountCollection,
    context: AppContext,
    errors: dict[str, str],
) -> tuple[int, int]:
    """Process all settings for a client and return statistics."""
    processed_count = 0
    successful_count = 0

    async with accounts.session():
        results = await asyncio.gather(
            *[
                process_setting_outer(
                    client.name,
                    setting,
                    accounts,
                    errors,
                    client,
                    context.supabase_logs,
                )
                for setting in client.load_settings()
                if setting.active
            ],
            return_exceptions=True,
        )

        # Process results and handle any exceptions from gather
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Setting processing failed: {result}")
                errors[""] = f"Processing error: {str(result)}"
            elif isinstance(result, tuple) and len(result) == 2:
                was_processed, was_successful = result
                if was_processed:
                    processed_count += 1
                    if was_successful:
                        successful_count += 1

    return processed_count, successful_count


async def process_client(
    app_settings: AppSettings, context: AppContext, client: Client
) -> None:
    """Process a single client with proper error handling and resource management."""
    errors: dict[str, str] = {}
    processed_count = 0
    successful_count = 0
    accounts = None

    try:
        try:
            settings = client.load_settings()
        except Exception as exc:
            # Add settings loading failure to errors for alert reporting
            errors[""] = f"Не удалось загрузить настройки: {str(exc)}"
            raise ProcessingError(
                f"Settings loading failed: {traceback.format_exc()}"
            ) from exc

        if not any(s.active for s in settings):
            logger.warning(f"No active settings for {client.name}")
            return

        # Set up accounts and load results
        accounts = set_up_accounts(app_settings, context.filesystem, settings, client)
        context.supabase_logs.load_results_for_client(client.name)

        # Process settings and collect statistics
        processed_count, successful_count = await process_client_settings(
            client, accounts, context, errors
        )

    except AccountStartFailed as exc:
        raise AccountInitializationError(exc.phone, "не был инициализирован") from exc
    except Exception as exc:
        raise ProcessingError(f"Unexpected error: {traceback.format_exc()}") from exc
    finally:
        # Always publish stats and update sheets, even if there were errors
        try:
            await publish_stats(
                errors,
                context.filesystem,
                client,
                processed_count,
                successful_count,
                app_settings,
            )
            client.update_settings_in_gsheets(["active", "error", "link"])
        except Exception as exc:
            logger.error(f"Failed to publish stats for {client.name}: {exc}")
            # Don't re-raise to avoid masking the original error


def create_sender_account(
    fs: SupabaseTableFileSystem, phone: str, api_id: int, api_hash: str
) -> SenderAccount:
    """Centralized account creation function."""
    return SenderAccount(
        fs=fs,
        phone=phone,
        api_id=api_id,
        api_hash=api_hash,
    )


def set_up_accounts(
    app_settings: AppSettings,
    fs: SupabaseTableFileSystem,
    settings: list[Setting],
    client: Optional[Client] = None,
) -> AccountCollection:
    """Set up and return account collection for active settings."""
    accounts_dict = {
        setting.account: create_sender_account(
            fs, setting.account, app_settings.api_id, app_settings.api_hash
        )
        for setting in settings
        if setting.active
    }

    return AccountCollection(accounts_dict, fs=fs, invalid="raise")


if __name__ == "__main__":
    asyncio.run(main())
