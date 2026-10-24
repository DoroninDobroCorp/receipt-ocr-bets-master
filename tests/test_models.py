"""
Unit tests for models and numeric/string parsing edge cases.
"""

from __future__ import annotations
import math
from src.models import ReceiptOutput, parse_numeric_float


class TestModels:
    """Tests for ReceiptOutput model and parsing utilities."""

    def test_parse_numeric_float_edge_cases(self) -> None:
        """Test float parsing against booleans, null strings, nan, inf, and currencies."""
        # Booleans must return None (not 1.0 or 0.0)
        assert parse_numeric_float(True) is None
        assert parse_numeric_float(False) is None

        # None and null strings
        assert parse_numeric_float(None) is None
        assert parse_numeric_float("null") is None
        assert parse_numeric_float("None") is None
        assert parse_numeric_float("") is None

        # Non-finite values
        assert parse_numeric_float(float("nan")) is None
        assert parse_numeric_float(float("inf")) is None
        assert parse_numeric_float(float("-inf")) is None
        assert parse_numeric_float("nan") is None
        assert parse_numeric_float("inf") is None

        # Negative and zero values
        assert parse_numeric_float(0.0) is None
        assert parse_numeric_float(-5.0) is None
        assert parse_numeric_float("-100.00") is None

        # Fractional odds vs slash codes
        assert parse_numeric_float("5/2") == 3.5
        assert parse_numeric_float("35107/44985") is None
        assert parse_numeric_float("08/03/2025") is None

        # Valid numbers and currencies
        assert parse_numeric_float(1.85) == 1.85
        assert parse_numeric_float("2.10") == 2.10
        assert parse_numeric_float("EUR 100,00") == 100.0
        assert parse_numeric_float("25.00 €") == 25.0
        assert parse_numeric_float("$50.50") == 50.5
        assert parse_numeric_float("1,000.50") == 1000.5
        assert parse_numeric_float("1.000,50 EUR") == 1000.5

    def test_receipt_output_string_coercion_guards(self) -> None:
        """Booleans, dicts, lists, and literal 'null' strings must become None."""
        output = ReceiptOutput(
            bet_time="null",
            match={"team1": "A", "team2": "B"},  # type: ignore
            outcome=False,  # type: ignore
            source_image_id=["id1", "id2"],  # type: ignore
        )
        data = output.to_dict()
        assert data["bet_time"] is None
        assert data["match"] is None
        assert data["outcome"] is None
        assert data["source_image_id"] is None

    def test_receipt_output_to_dict_ordering(self) -> None:
        """Verify strict key ordering in to_dict output."""
        output = ReceiptOutput(
            bet_time="2025-08-19 14:32:05",
            match="Team A - Team B",
            outcome="1",
            odds=1.85,
            stake=100.0,
            source_image_id="img.jpg",
        )
        assert list(output.to_dict().keys()) == [
            "bet_time",
            "match",
            "outcome",
            "odds",
            "stake",
            "source_image_id",
        ]
