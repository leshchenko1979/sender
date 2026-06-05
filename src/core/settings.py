import hashlib
from datetime import datetime
from datetime import timezone as tz
from zoneinfo import ZoneInfo

import croniter
import pydantic


class Setting(pydantic.BaseModel):
    active: int | bool
    account: str = ""
    schedule: str
    chat_id: str
    text: str
    error: str = ""
    link: str = ""

    @pydantic.field_validator("active", mode="before")
    @classmethod
    def active_must_be_bool_or_int(cls, v) -> int | bool:
        if v == "" or v is None:
            return False
        if isinstance(v, str):
            if v.lower() in ("true", "1", "yes", "on"):
                return True
            elif v.lower() in ("false", "0", "no", "off"):
                return False
            else:
                try:
                    return int(v)
                except ValueError:
                    return False
        return v

    def __str__(self):
        return f"{self.chat_id} {self.text[:100]}"

    def should_be_run(self, last_run: datetime) -> bool:
        return self.active and check_cron_tz(
            self.schedule, ZoneInfo("Europe/Moscow"), last_run, datetime.now(tz=tz.utc)
        )

    def get_hash(self) -> str:
        # No longer includes account field (removed from settings table)
        data = f"{self.chat_id}_{self.text}"
        return hashlib.blake2b(data.encode(), digest_size=8).hexdigest()


def check_cron(crontab: str, last_run: datetime, now: datetime) -> bool:
    cron = croniter.croniter(crontab, last_run)
    next_run = cron.get_next(datetime)
    return next_run <= now


def check_cron_tz(
    crontab: str, crontab_tz: ZoneInfo, last_run: datetime, now: datetime
) -> bool:
    last_run_utc = last_run.astimezone(crontab_tz).replace(tzinfo=None)
    now_utc = now.astimezone(crontab_tz).replace(tzinfo=None)
    return check_cron(crontab, last_run_utc, now_utc)
