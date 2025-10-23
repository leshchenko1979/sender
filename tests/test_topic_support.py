import pytest

from sender import parse_chat_and_topic


class TestParseChatAndTopic:
    """Test cases for parse_chat_and_topic function."""

    def test_parse_chat_with_topic_username(self):
        """Test parsing chat with topic using username format."""
        chat_id, topic_id = parse_chat_and_topic("@mychannel/123")
        assert chat_id == "@mychannel"
        assert topic_id == 123

    def test_parse_chat_with_topic_numeric_id(self):
        """Test parsing chat with topic using numeric chat ID."""
        chat_id, topic_id = parse_chat_and_topic("-1001234567890/456")
        assert chat_id == "-1001234567890"
        assert topic_id == 456

    def test_parse_chat_without_topic_username(self):
        """Test parsing chat without topic using username format."""
        chat_id, topic_id = parse_chat_and_topic("@mychannel")
        assert chat_id == "@mychannel"
        assert topic_id is None

    def test_parse_chat_without_topic_numeric_id(self):
        """Test parsing chat without topic using numeric chat ID."""
        chat_id, topic_id = parse_chat_and_topic("-1001234567890")
        assert chat_id == "-1001234567890"
        assert topic_id is None

    def test_parse_chat_with_invalid_topic_format(self):
        """Test parsing chat with invalid topic format (non-numeric)."""
        chat_id, topic_id = parse_chat_and_topic("@mychannel/invalid")
        assert chat_id == "@mychannel/invalid"
        assert topic_id is None

    def test_parse_chat_with_multiple_slashes(self):
        """Test parsing chat with multiple slashes (should use rightmost)."""
        chat_id, topic_id = parse_chat_and_topic("@mychannel/path/to/topic/123")
        assert chat_id == "@mychannel/path/to/topic"
        assert topic_id == 123

    def test_parse_chat_with_zero_topic(self):
        """Test parsing chat with topic ID of 0."""
        chat_id, topic_id = parse_chat_and_topic("@mychannel/0")
        assert chat_id == "@mychannel"
        assert topic_id == 0

    def test_parse_chat_with_negative_topic(self):
        """Test parsing chat with negative topic ID."""
        chat_id, topic_id = parse_chat_and_topic("@mychannel/-123")
        assert chat_id == "@mychannel"
        assert topic_id == -123  # Function accepts negative numbers as valid integers

    def test_parse_chat_with_large_topic_id(self):
        """Test parsing chat with large topic ID."""
        chat_id, topic_id = parse_chat_and_topic("@mychannel/999999999")
        assert chat_id == "@mychannel"
        assert topic_id == 999999999

    def test_parse_chat_with_empty_string(self):
        """Test parsing empty string."""
        chat_id, topic_id = parse_chat_and_topic("")
        assert chat_id == ""
        assert topic_id is None

    def test_parse_chat_with_slash_only(self):
        """Test parsing string with only slash."""
        chat_id, topic_id = parse_chat_and_topic("/")
        assert chat_id == "/"
        assert topic_id is None

    def test_parse_chat_with_topic_only(self):
        """Test parsing string with only topic ID."""
        chat_id, topic_id = parse_chat_and_topic("/123")
        assert chat_id == ""
        assert topic_id == 123

    def test_parse_chat_with_phone_number(self):
        """Test parsing phone number format."""
        chat_id, topic_id = parse_chat_and_topic("+1234567890/456")
        assert chat_id == "+1234567890"
        assert topic_id == 456

    def test_parse_chat_with_phone_number_no_topic(self):
        """Test parsing phone number without topic."""
        chat_id, topic_id = parse_chat_and_topic("+1234567890")
        assert chat_id == "+1234567890"
        assert topic_id is None
