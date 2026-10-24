"""
Models module
-------------
Pydantic data models for receipt extraction schema and validation.
"""

from __future__ import annotations
from typing import Any, Dict, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


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
        """Convert float/int/comma-separated strings to float or None."""
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            cleaned = v.replace(",", ".").strip()
            if not cleaned:
                return None
            try:
                return float(cleaned)
            except ValueError:
                return None
        return None

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
