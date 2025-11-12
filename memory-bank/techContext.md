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

### Environment Loading
- **Pydantic Settings**: `AppSettings` loads from `.env` file using `SettingsConfigDict(env_file='.env', extra='allow')`
- **Dependency Injection**: API credentials passed directly to `tg` library constructors instead of relying on environment variables
- **Clean Architecture**: No runtime environment variable sourcing needed - all configuration handled through pydantic-settings
- **Updated tg Library**: Modified to accept `api_id` and `api_hash` parameters in `Account.__init__()` for proper dependency injection

### Google Service Account Configuration
```bash
# Preferred: path to Google service account JSON file
GOOGLE_SERVICE_ACCOUNT_FILE=google-service-account.json

# Legacy fallback: inline JSON string
# GOOGLE_SERVICE_ACCOUNT={"type":"service_account", ...}
```

Choose one of the Google authentication methods above. The file-based approach is preferred for security.

## Project Structure

```
sender/
├── .env                    # Environment configuration (API credentials, Supabase, etc.)
├── .env.template          # Template for environment setup
├── requirements.txt       # Python dependencies managed with uv
├── ruff.toml             # Code quality and formatting configuration
├── pyproject.toml        # Project metadata and build configuration
├── Dockerfile            # Container build configuration
├── deploy.sh             # Deployment script (runs only unit tests)
├── run.sh                # Application startup script
├── sender.logrotate      # Log rotation configuration
├── clients.yaml          # Client configuration file
├── google-service-account.json  # Google Sheets API credentials
├── memory-bank/          # Project documentation and context
├── src/                  # Source code
│   ├── cli.py            # Main orchestration entry point
│   ├── validate_accounts.py  # Account validation utility
│   ├── core/             # Core domain logic
│   │   ├── config.py     # Application configuration
│   │   ├── clients.py    # Google Sheets client management
│   │   └── settings.py   # Data models and validation
│   ├── messaging/        # Message processing
│   │   ├── sender.py     # Main sending orchestration
│   │   ├── telegram_sender.py  # Telegram-specific operations
│   │   └── error_handlers.py   # Error handling logic
│   ├── infrastructure/   # External service integrations
│   │   └── supabase_logs.py  # Supabase logging bridge
│   ├── monitoring/       # Alerting and monitoring
│   │   └── stats_publisher.py  # Statistics publishing
│   ├── scheduling/       # Cron and timing utilities
│   │   └── cron_utils.py # Cron parsing and validation
│   └── utils/            # Shared utilities
│       └── telegram_utils.py  # Telegram URL parsing
└── tests/                # Test suites
    ├── unit/             # Fast unit tests (94 tests, run in CI/CD)
    │   ├── test_cron.py
    │   ├── test_cron_utils.py
    │   ├── test_settings.py
    │   ├── test_slow_mode.py
    │   └── test_topic_support.py
    └── integration/      # Slow integration tests (1 test, requires real API)
        └── test_caption_forward.py
```

## Development Setup
- Install with `pip install -e .[dev]`
- Docker support with Dockerfile
- Cron job deployment scripts
- Supabase file system for session storage

## Testing Strategy

### Test Categories
- **Unit Tests** (94 tests): Fast, isolated tests without external dependencies
  - Run in CI/CD pipeline via `deploy.sh`
  - Execution time: ~0.14s
  - Coverage: Core logic, validation, utilities
- **Integration Tests** (1 test): Real API calls with external dependencies
  - Requires `.env` file with valid credentials
  - Tests actual Telegram message forwarding
  - Slower execution, may send real messages
  - Status: ✅ Functional and passing

### Test Commands
```bash
# Run unit tests only (used by deploy.sh)
pytest tests/unit/

# Run integration tests (requires .env)
pytest tests/integration/

# Run all tests
pytest tests/
```

### Deployment Testing
- `deploy.sh` runs only unit tests for fast, reliable deployment
- No external API calls during deployment
- Integration tests run separately when needed

## Deployment Features
- **Enhanced deploy.sh**: Comprehensive visual feedback with ANSI colors and section timing
- **Three-Phase Deployment**: Local Preparation → Package Deployment → Server Configuration
- **Clean Logging**: Suppressed verbose output from tar and logrotate operations
- **Docker Optimization**: Efficient layer caching with separated dependency installation
- **Progress Indicators**: Real-time feedback with emojis and colored status messages
- **Timing Information**: Individual section timing plus total deployment duration
- **Completion Summary**: Shows total time and exact completion timestamp

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


