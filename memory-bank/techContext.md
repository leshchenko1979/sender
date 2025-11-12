# Technical Context

## Technology Stack
- **Python 3.10+**: Core runtime
- **Telethon**: Telegram API client library
- **Supabase**: Database and file storage
- **Google Sheets API**: Configuration management
- **Cron**: Scheduling system

## Dependencies
- `telethon`: Telegram interactions
- `supabase`: Database operations
- `gspread`: Google Sheets integration
- `pydantic`, `pydantic-settings`: Data modelling and configuration loading
- `croniter`: Cron schedule parsing
- `icontract`, `reretry`, `more-itertools`, `tg` (custom account helpers)

## Environment Variables

### Required Variables
- `SUPABASE_URL`: Database connection
- `SUPABASE_KEY`: Database authentication
- `GOOGLE_SERVICE_ACCOUNT_FILE` **or** `GOOGLE_SERVICE_ACCOUNT`: Google credentials JSON

### Optional Variables
- `ALERT_ACCOUNT`: Telegram account used for alert reporting
- Telegram API credentials (`API_ID`, `API_HASH`) consumed by the shared `tg` dependency

### Google Service Account Configuration
```bash
# Preferred: path to Google service account JSON file
GOOGLE_SERVICE_ACCOUNT_FILE=google-service-account.json

# Legacy fallback: inline JSON string
# GOOGLE_SERVICE_ACCOUNT={"type":"service_account", ...}
```

Choose one of the Google authentication methods above. The file-based approach is preferred for security.

- `.env`: Environment configuration (loaded once inside `core.config`)
- `pyproject.toml`: Single source of dependencies and packaging metadata
- `src/cli.py`: Main orchestration entry point (`python -m src.cli`)
- `src/validate_accounts.py`: Session validation helper
- `src/core/`: Domain models (`settings.py`), Google client/controller (`clients.py`), configuration (`config.py`)
- `src/messaging/`: Orchestrator, sender, and slow-mode error handlers
- `src/infrastructure/`: Supabase logging bridge
- `src/monitoring/`: Alert publisher
- `src/scheduling/`: Cron utilities
- `src/utils/`: Telegram URL helpers
- `clients.yaml`: Client configuration
- `google-service-account.json`: Google credentials
- `memory-bank/`: Project documentation
- `tests/unit/`: Pytest suites with shared fixtures (`tests/conftest.py`)

## Development Setup
- Install with `pip install -e .[dev]`
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


