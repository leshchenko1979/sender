import datetime
from logging import getLogger

import supabase
from reretry import retry

import settings

logger = getLogger(__name__)


class SupabaseLogHandler:
    def __init__(self, supabase_client: supabase.Client):
        self.supabase_client = supabase_client

    @retry
    def load_results_for_client(self, client_name: str):
        """Calls the stored function "last_successful_entries"
        that returns 1 last successful entry for each setting_unique_id for a given client
        and stores the results in the cache"""

        """
        Query to create the stored function:

        create or replace function last_successful_entries (client_name text) returns table(setting_unique_id text, datetime timestamp with time zone)
        language sql
        AS $$
        select
        setting_unique_id, max(datetime) as datetime
        from (select * from
        log_entries
        where
        result like '%successfully%' and
        client_name = $1
        order by datetime desc
        ) as successful
        group by setting_unique_id;
        $$
        """

        results = self.supabase_client.rpc(
            "last_successful_entries", {"client_name": client_name}
        ).execute()

        self.cache = {row["setting_unique_id"]: row["datetime"] for row in results.data}

    @retry
    def get_last_successful_entry(self, setting: settings.Setting):
        """
        Retrieves the last successful log entry based on a given setting.

        Parameters:
            self (obj): The current instance of the class.
            setting (settings.Setting): The setting object to retrieve
                the last successful log entry for.

        Returns:
            datetime.datetime: The datetime of the last successful entry if found, None otherwise.
        """

        result = self.cache.get(setting.get_hash())
        if result:
            return datetime.datetime.fromisoformat(result)

    @retry
    def add_log_entry(self, client_name: str, setting: settings.Setting, result: str):
        # Save time by not writing `skipped` and `already sent`
        # into the database
        entry = {
            "client_name": client_name,
            "account": setting.account,
            "chat_id": setting.chat_id,
            "result": result,
            "setting_unique_id": setting.get_hash(),
        }

        if "skipped" not in result and "already sent" not in result:
            self.supabase_client.table("log_entries").insert(entry).execute()

        # Log errors as warnings for easier search in the log
        method = logger.warning if "error" in result.lower() else logger.info
        method(f"Logged {entry}", extra=entry)
