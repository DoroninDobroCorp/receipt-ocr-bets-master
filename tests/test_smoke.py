"""
Smoke tests ensuring discovery and basic package module imports work properly.
"""

from __future__ import annotations


def test_smoke_package_imports() -> None:
    """Verify package public API is importable and exposed."""
    import src

    assert hasattr(src, "ReceiptExtractor")
    assert hasattr(src, "ReceiptOutput")
    assert hasattr(src, "Config")
    assert hasattr(src, "ImageProcessor")
