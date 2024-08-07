import asyncio
import datetime
import os
import traceback
from datetime import datetime

import dotenv
import pyrogram
import supabase
from flask import Flask
from pyrogram.errors import (
    ChatAdminRequired,
    ChatSendMediaForbidden,
    ChatWriteForbidden,
    InviteRequestSent,
    RPCError,
    SlowmodeWait,
)
from tg.account import Account, AccountCollection, AccountStartFailed
from tg.supabasefs import SupabaseTableFileSystem
from tg.utils import parse_telegram_message_url

from clients import Client, load_clients
from settings import Setting
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
        errors = {}

        settings = client.load_settings()

        if any(s.active for s in settings):
            accounts = set_up_accounts(fs, settings)
            supabase_logs.load_results_for_client(client.name)

            async with accounts.session():
                await asyncio.gather(
                    *[
                        process_setting_outer(client.name, setting, accounts, errors)
                        for setting in settings
                    ]
                )
        else:
            logger.warning(f"No active settings for {client.name}")

    except AccountStartFailed as exc:
        errors[""] = f"Телефон {exc.phone} не был инициализирован."
    except Exception:
        errors[""] = f"Error: {traceback.format_exc()}"

    await publish_stats(errors, fs, client)

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


async def process_setting_outer(
    client_name: str, setting: Setting, accounts: AccountCollection, errors: list[str]
):
    if setting.active:
        try:
            successful = supabase_logs.get_last_successful_entry(setting)
            result = check_setting_time(setting, successful)
            if not result:
                result = await send_setting(setting, accounts)

        except Exception:
            result = f"Error: {traceback.format_exc()}"
    else:
        result = "Setting skipped"

    # add log entry
    try:
        supabase_logs.add_log_entry(client_name, setting, result)
    except Exception:
        result = f"Logging error: {traceback.format_exc()}"

    # add error to error list and setting
    if "error" in result.lower():
        errors[setting.get_hash()] = result
        setting.error = result
        setting.active = 0
    elif "successfully" in result.lower():
        setting.error = ""


def check_setting_time(setting: Setting, last_time_sent: datetime | None):
    """
    Check the setting time to determine if a message should be sent based
    on the last time it was sent.

    Parameters:
    - setting: Setting object to check against
    - last_time_sent: Datetime object representing the last time the message was sent,
        or None if never sent

    Returns:
    - str: Message indicating the result of the check, or None
        if the message should be sent
    """
    if not last_time_sent:
        return "Message was never sent before: logged successfully"

    try:
        should_be_run = setting.should_be_run(last_time_sent)
        return None if should_be_run else "Message already sent recently"
    except Exception as e:
        return f"Error: Could not figure out the crontab setting: {str(e)}"


async def send_setting(setting: Setting, accounts: AccountCollection):
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

    except ChatWriteForbidden:
        result = "Error: Нет прав для отправки сообщения"

    except ChatSendMediaForbidden:
        result = "Error: Нет прав для отправки изображений"

    except ChatAdminRequired:
        result = "Error: Это канал, а не группа"

    except InviteRequestSent:
        result = "Error: До сих пор не принят запрос на вступление"

    except SlowmodeWait as e:
        result = f"Error: Слишком рано отправляется (подождать {e.value} секунд)"

    except RPCError as e:
        result = f"Error sending message: {e}"

    return result


ALERT_HEADING = "Результаты последней рассылки:"


async def publish_stats(errors: dict, fs, client: Client):
    alert_acc = SenderAccount(fs, client.alert_account)

    async with alert_acc.session(revalidate=False):
        # Send common errors like no accounts started
        if "" in errors:
            await alert_acc.send_message(chat_id=client.alert_chat, text=errors[""])

        # Delete last message if it contains alert heading
        app = alert_acc.app
        last_msg: pyrogram.types.Message = await anext(
            app.get_chat_history(chat_id=client.alert_chat, limit=1)
        )
        if last_msg.text and ALERT_HEADING in last_msg.text:
            await app.delete_messages(
                chat_id=client.alert_chat, message_ids=[last_msg.id]
            )

        # Calculate error stats from client.settings:
        # turned off with errors, active with errors

        stats_msg = prep_stats_msg(client)

        # Send error message
        if stats_msg:
            await alert_acc.send_message(chat_id=client.alert_chat, text=stats_msg)

    logger.warning("Alert message sent", extra={"errors": errors})


def prep_stats_msg(client: Client):
    turned_off_with_errors = len(
        [s for s in client.settings if not s.active and s.error]
    )
    turned_off_no_errors = len(
        [s for s in client.settings if not s.active and not s.error]
    )

    if not turned_off_with_errors and not turned_off_no_errors:
        return ""

    working = len([s for s in client.settings if s.active])

    text = f"{ALERT_HEADING}\n\n"

    if turned_off_with_errors:
        text += (
            f"{turned_off_with_errors} рассылок отключены из-за ошибок. "
            "Исправьте и включите заново.\n\n"
        )

    if turned_off_no_errors:
        text += (
            f"{turned_off_no_errors} отключенных рассылок без ошибок. "
            "Почему отключены?\n\n"
        )

    text += f"{working} (из {len(client.settings)} всего) активных рассылок.\n\n"
    text += f"Подробности в файле настроек: {client.spreadsheet_url}."

    return text


app = Flask(__name__)


@app.route("/", methods=["GET", "POST"])
def handler():
    asyncio.run(main())
    return "OK"


if __name__ == "__main__":
    asyncio.run(main())
