"""Logging configuration for the Telegram sender application."""

import logging
import sys
from urllib.error import URLError
from urllib.request import Request, urlopen

import logfire

from ..core.config import AppSettings


class TelegramLoggingHandler(logging.Handler):
    """Custom logging handler that sends messages to Telegram."""

    def __init__(self, bot_token: str, chat_id: str):
        super().__init__()
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.setLevel(logging.WARNING)  # Only log warnings and above
        self.setFormatter(
            logging.Formatter(
                "🚨 %(levelname)s from %(name)s\n%(asctime)s\n%(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )

    def emit(self, record: logging.LogRecord) -> None:
        """Send log message to Telegram."""
        # Only process messages at WARNING level or higher
        if record.levelno < logging.WARNING:
            return

        try:
            message = self.format(record)
            self._send_to_telegram(message)
        except Exception as e:
            # Don't let logging errors crash the application
            print(f"Failed to send log to Telegram: {e}", file=sys.stderr)

    def _send_to_telegram(self, message: str) -> None:
        """Send message to Telegram bot API using urllib."""
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        data = {
            "chat_id": self.chat_id,
            "text": message[:4096],  # Telegram message limit
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }

        # Convert data to URL-encoded bytes
        import urllib.parse

        data_bytes = urllib.parse.urlencode(data).encode("utf-8")

        # Create request with timeout
        req = Request(url, data=data_bytes, method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")

        try:
            with urlopen(req, timeout=10) as response:
                if response.status != 200:
                    raise URLError(f"HTTP {response.status}: {response.reason}")
        except URLError as e:
            raise URLError(f"Failed to send Telegram message: {e}")


def setup_logging(app_settings: AppSettings) -> None:
    """Set up all logging configuration including standard logging, Logfire, and Telegram."""
    # Configure Logfire if available (handles both console and remote logging)
    if not app_settings.testing and app_settings.logfire_token:
        try:
            # Configure Logfire with console output enabled and token
            logfire.configure(token=app_settings.logfire_token, console=True)

            # Install auto-tracing for application modules
            logfire.install_auto_tracing(
                modules=["src"],
                min_duration=0.01,
                check_imported_modules="warn",  # Allow tracing of already imported modules
            )

            logger.info("Logfire monitoring configured successfully")
        except Exception as e:
            logger.warning(f"Failed to configure Logfire: {e}")
            # Fall back to standard logging if Logfire fails
            logging.basicConfig(
                level=logging.INFO,
                format="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
                handlers=[logging.StreamHandler(stream=sys.stdout)],
                force=True,
            )
    else:
        # Standard logging configuration when Logfire is not available
        logging.basicConfig(
            level=logging.INFO,
            format="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            handlers=[logging.StreamHandler(stream=sys.stdout)],
            force=True,
        )

    # Set third-party library log levels to reduce noise
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("telethon").setLevel(logging.WARNING)

    # Configure Telegram logging handler for warnings and above
    if app_settings.telegram_bot_token and app_settings.telegram_chat_id:
        try:
            telegram_handler = TelegramLoggingHandler(
                app_settings.telegram_bot_token, app_settings.telegram_chat_id
            )
            logging.getLogger().addHandler(telegram_handler)
            logger.info("Telegram logging handler configured successfully")
        except Exception as e:
            logger.warning(f"Failed to configure Telegram logging handler: {e}")
    elif app_settings.telegram_bot_token or app_settings.telegram_chat_id:
        logger.info(
            "Telegram logging partially configured - both TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set"
        )
    else:
        logger.info(
            "Telegram logging not configured - set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID to enable"
        )


# Initialize logger (logging config will be set up in setup_logging function)
logger = logging.getLogger(__name__)
