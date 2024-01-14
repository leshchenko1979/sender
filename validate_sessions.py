import asyncio
import os

import streamlit as st
import supabase

asyncio.set_event_loop(asyncio.new_event_loop())

import pyrogram
from pyrogram.errors import (
    AuthKeyUnregistered,
    UserDeactivated,
    SessionPasswordNeeded,
    PasswordHashInvalid,
    PhoneCodeInvalid,
)


import settings
from account.account import Account
from supabasefs.supabasefs import SupabaseTableFileSystem

AUTH_NEEDED = 1
CODE_REQUESTED = 2
PASSWORD_NEEDED = 3
ACCEPTED = 4


async def main():
    if "GOOGLE_SERVICE_ACCOUNT" not in os.environ:
        import dotenv
        dotenv.load_dotenv()

    st.header("Проверка аккаунтов для рассылки ОД")

    settings = load_settings()

    fs = load_fs()

    init_state_cache()

    await validate_accs(settings, fs)

    st.write("Готово")


@st.cache_data(show_spinner="Загружаю настройки...")
def load_settings():
    return settings.load_settings()


@st.cache_resource
def load_fs():
    return SupabaseTableFileSystem(
        supabase.create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"]),
        "sessions",
    )


def init_state_cache():
    if "accounts" not in st.session_state:
        st.session_state["accounts"] = {}


async def validate_accs(settings, fs):
    distinct_account_ids = {setting.account for setting in settings if setting.active} | {os.environ["ALERT_ACCOUNT"]}
    for account in distinct_account_ids:
        with st.container(border=True):
            st.subheader(f"Аккаунт: {account}")
            await check_account(fs, account)


async def check_account(fs, account):
    if account not in st.session_state["accounts"]:
        acc = await init_account(fs, account)
        st.session_state["accounts"][account] = acc
    else:
        acc = st.session_state["accounts"][account]

    await display_acc(account, acc)


async def init_account(fs, account):
    st.write("Попытка подключения...")

    acc = Account(fs, account)

    if fs.exists(acc.filename):
        with fs.open(acc.filename, "r") as f:
            session_str = f.read()

        acc.app = pyrogram.Client(
            account,
            session_string=session_str,
            in_memory=True,
            no_updates=True,
        )

        try:
            await acc.app.start()
            acc.state = ACCEPTED
            await acc.app.stop()

        except (AuthKeyUnregistered, UserDeactivated):
            acc.state = AUTH_NEEDED

    else:
        acc.state = AUTH_NEEDED

    if acc.state == AUTH_NEEDED:
        acc.app = pyrogram.Client(
            account,
            os.environ["API_ID"],
            os.environ["API_HASH"],
            in_memory=True,
            no_updates=True,
            phone_number=account,
        )

        await acc.app.connect()
        acc.code_object = await acc.app.send_code(account)
        print("Code sent to", account, acc.code_object)
        acc.state = CODE_REQUESTED

    return acc


async def display_acc(account, acc: Account):
    if acc.state == ACCEPTED:
        st.success("OK")
        return

    if acc.state == CODE_REQUESTED:
        code = st.text_input("Введите код, пришедший в Telegram:")
        if not code:
            st.stop()
        else:
            try:
                await acc.app.sign_in(account, acc.code_object.phone_code_hash, code)
                await acc.stop()
                acc.state = ACCEPTED
                st.rerun()
            except SessionPasswordNeeded:
                acc.state = PASSWORD_NEEDED
                st.rerun()
            except PhoneCodeInvalid:
                st.error("Неверный код")
                st.stop()

    if acc.state == PASSWORD_NEEDED:
        password = st.text_input("Введите пароль от Telegram:")
        if not password:
            st.stop()
        else:
            try:
                await acc.app.check_password(password)
                await acc.stop()
                acc.state = ACCEPTED
                st.rerun()
            except PasswordHashInvalid:
                st.error("Неверный пароль")
                st.stop()


asyncio.run(main())
