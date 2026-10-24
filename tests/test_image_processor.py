"""
Unit tests for ImageProcessor.
"""

from __future__ import annotations
import base64
from pathlib import Path
import pytest
from PIL import Image

from src.image_processor import ImageProcessor


class TestImageProcessor:
    """Tests for ImageProcessor utility."""

    def test_encode_to_base64_valid_rgb(self, tmp_path: Path) -> None:
        """Encoding valid RGB image to base64 string."""
        img_path = tmp_path / "test.jpg"
        Image.new("RGB", (100, 100), color="blue").save(img_path)

        b64 = ImageProcessor.encode_to_base64(img_path)
        assert isinstance(b64, str)
        assert len(b64) > 0
        decoded = base64.b64decode(b64)
        assert len(decoded) > 0

    def test_encode_to_base64_rgba_converted(self, tmp_path: Path) -> None:
        """RGBA image should be converted to RGB without errors."""
        img_path = tmp_path / "test.png"
        Image.new("RGBA", (50, 50), color=(255, 0, 0, 128)).save(img_path)

        b64 = ImageProcessor.encode_to_base64(img_path)
        assert isinstance(b64, str)

    def test_downscale_large_image(self, tmp_path: Path) -> None:
        """Images larger than MAX_DIMENSION should be safely downscaled."""
        img_path = tmp_path / "large.jpg"
        Image.new("RGB", (3000, 2000), color="white").save(img_path)

        processed = ImageProcessor.preprocess_image(img_path)
        assert max(processed.width, processed.height) <= ImageProcessor.MAX_DIMENSION

    def test_invalid_image_raises_value_error(self, tmp_path: Path) -> None:
        """Non-image file should raise ValueError."""
        corrupt_file = tmp_path / "not_an_image.txt"
        corrupt_file.write_text("plain text", encoding="utf-8")

        with pytest.raises(ValueError, match="Failed to process image"):
            ImageProcessor.encode_to_base64(corrupt_file)
