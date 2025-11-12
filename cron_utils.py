from datetime import datetime, timedelta

import croniter


def humanize_seconds(seconds: int) -> str:
    """Convert seconds to Russian human-readable format."""
    if seconds < 60:
        return f"{seconds} секунд"
    elif seconds < 3600:
        minutes = seconds // 60
        if minutes == 1:
            return "1 минуту"
        elif minutes < 5:
            return f"{minutes} минуты"
        else:
            return f"{minutes} минут"
    else:
        hours = seconds // 3600
        if hours == 1:
            return "1 час"
        elif hours < 5:
            return f"{hours} часа"
        else:
            return f"{hours} часов"


def calculate_interval_hours(cron_expr: str) -> float:
    """Calculate average interval between cron runs over a 7-day period."""
    now = datetime.now()

    try:
        cron = croniter.croniter(cron_expr, now)
    except (ValueError, TypeError, Exception):
        # Invalid cron expression
        return 24 * 7  # Default to weekly

    # Get runs within 7 days
    runs = []
    for _ in range(100):  # Safety limit
        try:
            next_run = cron.get_next(datetime)
            if next_run > now + timedelta(days=7):
                break
            runs.append(next_run)
        except (ValueError, TypeError, Exception):
            # Invalid cron expression
            return 24 * 7  # Default to weekly

    if len(runs) < 2:
        return 24 * 7  # If only 1 run in 7 days, treat as weekly

    # Calculate average interval
    intervals = [
        (runs[i + 1] - runs[i]).total_seconds() / 3600 for i in range(len(runs) - 1)
    ]
    return sum(intervals) / len(intervals)


def adjust_cron_interval(cron_expr: str, required_hours: int) -> str:
    """
    Adjust cron to ensure minimum interval while preserving day/month/dow constraints.

    Args:
        cron_expr: Original cron expression
        required_hours: Minimum hours between runs (rounded up to next hour)

    Returns:
        New cron expression with adjusted interval
    """
    parts = cron_expr.strip().split()

    if len(parts) != 5:
        raise ValueError(f"Invalid cron expression: {cron_expr}")

    minute, hour, day, month, dow = parts

    # Calculate current interval
    current_interval_hours = calculate_interval_hours(cron_expr)

    # If current interval is already sufficient, return original
    if current_interval_hours >= required_hours:
        return cron_expr

    # Handle edge case: required_hours > 24
    if required_hours > 24:
        # Use daily schedule
        return f"0 0 {day} {month} {dow}"

    # CASE 1: Simple repeating pattern (*/N or *)
    if hour.startswith("*/") or hour == "*":
        new_minute = "0"  # Start at top of hour for clarity
        new_hour = f"*/{required_hours}"
        return f"{new_minute} {new_hour} {day} {month} {dow}"

    # CASE 2: Specific hours (e.g., "10,14,18" or just "9")
    # Convert to interval-based pattern
    elif "," in hour or hour.isdigit():
        return f"0 */{required_hours} {day} {month} {dow}"

    # CASE 3: Range (e.g., "9-17" business hours)
    elif "-" in hour:
        # Convert to interval-based
        return f"0 */{required_hours} {day} {month} {dow}"

    # CASE 4: Any other pattern - convert to interval-based
    else:
        return f"0 */{required_hours} {day} {month} {dow}"


def format_schedule_change_message(
    wait_seconds: int,
    old_schedule: str,
    new_schedule: str,
    required_hours: int,
    affected_count: int,
) -> str:
    """Generate user-friendly Russian message explaining the automatic change."""
    humanized_wait = humanize_seconds(wait_seconds)

    return (
        f"Автоматически изменено расписание с '{old_schedule}' на '{new_schedule}' "
        f"из-за slow mode в чате (требуется подождать {humanized_wait}). "
        f"Применено ко всем {affected_count} настройкам для этого чата."
    )
