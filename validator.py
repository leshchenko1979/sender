print("Идет подготовка...")


import asyncio
import os
from logging import ERROR, getLogger

import dotenv
import supabase
from pyrogram.errors import FloodWait, PasswordHashInvalid, PhoneCodeInvalid

import settings as stng
from account.account import Account
from supabasefs.supabasefs import SupabaseTableFileSystem

getLogger("httpx").setLevel(ERROR)
getLogger("pyrogram").setLevel(ERROR)


async def main():
    dotenv.load_dotenv()

    settings = stng.load_settings()

    fs = load_fs()

    print("Подготовка закончена.")

    await validate_accs(settings, fs)

    print("Все аккаунты проверены.")


def load_fs():
    return SupabaseTableFileSystem(
        supabase.create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"]),
        "sessions",
    )


async def validate_accs(settings, fs):
    distinct_account_ids = {
        setting.account for setting in settings if setting.active
    } | {os.environ["ALERT_ACCOUNT"]}

    for account in distinct_account_ids:
        print("Проверка аккаунта", to_phone_format(account))
        while True:
            try:
                async with Account(fs, account).session(revalidate=True):
                    print("OK")
                    break
            except (PasswordHashInvalid, PhoneCodeInvalid):
                print("Некорректно")
            except FloodWait as e:
                print(
                    "Слишком много неправильных попыток. Подождите {humanized_seconds(e.value).}"
                )


def to_phone_format(s):
    # Transform a 11-digit string to a +X (XXX) XXX-XX-XX format
    return f"+{s[:1]} ({s[1:4]}) {s[4:7]}-{s[7:9]}-{s[9:]}"


def humanized_seconds(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds} секунд"
    elif seconds < 3600:
        return f"{seconds // 60} минут"
    else:
        return f"{seconds // 3600} часов"


if __name__ == "__main__":
    asyncio.run(main())
