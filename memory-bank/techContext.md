# Technical Context

## Technology Stack
- **Python 3.x**: Core runtime
- **Telethon**: Telegram API client library
- **Supabase**: Database and file storage
- **Google Sheets API**: Configuration management
- **Cron**: Scheduling system

## Dependencies
- `telethon`: Telegram API interactions
- `supabase`: Database operations
- `gspread`: Google Sheets integration
- `pydantic`: Data validation
- `croniter`: Cron schedule parsing
- `python-dotenv`: Environment variable management

## Environment Variables
- `SUPABASE_URL`: Database connection
- `SUPABASE_KEY`: Database authentication
- `GOOGLE_SERVICE_ACCOUNT_FILE`: Google Sheets credentials (file path)
- `GOOGLE_SERVICE_ACCOUNT`: Google Sheets credentials (JSON string)

## File Structure
- `sender.py`: Main application logic
- `clients.py`: Client and Google Sheets integration
- `settings.py`: Setting model and cron utilities
- `clients.yaml`: Client configuration
- `google-service-account.json`: Google credentials
- `memory-bank/`: Project documentation

## Development Setup
- Uses virtual environment
- Docker support with Dockerfile
- Cron job deployment scripts
- Supabase file system for session storage

## Logging and Monitoring
- **Primary Log Location**: `/var/log/sender.log` (VDS)
- **Log Rotation**: Daily rotation with 30-day retention
  - Configuration: `/etc/logrotate.d/sender`
  - Compressed old logs
  - Automatic cleanup
- **Log Content**: 
  - Start/finish timestamps for each run
  - Full application stdout/stderr from Docker containers with timestamps
  - Error messages and warnings with timestamps
  - Message processing results with timestamps
- **Historical Logs**: Available in rotated files (`/var/log/sender.log.1.gz`, etc.)
- **Application Logs**: Also logged to Supabase for message outcomes

## Key Technical Decisions
- **Session Management**: Uses Supabase file system for Telegram sessions
- **Error Handling**: Comprehensive exception handling with specific error messages
- **Schedule Management**: Moscow timezone for all cron operations
- **Media Handling**: Special logic for grouped media messages
- **Auto-Join**: Proactive chat joining to reduce permission errors


