import asyncio
import datetime
import os
import traceback
from datetime import datetime
from functools import cache

import dotenv
import more_itertools
import pyrogram
import supabase
from flask import Flask
from pyrogram.errors import ChatWriteForbidden
from tg.account import Account, AccountCollection, AccountStartFailed
from tg.supabasefs import SupabaseTableFileSystem
from tg.utils import parse_telegram_message_url

from clients import Client, load_clients
from settings import Setting, load_settings
from yandex_logging import init_logging

logger = init_logging(__name__)


class SenderAccount(Account):
    async def send_message(self, chat_id, text, forced_entry=True):
        if not self.started:
            raise RuntimeError("App is not started")

        try:
            return await self.app.send_message(chat_id, text)

        except ChatWriteForbidden:
            if forced_entry:
                await self.app.join_chat(chat_id)
                return await self.app.send_message(chat_id, text)
            else:
                raise


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

    global supabase_client

    supabase_client = supabase.create_client(
        os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"]
    )

    return SupabaseTableFileSystem(supabase_client, "sessions")


async def process_client(fs, client: Client):
    try:
        errors = []

        settings = load_settings(client)

        if any(s.active for s in settings):
            accounts = set_up_accounts(fs, settings)
            async with accounts.session():
                for setting in settings:
                    await process_setting_outer(client.name, setting, accounts, errors)
        else:
            logger.warning(f"No active settings for {client.name}")

    except AccountStartFailed:
        errors.append(
            "Не все аккаунты были привязаны.\n" "Запустите привязку аккаунтов."
        )
    except Exception:
        errors.append(f"Error: {traceback.format_exc()}")

    if errors:
        await alert(errors, fs, client)


def set_up_accounts(fs, settings: list[Setting]):
    distinct_account_ids = {setting.account for setting in settings if setting.active}

    collection = get_account_collection_from_supabase(fs)

    for account_id in distinct_account_ids:
        if account_id not in collection.accounts:
            collection.accounts[account_id] = SenderAccount(fs, account_id)

    return collection


@cache
def get_account_collection_from_supabase(fs):
    return AccountCollection({}, fs, invalid="raise")


async def process_setting_outer(
    client_name: str, setting: Setting, accounts: AccountCollection, errors: list[str]
):
    if setting.active:
        try:
            successful = get_last_successful_entry(setting)
            result = await process_setting(setting, accounts, successful)

        except Exception:
            result = f"Error: {traceback.format_exc()}"
    else:
        result = "Setting skipped"

    try:
        add_log_entry(client_name, setting, result)
    except Exception:
        result = f"Logging error: {traceback.format_exc()}"

    if "error" in result.lower():
        errors.append(f"{setting}: {result}")


async def process_setting(
    setting: Setting, accounts: AccountCollection, last_successful_entry
):
    if not last_successful_entry:
        should_be_run = True
    else:
        last_time_sent = datetime.fromisoformat(last_successful_entry["datetime"])
        try:
            should_be_run = setting.should_be_run(last_time_sent)
        except Exception as e:
            return f"Error: Could not figure out the crontab setting: {str(e)}"

    if not should_be_run:
        return "Message already sent recently"

    try:
        from_chat_id, message_id = parse_telegram_message_url(setting.text)
        forward_needed = True
    except Exception:  # not a valid telegram url
        forward_needed = False

    app = accounts[setting.account].app

    return (
        await forward_message(app, setting, from_chat_id, message_id)
        if forward_needed
        else await send_text_message(app, setting)
    )


async def send_text_message(app: pyrogram.client.Client, setting: Setting):
    try:
        # Send text message
        await app.send_message(chat_id=setting.chat_id, text=setting.text)
        result = "Message sent successfully"

    except pyrogram.errors.RPCError as e:
        result = f"Error sending message: {e}"

    return result


async def forward_message(
    app: pyrogram.client.Client, setting: Setting, from_chat_id, message_id
):
    try:
        # Forward message hiding the sender
        await app.invoke(
            pyrogram.raw.functions.messages.forward_messages.ForwardMessages(
                from_peer=await app.resolve_peer(from_chat_id),
                id=[message_id],
                to_peer=await app.resolve_peer(setting.chat_id),
                drop_author=True,
                random_id=[app.rnd_id()],
            )
        )
        result = "Message forwarded successfully"

    except pyrogram.errors.RPCError as e:
        result = f"Error forwarding message: {e}"

    return result


def get_last_successful_entry(setting: Setting):
    # Query for most recent log entry
    result = (
        supabase_client.table("log_entries")
        .select("datetime")
        .eq("setting_unique_id", setting.get_hash())
        .like("result", "%successfully%")
        .order("datetime", desc=True)
        .limit(1)
        .execute()
    )

    return result.data[0] if result.data else None


def add_log_entry(client_name: str, setting: Setting, result: str):
    # Add log entry
    entry = {
        "client_name": client_name,
        "account": setting.account,
        "chat_id": setting.chat_id,
        "result": result,
        "setting_unique_id": setting.get_hash(),
    }

    supabase_client.table("log_entries").insert(entry).execute()

    logger.info(f"Logged {entry}", extra=entry)


async def alert(errors, fs, client: Client):
    # Send alert message
    alert_acc = SenderAccount(fs, client.alert_account)

    shortened_errs = "\n".join(
        err if len(err) < 200 else f"{err[:200]}..." for err in errors
    )
    msgs = ("".join(msg) for msg in more_itertools.batched(shortened_errs, 4096))

    async with alert_acc.session(revalidate=False):
        for msg in msgs:
            await alert_acc.send_message(chat_id=client.alert_chat, text=msg)

    logger.warning("Alert message sent", extra={"errors": errors})


app = Flask(__name__)


@app.route("/", methods=["GET", "POST"])
def handler():
    asyncio.run(main())
    return "OK"


if __name__ == "__main__":
    asyncio.run(main())
