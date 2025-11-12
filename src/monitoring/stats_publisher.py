import logging
from typing import Optional

from ..core.config import AppSettings
from ..messaging.telegram_sender import SenderAccount

logger = logging.getLogger(__name__)

ALERT_HEADING = "Результаты последней рассылки:"


class AlertManager:
    """Manages alert account authentication and publishing."""

    def __init__(self, fs, app_settings: Optional[AppSettings] = None):
        self.fs = fs
        self.app_settings = app_settings

    def create_alert_account(self, phone: str):
        """Create an alert account with proper credentials."""
        if not self.app_settings:
            raise ValueError("AppSettings required for alert account creation")

        return SenderAccount(
            fs=self.fs,
            phone=phone,
            api_id=self.app_settings.api_id,
            api_hash=self.app_settings.api_hash,
        )

    async def send_alert(self, alert_account, chat_id: str, message: str):
        """Send an alert message using the provided account."""
        async with alert_account.session(revalidate=True):
            app = alert_account.app
            await app.send_message(chat_id, message)

    async def delete_last_alert(self, alert_account, chat_id: str):
        """Delete the last alert message if it exists."""
        async with alert_account.session(revalidate=True):
            app = alert_account.app
            msgs = await app.get_messages(chat_id, limit=1)
            if msgs:
                last_msg = msgs[0]
                if (
                    getattr(last_msg, "message", None)
                    and ALERT_HEADING in last_msg.message
                ):
                    await app.delete_messages(chat_id, [last_msg.id])


async def publish_stats(
    errors: dict,
    fs,
    client,
    processed_count: int,
    successful_count: int,
    app_settings=None,
):
    """Publish statistics and alerts for a client."""
    logger.info(
        f"publish_stats called for client {client.name}, alert_account: {repr(client.alert_account)}"
    )

    # Use AlertManager for proper separation of concerns
    alert_manager = AlertManager(fs, app_settings)
    alert_account = alert_manager.create_alert_account(client.alert_account)

    # Delete last alert message if it exists
    await alert_manager.delete_last_alert(alert_account, client.alert_chat)

    # Build alert message
    text = f"{ALERT_HEADING}\n\n"

    # If there are critical errors (like authorization failure), show only them
    if "" in errors:
        text += f"❌ {errors['']}\n\n"
        text += f"Подробности в файле настроек: {client.spreadsheet_url}."
    else:
        # Добавляем статистику обработанных и успешных отправок
        if processed_count > 0:
            text += f"Наступило время для: {processed_count} рассылок\n"
            text += f"Успешных отправок: {successful_count} из {processed_count}\n\n"
        else:
            text += "Наступило время для: 0 рассылок\n\n"

        # Calculate error stats from client.settings:
        # turned off with errors, active with errors
        turned_off_with_errors = len(
            [s for s in client.settings if not s.active and s.error]
        )
        turned_off_no_errors = len(
            [s for s in client.settings if not s.active and not s.error]
        )

        if turned_off_with_errors:
            text += (
                f"{turned_off_with_errors} рассылок отключены из-за ошибок. "
                "Исправьте и включите заново.\n\n"
            )

        if turned_off_no_errors:
            text += (
                f"{turned_off_no_errors} отключенных рассылок без ошибок. "
                "Почему отключены?\n\n"
            )

        text += (
            f"{len([s for s in client.settings if s.active])} "
            f"(из {len(client.settings)} всего) активных рассылок.\n\n"
            f"Подробности в файле настроек: {client.spreadsheet_url}."
        )

    # Send alert message
    await alert_manager.send_alert(alert_account, client.alert_chat, text)

    if errors:
        logger.warning("Alert message sent", extra={"errors": errors})
    else:
        logger.info("Alert message sent with success statistics")
