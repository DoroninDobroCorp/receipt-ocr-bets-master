"""
Receipt Extractor module
------------------------
Handles interaction with OpenAI API and normalizes results.
"""

from __future__ import annotations
import json
import re
from pathlib import Path
from typing import Any, Dict, Optional

from openai import OpenAI, APIConnectionError, APITimeoutError, RateLimitError
from .config import Config
from .image_processor import ImageProcessor


class ReceiptExtractor:
    """Core class responsible for interacting with OpenAI and extracting structured data."""

    SYSTEM_PROMPT: str = (
        "You extract fields from betting receipts. "
        "Return ONLY one JSON object with EXACT keys in THIS ORDER: "
        "bet_time, match, outcome, odds, stake, source_image_id. "
        "Rules: "
        "(1) bet_time = TICKET CREATION TIME printed near the ticket id/header (often includes seconds, e.g. '08/03/2025 20:25:36'). "
        "Do NOT use the match start time shown in the market block. "
        "(2) outcome = exact market selection (keep punctuation: 'HANDICAP 0:2'; if market says 'MATCH RESULT 1' → outcome '1'). "
        "(3) odds and stake are floats (convert commas to dots), ignore currency symbols. "
        "(4) Missing/unreadable → null. "
        "(5) No extra keys or text outside JSON."
    )

    def __init__(self, config: Config) -> None:
        """
        Initialize the ReceiptExtractor with API client.

        Args:
            config (Config): Loaded configuration with API key and timeout.
        """
        self.client: OpenAI = OpenAI(api_key=config.api_key, timeout=config.timeout)

    @staticmethod
    def _to_float(v: Any) -> Optional[float]:
        """Convert value to float, handling commas and empty strings."""
        try:
            if v is None:
                return None
            if isinstance(v, str):
                v = v.replace(",", ".").strip()
            return float(v)
        except Exception:
            return None

    @staticmethod
    def _to_str(v: Any) -> Optional[str]:
        """Convert value to str, stripping whitespace, or None if empty."""
        if v is None:
            return None
        s = str(v).strip()
        return s if s else None

    def _normalize(self, payload: Dict[str, Any], image_name: str) -> Dict[str, Any]:
        """
        Normalize AI response to a strict schema.

        Args:
            payload (Dict[str, Any]): Raw response dictionary.
            image_name (str): Image filename as fallback for source_image_id.

        Returns:
            Dict[str, Any]: Normalized dict with fixed keys.
        """
        out = self._to_str(payload.get("outcome"))
        if out:
            # Keep 'HANDICAP 0:2' instead of '0.2'
            out = re.sub(r"(?i)\b(handicap\s+)(\d)\.(\d)\b", r"\1\2:\3", out)
            # Map 'MATCH RESULT 1'/'RESULT 1' → '1'
            m = re.search(
                r"(?i)\b(match\s+result|result)\s*[:\-]?\s*([12X])\b", out
                )
            if m:
                out = m.group(2)

        bet = self._to_str(payload.get("bet_time"))

        # Fallback: if model returned only 'HH:MM[:SS]',
        # try to stitch date from filename like 'photo_YYYY-MM-DD_HH-MM-SS.jpg'
        if bet and re.fullmatch(r"\d{2}:\d{2}(:\d{2})?", bet):
            m = re.search(
                r"(\d{4})-(\d{2})-(\d{2})[_-](\d{2})-(\d{2})-(\d{2})",
                image_name
                )
            if m:
                bet = f"{m.group(1)}-{m.group(2)}-{m.group(3)} {m.group(4)}:{m.group(5)}:{m.group(6)}"
        return {
            "bet_time": bet,
            "match": self._to_str(payload.get("match")),
            "outcome": out,
            "odds": self._to_float(payload.get("odds")),
            "stake": self._to_float(payload.get("stake")),
            "source_image_id": self._to_str(
                payload.get("source_image_id")
                ) or image_name,
        }

    def extract(self, image_path: str) -> Dict[str, Any]:
        """
        Extract structured data from a betting receipt image.

        Args:
            image_path (str): Path to the receipt image.

        Returns:
            Dict[str, Any]: Normalized JSON object with betting fields.
        """
        p = Path(image_path)
        if not p.exists() or not p.is_file():
            raise FileNotFoundError(f"Image not found: {image_path}")

        b64 = ImageProcessor.encode_to_base64(p)

        try:
            resp = self.client.chat.completions.create(
                model="gpt-4o-mini",
                temperature=0,
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "Return EXACT JSON with required keys only."
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{b64}",
                                    "detail": "high",
                                    # ask model to inspect carefully
                                },
                            },
                        ],
                    },
                ],
                response_format={"type": "json_object"},
            )
        except (APITimeoutError, APIConnectionError) as e:
            raise TimeoutError(f"AI request timeout/connection error: {e}") from e
        except RateLimitError as e:
            raise RuntimeError(f"AI rate limit exceeded: {e}") from e
        except Exception as e:
            raise RuntimeError(f"AI request failed: {e}") from e

        raw = resp.choices[0].message.content
        if not raw:
            raise RuntimeError("Empty AI response.")

        data = json.loads(raw)
        return self._normalize(data, p.name)
