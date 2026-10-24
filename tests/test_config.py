"""
Unit tests for Config module.
"""

from __future__ import annotations
from typing import Any
import pytest

from src.config import Config


class TestConfig:
    """Tests for Config environment variables loading and defaults."""

    def test_missing_api_key_raises_error(self, monkeypatch: Any) -> None:
        """Missing OPENAI_API_KEY should raise RuntimeError."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        with pytest.raises(RuntimeError, match="OPENAI_API_KEY is missing"):
            Config()

    def test_config_defaults_and_custom(self, monkeypatch: Any) -> None:
        """Check loading of custom timeout, model, and base_url."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-custom-key")
        monkeypatch.setenv("OPENAI_REQUEST_TIMEOUT", "45")
        monkeypatch.setenv("OPENAI_MODEL", "gpt-4o")
        monkeypatch.setenv("OPENAI_BASE_URL", "https://proxy.example.com/v1")
        monkeypatch.setenv("OPENAI_MAX_RETRIES", "5")

        cfg = Config()
        assert cfg.api_key == "sk-custom-key"
        assert cfg.timeout == 45
        assert cfg.model == "gpt-4o"
        assert cfg.base_url == "https://proxy.example.com/v1"
        assert cfg.max_retries == 5

    def test_invalid_timeout_fallback(self, monkeypatch: Any) -> None:
        """Non-integer timeout should fall back to default 30."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-key")
        monkeypatch.setenv("OPENAI_REQUEST_TIMEOUT", "invalid")

        cfg = Config()
        assert cfg.timeout == 30

    def test_minimum_boundaries_for_timeout_and_retries(self, monkeypatch: Any) -> None:
        """Zero or negative values should be normalized to at least 1."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-key")
        monkeypatch.setenv("OPENAI_REQUEST_TIMEOUT", "-10")
        monkeypatch.setenv("OPENAI_MAX_RETRIES", "0")

        cfg = Config()
        assert cfg.timeout >= 1
        assert cfg.max_retries >= 1
