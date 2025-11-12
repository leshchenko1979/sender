import asyncio
import logging
import traceback

import supabase
from tg.account import AccountCollection, AccountStartFailed
from tg.supabasefs import SupabaseTableFileSystem

from .core.clients import Client, load_clients
from .core.config import AppSettings, get_settings
from .core.settings import Setting
from .infrastructure.supabase_logs import SupabaseLogHandler
from .messaging.orchestrator import process_setting_outer
from .messaging.telegram_sender import SenderAccount
from .monitoring.stats_publisher import publish_stats

# Set up standard Python logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


async def main():
    app_settings = get_settings()
    fs = set_up_supabase(app_settings)
    clients = load_clients()

    for client in clients:
        logger.info(f"Starting {client.name}")
        await process_client(app_settings, fs, client)
        logger.info(f"Finished {client.name}")

    logger.info("Messages sent and logged successfully")


def set_up_supabase(app_settings: AppSettings):
    global supabase_client, supabase_logs

    supabase_client = supabase.create_client(
        app_settings.supabase_url,
        app_settings.supabase_key,
    )

    supabase_logs = SupabaseLogHandler(supabase_client)

    return SupabaseTableFileSystem(supabase_client, "sessions")


async def process_client(app_settings, fs, client: Client):
    try:
        errors = {}
        processed_count = 0
        successful_count = 0

        settings = client.load_settings()

        if any(s.active for s in settings):
            accounts = set_up_accounts(app_settings, fs, settings)
            supabase_logs.load_results_for_client(client.name)

            async with accounts.session():
                results = await asyncio.gather(
                    *[
                        process_setting_outer(
                            client.name,
                            setting,
                            accounts,
                            errors,
                            client,
                            supabase_logs,
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

    await publish_stats(
        errors, fs, client, processed_count, successful_count, app_settings
    )

    client.update_settings_in_gsheets(["active", "error", "link"])


def set_up_accounts(app_settings, fs, settings: list[Setting]):
    return AccountCollection(
        {
            setting.account: SenderAccount(
                fs, setting.account, app_settings.api_id, app_settings.api_hash
            )
            for setting in settings
            if setting.active
        },
        fs,
        invalid="raise",
    )


if __name__ == "__main__":
    asyncio.run(main())
