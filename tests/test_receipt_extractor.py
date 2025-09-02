"""
Unit tests for ReceiptExtractor (no real API calls).
We mock OpenAI chat.completions.create and set env vars via monkeypatch.
"""

from __future__ import annotations
import json
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from src.config import Config
from src.receipt_extractor import ReceiptExtractor


class DummyResp:
    """Minimal stub for OpenAI chat.completions.create response."""
    def __init__(self, content: str) -> None:
        self.choices = [type("obj", (), {"message": type("msg", (), {"content": content})})]


@pytest.fixture
def fake_image(tmp_path: Path) -> Path:
    """Create a small valid JPEG image."""
    p = tmp_path / "fake.jpg"
    Image.new("RGB", (24, 24), color="white").save(p)
    return p


class TestReceiptExtractor:
    """Tests for ReceiptExtractor class."""

    @staticmethod
    def _prepare_extractor(monkeypatch: Any) -> ReceiptExtractor:
        """Build extractor with fake env (no real .env needed)."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-dummy")
        monkeypatch.setenv("OPENAI_REQUEST_TIMEOUT", "5")
        cfg = Config()
        return ReceiptExtractor(cfg)

    def test_extract_full_ok(self, monkeypatch: Any, fake_image: Path) -> None:
        """Happy path: all fields present and normalized."""
        extractor = self._prepare_extractor(monkeypatch)

        def fake_create(*args: Any, **kwargs: Any) -> DummyResp:
            payload = {
                "bet_time": "2025-08-19 14:32:05",
                "match": "Team A vs Team B",
                "outcome": "P0 1",
                "odds": "1,87",
                "stake": "25.00",
                "source_image_id": "fake.jpg",
            }
            return DummyResp(json.dumps(payload))

        monkeypatch.setattr(extractor.client.chat.completions, "create", fake_create)

        result = extractor.extract(str(fake_image))
        assert result == {
            "bet_time": "2025-08-19 14:32:05",
            "match": "Team A vs Team B",
            "outcome": "P0 1",
            "odds": 1.87,
            "stake": 25.0,
            "source_image_id": "fake.jpg",
        }

    def test_extract_missing_fields(self, monkeypatch: Any, fake_image: Path) -> None:
        """Missing fields must become None; schema must remain fixed."""
        extractor = self._prepare_extractor(monkeypatch)

        def fake_create(*args: Any, **kwargs: Any) -> DummyResp:
            return DummyResp(json.dumps({}))  # empty JSON

        monkeypatch.setattr(extractor.client.chat.completions, "create", fake_create)

        result = extractor.extract(str(fake_image))
        assert list(result.keys()) == [
            "bet_time",
            "match",
            "outcome",
            "odds",
            "stake",
            "source_image_id",
        ]
        assert result["bet_time"] is None
        assert result["match"] is None
        assert result["outcome"] is None
        assert result["odds"] is None
        assert result["stake"] is None
        assert result["source_image_id"] == "fake.jpg"

    def test_file_not_found(self, monkeypatch: Any) -> None:
        """Nonexistent image should raise FileNotFoundError."""
        extractor = self._prepare_extractor(monkeypatch)
        with pytest.raises(FileNotFoundError):
            extractor.extract("samples/does_not_exist.jpg")
