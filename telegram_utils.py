import logging

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
                pass

        if entity and hasattr(entity, "username") and entity.username:
            # Public chat with username
            clean_username = entity.username.lstrip("@")
            if topic_id:
                return f"https://t.me/{clean_username}/{topic_id}/{message_id}"
            else:
                return f"https://t.me/{clean_username}/{message_id}"
        else:
            # Private chat - use numeric ID
            channel_id = _normalize_channel_id(str(chat_id))
            if topic_id:
                return f"https://t.me/c/{channel_id}/{topic_id}/{message_id}"
            else:
                return f"https://t.me/c/{channel_id}/{message_id}"
    except Exception as e:
        logger.warning(f"Failed to generate message link: {e}")
        return None
