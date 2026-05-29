"""Unit tests for Settings validation rules."""
import pytest
from pydantic import ValidationError

from pdf_epub.config import Settings


def test_development_settings_do_not_require_api_key() -> None:
    s = Settings(environment="development")
    assert not s.api_key


def test_production_settings_require_api_key() -> None:
    with pytest.raises(ValidationError, match="API_KEY must be set"):
        Settings(environment="production")


def test_production_settings_with_api_key_are_valid() -> None:
    s = Settings(environment="production", api_key="supersecret")
    assert s.is_production
    assert s.api_key == "supersecret"
