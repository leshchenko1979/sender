import asyncio
import contextlib
import datetime as dt
import os

import fsspec
import pyrogram
from pyrogram.errors import AuthKeyUnregistered, UserDeactivated


class Account:
    app: pyrogram.Client
    fs: fsspec.spec.AbstractFileSystem
    phone: str
    filename: str

    started: bool
    flood_wait_timeout: int
    flood_wait_from: dt.datetime

    def __init__(
        self, /, fs: fsspec.spec.AbstractFileSystem, phone=None, filename=None
    ):
        self.filename = filename or f"{phone}.session"
        self.fs = fs
        self.phone = phone
        self.started = False
        self.flood_wait_timeout = 0
        self.flood_wait_from = None
        self.app = None

    def __repr__(self) -> str:
        return f"<Account {self.filename}>"

    async def start(
        self, revalidate=True, code_retrieval_func=lambda: input("Enter code:")
    ):
        if self.fs.exists(self.filename):
            with self.fs.open(self.filename, "r") as f:
                session_str = f.read()

            self.app = pyrogram.Client(
                self.phone,
                session_string=session_str,
                in_memory=True,
                no_updates=True,
            )

        else:
            self.setup_new_session(code_retrieval_func)

        try:
            await self.app.start()

        except (AuthKeyUnregistered, UserDeactivated):
            if not revalidate:
                raise

            self.setup_new_session(code_retrieval_func)

            await self.app.start()

        self.started = True
        self.flood_wait_timeout = 0
        self.flood_wait_from = None

    async def setup_new_session(self, code_retrieval_func):
        print(self.phone)
        self.app = pyrogram.Client(
            self.phone,
            os.environ["API_ID"],
            os.environ["API_HASH"],
            in_memory=True,
            no_updates=True,
            phone_number=self.phone,
        )

        await self.app.connect()

        code_object = await self.app.send_code(self.phone)

        self.app.sign_in(self.phone, code_object.phone_code_hash, code_retrieval_func())

    async def stop(self):
        session_str = await self.app.export_session_string()

        with self.fs.open(self.filename, "w") as f:
            f.write(session_str)

        await self.app.stop()

        self.started = False

    @contextlib.asynccontextmanager
    async def session(self):
        try:
            await self.start()
            yield

        finally:
            await self.stop()


class AccountCollection:
    accounts: list[Account]

    def __init__(self, accounts: dict[str, Account], fs, revalidate_sessions=True):
        self.accounts = accounts
        self.fs = fs
        self.revalidate_sessions = revalidate_sessions

    def __getitem__(self, item):
        return self.accounts[item]

    async def start_sessions(self):
        await asyncio.gather(
            *(
                acc.start(revalidate=self.revalidate_sessions)
                for acc in self.accounts.values()
            ),
            return_exceptions=not self.revalidate_sessions,
        )

    async def close_sessions(self):
        await asyncio.gather(
            *[acc.stop() for acc in self.accounts.values() if acc.started]
        )

    @contextlib.asynccontextmanager
    async def session(self, pbar=None):
        SESSION_LOCK = ".session_lock"
        if self.fs.exists(SESSION_LOCK):
            raise RuntimeError("Sessions are already in use")

        self.pbar = pbar

        try:
            await self.start_sessions()

            self.fs.touch(SESSION_LOCK)

            yield

        finally:
            self.pbar = None

            self.fs.rm(SESSION_LOCK)

            await self.close_sessions()
