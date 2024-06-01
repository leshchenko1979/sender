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
        return self.settings

    def write_errors_to_settings(self, errors: dict[str, str]):
        worksheet = get_worksheet(self.spreadsheet_url)

        ERROR_COL = len(Setting.model_fields.keys()) + 1

        for i, row in enumerate(self.settings):
            row_hash = row.get_hash()
            if row_hash in errors:
                worksheet.update_cell(i + 2, ERROR_COL, errors[row_hash])
            else:
                worksheet.update_cell(i + 2, ERROR_COL, "")


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
