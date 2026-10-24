"""
Image Processor module
----------------------
Handles preprocessing and encoding of receipt images before sending to the API.
"""

from __future__ import annotations
import base64
import io
from pathlib import Path
from PIL import Image, ImageOps


class ImageProcessor:
    """Utility class for preprocessing images before encoding."""

    MAX_DIMENSION: int = 2048

    @classmethod
    def preprocess_image(cls, path: Path) -> Image.Image:
        """
        Open image, correct EXIF orientation, convert to RGB (with clean white background for alpha),
        downscale large images while preserving aspect ratio, and apply tone-preserving contrast.

        Args:
            path (Path): Path to the image file.

        Returns:
            Image.Image: Preprocessed PIL Image in RGB mode.
        """
        try:
            with Image.open(path) as raw_img:
                # Correct EXIF rotation (critical for mobile phone camera shots)
                img = ImageOps.exif_transpose(raw_img)

                # Composite transparent images (RGBA / LA / transparent palette) over white background
                if img.mode in ("RGBA", "LA") or (
                    img.mode == "P" and "transparency" in img.info
                ):
                    rgba_img = img.convert("RGBA")
                    bg = Image.new("RGB", rgba_img.size, (255, 255, 255))
                    bg.paste(rgba_img, mask=rgba_img.split()[3])
                    img = bg
                elif img.mode != "RGB":
                    img = img.convert("RGB")

                # Downscale if exceeding MAX_DIMENSION to save network bandwidth and tokens
                if max(img.width, img.height) > cls.MAX_DIMENSION:
                    img.thumbnail(
                        (cls.MAX_DIMENSION, cls.MAX_DIMENSION),
                        Image.Resampling.LANCZOS,
                    )

                # Enhance contrast preserving tone to avoid per-channel color cast
                img = ImageOps.autocontrast(img, cutoff=0.5, preserve_tone=True)

                # Return a memory copy so file handle can close safely
                return img.copy()
        except Exception as e:
            raise ValueError(f"Failed to process image '{path}': {e}") from e

    @classmethod
    def encode_to_base64(cls, path: Path) -> str:
        """
        Load an image, preprocess, and return its Base64-encoded JPEG representation.

        Args:
            path (Path): Path to the image file.

        Returns:
            str: Base64 string of the image.
        """
        img = cls.preprocess_image(path)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=90)
        return base64.b64encode(buf.getvalue()).decode("utf-8")
