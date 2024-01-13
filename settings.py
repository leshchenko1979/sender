import collections
import orjson as json
import os

import gspread
from icontract import ensure

Setting = collections.namedtuple(
    "Setting", ["active", "account", "schedule", "chat_id", "text"]
)


@ensure(lambda result: result, "No settings found")
def load_settings() -> list[Setting]:
    service_dict = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT"], )
    gc = gspread.service_account_from_dict(service_dict)
    sheet = gc.open_by_url(os.environ["SPREADSHEET_URL"])
    worksheet = sheet.get_worksheet(0)

    settings = worksheet.get_all_values()

    if not settings:
        raise ValueError("No settings found")

    # Validate columns
    missing = set(Setting._fields) - set(settings[0])
    if missing:
        raise ValueError(f"Missing required fields: {missing}")

    # convert to a list of named tuples
    settings = [Setting(*row) for row in settings[1:]]  # skip header row

    return settings
