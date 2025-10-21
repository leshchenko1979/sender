from unittest.mock import MagicMock, Mock, patch

import pytest

from clients import Client
from sender import handle_slow_mode_error
from settings import Setting


class TestHandleSlowModeError:
    """Test handle_slow_mode_error function with various scenarios."""

    def setup_method(self):
        """Set up test fixtures."""
        # Create mock client with settings
        self.client = Mock(spec=Client)
        self.client.settings = []

        # Create test settings
        self.setting1 = Mock(spec=Setting)
        self.setting1.chat_id = "test_chat_123"
        self.setting1.active = True
        self.setting1.schedule = "*/30 * * * *"
        self.setting1.error = ""

        self.setting2 = Mock(spec=Setting)
        self.setting2.chat_id = "test_chat_123"
        self.setting2.active = True
        self.setting2.schedule = "*/15 * * * *"
        self.setting2.error = ""

        self.setting3 = Mock(spec=Setting)
        self.setting3.chat_id = "other_chat_456"
        self.setting3.active = True
        self.setting3.schedule = "*/30 * * * *"
        self.setting3.error = ""

        self.client.settings = [self.setting1, self.setting2, self.setting3]

    def test_single_setting_same_chat(self):
        """Test handling when only one setting targets the chat."""
        # Set up: only setting1 targets the chat
        self.client.settings = [self.setting1]

        result = handle_slow_mode_error(self.client, self.setting1, 3600)  # 1 hour wait

        # Should adjust schedule and update Google Sheets
        assert "Schedule auto-adjusted to every 2 hours" in result
        assert self.setting1.schedule != "*/30 * * * *"  # Should be changed
        self.client.update_settings_in_gsheets.assert_called_once_with(
            ["schedule", "error"]
        )

    def test_multiple_settings_same_chat(self):
        """Test handling when multiple settings target the same chat."""
        # Set up: setting1 and setting2 target the same chat
        self.client.settings = [self.setting1, self.setting2, self.setting3]

        result = handle_slow_mode_error(self.client, self.setting1, 3600)  # 1 hour wait

        # Should adjust both settings for the same chat
        assert "Schedule auto-adjusted to every 2 hours for 2 settings" in result
        assert self.setting1.schedule != "*/30 * * * *"  # Should be changed
        assert self.setting2.schedule != "*/15 * * * *"  # Should be changed
        assert (
            self.setting3.schedule == "*/30 * * * *"
        )  # Should NOT be changed (different chat)
        self.client.update_settings_in_gsheets.assert_called_once_with(
            ["schedule", "error"]
        )

    def test_no_active_settings_same_chat(self):
        """Test handling when no active settings target the chat."""
        # Set up: no active settings for the chat
        self.setting1.active = False
        self.client.settings = [self.setting1]

        result = handle_slow_mode_error(self.client, self.setting1, 3600)

        assert "No active settings found for this chat" in result
        self.client.update_settings_in_gsheets.assert_not_called()

    def test_already_sufficient_interval(self):
        """Test when current intervals are already sufficient."""
        # Set up: settings already have sufficient intervals
        self.setting1.schedule = "0 */3 * * *"  # Every 3 hours
        self.setting2.schedule = "0 */4 * * *"  # Every 4 hours
        self.client.settings = [self.setting1, self.setting2]

        result = handle_slow_mode_error(
            self.client, self.setting1, 3600
        )  # Need 2 hours

        assert "No schedule adjustments needed" in result
        assert "current intervals already sufficient" in result
        # Schedules should not be changed
        assert self.setting1.schedule == "0 */3 * * *"
        assert self.setting2.schedule == "0 */4 * * *"
        self.client.update_settings_in_gsheets.assert_called_once_with(
            ["schedule", "error"]
        )

    def test_round_up_to_hours(self):
        """Test that wait time is properly rounded up to hours."""
        # 30 minutes wait should round up to 1 hour
        result = handle_slow_mode_error(self.client, self.setting1, 1800)  # 30 minutes

        assert "every 1 hours" in result

        # 90 minutes wait should round up to 2 hours (with 20% buffer)
        result = handle_slow_mode_error(self.client, self.setting1, 5400)  # 90 minutes

        assert "every 2 hours" in result

    def test_error_message_formatting(self):
        """Test that error messages are properly formatted."""
        result = handle_slow_mode_error(self.client, self.setting1, 3600)

        # Check that error message contains expected elements
        assert self.setting1.error != ""
        assert "Автоматически изменено расписание" in self.setting1.error
        assert "*/30 * * * *" in self.setting1.error  # Old schedule
        assert "1 час" in self.setting1.error  # Humanized wait time

    def test_different_chat_ids(self):
        """Test that only settings for the same chat are affected."""
        # Set up: settings for different chats
        self.client.settings = [self.setting1, self.setting3]  # Different chat IDs

        result = handle_slow_mode_error(self.client, self.setting1, 3600)

        # Only setting1 should be affected
        assert "for 1 settings" in result
        assert self.setting1.schedule != "*/30 * * * *"  # Should be changed
        assert self.setting3.schedule == "*/30 * * * *"  # Should NOT be changed

    def test_very_long_wait_time(self):
        """Test handling of very long wait times (>24 hours)."""
        # 25 hours wait should result in daily schedule
        result = handle_slow_mode_error(self.client, self.setting1, 90000)  # 25 hours

        assert "every 25 hours" in result
        # The schedule should be adjusted to daily (0 0 * * *)
        assert "0 0" in self.setting1.schedule

    def test_google_sheets_update_called(self):
        """Test that Google Sheets is updated with correct fields."""
        handle_slow_mode_error(self.client, self.setting1, 3600)

        # Should call update_settings_in_gsheets with schedule and error fields
        self.client.update_settings_in_gsheets.assert_called_once_with(
            ["schedule", "error"]
        )

    def test_preserve_cron_constraints(self):
        """Test that cron constraints (day, month, weekday) are preserved."""
        # Set up setting with complex cron constraints
        self.setting1.schedule = "30 14 1 * 1-5"  # 1st of month, weekdays at 14:30
        self.client.settings = [self.setting1]

        result = handle_slow_mode_error(self.client, self.setting1, 3600)

        # Should preserve day (1), month (*), and weekday (1-5) constraints
        new_schedule = self.setting1.schedule
        assert "1" in new_schedule  # Day constraint preserved
        assert "1-5" in new_schedule  # Weekday constraint preserved
        assert "*/2" in new_schedule  # Hour interval adjusted


