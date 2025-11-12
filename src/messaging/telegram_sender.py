import re

from telethon.errors import RPCError
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import (
    ForwardMessagesRequest,
    ImportChatInviteRequest,
)
from tg.account import Account


class SenderAccount(Account):
    """Defines methods for sending and forwarding messages
    with forced joining the group if the peer is not in the chat yet."""

    async def _get_grouped_message_ids(self, from_chat_id, message_id, grouped_id):
        """Retrieve all message IDs in a media group around the given message."""
        search_window = 20  # Search 20 messages before and after
        offsets_to_try = [message_id + search_window, message_id]

        for offset_id in offsets_to_try:
            grouped_messages = []
            try:
                async for msg in self.app.iter_messages(
                    from_chat_id,
                    offset_id=offset_id,
                    limit=search_window * 2,
                ):
                    if hasattr(msg, "grouped_id") and msg.grouped_id == grouped_id:
                        grouped_messages.append(msg.id)

                if grouped_messages:
                    return grouped_messages
            except ValueError:
                # Try next offset if this one fails
                continue

        return []

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
            if not grouped_messages:
                raise ValueError("Медиагруппа неполная или недоступна")
            message_ids = sorted(grouped_messages)
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
