import logging
from unittest.mock import Mock, patch
import pytest

from src.cli import TelegramLoggingHandler


class TestTelegramLoggingHandler:
    """Test the Telegram logging handler."""

    def test_handler_initialization(self):
        """Test that the handler is initialized correctly."""
        bot_token = "123456:test_token"
        chat_id = "@test_channel"

        handler = TelegramLoggingHandler(bot_token, chat_id)

        assert handler.bot_token == bot_token
        assert handler.chat_id == chat_id
        assert handler.level == logging.WARNING
        assert handler.formatter is not None

    def test_handler_only_logs_warnings_and_above(self):
        """Test that the handler only processes warnings and higher."""
        handler = TelegramLoggingHandler("token", "chat_id")

        # Should not emit for INFO
        with patch.object(handler, "_send_to_telegram") as mock_send:
            record = logging.LogRecord(
                name="test",
                level=logging.INFO,
                pathname="",
                lineno=0,
                msg="Test info message",
                args=(),
                exc_info=None,
            )
            handler.emit(record)
            mock_send.assert_not_called()

        # Should emit for WARNING
        with patch.object(handler, "_send_to_telegram") as mock_send:
            record = logging.LogRecord(
                name="test",
                level=logging.WARNING,
                pathname="",
                lineno=0,
                msg="Test warning message",
                args=(),
                exc_info=None,
            )
            handler.emit(record)
            mock_send.assert_called_once()

        # Should emit for ERROR
        with patch.object(handler, "_send_to_telegram") as mock_send:
            record = logging.LogRecord(
                name="test",
                level=logging.ERROR,
                pathname="",
                lineno=0,
                msg="Test error message",
                args=(),
                exc_info=None,
            )
            handler.emit(record)
            mock_send.assert_called_once()

    def test_message_formatting(self):
        """Test that messages are formatted correctly."""
        handler = TelegramLoggingHandler("token", "chat_id")

        record = logging.LogRecord(
            name="test.logger",
            level=logging.WARNING,
            pathname="test.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        formatted = handler.format(record)
        assert "🚨 WARNING from test.logger" in formatted
        assert "Test message" in formatted

    @patch("src.cli.urlopen")
    def test_send_to_telegram_success(self, mock_urlopen):
        """Test successful sending to Telegram."""
        mock_response = Mock()
        mock_response.status = 200
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=None)
        mock_urlopen.return_value = mock_response

        handler = TelegramLoggingHandler("token", "chat_id")
        handler._send_to_telegram("Test message")

        mock_urlopen.assert_called_once()
        call_args = mock_urlopen.call_args
        req = call_args[0][0]

        # Check that the request contains the right data
        import urllib.parse

        data = urllib.parse.parse_qs(req.data.decode("utf-8"))
        assert data["chat_id"][0] == "chat_id"
        assert data["text"][0] == "Test message"
        assert data["parse_mode"][0] == "HTML"
        # Check Content-Type header in the headers dict (urllib uses 'Content-type')
        assert req.headers.get("Content-type") == "application/x-www-form-urlencoded"

    @patch("src.cli.urlopen")
    def test_send_to_telegram_failure(self, mock_urlopen):
        """Test handling of Telegram API failures."""
        from urllib.error import URLError

        mock_urlopen.side_effect = URLError("Network error")

        handler = TelegramLoggingHandler("token", "chat_id")

        # Should raise exception (this is expected behavior)
        with pytest.raises(URLError, match="Network error"):
            handler._send_to_telegram("Test message")

    def test_emit_handles_exceptions(self):
        """Test that emit method handles exceptions gracefully."""
        handler = TelegramLoggingHandler("token", "chat_id")

        # Mock _send_to_telegram to raise an exception
        with patch.object(
            handler, "_send_to_telegram", side_effect=Exception("Send failed")
        ):
            record = logging.LogRecord(
                name="test",
                level=logging.WARNING,
                pathname="",
                lineno=0,
                msg="Test warning",
                args=(),
                exc_info=None,
            )

            # Should not raise exception and should print error to stderr
            with patch("sys.stderr") as mock_stderr:
                handler.emit(record)
                # Check that error was printed to stderr
                mock_stderr.write.assert_called()

    @patch("src.cli.urlopen")
    def test_message_length_limit(self, mock_urlopen):
        """Test that long messages are truncated to Telegram's limit."""
        mock_response = Mock()
        mock_response.status = 200
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=None)
        mock_urlopen.return_value = mock_response

        handler = TelegramLoggingHandler("token", "chat_id")

        # Create a message longer than 4096 characters
        long_message = "A" * 5000

        handler._send_to_telegram(long_message)

        # Check that the message sent to Telegram API is truncated
        call_args = mock_urlopen.call_args
        req = call_args[0][0]

        import urllib.parse

        data = urllib.parse.parse_qs(req.data.decode("utf-8"))
        sent_message = data["text"][0]
        assert len(sent_message) == 4096
