import supabase

import settings

from logging import getLogger
logger = getLogger(__name__)

class SupabaseLogHandler:
    def __init__(self, supabase_client: supabase.Client):
        self.supabase_client = supabase_client

    def get_last_successful_entry(self, setting: settings.Setting):
        # Query for most recent log entry
        result = (
            self.supabase_client.table("log_entries")
            .select("datetime")
            .eq("setting_unique_id", setting.get_hash())
            .like("result", "%successfully%")
            .order("datetime", desc=True)
            .limit(1)
            .execute()
        )

        return result.data[0] if result.data else None

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
