import asyncio


import os

import dotenv
import streamlit as st
import supabase

asyncio.set_event_loop(asyncio.new_event_loop())

from account.account import Account
from settings import load_settings
from supabasefs.supabasefs import SupabaseTableFileSystem


async def main():
    dotenv.load_dotenv()

    st.header("Проверка аккаунтов для рассылки ОД")

    settings = load_settings()

    supabase_client = supabase.create_client(
        os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"]
    )

    fs = SupabaseTableFileSystem(supabase_client, "sessions")

    for setting in settings:
        account = setting.account
        with st.container(border=True):
            st.subheader(f"Аккаунт: {account}")
            st.write(f"Статус: {setting.active}")
            if setting.active:
                st.write(f"Попытка подключения...")
                app = Account(fs, setting.account)
                await app.start(revalidate=True, code_retrieval_func=ask_for_code)
                if app.started:
                    st.success(f"OK")
                else:
                    st.warning("Ошибка")

    st.write("Готово")


def ask_for_code():
    return st.text_input(f"Введите код, пришедший в приложение Telegram")


asyncio.run(main())
