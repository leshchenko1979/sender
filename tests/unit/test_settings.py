from unittest.mock import Mock, patch

from src.core.clients import Client
from src.core.settings import Setting


# Test load_settings
@patch("src.core.clients.get_worksheet")
def test_load_settings(mock_get_worksheet):
    # Arrange
    mock_worksheet = Mock()
    mock_worksheet.get_all_values.return_value = [
        ["active", "schedule", "chat_id", "text", "error", "link"],
        ["1", "0 5 * * *", "chat_id_1", "Hello!", "", ""],
        [False, "0 6 * * *", "chat_id_2", "Hi there!", "", ""],
    ]
    mock_get_worksheet.return_value = mock_worksheet

    client = Client(
        name="abc",
        spreadsheet_url="https://example.com/spreadsheet",
        alert_account="9 123 456 78 90",
        alert_chat="chat_id_3",
    )

    # Act
    settings = client.load_settings()

    # Assert
    assert len(settings) == 2
    assert all(isinstance(setting, Setting) for setting in settings)
    # Check default values for error and link fields
    assert settings[0].error == ""
    assert settings[0].link == ""
    assert settings[1].error == ""
    assert settings[1].link == ""


# Test backward compatibility - loading with fewer columns than model fields
@patch("src.core.clients.get_worksheet")
def test_load_settings_backward_compatibility(mock_get_worksheet):
    """Test that loading works when Google Sheets has fewer columns than model fields."""
    # Arrange
    mock_worksheet = Mock()
    # Only 4 columns (old format without account, error and link)
    mock_worksheet.get_all_values.return_value = [
        ["active", "schedule", "chat_id", "text"],
        ["1", "0 5 * * *", "chat_id_1", "Hello!"],
        [False, "0 6 * * *", "chat_id_2", "Hi there!"],
    ]
    mock_get_worksheet.return_value = mock_worksheet

    client = Client(
        name="abc",
        spreadsheet_url="https://example.com/spreadsheet",
        alert_account="9 123 456 78 90",
        alert_chat="chat_id_3",
    )

    # Act
    settings = client.load_settings()

    # Assert - should still work with default values
    assert len(settings) == 2
    assert all(isinstance(setting, Setting) for setting in settings)
    # Default values should be used for missing columns
    assert settings[0].error == ""
    assert settings[0].link == ""
    assert settings[1].error == ""
    assert settings[1].link == ""


# Test get_worksheet function
@patch("src.core.clients.get_google_client")
def test_get_worksheet(mock_get_google_client):
    # Arrange
    mock_service_account = Mock()
    mock_get_google_client.return_value = mock_service_account
    mock_worksheet = Mock()
    mock_service_account.open_by_url.return_value.get_worksheet.return_value = (
        mock_worksheet
    )

    # Act
    from src.core.clients import get_worksheet

    result = get_worksheet("https://example.com/spreadsheet")

    # Assert
    assert mock_service_account.open_by_url.called
    assert result == mock_worksheet
