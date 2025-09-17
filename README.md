The whole app is a container run periodically that uses designated telegram user accounts to post designated messages to designated telegram groups acoording to a designated schedule.

# Classes
```mermaid
    classDiagram
        class Setting
        Setting: bool active
        Setting: string account
        Setting: string schedule
        Setting: string chat_id
        Setting: string text

        class LogEntry
        LogEntry: datetime datetime
        LogEntry: string Account
        LogEntry: chat_id
        LogEntry: string result
```

Settings are stored in a Google Sheets table.

Log entries are stored in a supabase table.

Schedules use cron notation.

Environment configuration (in `.env`):

```
# Preferred: path to Google service account JSON file
GOOGLE_SERVICE_ACCOUNT_FILE=google-service-account.json

# Legacy fallback: inline JSON string
# GOOGLE_SERVICE_ACCOUNT={"type":"service_account", ...}

API_ID=...
API_HASH=...
SUPABASE_URL=...
SUPABASE_KEY=...
```

# Functionality
```mermaid
mindmap
    ((Functionality))
        Load settings from Google Spreadsheets
        For each setting
            Check if active
            Check if needs to be sent
                Calculate most recent schedule mark
                Load the most recent log entry for this account and chat
                Check if this log entry after the calculated mark
            Send
                Check if account belongs to the designated group
                Join the group if needed
                Send the designated message
            Add results to log
        Alert of errors to a chat
```
