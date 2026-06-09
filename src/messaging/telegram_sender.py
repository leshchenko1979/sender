"""Replaces Telegram Telethon calls with HTTP calls to fast-mcp-telegram MTProto bridge.

Previously used Telethon + tg.account.Account for all Telegram operations.
Now uses telegram_bridge module (HTTP POST to fast-mcp-telegram).
Each client provides its own Bearer token for the bridge.
"""

from __future__ import annotations

import re

import telegram_bridge as bridge

# Telegram API constants
MEDIA_GROUP_MAX_SIZE = 10  # Maximum messages in a Telegram media group

# Global album-level cache: (chat_id_or_username, grouped_id) -> sorted message IDs
_GROUPED_MESSAGES_CACHE: dict[tuple[int | str, int], list[int]] = {}


class SenderAccount:
    """Thin wrapper around telegram_bridge for sending/forwarding messages.

    Instead of a Telethon Account, this holds a per-client Bearer token
    passed to every bridge call.
    """

    def __init__(self, bearer_token: str | None = None, *_args, **_kwargs):
        """Construct with an optional per-client bearer token.

        If None, falls back to FAST_MCP_BEARER env var in the bridge module.
        """
        self._bearer_token = bearer_token

    def _get_grouped_message_ids(
        self,
        from_chat_id: int | str,
        message_id: int,
        grouped_id: int,
    ) -> list[int]:
        cache_key = (from_chat_id, grouped_id)
        cached = _GROUPED_MESSAGES_CACHE.get(cache_key)
        if cached is not None:
            return sorted(set(cached + [message_id]))

        try:
            result = bridge.get_history(
                peer=from_chat_id,
                offset_id=message_id,
                add_offset=-MEDIA_GROUP_MAX_SIZE,
                limit=MEDIA_GROUP_MAX_SIZE * 2,
                bearer_token=self._bearer_token,
            )
            messages = result.get("messages", [])
            grouped = [m["id"] for m in messages if m.get("grouped_id") == grouped_id]
            if message_id not in grouped:
                grouped.append(message_id)
            grouped = sorted(grouped)
        except Exception:
            grouped = [message_id]

        _GROUPED_MESSAGES_CACHE[cache_key] = grouped
        return grouped

    def _forward_grouped_or_single(
        self,
        chat_id: int | str,
        from_chat_id: int | str,
        message_id: int,
        reply_to_msg_id: int | None = None,
    ) -> dict:
        source = bridge.get_messages(
            from_chat_id, [message_id], bearer_token=self._bearer_token
        )
        msgs = source.get("messages", [])
        if not msgs:
            raise ValueError("Не удалось получить исходное сообщение")

        source_msg = msgs[0]
        grouped_id = source_msg.get("grouped_id")

        if grouped_id is not None:
            grouped_ids = self._get_grouped_message_ids(
                from_chat_id, message_id, grouped_id
            )
            message_ids = sorted(set(grouped_ids + [message_id]))
        else:
            message_ids = [message_id]

        return bridge.forward_messages(
            from_peer=from_chat_id,
            to_peer=chat_id,
            message_ids=message_ids,
            top_msg_id=reply_to_msg_id,
            drop_author=True,
            bearer_token=self._bearer_token,
        )

    def _join_chat(self, chat_id: int | str) -> None:
        try:
            if invite_hash := self._extract_invite_hash(str(chat_id)):
                try:
                    bridge.import_chat_invite(
                        invite_hash, bearer_token=self._bearer_token
                    )
                    return
                except bridge.MtProtoError:
                    pass
            bridge.join_channel(str(chat_id), bearer_token=self._bearer_token)
        except bridge.MtProtoError:
            pass

    @staticmethod
    def _extract_invite_hash(text: str) -> str | None:
        m = re.search(r"t\.me/(?:joinchat/|\+)([A-Za-z0-9_-]{16,})", text)
        return m[1] if m else None
