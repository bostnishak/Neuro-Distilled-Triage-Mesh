"""Unit tests for Module 1: Image Quality and Triage Validation."""
import io
import numpy as np
from PIL import Image
from core.config import get_settings
from services.triage_service import ImageQualityInspector


def test_image_quality_inspector_sharp_image():
    settings = get_settings()
    inspector = ImageQualityInspector(settings)

    # Generate synthetic sharp patterned image
    arr = np.zeros((400, 400), dtype=np.uint8)
    arr[::20, :] = 255
    arr[:, ::20] = 255
    img = Image.fromarray(arr).convert("RGB")

    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    data = buf.getvalue()

    report = inspector.inspect(data)
    assert report.valid is True
    assert report.format == "JPEG"
    assert report.width == 400
    assert report.height == 400
    assert report.blur_score is not None
    assert report.blur_score > settings.blur_threshold


def test_image_quality_inspector_blurry_image():
    settings = get_settings()
    inspector = ImageQualityInspector(settings)

    # Flat grey image has near zero Laplacian variance
    arr = np.full((350, 350), 128, dtype=np.uint8)
    img = Image.fromarray(arr).convert("RGB")

    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    data = buf.getvalue()

    report = inspector.inspect(data)
    assert report.valid is False
    assert "IMAGE_BLURRY" in report.issues


def test_image_quality_inspector_low_resolution():
    settings = get_settings()
    inspector = ImageQualityInspector(settings)

    # 100x100 is below min_image_width (320)
    arr = np.random.randint(0, 255, (100, 100), dtype=np.uint8)
    img = Image.fromarray(arr).convert("RGB")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    data = buf.getvalue()

    report = inspector.inspect(data)
    assert report.valid is False
    assert "IMAGE_LOW_RESOLUTION" in report.issues
