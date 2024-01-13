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
