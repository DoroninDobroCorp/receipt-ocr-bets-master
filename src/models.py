"""
Models module
-------------
Pydantic data models for receipt extraction schema and validation.
"""

from __future__ import annotations
import re
from typing import Any, Dict, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


def parse_numeric_float(v: Any) -> Optional[float]:
    """
    Extract a positive float from numeric or string values.
    Handles currency symbols, European/US decimal/thousand separators, and whitespace.
    """
    if v is None:
        return None
    if isinstance(v, (int, float)):
        val = float(v)
        return val if val > 0 else None
    if isinstance(v, str):
        s = v.strip()
        # Keep only digits, comma, dot, and plus/minus
        s = re.sub(r"[^\d,.\-+]", "", s)
        if not s:
            return None

        # Handle thousand and decimal separators if both exist
        if "," in s and "." in s:
            if s.rfind(",") > s.rfind("."):
                # European style: 1.000,50 -> 1000.50
                s = s.replace(".", "").replace(",", ".")
            else:
                # US style: 1,000.50 -> 1000.50
                s = s.replace(",", "")
        elif "," in s:
            # European decimal comma: 100,00 -> 100.00
            s = s.replace(",", ".")

        m = re.search(r"[-+]?\d+(?:\.\d+)?", s)
        if m:
            try:
                val = float(m.group(0))
                return val if val > 0 else None
            except ValueError:
                return None
    return None


class ReceiptOutput(BaseModel):
    """
    Strict betting receipt extraction schema.
    Maintains fixed key order and type constraints.
    """

    model_config = ConfigDict(extra="ignore")

    bet_time: Optional[str] = Field(
        default=None,
        description="Ticket creation/bet timestamp formatted as 'YYYY-MM-DD HH:MM:SS' (or 'HH:MM:SS').",
    )
    match: Optional[str] = Field(
        default=None,
        description="Competitors/teams involved in the match (e.g. 'Team A - Team B'). Exclude sport or league titles.",
    )
    outcome: Optional[str] = Field(
        default=None,
        description="Selected bet outcome/prediction (e.g. '1', 'X', '2', 'HANDICAP 0:2', 'Over 2.5', 'ug 0-1'). Exclude the market type question.",
    )
    odds: Optional[float] = Field(
        default=None,
        description="The decimal odds multiplier (e.g. 1.85, 2.10).",
    )
    stake: Optional[float] = Field(
        default=None,
        description="Stake or bet amount wagered (numeric, without currency symbol).",
    )
    source_image_id: Optional[str] = Field(
        default=None,
        description="Ticket / receipt identifier, barcode serial number, or image name.",
    )

    @field_validator("odds", "stake", mode="before")
    @classmethod
    def _parse_float(cls, v: Any) -> Optional[float]:
        """Convert float/int/currency-separated strings to float or None."""
        return parse_numeric_float(v)

    @field_validator("bet_time", "match", "outcome", "source_image_id", mode="before")
    @classmethod
    def _parse_str(cls, v: Any) -> Optional[str]:
        """Convert empty or whitespace strings to None."""
        if v is None:
            return None
        s = str(v).strip()
        return s if s else None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict with guaranteed key order matching the specification."""
        return {
            "bet_time": self.bet_time,
            "match": self.match,
            "outcome": self.outcome,
            "odds": self.odds,
            "stake": self.stake,
            "source_image_id": self.source_image_id,
        }
