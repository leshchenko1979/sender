import json
import os

import gspread
from icontract import ensure
import pydantic


class Setting(pydantic.BaseModel):
    active: bool
    account: str
    schedule: str
    chat_id: str
    text: str

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


def load_settings() -> list[Setting]:
    settings = load_from_gsheets()
    fields = list(Setting.model_fields.keys())
    return [Setting(**dict(zip(fields, row))) for row in settings[1:]]


@ensure(lambda result: result, "No settings found")
def load_from_gsheets():
    service_string = os.environ["GOOGLE_SERVICE_ACCOUNT"]
    service_dict = json.loads(service_string)
    gc = gspread.service_account_from_dict(service_dict)

    sheet = gc.open_by_url(os.environ["SPREADSHEET_URL"])
    worksheet = sheet.get_worksheet(0)

    return worksheet.get_all_values()
