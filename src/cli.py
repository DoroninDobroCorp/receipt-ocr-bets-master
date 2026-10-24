"""
CLI entrypoint
--------------
Provides a command-line interface for running receipt extraction.
"""

from __future__ import annotations
import json
import sys
from pathlib import Path
from typing import Optional

# Support direct execution via `python src/cli.py`
if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import Config
from src.receipt_extractor import ReceiptExtractor


def _resolve_output_path(path_str: str, image_path_str: str) -> Path:
    """
    Resolve output path. If a directory or trailing slash is provided,
    generate filename based on the source image stem.
    """
    p = Path(path_str)
    if p.is_dir() or path_str.endswith(("/", "\\")):
        p.mkdir(parents=True, exist_ok=True)
        img_stem = Path(image_path_str).stem or "receipt"
        return p / f"{img_stem}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _write_json_file(path_str: str, payload: dict, image_path_str: str = "") -> Path:
    """Write JSON payload to a file, safely creating parent directories if needed."""
    target = _resolve_output_path(path_str, image_path_str)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def _save_error(out_path: Optional[str], payload: dict, image_path_str: str = "") -> None:
    """Write error JSON to file when output path is provided."""
    if out_path:
        try:
            _write_json_file(out_path, payload, image_path_str)
        except Exception as e:
            sys.stderr.write(f"Warning: Failed to write error output to '{out_path}': {e}\n")


def run() -> None:
    """CLI entrypoint for receipt extraction."""
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(
            json.dumps(
                {
                    "status": "error",
                    "message": "Usage: poetry run python -m src.cli <image_path> [output.json]",
                },
                ensure_ascii=False,
            )
        )
        raise SystemExit(2)

    image = sys.argv[1]
    out: Optional[str] = sys.argv[2] if len(sys.argv) > 2 else None

    try:
        config = Config()
        extractor = ReceiptExtractor(config)
        result = extractor.extract(image)

        # Print strictly valid JSON to stdout
        print(json.dumps(result, ensure_ascii=False, indent=2))

        if out:
            saved_file = _write_json_file(out, result, image)
            # Log informational message to stderr to avoid corrupting stdout JSON stream
            sys.stderr.write(f"Saved → {saved_file}\n")

    except TimeoutError as e:
        err = {"status": "timeout", "message": str(e)}
        print(json.dumps(err, ensure_ascii=False))
        _save_error(out, err, image)
        raise SystemExit(3)
    except FileNotFoundError as e:
        err = {"status": "error", "message": str(e)}
        print(json.dumps(err, ensure_ascii=False))
        _save_error(out, err, image)
        raise SystemExit(2)
    except Exception as e:
        err = {"status": "error", "message": str(e)}
        print(json.dumps(err, ensure_ascii=False))
        _save_error(out, err, image)
        raise SystemExit(1)


if __name__ == "__main__":
    run()
