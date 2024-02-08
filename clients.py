import pydantic
import yaml


class Client(pydantic.BaseModel):
    name: str
    spreadsheet_url: str
    alert_chat: str
    alert_account: str | int


def load_clients():
    with open("clients.yaml", "r") as f:
        return [
            Client(name=name, **content) for name, content in yaml.safe_load(f).items()
        ]
