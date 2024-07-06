import json
import os
from functools import cache

import gspread
import pydantic
import yaml
from icontract import ensure
from reretry import retry

from settings import Setting


class Client(pydantic.BaseModel, extra="allow"):
    name: str
    spreadsheet_url: str
    alert_chat: str
    alert_account: str | int

    def load_settings(self) -> list[Setting]:
        data = get_worksheet(self.spreadsheet_url).get_all_values()
        fields = list(Setting.model_fields.keys())

        self.settings = [Setting(**dict(zip(fields, row))) for row in data[1:]]

        self.check_for_duplicate_chat_ids()

        return self.settings

    def check_for_duplicate_chat_ids(self):
        # store duplicate chat_ids in a list
        processed = []
        for setting in self.settings:
            key = (setting.chat_id, setting.text)
            if key in processed:
                setting.error = "Error: Повторяющееся название чата и сообщение"
                setting.active = 0
            else:
                processed.append(key)  # add to list if not duplicate

    def update_settings_in_gsheets(self, fields: list[str]):
        """Get data from self.settings and write it to corresponding columns in Google Sheets.

        Args:
            fields (list[str]): A list of fields from Setting model to write to Google Sheets.
        """

        sheet: gspread.Worksheet = get_worksheet(self.spreadsheet_url)

        if isinstance(fields, str):
            fields = [fields]

        for field in fields:
            col_num = list(Setting.model_fields.keys()).index(field)
            col_letter = chr(ord("A") + col_num)
            range_str = f"{col_letter}2:{col_letter}{len(self.settings) + 1}"
            data = [[getattr(setting, field)] for setting in self.settings]
            sheet.update(range_str, data)


def load_clients():
    with open("clients.yaml", "r") as f:
        return [
            Client(name=name, **content) for name, content in yaml.safe_load(f).items()
        ]


@cache
@ensure(lambda result: result, "Cannot load data from Google Sheets")
@retry(tries=3)
def get_worksheet(spreadsheet_url) -> gspread.Worksheet:
    sheet = get_google_client().open_by_url(spreadsheet_url)
    return sheet.get_worksheet(0)


@cache
@ensure(lambda result: result, "Cannot load data from Google Sheets")
@retry(tries=3)
def get_google_client():
    service_string = os.environ["GOOGLE_SERVICE_ACCOUNT"]
    service_dict = json.loads(service_string)
    return gspread.service_account_from_dict(service_dict)
