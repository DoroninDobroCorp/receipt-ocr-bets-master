"""
Image Processor module
----------------------
Handles preprocessing of receipt images before sending to the API.
"""

from __future__ import annotations
import base64, io
from pathlib import Path
from PIL import Image, ImageOps


class ImageProcessor:
    """Utility class for preprocessing images before encoding."""

    @staticmethod
    def encode_to_base64(path: Path) -> str:
        """
        Load an image, preprocess (convert to RGB, auto-contrast),
        and return its Base64-encoded JPEG representation.

        Args:
            path (Path): Path to the image file.

        Returns:
            str: Base64 string of the image.
        """
        img = Image.open(path)
        if img.mode != "RGB":
            img = img.convert("RGB")
        img = ImageOps.autocontrast(img)

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=90)
        return base64.b64encode(buf.getvalue()).decode("utf-8")
