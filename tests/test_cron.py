from datetime import datetime
from zoneinfo import ZoneInfo

import croniter
import pytest

from settings import check_cron, check_cron_tz


# Happy path tests with various realistic test values
@pytest.mark.parametrize(
    "crontab, last_run, now, expected, _id",
    [
        (
            "0 * * * *",
            datetime(2021, 1, 1, 10, 30),
            datetime(2021, 1, 1, 11, 1),
            True,
            "ID001",
        ),
        (
            "*/15 * * * *",
            datetime(2021, 1, 1, 10, 45),
            datetime(2021, 1, 1, 11, 0),
            True,
            "ID002",
        ),
        ("0 0 1 * *", datetime(2021, 1, 1), datetime(2021, 2, 1), True, "ID003"),
        ("0 0 * * 0", datetime(2021, 1, 3), datetime(2021, 1, 10), True, "ID004"),
        ("0 0 * * 0", datetime(2021, 1, 3), datetime(2021, 1, 4), False, "ID005"),
        (
            "0 12 1 * *",
            datetime(2021, 1, 1, 12, 0),
            datetime(2021, 1, 1, 12, 1),
            False,
            "ID006",
        ),
        (
            "0 12 * * mon",
            datetime(2024, 2, 17, 12, 0),
            datetime(2024, 2, 18, 12, 0),
            False,
            "ID007",
        ),
        (
            "0 12 * * mon",
            datetime(2024, 2, 19, 11, 59),
            datetime(2024, 2, 19, 12, 1),
            True,
            "ID008",
        ),
        (
            "0 12 * * mon,fri",
            datetime(2024, 2, 19, 11, 59),
            datetime(2024, 2, 19, 12, 1),
            True,
            "ID009",
        ),
    ],
)
def test_check_cron_happy_path(crontab, last_run, now, expected, _id):
    # Act
    result = check_cron(crontab, last_run, now)

    # Assert
    assert result == expected, f"Failed {_id}"


# Edge cases
@pytest.mark.parametrize(
    "crontab, last_run, now, expected, _id",
    [
        (
            "0 * * * *",
            datetime(2021, 1, 1, 10, 59),
            datetime(2021, 1, 1, 11, 0),
            True,
            "ID007",
        ),
        ("0 0 29 2 *", datetime(2020, 2, 29), datetime(2024, 2, 29), True, "ID008"),
        ("0 0 29 2 *", datetime(2020, 2, 29), datetime(2024, 2, 28), False, "ID008.1"),
        ("0 0 29 2 *", datetime(2020, 2, 28), datetime(2024, 2, 28), True, "ID008.2"),
        ("0 0 28 2 *", datetime(2020, 2, 29), datetime(2024, 2, 29), True, "ID008.3"),
        ("0 0 29 2 *", datetime(2021, 2, 28), datetime(2021, 3, 1), False, "ID009"),
        (
            "0 0 1 1 *",
            datetime(2021, 12, 31, 23, 59),
            datetime(2022, 1, 1, 0, 0),
            True,
            "ID010",
        ),
    ],
)
def test_check_cron_edge_cases(crontab, last_run, now, expected, _id):
    # Act
    result = check_cron(crontab, last_run, now)

    # Assert
    assert result == expected, f"Failed {_id}"


# Error cases
@pytest.mark.parametrize(
    "crontab, last_run, now, expected_exception, _id",
    [
        (
            "not a cron",
            datetime(2021, 1, 1),
            datetime(2021, 1, 1, 1),
            ValueError,
            "ID011",
        ),
        ("* * *", datetime(2021, 1, 1), datetime(2021, 1, 1, 1), ValueError, "ID012"),
        ("0 * * * *", "2021-01-01 10:00", datetime(2021, 1, 1, 11), TypeError, "ID013"),
        ("0 * * * *", datetime(2021, 1, 1, 10), "2021-01-01 11:00", TypeError, "ID014"),
    ],
)
def test_check_cron_error_cases(crontab, last_run, now, expected_exception, _id):
    # Act and Assert
    with pytest.raises(expected_exception):
        check_cron(crontab, last_run, now)


@pytest.mark.parametrize(
    "crontab, last_run, now, expected, _id",
    [
        (
            "0 * * * *",
            datetime(2021, 1, 1, 10, 59),
            datetime(2021, 1, 1, 11, 0),
            False,
            "ID007",
        ),
        ("0 0 29 2 *", datetime(2020, 2, 29), datetime(2024, 2, 29), True, "ID008.1"),
        (
            "0 0 1 1 *",
            datetime(2021, 12, 31, 23, 59),
            datetime(2022, 1, 1, 0, 0),
            False,
            "ID010",
        ),
    ],
)
def test_croniter(crontab, last_run, now, expected, _id):
    assert croniter.croniter(crontab, last_run).get_next(datetime) == now


UTC = ZoneInfo("UTC")
Moscow = ZoneInfo("Europe/Moscow")


@pytest.mark.parametrize(
    "crontab, tz, last_run, now, expected, _id",
    [
        (
            "0 9 * * *",
            Moscow,
            datetime(2021, 1, 1, 8, 30, tzinfo=UTC),
            datetime(2021, 1, 1, 9, 30, tzinfo=UTC),
            False,
            "ID001",
        ),
        (
            "0 14 * * *",
            Moscow,
            datetime(2024, 1, 14, 10, 30, tzinfo=UTC),
            datetime(2024, 1, 14, 11, 30, tzinfo=UTC),
            True,
            "ID002",
        ),
    ],
)
def test_check_cron_tz_happy_path(crontab, tz, last_run, now, expected, _id):
    # Act
    result = check_cron_tz(crontab, tz, last_run, now)

    # Assert
    assert result == expected, f"Failed {_id}"
