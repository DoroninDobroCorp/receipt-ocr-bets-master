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
from .models import ReceiptOutput, parse_numeric_float


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
        """Convert value to float, handling currencies, commas, and empty strings."""
        return parse_numeric_float(v)

    @staticmethod
    def _to_str(v: Any) -> Optional[str]:
        """Convert value to str, stripping whitespace, or None if empty or invalid."""
        if v is None or isinstance(v, (bool, dict, list)):
            return None
        s = str(v).strip()
        if s.lower() in ("null", "none"):
            return None
        return s if s else None

    @classmethod
    def _parse_time_string(cls, t_raw: str) -> str:
        """Parse time string with optional 12-hour AM/PM format into 24-hour HH:MM:SS."""
        t_clean = t_raw.strip()
        am_pm_match = re.search(r"(?i)\b(am|pm)\b", t_clean)
        am_pm = am_pm_match.group(1).upper() if am_pm_match else None
        numeric_part = re.sub(r"(?i)\s*(?:am|pm)\s*", "", t_clean).strip()

        parts = [int(p) for p in numeric_part.split(":")]
        h = parts[0]
        m = parts[1]
        s = parts[2] if len(parts) > 2 else 0

        if am_pm == "PM" and h < 12:
            h += 12
        elif am_pm == "AM" and h == 12:
            h = 0

        return f"{h:02d}:{m:02d}:{s:02d}"

    @classmethod
    def _normalize_datetime(cls, raw: Any, image_name: str) -> Optional[str]:
        """
        Normalize date/time string to 'YYYY-MM-DD HH:MM:SS' or 'HH:MM:SS'.
        Supports European/US betting slip date formats, ISO formats, AM/PM, and day prefixes.
        """
        if raw is None or isinstance(raw, (bool, dict, list)):
            return None
        s = str(raw).strip()
        if not s or s.lower() in ("null", "none"):
            return None

        # Remove leading day-of-week prefixes like "Pet. ", "Sub. ", "Mon ", "ne"
        s = re.sub(r"^(?:[A-Za-zА-Яа-я]{2,4}\.?\s*|\b[a-z]{2}\b\s*)", "", s).strip()
        # Remove trailing timezone identifiers or offsets like "Z", "UTC", "+02:00"
        s = re.sub(r"(?i)\s*(?:z|utc|[+-]\d{2}:?\d{2})\s*$", "", s).strip()

        # 1. Year first: YYYY/MM/DD, YYYY.MM.DD, YYYY-MM-DD (with T or space, optional ms & am/pm)
        m_year = re.match(
            r"^(\d{4})[/.-](\d{1,2})[/.-](\d{1,2})[T\s]+(\d{1,2}:\d{2}(?::\d{2})?(?:\s*[AaPp][Mm])?)(?:\.\d+)?$",
            s,
        )
        if m_year:
            y, mon, d, t = (
                int(m_year.group(1)),
                int(m_year.group(2)),
                int(m_year.group(3)),
                m_year.group(4),
            )
            # If month > 12 and day <= 12, swap
            if mon > 12 and 1 <= d <= 12:
                d, mon = mon, d
            if 1 <= mon <= 12 and 1 <= d <= 31:
                t_norm = cls._parse_time_string(t)
                return f"{y:04d}-{mon:02d}-{d:02d} {t_norm}"

        # 2. Day/Month first: DD/MM/YYYY, MM/DD/YYYY, DD.MM.YYYY, DD-MM-YYYY
        m_day = re.match(
            r"^(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})[T\s]+(\d{1,2}:\d{2}(?::\d{2})?(?:\s*[AaPp][Mm])?)(?:\.\d+)?$",
            s,
        )
        if m_day:
            d, mon, y, t = (
                int(m_day.group(1)),
                int(m_day.group(2)),
                int(m_day.group(3)),
                m_day.group(4),
            )
            if y < 100:
                y += 2000
            # If month > 12 and day <= 12, it is US format (MM/DD/YYYY)
            if mon > 12 and 1 <= d <= 12:
                d, mon = mon, d
            if 1 <= mon <= 12 and 1 <= d <= 31:
                t_norm = cls._parse_time_string(t)
                return f"{y:04d}-{mon:02d}-{d:02d} {t_norm}"

        # 3. If time only: HH:MM:SS or HH:MM (with optional am/pm)
        if re.fullmatch(r"\d{1,2}:\d{2}(?::\d{2})?(?:\s*[AaPp][Mm])?", s):
            t_norm = cls._parse_time_string(s)
            # If filename contains date pattern (e.g. photo_YYYY-MM-DD_...), stitch it
            mf = re.search(r"(\d{4})[._-](\d{2})[._-](\d{2})", image_name)
            if mf:
                return f"{mf.group(1)}-{mf.group(2)}-{mf.group(3)} {t_norm}"
            return t_norm

        return s

    @classmethod
    def _normalize_outcome(cls, raw: Any) -> Optional[str]:
        """Normalize outcome string (clean up handicap formatting and market names)."""
        if raw is None or isinstance(raw, (bool, dict, list)):
            return None
        s = str(raw).strip().strip("'\"").strip()
        if not s or s.lower() in ("null", "none"):
            return None

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
        """Normalize match string (strip leading sport tags and clean extra spaces)."""
        if raw is None or isinstance(raw, (bool, dict, list)):
            return None
        s = str(raw).strip().strip("'\"").strip()
        if not s or s.lower() in ("null", "none"):
            return None

        s = re.sub(
            r"(?i)^(?:football|soccer|basketball|tennis|hockey)\s*-\s*", "", s
        ).strip()
        s = re.sub(r"\s+", " ", s).strip()
        return s or None

    def _normalize(self, payload: Any, image_name: str) -> Dict[str, Any]:
        """
        Normalize raw API payload to strict schema using Pydantic.

        Args:
            payload (Any): Parsed JSON (dict or single-item list) from model response.
            image_name (str): Filename as fallback for source_image_id.

        Returns:
            Dict[str, Any]: Strictly ordered dictionary adhering to the project schema.
        """
        if isinstance(payload, list) and len(payload) > 0 and isinstance(payload[0], dict):
            payload = payload[0]

        if not isinstance(payload, dict):
            payload = {}

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

    @staticmethod
    def _clean_raw_json(raw: str) -> str:
        """Strip surrounding markdown code blocks (e.g. ```json ... ```) if present."""
        s = raw.strip()
        if s.startswith("```"):
            s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.IGNORECASE)
            s = re.sub(r"\s*```$", "", s)
        return s.strip()

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

        cleaned_raw = self._clean_raw_json(raw)
        try:
            data = json.loads(cleaned_raw)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Failed to parse AI response as JSON: {e}") from e

        return self._normalize(data, p.name)
