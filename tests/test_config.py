import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_settings_fail_when_required_env_is_missing(monkeypatch):
    monkeypatch.delenv("DATABASE_URL")
    monkeypatch.delenv("CORS_ORIGINS")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)
