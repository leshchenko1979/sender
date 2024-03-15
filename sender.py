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
from pyrogram.errors import ChatWriteForbidden, RPCError
from tg.account import Account, AccountCollection, AccountStartFailed
from tg.supabasefs import SupabaseTableFileSystem
from tg.utils import parse_telegram_message_url

from clients import Client, load_clients
from settings import Setting, load_settings
from supabase_logs import SupabaseLogHandler
from yandex_logging import init_logging

logger = init_logging(__name__)


class SenderAccount(Account):
    """Defines methods for sending and forwarding messages
    with forced joining the group if the peer is not in the chat yet."""

    async def send_message(self, chat_id, text):
        if not self.started:
            raise RuntimeError("App is not started")

        try:
            return await self.app.send_message(chat_id, text)

        except ChatWriteForbidden:
            await self.app.join_chat(chat_id)
            return await self.app.send_message(chat_id, text)

    async def forward_message(self, chat_id, from_chat_id, message_id):
        """Forward message from chat to chat with forced joining the group
        if the peer is not in the group yet and omitting the info
        about the original author."""

        if not self.started:
            raise RuntimeError("App is not started")

        from_peer = await self.app.resolve_peer(from_chat_id)
        to_peer = await self.app.resolve_peer(chat_id)
        wrapper = pyrogram.raw.functions.messages.forward_messages.ForwardMessages
        forward_messages_query = wrapper(
            from_peer=from_peer,
            id=[message_id],
            to_peer=to_peer,
            drop_author=True,
            random_id=[self.app.rnd_id()],
        )

        try:
            return await self.app.invoke(forward_messages_query)

        except ChatWriteForbidden:
            await self.app.join_chat(chat_id)
            return await self.app.invoke(forward_messages_query)


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
        errors = []

        settings = load_settings(client)

        if any(s.active for s in settings):
            accounts = set_up_accounts(fs, settings)
            async with accounts.session():
                await asyncio.gather(
                    *[
                        process_setting_outer(client.name, setting, accounts, errors)
                        for setting in settings
                    ]
                )
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
            successful = supabase_logs.get_last_successful_entry(setting)
            result = await process_setting(setting, accounts, successful)

        except Exception:
            result = f"Error: {traceback.format_exc()}"
    else:
        result = "Setting skipped"

    try:
        supabase_logs.add_log_entry(client_name, setting, result)
    except Exception:
        result = f"Logging error: {traceback.format_exc()}"

    if "error" in result.lower():
        errors.append(f"{setting}: {result}")


async def process_setting(
    setting: Setting, accounts: AccountCollection, last_successful_entry
):
    if not last_successful_entry:
        return "Message was never sent before: logged successfully"

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

    acc: SenderAccount = accounts[setting.account]

    try:
        if forward_needed:
            await acc.forward_message(
                chat_id=setting.chat_id,
                from_chat_id=from_chat_id,
                message_id=message_id,
            )
            result = "Message forwarded successfully"

        else:
            await acc.send_message(chat_id=setting.chat_id, text=setting.text)
            result = "Message sent successfully"

    except RPCError as e:
        result = f"Error sending message: {e}"

    return result


async def alert(errors, fs, client: Client):
    # Send alert message
    alert_acc = SenderAccount(fs, client.alert_account)

    shortened_errs = "\n\n".join(
        err if len(err) < 300 else f"{err[:300]}..." for err in errors
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
