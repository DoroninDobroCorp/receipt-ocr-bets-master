"""
Unit tests for CLI interface.
"""

from __future__ import annotations
import json
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from src.cli import run, _save_error
from src.receipt_extractor import ReceiptExtractor


class DummyResp:
    def __init__(self, content: str) -> None:
        self.choices = [
            type("obj", (), {"message": type("msg", (), {"content": content})})
        ]


class TestCLI:
    """CLI tests covering arguments, outputs, error handling, and directory creation."""

    def test_cli_no_args_exits_2(self, monkeypatch: Any, capsys: Any) -> None:
        """Invoking CLI without args must print JSON error and exit with code 2."""
        monkeypatch.setattr("sys.argv", ["cli.py"])
        with pytest.raises(SystemExit) as exc:
            run()
        assert exc.value.code == 2

        out, _ = capsys.readouterr()
        data = json.loads(out)
        assert data["status"] == "error"
        assert "Usage:" in data["message"]

    def test_cli_help_flag_exits_2(self, monkeypatch: Any, capsys: Any) -> None:
        """Invoking CLI with -h / --help must print usage and exit with code 2."""
        monkeypatch.setattr("sys.argv", ["cli.py", "--help"])
        with pytest.raises(SystemExit) as exc:
            run()
        assert exc.value.code == 2

        out, _ = capsys.readouterr()
        data = json.loads(out)
        assert data["status"] == "error"
        assert "Usage:" in data["message"]

    def test_cli_file_not_found_exits_2(self, monkeypatch: Any, capsys: Any) -> None:
        """Nonexistent image must output error JSON and exit with code 2."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-dummy")
        monkeypatch.setattr("sys.argv", ["cli.py", "does_not_exist.jpg"])

        with pytest.raises(SystemExit) as exc:
            run()
        assert exc.value.code == 2

        out, _ = capsys.readouterr()
        data = json.loads(out)
        assert data["status"] == "error"
        assert "Image not found" in data["message"]

    def test_cli_timeout_exits_3(
        self, monkeypatch: Any, tmp_path: Path, capsys: Any
    ) -> None:
        """TimeoutError in extractor should exit with code 3."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-dummy")
        img_path = tmp_path / "valid.jpg"
        Image.new("RGB", (20, 20), color="white").save(img_path)

        monkeypatch.setattr("sys.argv", ["cli.py", str(img_path)])

        def fake_extract(*args: Any, **kwargs: Any) -> None:
            raise TimeoutError("AI request timeout/connection error: timed out")

        monkeypatch.setattr(ReceiptExtractor, "extract", fake_extract)

        with pytest.raises(SystemExit) as exc:
            run()
        assert exc.value.code == 3

        out, _ = capsys.readouterr()
        data = json.loads(out)
        assert data["status"] == "timeout"

    def test_cli_unexpected_error_exits_1(
        self, monkeypatch: Any, tmp_path: Path, capsys: Any
    ) -> None:
        """Unexpected RuntimeError in extractor should exit with code 1."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-dummy")
        img_path = tmp_path / "valid.jpg"
        Image.new("RGB", (20, 20), color="white").save(img_path)

        monkeypatch.setattr("sys.argv", ["cli.py", str(img_path)])

        def fake_extract(*args: Any, **kwargs: Any) -> None:
            raise RuntimeError("Unexpected failure")

        monkeypatch.setattr(ReceiptExtractor, "extract", fake_extract)

        with pytest.raises(SystemExit) as exc:
            run()
        assert exc.value.code == 1

        out, _ = capsys.readouterr()
        data = json.loads(out)
        assert data["status"] == "error"
        assert "Unexpected failure" in data["message"]

    def test_cli_success_and_save_to_nested_folder(
        self, monkeypatch: Any, tmp_path: Path, capsys: Any
    ) -> None:
        """CLI creates parent directory and outputs pure JSON on stdout."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-dummy")
        img_path = tmp_path / "valid.jpg"
        Image.new("RGB", (20, 20), color="white").save(img_path)

        out_path = tmp_path / "nested" / "dir" / "result.json"
        monkeypatch.setattr("sys.argv", ["cli.py", str(img_path), str(out_path)])

        fake_payload = {
            "bet_time": "2025-08-19 14:32:05",
            "match": "Team A vs Team B",
            "outcome": "1",
            "odds": 2.1,
            "stake": 100.0,
            "source_image_id": "valid.jpg",
        }

        monkeypatch.setattr(
            ReceiptExtractor,
            "_call_model_with_retry",
            lambda self, b64: json.dumps(fake_payload),
        )

        run()

        # Check stdout is strictly parseable JSON
        out, err = capsys.readouterr()
        parsed = json.loads(out)
        assert parsed["match"] == "Team A vs Team B"
        assert "Saved →" in err

        # Check file was written in nested dir
        assert out_path.exists()
        saved_data = json.loads(out_path.read_text(encoding="utf-8"))
        assert saved_data["odds"] == 2.1

    def test_save_error_creates_directory_safely(self, tmp_path: Path) -> None:
        """_save_error safely creates missing directory structure."""
        out_path = tmp_path / "sub" / "error.json"
        err_payload = {"status": "error", "message": "test"}
        _save_error(str(out_path), err_payload)

        assert out_path.exists()
        saved = json.loads(out_path.read_text(encoding="utf-8"))
        assert saved["status"] == "error"
