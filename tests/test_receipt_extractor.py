"""
Unit tests for ReceiptExtractor (no real API calls).
We mock OpenAI chat.completions.create and set env vars via monkeypatch.
"""

from __future__ import annotations
import json
from pathlib import Path
from typing import Any

import pytest
import httpx
from openai import APIConnectionError, APITimeoutError, RateLimitError
from PIL import Image

from src.config import Config
from src.receipt_extractor import ReceiptExtractor


class DummyResp:
    """Minimal stub for OpenAI chat.completions.create response."""

    def __init__(self, content: str) -> None:
        self.choices = [
            type("obj", (), {"message": type("msg", (), {"content": content})})
        ]


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
        monkeypatch.setenv("OPENAI_MAX_RETRIES", "2")
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

    def test_extract_markdown_code_fences(
        self, monkeypatch: Any, fake_image: Path
    ) -> None:
        """AI response wrapped in markdown ```json ... ``` blocks must be parsed."""
        extractor = self._prepare_extractor(monkeypatch)

        def fake_create(*args: Any, **kwargs: Any) -> DummyResp:
            raw_text = "```json\n{\n  \"match\": \"Team A - Team B\",\n  \"odds\": 1.95\n}\n```"
            return DummyResp(raw_text)

        monkeypatch.setattr(extractor.client.chat.completions, "create", fake_create)

        result = extractor.extract(str(fake_image))
        assert result["match"] == "Team A - Team B"
        assert result["odds"] == 1.95

    def test_extract_list_payload(
        self, monkeypatch: Any, fake_image: Path
    ) -> None:
        """AI response returning a list of dicts [{...}] should unpack cleanly."""
        extractor = self._prepare_extractor(monkeypatch)

        def fake_create(*args: Any, **kwargs: Any) -> DummyResp:
            raw_text = json.dumps([{"match": "Team A - Team B", "odds": 2.0}])
            return DummyResp(raw_text)

        monkeypatch.setattr(extractor.client.chat.completions, "create", fake_create)

        result = extractor.extract(str(fake_image))
        assert result["match"] == "Team A - Team B"
        assert result["odds"] == 2.0

    def test_extract_with_currency_in_stake_and_odds(
        self, monkeypatch: Any, fake_image: Path
    ) -> None:
        """Stake and odds with currencies and thousand separators must parse properly."""
        extractor = self._prepare_extractor(monkeypatch)

        def fake_create(*args: Any, **kwargs: Any) -> DummyResp:
            payload = {
                "bet_time": "2025-08-19 14:32:05",
                "match": "Team A vs Team B",
                "outcome": "1",
                "odds": "2.10x",
                "stake": "EUR 1.000,50",
            }
            return DummyResp(json.dumps(payload))

        monkeypatch.setattr(extractor.client.chat.completions, "create", fake_create)

        result = extractor.extract(str(fake_image))
        assert result["odds"] == 2.1
        assert result["stake"] == 1000.5

    def test_extract_missing_fields(self, monkeypatch: Any, fake_image: Path) -> None:
        """Missing fields must become None; schema and key order must remain fixed."""
        extractor = self._prepare_extractor(monkeypatch)

        def fake_create(*args: Any, **kwargs: Any) -> DummyResp:
            return DummyResp(json.dumps({}))

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

    def test_date_normalization(self, monkeypatch: Any, tmp_path: Path) -> None:
        """Verify normalizer handles multiple real-world ticket date patterns."""
        extractor = self._prepare_extractor(monkeypatch)

        # DD/MM/YYYY
        assert (
            extractor._normalize_datetime("08/03/2025 20:25:36", "test.jpg")
            == "2025-03-08 20:25:36"
        )
        # 12-hour AM/PM format
        assert (
            extractor._normalize_datetime("08/03/2025 08:25:36 PM", "test.jpg")
            == "2025-03-08 20:25:36"
        )
        assert (
            extractor._normalize_datetime("08/03/2025 08:25 AM", "test.jpg")
            == "2025-03-08 08:25:00"
        )
        # DD.MM.YYYY
        assert (
            extractor._normalize_datetime("12.03.2025 13:54:12", "test.jpg")
            == "2025-03-12 13:54:12"
        )
        # DD.MM.YY with 2-digit year
        assert (
            extractor._normalize_datetime("09.11.24 19:41:26", "test.jpg")
            == "2024-11-09 19:41:26"
        )
        # YYYY/MM/DD
        assert (
            extractor._normalize_datetime("2025/03/08 20:25:36", "test.jpg")
            == "2025-03-08 20:25:36"
        )
        # YYYY.MM.DD
        assert (
            extractor._normalize_datetime("2025.03.08 20:25:36", "test.jpg")
            == "2025-03-08 20:25:36"
        )
        # ISO with T and timezone Z
        assert (
            extractor._normalize_datetime("2025-03-08T20:25:36Z", "test.jpg")
            == "2025-03-08 20:25:36"
        )
        # ISO with fractional seconds
        assert (
            extractor._normalize_datetime("2025-03-08 20:25:36.456", "test.jpg")
            == "2025-03-08 20:25:36"
        )
        # Day of week prefix
        assert (
            extractor._normalize_datetime("Pet. 08.11.2024 11:03:04", "test.jpg")
            == "2024-11-08 11:03:04"
        )

        # Time-only with date in filename
        time_img = tmp_path / "photo_2025-03-08_20-48-40.jpg"
        Image.new("RGB", (10, 10)).save(time_img)
        assert (
            extractor._normalize_datetime("20:47:01", time_img.name)
            == "2025-03-08 20:47:01"
        )

    def test_outcome_normalization(self, monkeypatch: Any) -> None:
        """Verify outcome normalizer cleans market descriptions and punctuation."""
        extractor = self._prepare_extractor(monkeypatch)

        assert extractor._normalize_outcome("HANDICAP 0.2") == "HANDICAP 0:2"
        assert extractor._normalize_outcome("HANDICAP 0:3 2") == "HANDICAP 0:3 2"
        assert extractor._normalize_outcome("MATCH RESULT 1") == "1"
        assert extractor._normalize_outcome("RESULT: 2") == "2"
        assert extractor._normalize_outcome("RESULT - X") == "X"
        assert extractor._normalize_outcome("Who will win the match? 1") == "1"
        assert extractor._normalize_outcome("Tip: ug 0-1") == "ug 0-1"
        assert extractor._normalize_outcome("Over 2.5") == "Over 2.5"
        assert extractor._normalize_outcome("\"1\"") == "1"
        assert extractor._normalize_outcome("null") is None

    def test_match_normalization(self, monkeypatch: Any) -> None:
        """Verify match normalizer strips sport prefixes and normalizes spaces."""
        extractor = self._prepare_extractor(monkeypatch)

        assert (
            extractor._normalize_match("Football - Team A - Team B")
            == "Team A - Team B"
        )
        assert extractor._normalize_match("  Team A   vs   Team B  ") == "Team A vs Team B"
        assert extractor._normalize_match("null") is None

    def test_file_not_found(self, monkeypatch: Any) -> None:
        """Nonexistent image should raise FileNotFoundError."""
        extractor = self._prepare_extractor(monkeypatch)
        with pytest.raises(FileNotFoundError):
            extractor.extract("samples/does_not_exist.jpg")

    def test_empty_ai_response(self, monkeypatch: Any, fake_image: Path) -> None:
        """Empty AI response should raise RuntimeError."""
        extractor = self._prepare_extractor(monkeypatch)

        def fake_create(*args: Any, **kwargs: Any) -> DummyResp:
            return DummyResp("")

        monkeypatch.setattr(extractor.client.chat.completions, "create", fake_create)
        with pytest.raises(RuntimeError, match="Empty AI response"):
            extractor.extract(str(fake_image))

    def test_invalid_json_response(self, monkeypatch: Any, fake_image: Path) -> None:
        """Malformed JSON from AI should raise RuntimeError."""
        extractor = self._prepare_extractor(monkeypatch)

        def fake_create(*args: Any, **kwargs: Any) -> DummyResp:
            return DummyResp("{not-valid-json}")

        monkeypatch.setattr(extractor.client.chat.completions, "create", fake_create)
        with pytest.raises(RuntimeError, match="Failed to parse AI response"):
            extractor.extract(str(fake_image))

    def test_retry_on_transient_failure_then_succeed(
        self, monkeypatch: Any, fake_image: Path
    ) -> None:
        """Tenacity retries on transient connection error and succeeds on subsequent try."""
        extractor = self._prepare_extractor(monkeypatch)
        calls = 0

        def flaky_create(*args: Any, **kwargs: Any) -> DummyResp:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise APIConnectionError(request=None)
            payload = {
                "bet_time": "2025-08-19 14:32:05",
                "match": "Team A - Team B",
                "outcome": "1",
                "odds": 1.5,
                "stake": 10.0,
            }
            return DummyResp(json.dumps(payload))

        monkeypatch.setattr(extractor.client.chat.completions, "create", flaky_create)

        result = extractor.extract(str(fake_image))
        assert calls == 2
        assert result["odds"] == 1.5

    def test_api_timeout_error(self, monkeypatch: Any, fake_image: Path) -> None:
        """APITimeoutError exhausted retries should be converted to TimeoutError."""
        extractor = self._prepare_extractor(monkeypatch)

        def fake_create(*args: Any, **kwargs: Any) -> DummyResp:
            raise APITimeoutError(request=None)

        monkeypatch.setattr(extractor.client.chat.completions, "create", fake_create)
        with pytest.raises(TimeoutError, match="AI request timeout"):
            extractor.extract(str(fake_image))

    def test_rate_limit_error(self, monkeypatch: Any, fake_image: Path) -> None:
        """RateLimitError exhausted retries should raise RuntimeError."""
        extractor = self._prepare_extractor(monkeypatch)

        def fake_create(*args: Any, **kwargs: Any) -> DummyResp:
            resp = httpx.Response(
                429, request=httpx.Request("POST", "https://api.openai.com/v1")
            )
            raise RateLimitError(message="rate limit hit", response=resp, body=None)

        monkeypatch.setattr(extractor.client.chat.completions, "create", fake_create)
        with pytest.raises(RuntimeError, match="AI rate limit exceeded"):
            extractor.extract(str(fake_image))
