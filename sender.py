import asyncio
import logging
import os
import traceback

import dotenv
import supabase
from tg.account import AccountCollection, AccountStartFailed
from tg.supabasefs import SupabaseTableFileSystem

from clients import Client, load_clients
from message_processor import process_setting_outer
from settings import Setting
from stats_publisher import publish_stats
from supabase_logs import SupabaseLogHandler
from telegram_sender import SenderAccount


# Set up standard Python logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


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


if __name__ == "__main__":
    asyncio.run(main())
