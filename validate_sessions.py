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
    FloodWait,
)


import settings
from account.account import Account
from supabasefs.supabasefs import SupabaseTableFileSystem

AUTH_NEEDED = 1
CODE_REQUESTED = 2
PASSWORD_NEEDED = 3
ACCEPTED = 4
FLOOD_WAIT = 5
WRONG_CODE = 6
WRONG_PASSWORD = 7


async def main():
    if "GOOGLE_SERVICE_ACCOUNT" not in os.environ:
        import dotenv

        dotenv.load_dotenv()

    st.header("Проверка аккаунтов для рассылки ОД")

    settings = load_settings()

    fs = load_fs()

    init_state_cache()

    await validate_accs(settings, fs)


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
    distinct_account_ids = {
        setting.account for setting in settings if setting.active
    } | {os.environ["ALERT_ACCOUNT"]}

    for account in distinct_account_ids:
        with st.container(border=True):
            st.subheader(to_phone_format(account))
            await check_account(fs, account)


def to_phone_format(s):
    # Transform a 11-digit string to a +X (XXX) XXX-XX-XX format
    return f"+{s[:1]} ({s[1:4]}) {s[4:7]}-{s[7:9]}-{s[9:]}"


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

            await acc.app.stop()
            acc.state = ACCEPTED

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

        try:
            await acc.app.connect()
            acc.code_object = await acc.app.send_code(account)

        except FloodWait as e:
            acc.state = FLOOD_WAIT
            acc.flood_wait_timeout = e.value

        else:
            print("Code sent to", account, acc.code_object)
            acc.state = CODE_REQUESTED

    return acc


async def display_acc(account, acc: Account):
    if acc.state == ACCEPTED:
        st.success("OK")
        return

    if acc.state in {CODE_REQUESTED, WRONG_CODE}:
        if acc.state == WRONG_CODE:
            st.error("Неверный код")

        code = st.text_input(
            "Введите код, пришедший в Telegram:", key=f"code_{acc.phone}"
        )
        if code:
            try:
                st.session_state[f"code_{acc.phone}"] = ""

                await acc.app.sign_in(account, acc.code_object.phone_code_hash, code)

                acc.started = True
                await acc.stop()

                acc.state = ACCEPTED

            except SessionPasswordNeeded:
                acc.state = PASSWORD_NEEDED

            except PhoneCodeInvalid:
                acc.state = WRONG_CODE

            st.rerun()

    if acc.state in {PASSWORD_NEEDED, WRONG_PASSWORD}:
        if acc.state == WRONG_PASSWORD:
            st.error("Неверный пароль")

        password = st.text_input(
            "Введите пароль от Telegram:", type="password", key=f"password_{acc.phone}"
        )
        if password:
            try:
                st.session_state[f"password_{acc.phone}"] = ""

                await acc.app.check_password(password)

                acc.started = True
                await acc.stop()

                acc.state = ACCEPTED

            except PasswordHashInvalid:
                acc.state = WRONG_PASSWORD

            st.rerun()

    if acc.state == FLOOD_WAIT:
        st.error(
            "Слишком много неправильных попыток авторизации. "
            f"Ожидайте {humanized_seconds(acc.flood_wait_timeout)}."
        )


def humanized_seconds(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds} секунд"
    elif seconds < 3600:
        return f"{seconds // 60} минут"
    else:
        return f"{seconds // 3600} часов"


asyncio.run(main())
