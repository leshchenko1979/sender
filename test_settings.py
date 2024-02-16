import json
import os
from unittest.mock import Mock, patch

import pytest
from pydantic import ValidationError

from settings import Setting, load_from_gsheets, load_settings


class TestSettingValidation:
# Happy path tests
    @pytest.mark.parametrize("input_account, expected_account", [
        pytest.param("79234567890", "79234567890", id="standard-format"),
        pytest.param("89234567890", "79234567890", id="leading-8"),
        pytest.param("9234567890", "79234567890", id="leading-9"),
        pytest.param("+7 (999) 123-45-67", "79991234567", id="formatted-number"),
        pytest.param("999-123-45-67", "79991234567", id="missing-country-code"),
    ], ids=str)
    def test_setting_account_happy_path(self, input_account, expected_account):
        # Act
        setting = Setting(active=True, account=input_account, schedule="* * * * *", chat_id="12345", text="Hello")

        # Assert
        assert setting.account == expected_account

    # Edge cases
    @pytest.mark.parametrize("input_account", [
        pytest.param("7 999 123 45 678", id="extra-digit"),
        pytest.param("7 999 123 45 6", id="missing-digit"),
    ], ids=str)
    def test_setting_account_edge_cases(self, input_account):
        # Act & Assert
        with pytest.raises(ValidationError):
            Setting(active=True, account=input_account, schedule="* * * * *", chat_id="12345", text="Hello")

    # Error cases
    @pytest.mark.parametrize("input_account", [
        pytest.param("AXXXXXXXXX", id="non-digit-characters"),
        pytest.param("123", id="too-short"),
        pytest.param("123456789012", id="too-long"),
    ], ids=str)
    def test_setting_account_error_cases(self, input_account):
        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            Setting(active=True, account=input_account, schedule="* * * * *", chat_id="12345", text="Hello")


# Test load_settings
@patch('settings.load_from_gsheets')
def test_load_settings(mock_load_from_gsheets):
    # Arrange
    mock_load_from_gsheets.return_value = [
        ["active", "account", "schedule", "chat_id", "text"],
        ["1", "7 123 456 78 90", "0 5 * * *", "chat_id_1", "Hello!"],
        [False, "8 123 456 78 90", "0 6 * * *", "chat_id_2", "Hi there!"]
    ]

    # Act
    settings = load_settings("abc")

    # Assert
    assert len(settings) == 2
    assert all(isinstance(setting, Setting) for setting in settings)
    assert settings[0].account == "71234567890"
    assert settings[1].account == "71234567890"

# Test load_from_gsheets
@patch('gspread.service_account_from_dict')
@patch.dict(os.environ, {
    "GOOGLE_SERVICE_ACCOUNT": json.dumps({"type": "service_account"}),
    "SPREADSHEET_URL": "https://example.com/spreadsheet"
})
def test_load_from_gsheets(mock_service_account_from_dict):
    # Arrange
    mock_service_account = Mock()
    mock_service_account_from_dict.return_value = mock_service_account
    mock_worksheet = Mock()
    mock_service_account.open_by_url.return_value.get_worksheet.return_value = mock_worksheet
    mock_worksheet.get_all_values.return_value = [
        ["active", "account", "schedule", "chat_id", "text"],
        [True, "7XXXXXXXXXX", "0 5 * * *", "chat_id_1", "Hello!"]
    ]

    # Act
    result = load_from_gsheets("abc")

    # Assert
    assert mock_service_account_from_dict.called
    assert mock_service_account.open_by_url.called
    assert mock_worksheet.get_all_values.called
    assert result == [
        ["active", "account", "schedule", "chat_id", "text"],
        [True, "7XXXXXXXXXX", "0 5 * * *", "chat_id_1", "Hello!"]
    ]

# Test load_from_gsheets with no settings found
@patch('gspread.service_account_from_dict')
@patch.dict(os.environ, {
    "GOOGLE_SERVICE_ACCOUNT": json.dumps({"type": "service_account"}),
    "SPREADSHEET_URL": "https://example.com/spreadsheet"
})
def test_load_from_gsheets_no_settings_found(mock_service_account_from_dict):
    # Arrange
    mock_service_account = Mock()
    mock_service_account_from_dict.return_value = mock_service_account
    mock_worksheet = Mock()
    mock_service_account.open_by_url.return_value.get_worksheet.return_value = mock_worksheet
    mock_worksheet.get_all_values.return_value = []

    # Act & Assert
    with pytest.raises(AssertionError):
        load_from_gsheets("abc")
