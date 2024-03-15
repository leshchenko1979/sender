import supabase

import settings

from logging import getLogger
logger = getLogger(__name__)

class SupabaseLogHandler:
    def __init__(self, supabase_client: supabase.Client):
        self.supabase_client = supabase_client

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

        results = (
            self.supabase_client.rpc("last_successful_entries", {"client_name": client_name})
            .execute()
        )

        self.cache = {row["setting_unique_id"]: row["datetime"] for row in results["data"]}


    def get_last_successful_entry(self, setting: settings.Setting):
        return self.cache.get(setting.get_hash())

    def add_log_entry(self, client_name: str, setting: settings.Setting, result: str):
        # Save time by not writing `skipped` and `already sent`
        #into the database
        if "skipped" not in result and "already sent" not in result:
            entry = {
                "client_name": client_name,
                "account": setting.account,
                "chat_id": setting.chat_id,
                "result": result,
                "setting_unique_id": setting.get_hash(),
            }

            self.supabase_client.table("log_entries").insert(entry).execute()

        # Log errors as warnings for easier search in the log
        method = logger.warning if "error" in result.lower() else logger.info
        method(f"Logged {entry}", extra=entry)
