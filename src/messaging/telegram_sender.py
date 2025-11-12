import re

from telethon.errors import RPCError
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import (
    ForwardMessagesRequest,
    GetHistoryRequest,
    ImportChatInviteRequest,
)
from tg.account import Account


# Telegram API constants
MEDIA_GROUP_MAX_SIZE = 10  # Maximum messages in a Telegram media group

# Global album-level cache: (chat_id, grouped_id) -> sorted message IDs
_GROUPED_MESSAGES_CACHE: dict[tuple[int, int], list[int]] = {}


class SenderAccount(Account):
    """Defines methods for sending and forwarding messages
    with forced joining the group if the peer is not in the chat yet."""

    async def _get_grouped_message_ids(self, from_chat_id, message_id, grouped_id):
        """Retrieve all message IDs in a media group around the given message.

        Media groups contain max MEDIA_GROUP_MAX_SIZE messages. Uses a centered window
        approach with album-level caching for optimal performance.
        """
        # Check cache first (album-level caching)
        cache_key = (from_chat_id, grouped_id)
        cached_messages = _GROUPED_MESSAGES_CACHE.get(cache_key)
        if cached_messages is not None:
            # Ensure target message is included (defensive programming)
            if message_id not in cached_messages:
                cached_messages = sorted(cached_messages + [message_id])
            return cached_messages

        try:
            # Get a centered window of messages around the target message
            # Start half the window size back to ensure we capture the full group
            history_request = GetHistoryRequest(
                peer=from_chat_id,
                offset_id=message_id,
                offset_date=None,
                add_offset=-MEDIA_GROUP_MAX_SIZE,
                limit=MEDIA_GROUP_MAX_SIZE * 2,
                max_id=0,
                min_id=0,
                hash=0,
            )

            result = await self.app(history_request)

            # Extract messages with matching grouped_id using list comprehension
            grouped_messages = [
                msg.id
                for msg in result.messages
                if hasattr(msg, "grouped_id") and msg.grouped_id == grouped_id
            ]

            # Ensure target message is included and sort chronologically
            if message_id not in grouped_messages:
                grouped_messages.append(message_id)

            grouped_messages = sorted(grouped_messages)

        except Exception:
            # Fallback: return just the target message if search fails
            grouped_messages = [message_id]

        # Cache the result (simple dict - no size limit for now)
        _GROUPED_MESSAGES_CACHE[cache_key] = grouped_messages

        return grouped_messages

    async def _forward_grouped_or_single(
        self, chat_id, from_chat_id, message_id, reply_to_msg_id=None
    ):
        """Forward a message or entire media group if the message is part of one."""
        source_message = await self.app.get_messages(from_chat_id, ids=message_id)
        if not source_message:
            raise ValueError("Не удалось получить исходное сообщение")

        # Determine messages to forward
        if (
            hasattr(source_message, "grouped_id")
            and source_message.grouped_id is not None
        ):
            grouped_messages = await self._get_grouped_message_ids(
                from_chat_id, message_id, source_message.grouped_id
            )
            # Always include the original message_id in case it wasn't found in the search
            message_ids = sorted(list(set(grouped_messages + [message_id])))

            # For media groups, captions are attached to the media messages themselves,
            # so we don't need to look for separate preceding text messages
        else:
            message_ids = [message_id]

        # Forward messages using MTProto ForwardMessagesRequest (supports both regular and forum topics)
        return await self.app(
            ForwardMessagesRequest(
                from_peer=from_chat_id,
                id=message_ids,
                to_peer=chat_id,
                top_msg_id=reply_to_msg_id,  # None for regular forwarding, topic ID for forum topics
                drop_author=True,
            )
        )

    async def _join_chat(self, chat_id):
        try:
            # If chat_id is an invite link, try importing invite first
            invite_hash = self._extract_invite_hash(str(chat_id))
            if invite_hash:
                try:
                    await self.app(ImportChatInviteRequest(invite_hash))
                    return
                except RPCError:
                    # fall back to channel join attempt below
                    pass

            # For public channels/supergroups this will work with username or id
            await self.app(JoinChannelRequest(chat_id))
        except RPCError:
            # Silently ignore join failures; send/forward will raise clearer error
            pass

    def _extract_invite_hash(self, text: str):
        # Supports t.me/joinchat/<hash> and t.me/+<hash>
        m = re.search(r"t\.me/(?:joinchat/|\+)([A-Za-z0-9_-]{16,})", text)
        return m.group(1) if m else None
