import pytest

from src.core.settings import Setting


@pytest.fixture
def setting_factory():
    """Factory to build Setting instances with sensible defaults."""

    def _build(**overrides):
        data = {
            "active": True,
            "account": "71234567890",
            "schedule": "* * * * *",
            "chat_id": "test_chat",
            "text": "Hello",
        }
        data.update(overrides)
        return Setting(**data)

    return _build
