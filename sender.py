import asyncio
import datetime
import os
import traceback
from datetime import datetime

import dotenv
import pyrogram
import supabase
from flask import Flask
from pyrogram.errors import ChatWriteForbidden

from settings import Setting, load_settings
from tg.account import Account, AccountCollection, AccountStartFailed
from tg.supabasefs import SupabaseTableFileSystem
from tg.utils import parse_telegram_message_url


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
    settings = load_settings()
    fs = set_up_supabase()
    accounts = set_up_accounts(fs, settings)

    errors = []

    try:
        async with accounts.session():
            for setting in settings:
                if setting.active:
                    try:
                        last_successful_entry = get_last_successful_entry(
                            setting.account, setting.chat_id
                        )
                        result = await process_setting(
                            setting, accounts, last_successful_entry
                        )

                    except Exception:
                        result = f"Error: {traceback.format_exc()}"
                else:
                    result = "Setting skipped"

                try:
                    add_log_entry(setting, result)
                except Exception:
                    result = f"Logging error: {traceback.format_exc()}"

                if "error" in result.lower():
                    errors.append(f"{setting}: {result}")

    except AccountStartFailed:
        errors.append(
            "Не все аккаунты были привязаны.\n" "Запустите привязку аккаунтов."
        )
    except Exception:
        errors.append(f"Error: {traceback.format_exc()}")

    if errors:
        await alert(errors, fs)

    print("Messages sent and logged successfully")


def set_up_supabase():

    global supabase_client

    supabase_client = supabase.create_client(
        os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"]
    )

    return SupabaseTableFileSystem(supabase_client, "sessions")


def set_up_accounts(fs, settings):
    distinct_account_ids = {setting.account for setting in settings}

    if not distinct_account_ids:
        raise ValueError("No accounts found")

    return AccountCollection(
        {account: SenderAccount(fs, account) for account in distinct_account_ids},
        fs,
        invalid="raise",
    )


async def process_setting(setting: Setting, accounts: AccountCollection):
    # Load most recent log entry
    log_entry = get_last_successful_entry(setting.account, setting.chat_id)

    if not log_entry:
        should_be_run = True
    else:
        last_time_sent = datetime.fromisoformat(log_entry["datetime"])
        try:
            should_be_run = setting.should_be_run(last_time_sent)
        except Exception as e:
            return f"Error: Could not figure out the crontab setting: {str(e)}"

    if not should_be_run:
        return "Message already sent recently"

    # check if setting.text is a valid url like https://t.me/od_sender_alerts/43
    # if it is, retrieve the message_id this url refers to

    try:
        from_chat_id, message_id = parse_telegram_message_url(setting.text)
        forward_needed = True
    except Exception:  # not a valid telegram url
        forward_needed = False

    app = accounts[setting.account]

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


def get_last_successful_entry(account, chat_id):
    # Query for most recent log entry
    result = (
        supabase_client.table("log_entries")
        .select("*")
        .eq("account", account)
        .eq("chat_id", chat_id)
        .like("result", "%successfully%")
        .order("datetime", desc=True)
        .limit(1)
        .execute()
    )

    return result.data[0] if result.data else None


def add_log_entry(setting, result):
    # Add log entry
    supabase_client.table("log_entries").insert(
        {"account": setting.account, "chat_id": setting.chat_id, "result": result}
    ).execute()

    return


async def alert(errors, fs):
    # Send alert message
    alert_acc = SenderAccount(fs, os.environ["ALERT_ACCOUNT"])
    async with alert_acc.session(revalidate=False):
        await alert_acc.send_message(
            chat_id=os.environ["ALERT_CHAT"], text="\n".join(errors)
        )


app = Flask(__name__)


@app.route("/")
def handler():
    dotenv.load_dotenv()
    asyncio.run(main())
    return "OK"


if __name__ == "__main__":
    dotenv.load_dotenv()
    asyncio.run(main())
