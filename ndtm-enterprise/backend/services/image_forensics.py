"""Image forensics, magic-byte polyglot defense, EXIF stripping, and Laplacian blur detection."""
from __future__ import annotations

import base64
import hashlib
import io
import logging
from dataclasses import dataclass
from typing import Tuple

import numpy as np
from PIL import Image

from backend.core.config import get_settings
from backend.core.exceptions import QualityGateFailedError

logger = logging.getLogger("services.image_forensics")
settings = get_settings()

Image.MAX_IMAGE_PIXELS = 40_000_000

# Magic byte signatures
_MAGIC_BYTES = {
    b"\x89PNG\r\n\x1a\n": "PNG",
    b"\xff\xd8\xff": "JPEG",
    b"RIFF": "WEBP",  # WEBP format starts with RIFF....WEBP
}


@dataclass(slots=True)
class ImageAnalysisResult:
    is_valid: bool
    format: str
    sha256_hash: str
    laplacian_variance: float
    mean_intensity: float
    clean_bytes: bytes


class ImageForensicsService:
    def __init__(
        self,
        min_laplacian: float = 85.0,
        min_intensity: float = 20.0,
        max_intensity: float = 245.0,
    ) -> None:
        self.min_laplacian = min_laplacian
        self.min_intensity = min_intensity
        self.max_intensity = max_intensity

    def verify_magic_bytes(self, raw_bytes: bytes) -> str:
        """Inspects binary header bytes to prevent polyglot payload execution."""
        if len(raw_bytes) < 12:
            raise ValueError("Payload too short to verify image magic bytes.")

        if raw_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
            return "PNG"
        if raw_bytes.startswith(b"\xff\xd8\xff"):
            return "JPEG"
        if raw_bytes.startswith(b"RIFF") and raw_bytes[8:12] == b"WEBP":
            return "WEBP"

        raise ValueError("Unsupported or disguised image format. Expected valid PNG, JPEG, or WEBP header.")

    def compute_laplacian_variance(self, pil_image: Image.Image) -> float:
        """Computes the variance of the 2D Laplacian operator to quantify edge sharpness."""
        gray = pil_image.convert("L")
        arr = np.array(gray, dtype=np.float32)
        h, w = arr.shape
        if h < 3 or w < 3:
            return 0.0

        # Discrete 3x3 Laplacian convolution kernel
        conv = (
            arr[0 : h - 2, 1 : w - 1]
            + arr[2:h, 1 : w - 1]
            + arr[1 : h - 1, 0 : w - 2]
            + arr[1 : h - 1, 2:w]
            - 4.0 * arr[1 : h - 1, 1 : w - 1]
        )
        return float(np.var(conv))

    def process_and_validate(self, image_input: bytes | str) -> ImageAnalysisResult:
        """Strips EXIF, checks magic bytes, evaluates exposure and Laplacian blur."""
        if isinstance(image_input, str):
            # Strip data URL prefix if present
            if "," in image_input:
                image_input = image_input.split(",", 1)[1]
            raw_bytes = base64.b64decode(image_input)
        else:
            raw_bytes = image_input

        # 1. Magic byte verification
        fmt = self.verify_magic_bytes(raw_bytes)
        sha256 = hashlib.sha256(raw_bytes).hexdigest()

        # 2. Decode into PIL Image
        try:
            with Image.open(io.BytesIO(raw_bytes)) as img:
                img.verify()
            with Image.open(io.BytesIO(raw_bytes)) as img:
                # 3. Strip EXIF metadata for privacy compliance
                clean_buffer = io.BytesIO()
                clean_img = Image.new(img.mode, img.size)
                clean_img.putdata(list(img.getdata()))
                clean_img.save(clean_buffer, format=fmt)
                stripped_bytes = clean_buffer.getvalue()

                # 4. Measure Mean Intensity (Exposure)
                gray = clean_img.convert("L")
                arr = np.array(gray, dtype=np.float32)
                mean_intensity = float(np.mean(arr))

                if mean_intensity < self.min_intensity:
                    raise QualityGateFailedError(
                        reason="IMAGE_TOO_DARK",
                        laplacian_score=0.0,
                        prompt="Fotoğraf çok karanlık. Lütfen olay yerini aydınlık bir ortamda tekrar fotoğraflayınız.",
                    )

                if mean_intensity > self.max_intensity:
                    raise QualityGateFailedError(
                        reason="IMAGE_OVEREXPOSED",
                        laplacian_score=0.0,
                        prompt="Fotoğraf aşırı parlak / parlamış. Lütfen parlamayı engelleyecek bir açıdan tekrar çekiniz.",
                    )

                # 5. Measure Laplacian Variance (Sharpness)
                laplacian_var = self.compute_laplacian_variance(clean_img)
                if laplacian_var < self.min_laplacian:
                    raise QualityGateFailedError(
                        reason="IMAGE_TOO_BLURRY",
                        laplacian_score=round(laplacian_var, 2),
                        prompt=f"Fotoğraf net değil (Netlik skoru {laplacian_var:.1f} < {self.min_laplacian}). Lütfen kameranızı odaklayıp tekrar çekiniz.",
                    )

                return ImageAnalysisResult(
                    is_valid=True,
                    format=fmt,
                    sha256_hash=sha256,
                    laplacian_variance=round(laplacian_var, 2),
                    mean_intensity=round(mean_intensity, 2),
                    clean_bytes=stripped_bytes,
                )
        except QualityGateFailedError:
            raise
        except Exception as exc:
            raise ValueError(f"Corrupted or invalid image stream: {exc}")
