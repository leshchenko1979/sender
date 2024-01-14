import asyncio
import datetime
import os
import traceback
from datetime import datetime
from datetime import timezone as tz

import croniter
import dotenv
import pyrogram
import supabase
from flask import Flask

from account.account import Account, AccountCollection
from settings import load_settings
from supabasefs.supabasefs import SupabaseTableFileSystem


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
        {account: Account(fs, account) for account in distinct_account_ids},
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
            await accounts[setting.account].app.send_message(
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

    return get_recent_cron_datetime(setting.schedule) > datetime.fromisoformat(
        last_successful_entry["datetime"]
    )


def get_recent_cron_datetime(crontab):
    # Use croniter to parse the crontab string
    cron = croniter.croniter(crontab, datetime.now(tz.utc))

    return cron.get_prev(datetime)


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
    alert_acc = Account(fs, os.environ["ALERT_ACCOUNT"])
    async with alert_acc.session(invalid="raise"):
        await alert_acc.app.send_message(
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
