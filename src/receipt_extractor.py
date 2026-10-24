"""
Receipt Extractor module
------------------------
Handles interaction with OpenAI Vision API and normalizes extracted betting receipt data.
"""

from __future__ import annotations
import json
import re
from pathlib import Path
from typing import Any, Dict, Optional

from openai import OpenAI, APIConnectionError, APITimeoutError, RateLimitError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .config import Config
from .image_processor import ImageProcessor
from .models import ReceiptOutput


class ReceiptExtractor:
    """Core class responsible for interacting with OpenAI and extracting structured data."""

    SYSTEM_PROMPT: str = (
        "You are an expert AI system for extracting structured data from sports betting ticket slips and receipts.\n"
        "Return ONLY a single valid JSON object with EXACTLY these keys in THIS ORDER:\n"
        "bet_time, match, outcome, odds, stake, source_image_id.\n\n"
        "Field extraction guidelines:\n"
        "1. bet_time: The timestamp when the bet ticket was created/placed (often printed near header, acceptance time, or ticket ID).\n"
        "   - Normalize to 'YYYY-MM-DD HH:MM:SS' if date and time are both present.\n"
        "   - If only time is visible, return 'HH:MM:SS'.\n"
        "   - Do NOT confuse ticket creation time with the scheduled match kickoff time.\n"
        "2. match: The competing teams or players (e.g. 'Team A - Team B' or 'Team A vs Team B').\n"
        "   - EXCLUDE tournament, league, sport, or country names (e.g. omit 'Football - Senegal Coupes Nationales' or 'Liga TDP').\n"
        "3. outcome: The specific chosen selection/prediction (e.g. '1', 'X', '2', 'HANDICAP 0:2', 'Over 2.5', 'ug 0-1').\n"
        "   - Do NOT return the market category/question title (e.g. if the ticket says 'Who will win the match?' or 'MATCH RESULT' and selection is '1', outcome must be '1').\n"
        "4. odds: The decimal betting odds multiplier as a number (e.g. 1.87, 2.10, 3.76). Convert commas to dots.\n"
        "5. stake: Total stake/amount wagered as a number (e.g. 100.00, 25.00). Exclude currency symbols (EUR, USD, etc.).\n"
        "6. source_image_id: The unique ticket ID, slip number, or barcode serial string printed on the ticket slip. If not printed, return null.\n"
        "7. For any missing, unreadable, or unavailable field, set its value to null.\n"
        "8. Do not output any markdown, explanations, or text outside the JSON."
    )

    def __init__(self, config: Config) -> None:
        """
        Initialize ReceiptExtractor with API client configuration.

        Args:
            config (Config): Configuration containing API key, timeout, model, base_url.
        """
        self.config = config
        client_kwargs: Dict[str, Any] = {
            "api_key": config.api_key,
            "timeout": config.timeout,
        }
        if config.base_url:
            client_kwargs["base_url"] = config.base_url
        self.client: OpenAI = OpenAI(**client_kwargs)

    @staticmethod
    def _to_float(v: Any) -> Optional[float]:
        """Convert value to float, handling commas and empty strings."""
        if v is None:
            return None
        try:
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

    @classmethod
    def _normalize_datetime(cls, raw: Any, image_name: str) -> Optional[str]:
        """
        Normalize date/time string to 'YYYY-MM-DD HH:MM:SS' or 'HH:MM:SS'.
        Supports common European betting slip date formats and day-of-week prefixes.
        """
        if not raw:
            return None
        s = str(raw).strip()

        # Remove leading day-of-week prefixes like "Pet. ", "Sub. ", "Mon ", "ne19:35"
        s = re.sub(r"^(?:[A-Za-zА-Яа-я]{2,4}\.?\s*|\b[a-z]{2}\b\s*)", "", s).strip()

        # Already normalized: YYYY-MM-DD HH:MM:SS
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}", s):
            return re.sub(r"\s+", " ", s)

        # DD/MM/YYYY or DD.MM.YYYY or DD-MM-YYYY (with optional 2-digit year) + time
        m = re.match(
            r"^(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})\s+(\d{1,2}:\d{2}(?::\d{2})?)$",
            s,
        )
        if m:
            d, mon, y, t = int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4)
            if y < 100:
                y += 2000
            parts = t.split(":")
            if len(parts) == 2:
                t = f"{int(parts[0]):02d}:{int(parts[1]):02d}:00"
            else:
                t = f"{int(parts[0]):02d}:{int(parts[1]):02d}:{int(parts[2]):02d}"
            return f"{y:04d}-{mon:02d}-{d:02d} {t}"

        # If time only: HH:MM:SS or HH:MM
        if re.fullmatch(r"\d{1,2}:\d{2}(?::\d{2})?", s):
            parts = s.split(":")
            t = (
                f"{int(parts[0]):02d}:{int(parts[1]):02d}:{int(parts[2]):02d}"
                if len(parts) == 3
                else f"{int(parts[0]):02d}:{int(parts[1]):02d}:00"
            )
            # If filename contains date pattern (e.g. photo_YYYY-MM-DD_...), stitch it
            mf = re.search(r"(\d{4})-(\d{2})-(\d{2})", image_name)
            if mf:
                return f"{mf.group(1)}-{mf.group(2)}-{mf.group(3)} {t}"
            return t

        return s

    @classmethod
    def _normalize_outcome(cls, raw: Any) -> Optional[str]:
        """Normalize outcome string (clean up handicap formatting and market names)."""
        if not raw:
            return None
        s = str(raw).strip()

        # Fix dot notation in handicap: 'HANDICAP 0.2' -> 'HANDICAP 0:2'
        s = re.sub(r"(?i)\b(handicap\s+)(\d)\.(\d)\b", r"\1\2:\3", s)

        # Strip leading 'Tip:' / 'Tip '
        s = re.sub(r"(?i)^tip\s*[:\-]?\s*", "", s).strip()

        # Map 'MATCH RESULT 1' / 'RESULT: X' / 'Who will win the match? 1' -> '1' / 'X'
        m = re.search(
            r"(?i)(?:match\s+result|result|who\s+will\s+win(?:\s+the\s+match)?)[^\w]*\b([12X])\b",
            s,
        )
        if m:
            return m.group(1).upper()

        return s

    @classmethod
    def _normalize_match(cls, raw: Any) -> Optional[str]:
        """Normalize match string (strip leading sport tags)."""
        if not raw:
            return None
        s = str(raw).strip()
        s = re.sub(
            r"(?i)^(?:football|soccer|basketball|tennis|hockey)\s*-\s*", "", s
        ).strip()
        return s or None

    def _normalize(self, payload: Dict[str, Any], image_name: str) -> Dict[str, Any]:
        """
        Normalize raw API payload to strict schema using Pydantic.

        Args:
            payload (Dict[str, Any]): Parsed JSON from model response.
            image_name (str): Filename as fallback for source_image_id.

        Returns:
            Dict[str, Any]: Strictly ordered dictionary adhering to the project schema.
        """
        # Validate through Pydantic
        output = ReceiptOutput.model_validate(payload)

        bet_time = self._normalize_datetime(output.bet_time, image_name)
        match = self._normalize_match(output.match)
        outcome = self._normalize_outcome(output.outcome)
        odds = self._to_float(output.odds)
        stake = self._to_float(output.stake)

        # Fallback to image filename if ticket ID was not found on receipt
        source_id = self._to_str(output.source_image_id) or image_name

        result = ReceiptOutput(
            bet_time=bet_time,
            match=match,
            outcome=outcome,
            odds=odds,
            stake=stake,
            source_image_id=source_id,
        )
        return result.to_dict()

    def _call_model_with_retry(self, b64: str) -> str:
        """Call OpenAI Vision completion with automatic exponential backoff retry."""

        @retry(
            stop=stop_after_attempt(self.config.max_retries),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type(
                (APITimeoutError, APIConnectionError, RateLimitError)
            ),
            reraise=True,
        )
        def _execute() -> str:
            resp = self.client.chat.completions.create(
                model=self.config.model,
                temperature=0,
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "Extract all betting fields into the specified JSON object.",
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{b64}",
                                    "detail": "high",
                                },
                            },
                        ],
                    },
                ],
                response_format={"type": "json_object"},
            )
            content = resp.choices[0].message.content
            if not content:
                raise RuntimeError("Empty AI response.")
            return content

        return _execute()

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
            raw = self._call_model_with_retry(b64)
        except (APITimeoutError, APIConnectionError) as e:
            raise TimeoutError(f"AI request timeout/connection error: {e}") from e
        except RateLimitError as e:
            raise RuntimeError(f"AI rate limit exceeded: {e}") from e
        except Exception as e:
            raise RuntimeError(f"AI request failed: {e}") from e

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Failed to parse AI response as JSON: {e}") from e

        return self._normalize(data, p.name)
