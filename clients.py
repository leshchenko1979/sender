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

        self.settings = []
        for row in data[1:]:
            setting = Setting(**dict(zip(fields, row)))
            setting.error = ""
            self.settings.append(setting)

        return self.settings

    def write_errors_to_gsheets(self):
        ERROR_COL = list(Setting.model_fields.keys()).index("error") + 1

        sheet: gspread.Worksheet = get_worksheet(self.spreadsheet_url)

        cell_list = sheet.range(2, ERROR_COL, len(self.settings) + 1, ERROR_COL)

        for cell, setting in zip(cell_list, self.settings):
            cell.value = setting.error

        sheet.update_cells(cell_list)


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
