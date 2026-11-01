import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_settings_fail_when_required_env_is_missing(monkeypatch):
    monkeypatch.delenv("DATABASE_URL")
    monkeypatch.delenv("CORS_ORIGINS")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_anthropic_api_key_defaults_to_empty(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    assert Settings(_env_file=None).anthropic_api_key == ""


def test_anthropic_api_key_is_read_from_the_environment(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k-1")

    assert Settings(_env_file=None).anthropic_api_key == "k-1"
