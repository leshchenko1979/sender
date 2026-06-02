"""Tests for telegram_utils — now sync, bridge-based, no Telethon."""

from unittest.mock import patch


from src.utils.telegram_utils import (
    _check_message_exists,
    _generate_message_link,
    _parse_message_link,
)


class TestParseMessageLink:
    """Test cases for _parse_message_link function (pure string parsing, no mocking)."""

    def test_parse_public_chat_no_topic(self):
        link = "https://t.me/username/123"
        result = _parse_message_link(link)
        assert result == ("@username", 123, None)

    def test_parse_public_chat_with_topic(self):
        link = "https://t.me/username/456/123"
        result = _parse_message_link(link)
        assert result == ("@username", 123, 456)

    def test_parse_private_chat_no_topic(self):
        link = "https://t.me/c/123456789/789"
        result = _parse_message_link(link)
        assert result == ("-100123456789", 789, None)

    def test_parse_private_chat_with_topic(self):
        link = "https://t.me/c/123456789/456/789"
        result = _parse_message_link(link)
        assert result == ("-100123456789", 789, 456)

    def test_parse_invalid_link(self):
        link = "https://invalid.com/link"
        result = _parse_message_link(link)
        assert result == (None, None, None)

    def test_parse_empty_link(self):
        link = ""
        result = _parse_message_link(link)
        assert result == (None, None, None)

    def test_parse_link_without_protocol(self):
        link = "t.me/username/123"
        result = _parse_message_link(link)
        assert result == ("@username", 123, None)

    def test_parse_link_with_www(self):
        link = "https://www.t.me/username/123"
        result = _parse_message_link(link)
        assert result == ("@username", 123, None)


class TestCheckMessageExists:
    """Test cases for _check_message_exists — uses bridge.get_messages."""

    @patch("src.utils.telegram_utils.bridge.get_messages")
    def test_message_exists(self, mock_get_messages):
        mock_get_messages.return_value = {"messages": [{"id": 123}]}
        result = _check_message_exists("https://t.me/username/123")
        assert result is True
        mock_get_messages.assert_called_once_with("@username", [123], bearer_token=None)

    @patch("src.utils.telegram_utils.bridge.get_messages")
    def test_message_exists_with_bearer(self, mock_get_messages):
        mock_get_messages.return_value = {"messages": [{"id": 123}]}
        result = _check_message_exists(
            "https://t.me/username/123", bearer_token="tok_xxx"
        )
        assert result is True
        mock_get_messages.assert_called_once_with(
            "@username", [123], bearer_token="tok_xxx"
        )

    @patch("src.utils.telegram_utils.bridge.get_messages")
    def test_message_deleted(self, mock_get_messages):
        mock_get_messages.return_value = {"messages": [None]}
        result = _check_message_exists("https://t.me/username/123")
        assert result is False

    @patch("src.utils.telegram_utils.bridge.get_messages")
    def test_messages_field_missing(self, mock_get_messages):
        mock_get_messages.return_value = {}
        result = _check_message_exists("https://t.me/username/123")
        assert result is False

    @patch("src.utils.telegram_utils.bridge.get_messages")
    def test_empty_messages_list(self, mock_get_messages):
        mock_get_messages.return_value = {"messages": []}
        result = _check_message_exists("https://t.me/username/123")
        assert result is False

    @patch("src.utils.telegram_utils.bridge.get_messages")
    def test_api_exception(self, mock_get_messages):
        mock_get_messages.side_effect = Exception("Access denied")
        result = _check_message_exists("https://t.me/username/123")
        assert result is False

    def test_invalid_link(self):
        result = _check_message_exists("https://invalid.com/link")
        assert result is False

    def test_no_link_provided(self):
        result = _check_message_exists("")
        assert result is False

    def test_none_link(self):
        result = _check_message_exists(None)  # type: ignore[arg-type]
        assert result is False

    @patch("src.utils.telegram_utils.bridge.get_messages")
    def test_private_channel_with_topic(self, mock_get_messages):
        mock_get_messages.return_value = {"messages": [{"id": 789}]}
        result = _check_message_exists("https://t.me/c/123456789/456/789")
        assert result is True
        mock_get_messages.assert_called_once_with(
            "-100123456789", [789], bearer_token=None
        )


class TestGenerateMessageLink:
    """Test cases for _generate_message_link — uses bridge._call via _resolve_peer."""

    @patch("src.utils.telegram_utils.bridge._call")
    def test_public_chat_link(self, mock_call):
        mock_call.return_value = {"username": "testchannel"}
        result = _generate_message_link("@testchannel", 123)
        assert result == "https://t.me/testchannel/123"

    @patch("src.utils.telegram_utils.bridge._call")
    def test_public_chat_link_with_topic(self, mock_call):
        mock_call.return_value = {"username": "testchannel"}
        result = _generate_message_link("@testchannel", 456, topic_id=123)
        assert result == "https://t.me/testchannel/123/456"

    @patch("src.utils.telegram_utils.bridge._call")
    def test_private_channel_no_username(self, mock_call):
        mock_call.return_value = {"username": None}
        result = _generate_message_link("-1001234567890", 789)
        assert result == "https://t.me/c/1234567890/789"

    @patch("src.utils.telegram_utils.bridge._call")
    def test_private_supergroup_with_topic(self, mock_call):
        mock_call.return_value = {"username": None}
        result = _generate_message_link("-1001234567890", 456, topic_id=789)
        assert result == "https://t.me/c/1234567890/789/456"

    @patch("src.utils.telegram_utils.bridge._call")
    def test_entity_resolution_fails(self, mock_call):
        mock_call.side_effect = Exception("Network error")
        result = _generate_message_link("@testchannel", 123)
        # Falls back to c/ format when entity resolution fails
        assert result == "https://t.me/c/testchannel/123"

    @patch("src.utils.telegram_utils.bridge._call")
    def test_no_entity_found(self, mock_call):
        mock_call.return_value = None
        result = _generate_message_link("@testchannel", 123)
        # Falls back to c/ format when entity resolution returns None
        assert result == "https://t.me/c/testchannel/123"

    def test_private_channel_with_username(self):
        """When entity resolution not needed — just construct URL."""
        # Without bearer_token, _resolve_peer won't be called for numeric IDs
        # that aren't prefixed with -100. Let's check with known format.
        result = _generate_message_link("-1001234567890", 789, bearer_token="tok_x")
        # Should fall back to c/ format since _resolve_peer returns None
        assert result == "https://t.me/c/1234567890/789"
