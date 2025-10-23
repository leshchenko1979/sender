The whole app is a container run periodically that uses designated telegram user accounts to post designated messages to designated telegram groups according to a designated schedule.

## Forum Topic Support

The system now supports sending messages to specific topics within Telegram forum groups. Use the format `chat_id/topic_id` in the `chat_id` field of your settings:

- **Format**: `chat_id/topic_id`
- **Examples**: 
  - `@mychannel/123` - Send to topic 123 in @mychannel
  - `-1001234567890/456` - Send to topic 456 in group -1001234567890
- **Backwards Compatible**: Regular chat IDs without `/` continue to work as before
- **Topic ID**: The topic ID is the message ID of the first message in the forum topic thread

### How to Get Topic ID

1. Open the forum topic in Telegram
2. Right-click on any message in the topic and select "Copy message link"
3. The link format is: `https://t.me/c/CHAT_ID/TOPIC_ID/MESSAGE_ID`
4. The `TOPIC_ID` is the number you need for the `chat_id/topic_id` format

### Examples

- Regular chat: `@mychannel` or `-1001234567890`
- Forum topic: `@mychannel/123` or `-1001234567890/456`

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