class TestSlowModeIntegration:
    """Test integration scenarios for slow mode handling."""

    def test_multiple_clients_same_chat(self):
        """Test that slow mode affects only the current client's settings."""
        # This would be tested in a higher-level integration test
        # where multiple clients might have settings for the same chat
        pass

    def test_concurrent_slow_mode_errors(self):
        """Test handling of concurrent slow mode errors."""
        # This would test race conditions if multiple settings
        # trigger slow mode errors simultaneously
        pass

    def test_slow_mode_recovery(self):
        """Test that settings can recover from slow mode after adjustment."""
        # This would test that after schedule adjustment,
        # settings can run successfully without further slow mode errors
        pass


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_zero_wait_seconds(self):
        """Test handling of zero wait seconds."""
        client = Mock(spec=Client)
        client.settings = []
        setting = Mock(spec=Setting)
        setting.chat_id = "test_chat"
        setting.active = True
        setting.schedule = "*/30 * * * *"

        result = handle_slow_mode_error(client, setting, 0)

        # Should still round up to 1 hour minimum
        assert "every 1 hours" in result

    def test_negative_wait_seconds(self):
        """Test handling of negative wait seconds."""
        client = Mock(spec=Client)
        client.settings = []
        setting = Mock(spec=Setting)
        setting.chat_id = "test_chat"
        setting.active = True
        setting.schedule = "*/30 * * * *"

        result = handle_slow_mode_error(client, setting, -100)

        # Should handle gracefully and round up to 1 hour minimum
        assert "every 1 hours" in result

    def test_very_short_wait_time(self):
        """Test handling of very short wait times (seconds)."""
        client = Mock(spec=Client)
        setting = Mock(spec=Setting)
        setting.chat_id = "test_chat"
        setting.active = True
        setting.schedule = "*/30 * * * *"
        client.settings = [setting]

        result = handle_slow_mode_error(client, setting, 30)  # 30 seconds

        # Should round up to 1 hour minimum
        assert "every 1 hours" in result

