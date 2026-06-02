"""Publish run statistics and alerts via the fast-mcp-telegram bridge.

Uses per-client bearer token from client config.
"""

from __future__ import annotations

import logging

import telegram_bridge as bridge

logger = logging.getLogger(__name__)

ALERT_HEADING = "Результаты последней рассылки:"


class AlertManager:
    """Manages alert sending via the bridge."""

    def __init__(self, bearer_token: str | None = None):
        self._bearer_token = bearer_token

    def send_alert(self, chat_id: str, message: str) -> None:
        bridge.send_message(peer=chat_id, text=message, bearer_token=self._bearer_token)

    def delete_last_alert(self, chat_id: str) -> None:
        try:
            result = bridge.get_history(
                peer=chat_id, limit=1, bearer_token=self._bearer_token
            )
            messages = result.get("messages", [])
            if messages:
                last_msg = messages[0]
                msg_text = last_msg.get("message", "")
                last_id = last_msg.get("id")
                if last_id and ALERT_HEADING in msg_text:
                    bridge.delete_messages(
                        peer=chat_id, ids=[last_id], bearer_token=self._bearer_token
                    )
        except bridge.MtProtoError:
            pass


def publish_stats(
    errors: dict,
    fs,
    client,
    processed_count: int,
    successful_count: int,
    app_settings=None,
) -> None:
    """Publish statistics and alerts for a client."""
    logger.info(
        f"publish_stats called for client {client.name}, alert_chat: {repr(client.alert_chat)}"
    )

    token = client.fast_mcp_bearer if hasattr(client, "fast_mcp_bearer") else None
    alert_manager = AlertManager(bearer_token=token)
    alert_manager.delete_last_alert(client.alert_chat)

    text = f"{ALERT_HEADING}\n\n"

    if "" in errors:
        text += f"❌ {errors['']}\n\n"
        text += f"Подробности в файле настроек: {client.spreadsheet_url}."
    else:
        if processed_count > 0:
            text += f"Наступило время для: {processed_count} рассылок\n"
            text += f"Успешных отправок: {successful_count} из {processed_count}\n\n"
        else:
            text += "Наступило время для: 0 рассылок\n\n"

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

    alert_manager.send_alert(client.alert_chat, text)

    if errors:
        logger.warning("Alert message sent", extra={"errors": errors})
    else:
        logger.info("Alert message sent with success statistics")
