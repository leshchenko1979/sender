import hashlib
from datetime import datetime
from datetime import timezone as tz
from zoneinfo import ZoneInfo

import croniter
import pydantic


class Setting(pydantic.BaseModel):
    active: int | bool
    account: str
    schedule: str
    chat_id: str
    text: str
    error: str = ""
    link: str = ""

    @pydantic.field_validator("active", mode="before")
    @classmethod
    def active_must_be_bool_or_int(cls, v) -> int | bool:
        """Convert empty strings to False, and handle string representations of booleans."""
        if v == "" or v is None:
            return False
        if isinstance(v, str):
            # Handle common string representations
            if v.lower() in ("true", "1", "yes", "on"):
                return True
            elif v.lower() in ("false", "0", "no", "off"):
                return False
            else:
                # Try to convert to int, then to bool
                try:
                    return int(v)
                except ValueError:
                    return False
        return v

    def __str__(self):
        return f"{self.chat_id} {self.text[:100]}"

    @pydantic.field_validator("account")
    @classmethod
    def account_must_be_phone_number(cls, v: str) -> str:
        """Expect v to be a phone number in a format 7XXXXXXXXXX.
        Parenthesis, a leading plus sign, minus signs and spaces are allowed,
        but omitted in the result. Leading 7 may be added if omitted.
        """
        for s in " +-()":
            v = v.replace(s, "")

        if not v.isdigit():
            raise ValueError("Phone number must be digits only")

        if v.startswith("8"):
            v = f"7{v[1:]}"

        if v.startswith("9"):
            v = f"7{v}"

        if len(v) != 11:
            raise ValueError("Phone number must be 11 digits long")

        return v

    def should_be_run(self, last_run: datetime) -> bool:
        # Check if the setting should be processed
        return self.active and check_cron_tz(
            self.schedule, ZoneInfo("Europe/Moscow"), last_run, datetime.now(tz=tz.utc)
        )

    def get_hash(self) -> str:
        # Returns a 16-character hash that would be the same for the same setting
        data = f"{self.account}_{self.chat_id}_{self.text}"
        return hashlib.blake2b(data.encode(), digest_size=8).hexdigest()


def check_cron(crontab: str, last_run: datetime, now: datetime) -> bool:
    """Return True if, according to the crontab, there should have been
    another run between the last_run and now"""

    cron = croniter.croniter(crontab, last_run)
    next_run = cron.get_next(datetime)
    return next_run <= now


def check_cron_tz(
    crontab: str, crontab_tz: ZoneInfo, last_run: datetime, now: datetime
) -> bool:
    """Return True if, according to the crontab, there should have been
    another run between the last run and now.

    Crontab is in another timezone indicated by crontab_tz.
    """

    last_run_utc = last_run.astimezone(crontab_tz).replace(tzinfo=None)
    now_utc = now.astimezone(crontab_tz).replace(tzinfo=None)

    return check_cron(crontab, last_run_utc, now_utc)
