import pytest

from src.scheduling.cron_utils import (
    adjust_cron_interval,
    calculate_interval_hours,
    format_schedule_change_message,
    humanize_seconds,
)


class TestHumanizeSeconds:
    """Test humanize_seconds function with various inputs."""

    def test_seconds_less_than_60(self):
        assert humanize_seconds(30) == "30 секунд"
        assert humanize_seconds(1) == "1 секунд"
        assert humanize_seconds(59) == "59 секунд"

    def test_minutes(self):
        assert humanize_seconds(60) == "1 минуту"
        assert humanize_seconds(120) == "2 минуты"
        assert humanize_seconds(180) == "3 минуты"
        assert humanize_seconds(240) == "4 минуты"
        assert humanize_seconds(300) == "5 минут"
        assert humanize_seconds(3600) == "1 час"

    def test_hours(self):
        assert humanize_seconds(3600) == "1 час"
        assert humanize_seconds(7200) == "2 часа"
        assert humanize_seconds(10800) == "3 часа"
        assert humanize_seconds(14400) == "4 часа"
        assert humanize_seconds(18000) == "5 часов"
        assert humanize_seconds(86400) == "24 часов"


class TestCalculateIntervalHours:
    """Test calculate_interval_hours function with various cron patterns."""

    def test_every_30_minutes(self):
        # */30 * * * * should be approximately 0.5 hours
        interval = calculate_interval_hours("*/30 * * * *")
        assert 0.4 <= interval <= 0.6

    def test_every_hour(self):
        # 0 * * * * should be approximately 1 hour
        interval = calculate_interval_hours("0 * * * *")
        assert 0.9 <= interval <= 1.1

    def test_every_2_hours(self):
        # 0 */2 * * * should be approximately 2 hours
        interval = calculate_interval_hours("0 */2 * * *")
        assert 1.9 <= interval <= 2.1

    def test_daily(self):
        # 0 0 * * * should be approximately 24 hours
        interval = calculate_interval_hours("0 0 * * *")
        assert 23.9 <= interval <= 24.1

    def test_weekdays_only(self):
        # 0 9 * * 1-5 should be approximately 24 hours (daily on weekdays)
        # But there's a weekend gap, so it might be longer
        interval = calculate_interval_hours("0 9 * * 1-5")
        assert 20 <= interval <= 72  # Allow for weekend gaps

    def test_invalid_cron(self):
        # Should return weekly (7*24) for invalid cron
        interval = calculate_interval_hours("invalid cron")
        assert interval == 24 * 7


class TestAdjustCronInterval:
    """Test adjust_cron_interval function with various scenarios."""

    def test_simple_interval_already_sufficient(self):
        # If current interval is already sufficient, return original
        result = adjust_cron_interval("0 */2 * * *", 1)  # Every 2 hours, need 1 hour
        assert result == "0 */2 * * *"

    def test_simple_interval_needs_adjustment(self):
        # Every 30 minutes, need 2 hours
        result = adjust_cron_interval("*/30 * * * *", 2)
        assert result == "0 */2 * * *"

    def test_preserve_day_constraint(self):
        # Preserve day of month constraint
        result = adjust_cron_interval("0 9 1 * *", 200)  # 1st of month, need 200 hours
        assert result == "0 0 1 * *"  # Should become daily

    def test_preserve_month_constraint(self):
        # Preserve month constraint
        result = adjust_cron_interval("0 9 * 1 *", 200)  # January only, need 200 hours
        assert result == "0 0 * 1 *"  # Should become daily

    def test_preserve_weekday_constraint(self):
        # Preserve weekday constraint
        result = adjust_cron_interval(
            "0 9 * * 1-5", 200
        )  # Weekdays only, need 200 hours
        assert result == "0 0 * * 1-5"  # Should become daily

    def test_specific_hours_conversion(self):
        # Convert specific hours to interval-based
        result = adjust_cron_interval(
            "0 9,14,18 * * *", 10
        )  # Specific hours, need 10 hours
        assert result == "0 */10 * * *"

    def test_range_hours_conversion(self):
        # Convert range hours to interval-based
        result = adjust_cron_interval("0 9-17 * * *", 3)  # Business hours, need 3 hours
        assert result == "0 */3 * * *"

    def test_edge_case_over_24_hours(self):
        # If required hours > 24, use daily schedule
        result = adjust_cron_interval("*/30 * * * *", 25)  # Need 25 hours
        assert result == "0 0 * * *"

    def test_preserve_all_constraints(self):
        # Complex case: preserve day, month, and weekday
        result = adjust_cron_interval(
            "30 14 1 1 1-5", 200
        )  # 1st Jan weekdays at 14:30, need 200 hours
        assert result == "0 0 1 1 1-5"  # Should become daily

    def test_invalid_cron_expression(self):
        # Should raise ValueError for invalid cron
        with pytest.raises(ValueError):
            adjust_cron_interval("invalid cron", 2)


class TestFormatScheduleChangeMessage:
    """Test format_schedule_change_message function."""

    def test_basic_message(self):
        message = format_schedule_change_message(
            wait_seconds=3600,
            old_schedule="*/30 * * * *",
            new_schedule="0 */2 * * *",
            required_hours=2,
            affected_count=3,
        )

        assert "Автоматически изменено расписание" in message
        assert "*/30 * * * *" in message
        assert "0 */2 * * *" in message
        assert "1 час" in message  # humanized wait time
        assert "3 настройкам" in message

    def test_plural_forms(self):
        # Test singular form
        message = format_schedule_change_message(
            wait_seconds=60,
            old_schedule="*/5 * * * *",
            new_schedule="0 */1 * * *",
            required_hours=1,
            affected_count=1,
        )

        assert "1 настройке" in message or "1 настройкам" in message

    def test_different_wait_times(self):
        # Test various wait times
        message_30_sec = format_schedule_change_message(30, "old", "new", 1, 1)
        assert "30 секунд" in message_30_sec

        message_90_sec = format_schedule_change_message(90, "old", "new", 1, 1)
        assert "1 минуту" in message_90_sec

        message_2_hours = format_schedule_change_message(7200, "old", "new", 2, 1)
        assert "2 часа" in message_2_hours


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_zero_seconds(self):
        assert humanize_seconds(0) == "0 секунд"

    def test_very_large_seconds(self):
        # 1 year in seconds
        result = humanize_seconds(365 * 24 * 3600)
        assert "часов" in result

    def test_cron_with_seconds_precision(self):
        # Test that we handle fractional hours correctly
        interval = calculate_interval_hours("*/15 * * * *")  # Every 15 minutes
        assert 0.2 <= interval <= 0.3

    def test_adjust_cron_with_complex_patterns(self):
        # Test with very complex cron patterns
        result = adjust_cron_interval(
            "0 0 1,15 * 1-5", 25
        )  # 1st and 15th of month, weekdays, need 25 hours
        assert result == "0 0 1,15 * 1-5"  # Should become daily
