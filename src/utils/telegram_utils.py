import logging
import re

logger = logging.getLogger(__name__)


def parse_chat_and_topic(chat_id: str) -> tuple[str, int | None]:
    """
    Parse chat_id which may contain topic in format: chat_id/topic_id

    Examples:
        "@mychannel/123" -> ("@mychannel", 123)
        "-1001234567890/456" -> ("-1001234567890", 456)
        "1826486256/7832" -> ("-1001826486256", 7832)  # Auto-converts to supergroup format
        "@mychannel" -> ("@mychannel", None)

    Returns:
        Tuple of (chat_id, topic_id or None)
    """
    if "/" in chat_id:
        parts = chat_id.rsplit("/", 1)
        try:
            topic_id = int(parts[1])
            chat_part = parts[0]

            # Auto-convert numeric chat IDs to supergroup format if needed
            if chat_part.isdigit() and not chat_part.startswith("-100"):
                # Convert to supergroup format: add -100 prefix
                chat_part = f"-100{chat_part}"

            return chat_part, topic_id
        except ValueError:
            # Not a valid topic number, treat whole string as chat_id
            return chat_id, None
    return chat_id, None


def _normalize_channel_id(channel_id: str) -> str:
    """Normalize channel ID by removing -100 prefix for private channels."""
    return channel_id[4:] if channel_id.startswith("-100") else channel_id


def _build_query_string(
    thread_id: int | None = None,
    comment_id: int | None = None,
) -> str:
    """Build query string for Telegram links."""
    query_params = []
    if thread_id:
        query_params.append(f"thread={thread_id}")

    query_string = "&".join(query_params)
    return "?" + query_string if query_string else ""


async def _generate_message_link(
    chat_id: str,
    message_id: int,
    topic_id: int | None = None,
    account_app=None,
) -> str | None:
    """
    Generate Telegram message link.

    Returns link string or None if cannot generate.
    """
    try:
        # Try to resolve entity to get username
        entity = None
        if account_app:
            try:
                entity = await account_app.get_entity(chat_id)
            except Exception:
                logger.warning(f"Failed to resolve entity for chat_id {chat_id}")
                return None

        if not entity:
            logger.warning(f"Could not resolve entity for chat_id {chat_id}")
            return None

        # Check if it's a channel/supergroup without username (private)
        is_private_channel = (
            hasattr(entity, "megagroup")
            or hasattr(entity, "broadcast")
            or (hasattr(entity, "id") and str(entity.id).startswith("-100"))
        ) and not (hasattr(entity, "username") and entity.username)

        if hasattr(entity, "username") and entity.username and not is_private_channel:
            # Public chat with username
            clean_username = entity.username.lstrip("@")
            if topic_id:
                return f"https://t.me/{clean_username}/{topic_id}/{message_id}"
            else:
                return f"https://t.me/{clean_username}/{message_id}"
        else:
            # Private chat - use numeric ID
            if hasattr(entity, "id") and entity.id is not None:
                channel_id = _normalize_channel_id(str(entity.id))
                if topic_id:
                    return f"https://t.me/c/{channel_id}/{topic_id}/{message_id}"
                else:
                    return f"https://t.me/c/{channel_id}/{message_id}"
            else:
                logger.warning(f"Entity has no ID for private chat: {entity}")
                return None
    except Exception as e:
        logger.warning(f"Failed to generate message link: {e}")
        return None


async def _parse_message_link(link: str) -> tuple[str | None, int | None, int | None]:
    """
    Parse a Telegram message link to extract chat identifier, message ID, and topic ID.

    Supports formats:
    - https://t.me/username/message_id
    - https://t.me/username/topic_id/message_id
    - https://t.me/c/channel_id/message_id
    - https://t.me/c/channel_id/topic_id/message_id

    Returns:
        Tuple of (chat_identifier, message_id, topic_id) where:
        - chat_identifier: username (with @) or numeric chat ID
        - message_id: the message ID
        - topic_id: topic ID if present, None otherwise
        Returns (None, None, None) if parsing fails
    """
    if not link or not isinstance(link, str):
        return None, None, None

    # Remove protocol and www if present
    link = link.replace("https://", "").replace("http://", "").replace("www.", "")

    # Match different link patterns
    patterns = [
        # Private chat with topic: t.me/c/channel_id/topic_id/message_id
        r"t\.me/c/(\d+)/(\d+)/(\d+)",  # c/channel_id/topic_id/message_id
        # Private chat no topic: t.me/c/channel_id/message_id
        r"t\.me/c/(\d+)/(\d+)",  # c/channel_id/message_id
        # Public chat with topic: t.me/username/topic_id/message_id
        r"t\.me/([a-zA-Z0-9_]+)/(\d+)/(\d+)",  # username/topic_id/message_id
        # Public chat no topic: t.me/username/message_id
        r"t\.me/([a-zA-Z0-9_]+)/(\d+)",  # username/message_id
    ]

    for pattern in patterns:
        match = re.match(pattern, link)
        if match:
            groups = match.groups()
            if len(groups) == 3:
                # Has topic_id: c/channel_id/topic_id/message_id or username/topic_id/message_id
                if "c/" in link:
                    # Private chat: c/channel_id/topic_id/message_id
                    channel_id, topic_id, message_id = groups
                    return f"-100{channel_id}", int(message_id), int(topic_id)
                else:
                    # Public chat: username/topic_id/message_id
                    username, topic_id, message_id = groups
                    return f"@{username}", int(message_id), int(topic_id)
            elif len(groups) == 2:
                # No topic_id: c/channel_id/message_id or username/message_id
                if "c/" in link:
                    # Private chat: c/channel_id/message_id
                    channel_id, message_id = groups
                    return f"-100{channel_id}", int(message_id), None
                else:
                    # Public chat: username/message_id
                    username, message_id = groups
                    return f"@{username}", int(message_id), None

    return None, None, None


async def _check_message_exists(link: str, account_app=None) -> bool:
    """
    Check if a Telegram message exists by parsing its link and querying the API.

    Args:
        link: Telegram message link (https://t.me/...)
        account_app: Telegram account app instance for API calls

    Returns:
        True if message exists and is accessible, False if deleted or doesn't exist
    """
    if not link or not account_app:
        return False

    try:
        chat_id, message_id, topic_id = await _parse_message_link(link)
        if not chat_id or not message_id:
            logger.warning(f"Could not parse message link: {link}")
            return False

        # Try to get the message
        messages = await account_app.get_messages(entity=chat_id, ids=[message_id])

        # Check if we got a valid response
        if not messages:
            # No response means we likely don't have access to the chat (banned, etc.)
            logger.warning(
                f"Failed to get messages for link {link} - no access to chat"
            )
            return False

        # get_messages returns a list with None values for non-existent/deleted messages
        # So we check if the first (and only) element is not None
        return len(messages) > 0 and messages[0] is not None

    except Exception as e:
        logger.warning(f"Error checking message existence for link {link}: {e}")
        # If we can't check (e.g., banned from chat, no access), assume message doesn't exist
        # This will cause the setting to be disabled, which is appropriate since we can't access the chat
        return False
