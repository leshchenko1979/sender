import asyncio
import datetime
import os
import traceback
from datetime import datetime
from datetime import timezone as tz
from zoneinfo import ZoneInfo

import croniter
import dotenv
import pyrogram
import supabase
from flask import Flask
from pyrogram.errors import ChatWriteForbidden

from account.account import Account, AccountCollection
from settings import load_settings
from supabasefs.supabasefs import SupabaseTableFileSystem


class SenderAccount(Account):
    async def send_message(self, chat_id, text, forced_entry=True):
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
    set_up_clients(settings)
    errors = []

    async with accounts.session():
        for setting in settings:
            try:
                result = (
                    await send_message(setting) if setting.active else "Setting skipped"
                )
            except Exception:
                result = f"Error: {traceback.format_exc()}"

            try:
                add_log_entry(setting, result)
            except Exception:
                result = f"Logging error: {traceback.format_exc()}"

            if "error" in result.lower():
                errors.append(f"{setting}: {result}")

    if errors:
        await alert(errors, fs)

    print("Messages sent and logged successfully")


def set_up_clients(settings):
    # Set up Telegram and Supabase clients as global variables

    global supabase_client, accounts, fs

    supabase_client = supabase.create_client(
        os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"]
    )

    fs = SupabaseTableFileSystem(supabase_client, "sessions")

    distinct_account_ids = {setting.account for setting in settings}

    if not distinct_account_ids:
        raise ValueError("No accounts found")

    accounts = AccountCollection(
        {account: SenderAccount(fs, account) for account in distinct_account_ids},
        fs,
        invalid="raise",
    )


async def send_message(setting):
    # Load most recent log entry
    log_entry = get_last_successful_entry(setting.account, setting.chat_id)

    try:
        should_be_run_result = should_be_run(setting, log_entry)
    except Exception as e:
        return f"Error: Could not figure out the crontab setting: {str(e)}"

    if should_be_run_result:
        try:
            # Send message
            await accounts[setting.account].send_message(
                chat_id=setting.chat_id, text=setting.text
            )
            result = "Message sent successfully"

        except pyrogram.errors.RPCError as e:
            result = f"Error sending message: {e}"

    else:
        result = "Message already sent recently"

    return result


def should_be_run(setting, last_successful_entry):
    # Check if the message should be sent

    if not last_successful_entry:
        return True

    return check_cron_tz(
        setting.schedule,
        ZoneInfo("Europe/Moscow"),
        datetime.fromisoformat(last_successful_entry["datetime"]),
        datetime.now(tz=tz.utc),
    )


def check_cron(crontab: str, last_run: datetime, now: datetime) -> bool:
    # Return True if, according to the crontab, there should have been another run between the last run and now
    cron = croniter.croniter(crontab, last_run)
    next_run = cron.get_next(datetime)
    return next_run <= now


def check_cron_tz(
    crontab: str, crontab_tz: ZoneInfo, last_run: datetime, now: datetime
) -> bool:
    """Return True if, according to the crontab, there should have been
    another run between the last run and now.

    Crontab is in another timezone indicated by crontab_tz.
    """

    last_run_utc = last_run.astimezone(crontab_tz).replace(tzinfo=None)
    now_utc = now.astimezone(crontab_tz).replace(tzinfo=None)

    return check_cron(crontab, last_run_utc, now_utc)


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
    async with alert_acc.session(invalid="raise"):
        await alert_acc.send_message(
            chat_id=os.environ["ALERT_CHAT"], text="\n".join(errors)
        )


app = Flask(__name__)


@app.route("/")
def handler():
    dotenv.load_dotenv()
    asyncio.run(main())


if __name__ == "__main__":
    dotenv.load_dotenv()
    asyncio.run(main())
