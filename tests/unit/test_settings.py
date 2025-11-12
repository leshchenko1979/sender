from unittest.mock import Mock, patch

import pytest
from pydantic import ValidationError

from src.core.clients import Client
from src.core.settings import Setting


class TestSettingValidation:
    # Happy path tests
    @pytest.mark.parametrize(
        "input_account, expected_account",
        [
            pytest.param("79234567890", "79234567890", id="standard-format"),
            pytest.param("89234567890", "79234567890", id="leading-8"),
            pytest.param("9234567890", "79234567890", id="leading-9"),
            pytest.param("+7 (999) 123-45-67", "79991234567", id="formatted-number"),
            pytest.param("999-123-45-67", "79991234567", id="missing-country-code"),
        ],
        ids=str,
    )
    def test_setting_account_happy_path(
        self, setting_factory, input_account, expected_account
    ):
        # Act
        setting = setting_factory(account=input_account)

        # Assert
        assert setting.account == expected_account

    # Edge cases
    @pytest.mark.parametrize(
        "input_account",
        [
            pytest.param("7 999 123 45 678", id="extra-digit"),
            pytest.param("7 999 123 45 6", id="missing-digit"),
        ],
        ids=str,
    )
    def test_setting_account_edge_cases(self, setting_factory, input_account):
        # Act & Assert
        with pytest.raises(ValidationError):
            setting_factory(account=input_account)

    # Error cases
    @pytest.mark.parametrize(
        "input_account",
        [
            pytest.param("AXXXXXXXXX", id="non-digit-characters"),
            pytest.param("123", id="too-short"),
            pytest.param("123456789012", id="too-long"),
        ],
        ids=str,
    )
    def test_setting_account_error_cases(self, setting_factory, input_account):
        # Act & Assert
        with pytest.raises(ValidationError):
            setting_factory(account=input_account)


# Test load_settings
@patch("src.core.clients.get_worksheet")
def test_load_settings(mock_get_worksheet):
    # Arrange
    mock_worksheet = Mock()
    mock_worksheet.get_all_values.return_value = [
        ["active", "account", "schedule", "chat_id", "text", "error", "link"],
        ["1", "7 123 456 78 90", "0 5 * * *", "chat_id_1", "Hello!", "", ""],
        [False, "8 123 456 78 90", "0 6 * * *", "chat_id_2", "Hi there!", "", ""],
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
    assert settings[0].account == "71234567890"
    assert settings[1].account == "71234567890"
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
    # Only 5 columns (old format without error and link)
    mock_worksheet.get_all_values.return_value = [
        ["active", "account", "schedule", "chat_id", "text"],
        ["1", "7 123 456 78 90", "0 5 * * *", "chat_id_1", "Hello!"],
        [False, "8 123 456 78 90", "0 6 * * *", "chat_id_2", "Hi there!"],
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
    assert settings[0].account == "71234567890"
    assert settings[1].account == "71234567890"
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
