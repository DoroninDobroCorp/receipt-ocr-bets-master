"""
CLI entrypoint
--------------
Provides a command-line interface for running receipt extraction.
"""

from __future__ import annotations
import json
from pathlib import Path
from .config import Config
from .receipt_extractor import ReceiptExtractor


def run() -> None:
    """CLI entrypoint for receipt extraction."""
    import sys

    if len(sys.argv) < 2:
        print(json.dumps({
            "status": "error",
            "message": "Usage: poetry run python -m src.cli <image_path> [output.json]"
        }))
        raise SystemExit(2)

    image = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else None

    try:
        config = Config()
        extractor = ReceiptExtractor(config)
        result = extractor.extract(image)

        print(json.dumps(result, ensure_ascii=False, indent=2))
        if out:
            Path(out).write_text(json.dumps(result, ensure_ascii=False, indent=2))
            print(f"Saved → {out}")


    except TimeoutError as e:
        err = {"status": "timeout", "message": str(e)}
        print(json.dumps(err, ensure_ascii=False))
        _save_error(out, err)
        raise SystemExit(3)
    except FileNotFoundError as e:
        err = {"status": "error", "message": str(e)}
        print(json.dumps(err, ensure_ascii=False))
        _save_error(out, err)
        raise SystemExit(2)
    except Exception as e:
        err = {"status": "error", "message": str(e)}
        print(json.dumps(err, ensure_ascii=False))
        _save_error(out, err)
        raise SystemExit(1)


def _save_error(out_path: str | None, payload: dict) -> None:
    """Write error JSON to file when output path is provided."""
    if out_path:
        Path(out_path).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2)
        )


if __name__ == "__main__":
    run()
