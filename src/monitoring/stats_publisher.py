import logging

from ..messaging.telegram_sender import SenderAccount

logger = logging.getLogger(__name__)

ALERT_HEADING = "Результаты последней рассылки:"


async def publish_stats(
    errors: dict,
    fs,
    client,
    processed_count: int,
    successful_count: int,
    app_settings=None,
):
    alert_acc = SenderAccount(
        fs,
        client.alert_account,
        app_settings.api_id if app_settings else None,
        app_settings.api_hash if app_settings else None,
    )

    async with alert_acc.session(revalidate=False):
        app = alert_acc.app

        # Delete last message if it contains alert heading
        msgs = await app.get_messages(client.alert_chat, limit=1)
        if msgs:
            last_msg = msgs[0]
            if getattr(last_msg, "message", None) and ALERT_HEADING in last_msg.message:
                await app.delete_messages(client.alert_chat, [last_msg.id])

        text = f"{ALERT_HEADING}\n\n"

        # If there are critical errors (like authorization failure), show only them
        if "" in errors:
            text += f"❌ {errors['']}\n\n"
            text += f"Подробности в файле настроек: {client.spreadsheet_url}."
        else:
            # Добавляем статистику обработанных и успешных отправок
            if processed_count > 0:
                text += f"Наступило время для: {processed_count} рассылок\n"
                text += (
                    f"Успешных отправок: {successful_count} из {processed_count}\n\n"
                )
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

        await app.send_message(client.alert_chat, text)

        if errors:
            logger.warning("Alert message sent", extra={"errors": errors})
        else:
            logger.info("Alert message sent with success statistics")
