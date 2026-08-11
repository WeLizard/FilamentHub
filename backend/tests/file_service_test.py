from io import BytesIO

import pytest
from PIL import Image

from app.services.file_service import (
    MAX_BRAND_LOGO_EDGE,
    MAX_BRAND_LOGO_OUTPUT_BYTES,
    normalize_brand_logo_upload,
)


def test_brand_logo_is_resized_and_bounded_before_storage():
    source = BytesIO()
    Image.new("RGBA", (3000, 1200), (120, 40, 210, 180)).save(source, "PNG")

    normalized, extension = normalize_brand_logo_upload(source.getvalue(), ".png")

    assert extension == ".webp"
    assert len(normalized) <= MAX_BRAND_LOGO_OUTPUT_BYTES
    with Image.open(BytesIO(normalized)) as image:
        assert image.format == "WEBP"
        assert max(image.size) == MAX_BRAND_LOGO_EDGE
        assert image.width / image.height == pytest.approx(2.5, rel=0.01)
