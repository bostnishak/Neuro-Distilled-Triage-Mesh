"""Unit and integration tests for Multimodal Triage and PII Redaction."""
from __future__ import annotations

import base64
import io
import pytest
import numpy as np
from PIL import Image

from ndtm_platform.middleware.pii_redaction import PIIRedactor, validate_tckn_checksum
from ndtm_platform.services.triage_service import compute_laplacian_variance


def test_tckn_checksum_validation():
    # Valid TCKN example according to modulo 10/11 algorithm
    # e.g., 10000000146 -> d1..d9: 100000001, odd=2, even=0. (2*7 - 0)%10 = 4 (d10=4). sum(d1..d10)=6, 6%10=6 (d11=6).
    assert validate_tckn_checksum("10000000146") is True
    # Invalid checksum
    assert validate_tckn_checksum("10000000147") is False
    assert validate_tckn_checksum("01234567890") is False  # Cannot start with 0
    assert validate_tckn_checksum("12345") is False


def test_pii_redactor_masks_phone_and_email():
    redactor = PIIRedactor()
    raw_text = "Lütfen beni +90 532 123 4567 numarasından veya ahmet.yilmaz@belediye.gov.tr adresinden arayınız."
    cleaned, redactions = redactor.redact(raw_text)

    assert "+90 532 123 4567" not in cleaned
    assert "[REDACTED_PHONE]" in cleaned
    assert "ahmet.yilmaz@belediye.gov.tr" not in cleaned
    assert "[REDACTED_EMAIL]" in cleaned
    assert len(redactions) >= 2


def test_laplacian_sharpness_detection():
    # 1. Blurry / flat image (zero variance)
    flat_img = Image.new("L", (200, 200), color=128)
    blur_score = compute_laplacian_variance(flat_img)
    assert blur_score < 10.0

    # 2. Sharp edge / checkerboard image (high variance)
    arr = np.zeros((200, 200), dtype=np.uint8)
    arr[::20, :] = 255
    arr[:, ::20] = 255
    sharp_img = Image.fromarray(arr)
    sharp_score = compute_laplacian_variance(sharp_img)
    assert sharp_score > 60.0
