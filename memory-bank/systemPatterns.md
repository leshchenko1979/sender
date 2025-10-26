# System Patterns

## Architecture Overview
The system follows a client-settings pattern where:
- **Clients** contain multiple **Settings**
- Each **Setting** defines a message/forwarding task with schedule
- **Accounts** handle the actual Telegram operations

## Key Design Patterns

### Auto-Join Pattern
```python
async def send_message(self, chat_id, text, reply_to_msg_id=None):
    try:
        return await self.app.send_message(chat_id, text, reply_to=reply_to_msg_id)
    except ChatWriteForbiddenError:
        await self._join_chat(chat_id)  # Auto-join on permission error
        return await self.app.send_message(chat_id, text, reply_to=reply_to_msg_id)
```

### Media Group Handling
- Detects grouped messages by `grouped_id` attribute
- Forwards entire media groups together
- Searches for related messages in a 20-message window
- **URL Query Parameter Support**: Strips query parameters (like `?single`) before URL parsing to ensure media groups are properly detected and forwarded

### Error Recovery
- **Slow Mode**: Auto-adjusts cron schedules for all settings in the same chat
- **Permission Errors**: Attempts to join chat and retry
- **Media Errors**: Handles incomplete media groups gracefully

### Configuration Flow
1. Load clients from `clients.yaml`
2. Each client loads settings from Google Sheets
3. Process only active settings
4. Update Google Sheets with results/errors

## Critical Implementation Paths

### Message Processing Flow
1. Parse chat_id and optional topic_id
2. **Clean URL by stripping query parameters** (handles `?single` and other params)
3. Determine if forwarding or sending text
4. Join destination chat proactively
5. Execute send/forward operation
6. Handle errors with appropriate recovery

### Schedule Management
- Uses croniter for schedule checking
- Moscow timezone for schedule calculations
- Auto-adjustment for slow mode violations
- 20% buffer added to required intervals


