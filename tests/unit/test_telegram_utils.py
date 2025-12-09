import pytest
from unittest.mock import AsyncMock, MagicMock

from src.utils.telegram_utils import _parse_message_link, _check_message_exists


class TestParseMessageLink:
    """Test cases for _parse_message_link function."""

    @pytest.mark.asyncio
    async def test_parse_public_chat_no_topic(self):
        """Test parsing public chat link without topic."""
        link = "https://t.me/username/123"
        result = await _parse_message_link(link)
        assert result == ("@username", 123, None)

    @pytest.mark.asyncio
    async def test_parse_public_chat_with_topic(self):
        """Test parsing public chat link with topic."""
        link = "https://t.me/username/456/123"
        result = await _parse_message_link(link)
        assert result == ("@username", 123, 456)  # message_id, topic_id

    @pytest.mark.asyncio
    async def test_parse_private_chat_no_topic(self):
        """Test parsing private chat link without topic."""
        link = "https://t.me/c/123456789/789"
        result = await _parse_message_link(link)
        assert result == ("-100123456789", 789, None)

    @pytest.mark.asyncio
    async def test_parse_private_chat_with_topic(self):
        """Test parsing private chat link with topic."""
        link = "https://t.me/c/123456789/456/789"
        result = await _parse_message_link(link)
        assert result == ("-100123456789", 789, 456)  # message_id, topic_id

    @pytest.mark.asyncio
    async def test_parse_invalid_link(self):
        """Test parsing invalid link."""
        link = "https://invalid.com/link"
        result = await _parse_message_link(link)
        assert result == (None, None, None)

    @pytest.mark.asyncio
    async def test_parse_empty_link(self):
        """Test parsing empty link."""
        link = ""
        result = await _parse_message_link(link)
        assert result == (None, None, None)

    @pytest.mark.asyncio
    async def test_parse_link_without_protocol(self):
        """Test parsing link without https protocol."""
        link = "t.me/username/123"
        result = await _parse_message_link(link)
        assert result == ("@username", 123, None)

    @pytest.mark.asyncio
    async def test_parse_link_with_www(self):
        """Test parsing link with www prefix."""
        link = "https://www.t.me/username/123"
        result = await _parse_message_link(link)
        assert result == ("@username", 123, None)


class TestCheckMessageExists:
    """Test cases for _check_message_exists function."""

    @pytest.mark.asyncio
    async def test_message_exists(self):
        """Test when message exists."""
        # Mock message object
        mock_message = MagicMock()
        mock_account_app = AsyncMock()
        mock_account_app.get_messages.return_value = [mock_message]

        result = await _check_message_exists(
            "https://t.me/username/123", mock_account_app
        )
        assert result is True
        mock_account_app.get_messages.assert_called_once_with(
            entity="@username", ids=[123]
        )

    @pytest.mark.asyncio
    async def test_message_deleted(self):
        """Test when message is deleted (returns None)."""
        mock_account_app = AsyncMock()
        mock_account_app.get_messages.return_value = [None]

        result = await _check_message_exists(
            "https://t.me/username/123", mock_account_app
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_no_access_to_chat(self):
        """Test when we have no access to chat (get_messages returns None/empty)."""
        mock_account_app = AsyncMock()
        mock_account_app.get_messages.return_value = None

        result = await _check_message_exists(
            "https://t.me/username/123", mock_account_app
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_empty_response_list(self):
        """Test when get_messages returns empty list."""
        mock_account_app = AsyncMock()
        mock_account_app.get_messages.return_value = []

        result = await _check_message_exists(
            "https://t.me/username/123", mock_account_app
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_api_exception(self):
        """Test when API call raises exception (e.g., banned from chat)."""
        mock_account_app = AsyncMock()
        mock_account_app.get_messages.side_effect = Exception("Access denied")

        result = await _check_message_exists(
            "https://t.me/username/123", mock_account_app
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_invalid_link(self):
        """Test with invalid link."""
        mock_account_app = AsyncMock()

        result = await _check_message_exists(
            "https://invalid.com/link", mock_account_app
        )
        assert result is False
        # get_messages should not be called for invalid links
        mock_account_app.get_messages.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_link_provided(self):
        """Test with no link provided."""
        mock_account_app = AsyncMock()

        result = await _check_message_exists("", mock_account_app)
        assert result is False
        mock_account_app.get_messages.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_account_app(self):
        """Test with no account app provided."""
        result = await _check_message_exists("https://t.me/username/123", None)
        assert result is False

    @pytest.mark.asyncio
    async def test_private_channel_with_topic(self):
        """Test checking message in private channel with topic."""
        mock_message = MagicMock()
        mock_account_app = AsyncMock()
        mock_account_app.get_messages.return_value = [mock_message]

        result = await _check_message_exists(
            "https://t.me/c/123456789/456/789", mock_account_app
        )
        assert result is True
        mock_account_app.get_messages.assert_called_once_with(
            entity="-100123456789", ids=[789]
        )
