import asyncio
from logging import ERROR, getLogger

import supabase
from telethon.errors import (
    FloodWaitError,
    PasswordHashInvalidError,
    PhoneCodeInvalidError,
)
from tg.account import Account
from tg.supabasefs import SupabaseTableFileSystem

from .core.clients import load_clients
from .core.config import AppSettings, get_settings
from .core.settings import Setting
from .scheduling.cron_utils import humanize_seconds

getLogger("httpx").setLevel(ERROR)


async def main():
    app_settings = get_settings()
    clients = load_clients()
    settings: list[Setting] = []
    for client in clients:
        settings.extend(client.load_settings())

    fs = load_fs(app_settings)

    print("Подготовка закончена.")

    await validate_accs(settings, fs, app_settings)

    print("Все аккаунты проверены.")


def load_fs(app_settings: AppSettings):
    return SupabaseTableFileSystem(
        supabase.create_client(app_settings.supabase_url, app_settings.supabase_key),
        "sessions",
    )


async def validate_accs(settings: list[Setting], fs, app_settings: AppSettings):
    distinct_account_ids = {setting.account for setting in settings if setting.active}
    if app_settings.alert_account:
        distinct_account_ids.add(app_settings.alert_account)

    for account in distinct_account_ids:
        print("Проверка аккаунта", to_phone_format(account))
        while True:
            try:
                async with Account(fs, account).session(revalidate=True):
                    print("OK")
                    break
            except (PasswordHashInvalidError, PhoneCodeInvalidError):
                print("Некорректно")
            except FloodWaitError as e:
                print(
                    f"Слишком много неправильных попыток. Подождите {humanize_seconds(e.value)}"
                )


def to_phone_format(s):
    # Transform a 11-digit string to a +X (XXX) XXX-XX-XX format
    return f"+{s[:1]} ({s[1:4]}) {s[4:7]}-{s[7:9]}-{s[9:]}"


if __name__ == "__main__":
    asyncio.run(main())
