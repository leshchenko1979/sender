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
        search_window = 50  # Search 50 messages before and after to ensure we get all group messages
        grouped_messages = []

        try:
            # Search backwards from the target message
            async for msg in self.app.iter_messages(
                from_chat_id,
                offset_id=message_id,
                limit=search_window,
                reverse=True,  # Search backwards (older messages first)
            ):
                if hasattr(msg, "grouped_id") and msg.grouped_id == grouped_id:
                    grouped_messages.append(msg.id)

            # Search forwards from the target message (excluding the target message itself)
            async for msg in self.app.iter_messages(
                from_chat_id,
                offset_id=message_id,
                limit=search_window,
            ):
                if (
                    hasattr(msg, "grouped_id")
                    and msg.grouped_id == grouped_id
                    and msg.id != message_id
                ):  # Don't duplicate the target message
                    grouped_messages.append(msg.id)

            # Remove duplicates and sort to maintain chronological order
            grouped_messages = sorted(list(set(grouped_messages)))

        except ValueError:
            # If search fails, return empty list
            pass

        return grouped_messages

    async def _find_preceding_text_message(self, from_chat_id, first_media_message_id):
        """Find a text message immediately preceding a media group that might be related."""
        try:
            # Look for messages immediately before the first media message
            async for msg in self.app.iter_messages(
                from_chat_id,
                offset_id=first_media_message_id,
                limit=5,  # Check up to 5 messages before
                reverse=True,  # Search backwards (older messages first)
            ):
                # Skip messages that are part of the same media group
                if hasattr(msg, "grouped_id") and msg.grouped_id is not None:
                    continue

                # Check if this is a text message (has text but no media)
                if (
                    hasattr(msg, "text")
                    and msg.text
                    and not hasattr(msg, "media")
                    or msg.media is None
                ):
                    # Only include if it's reasonably close (within 10 message IDs)
                    if first_media_message_id - msg.id <= 10:
                        return msg.id

                # Stop searching if we find a message that's too old or has media
                # This prevents including unrelated text messages
                if first_media_message_id - msg.id > 10:
                    break

        except ValueError:
            # If search fails, return None
            pass

        return None

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
                # If no other grouped messages found, just forward the single message
                # This handles cases where the media group might be incomplete or single-item
                message_ids = [message_id]
            else:
                message_ids = sorted(grouped_messages)

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
