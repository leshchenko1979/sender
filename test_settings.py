from unittest.mock import Mock, patch

import pytest
from pydantic import ValidationError

from clients import Client
from settings import Setting


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
    def test_setting_account_happy_path(self, input_account, expected_account):
        # Act
        setting = Setting(
            active=True,
            account=input_account,
            schedule="* * * * *",
            chat_id="12345",
            text="Hello",
        )

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
    def test_setting_account_edge_cases(self, input_account):
        # Act & Assert
        with pytest.raises(ValidationError):
            Setting(
                active=True,
                account=input_account,
                schedule="* * * * *",
                chat_id="12345",
                text="Hello",
            )

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
    def test_setting_account_error_cases(self, input_account):
        # Act & Assert
        with pytest.raises(ValidationError):
            Setting(
                active=True,
                account=input_account,
                schedule="* * * * *",
                chat_id="12345",
                text="Hello",
            )


# Test load_settings
@patch("clients.get_worksheet")
def test_load_settings(mock_get_worksheet):
    # Arrange
    mock_worksheet = Mock()
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

    # Assert
    assert len(settings) == 2
    assert all(isinstance(setting, Setting) for setting in settings)
    assert settings[0].account == "71234567890"
    assert settings[1].account == "71234567890"


# Test get_worksheet function
@patch("clients.get_google_client")
def test_get_worksheet(mock_get_google_client):
    # Arrange
    mock_service_account = Mock()
    mock_get_google_client.return_value = mock_service_account
    mock_worksheet = Mock()
    mock_service_account.open_by_url.return_value.get_worksheet.return_value = (
        mock_worksheet
    )

    # Act
    from clients import get_worksheet

    result = get_worksheet("https://example.com/spreadsheet")

    # Assert
    assert mock_service_account.open_by_url.called
    assert result == mock_worksheet
