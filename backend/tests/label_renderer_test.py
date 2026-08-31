"""Print outputs must resolve the same SKU and keep physical dimensions."""

import re
import zlib
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree as ET

import cv2
import numpy as np
import pytest
from PIL import Image
from sqlalchemy import func, select

from app.models.brand import Brand
from app.models.filament import Filament
from app.models.user_spool import UserSpool
from app.schemas.label import LabelExportOptions, LabelOptions
from app.services.label_fonts import measure_text
from app.services.label_layout import LabelData, LabelDoesNotFit
from app.services.label_renderer import _fetch_embedded, export_label, render_label, sheet_svg
from app.services.qr_mark import mark_paths
from app.services.qr_service import _qr_target_url


@pytest.fixture
def label_data():
    return LabelData(
        "FH-001",
        "OlgaCraft",
        "PETG-CF",
        "Arctic Graphite",
        (
            ("nozzle", "Сопло", "235–255\u00a0°C"),
            ("bed", "Стол", "75–90\u00a0°C"),
            ("drying", "Сушка", "65\u00a0°C · 6\u00a0ч"),
            ("abrasiveness", "Сопло", "≥55\u00a0HRC"),
            ("diameter", "Диаметр", "1,75\u00a0мм"),
            ("density", "Плотность", "1,25\u00a0г/см³"),
        ),
        comment_heading="Комментарий",
    )


@pytest.mark.parametrize(
    "dimensions", [(40, 30), (50, 30), (62, 29), (54, 25), (63.5, 38.1), (40, 12)]
)
@pytest.mark.parametrize("rotate", [False, True])
@pytest.mark.parametrize("attribution", ["full", "mark", "none"])
@pytest.mark.parametrize("dpi", [203, 300, 600])
def test_label_png_decodes_actual_scene(label_data, dimensions, rotate, attribution, dpi):
    width, height = dimensions[::-1] if rotate else dimensions
    options = LabelOptions(width_mm=width, height_mm=height, attribution=attribution, dpi=dpi)
    result = render_label(label_data, options)
    if not result["printable"]:
        assert result["scene"]["dots_per_module"] < 2
        with pytest.raises(LabelDoesNotFit):
            export_label(label_data, LabelExportOptions(label=options, format="png"))
        return
    png = export_label(label_data, LabelExportOptions(label=options, format="png"))
    image = Image.open(BytesIO(png))
    assert image.size == (round(width * dpi / 25.4), round(height * dpi / 25.4))
    assert image.info["dpi"][0] == pytest.approx(dpi, abs=0.1)
    decoded = cv2.QRCodeDetectorAruco().detectAndDecode(np.array(image.convert("RGB")))[0]
    assert decoded == _qr_target_url(label_data.sku)
    assert "<text" not in result["svg"]


@pytest.mark.parametrize("branded", [False, True])
@pytest.mark.parametrize("sku", ["FH-001", "FH-P7C41A", "FH-SHOW-CARBON-PETG-GRAPHITE"])
@pytest.mark.parametrize("size,dpi", [(20, 203), (30, 300), (40, 600)])
def test_label_classic_mark_remains_decodable(label_data, branded, sku, size, dpi):
    label_data = replace(label_data, sku=sku)
    options = LabelOptions(kind="classic", width_mm=size, height_mm=size, qr_mark=branded, dpi=dpi)
    png = export_label(label_data, LabelExportOptions(label=options, format="png"))
    image = np.array(Image.open(BytesIO(png)).convert("RGB"))
    # The contour detector misses the same unbranded H matrix for long SKUs
    # at these larger raster sizes. ArUco detects its finders without changing
    # the image, payload, mask or strict decode assertion.
    assert cv2.QRCodeDetectorAruco().detectAndDecode(image)[0] == _qr_target_url(label_data.sku)


def test_classic_uses_special_round_mark_with_one_module_white_frame(label_data):
    result = render_label(
        label_data, LabelOptions(kind="classic", width_mm=30, height_mm=30, qr_mark=True)
    )
    root = ET.fromstring(result["svg"])
    ns = {"s": "http://www.w3.org/2000/svg"}
    frame = root.find(".//s:rect[@data-role='qr-mark-frame']", ns)
    background = root.find(".//s:rect[@data-role='qr-mark-background']", ns)
    mark = root.find(".//s:g[@data-role='qr-mark']", ns)
    module = result["scene"]["qr"]["width"] / result["modules"]
    assert frame.attrib["fill"] == "white" and background.attrib["fill"] == "black"
    assert float(background.attrib["x"]) - float(frame.attrib["x"]) == pytest.approx(module)
    assert float(background.attrib["width"]) == pytest.approx(
        float(frame.attrib["width"]) - 2 * module
    )
    assert float(background.attrib["width"]) >= result["scene"]["qr"]["width"] * 0.2
    assert [p.attrib["d"] for p in mark] == mark_paths()
    assert mark.attrib["fill"] == "white"
    x, y, scale = map(float, re.findall(r"[\d.]+", mark.attrib["transform"]))
    assert x - float(background.attrib["x"]) == pytest.approx(module, abs=1e-6)
    assert y - float(background.attrib["y"]) == pytest.approx(module, abs=1e-6)
    assert scale * 20 == pytest.approx(float(background.attrib["width"]) - 2 * module)
    assert not result["scene"]["texts"]


def test_label_corner_shape_is_shared_by_svg_and_png(label_data):
    options = LabelOptions()
    result = render_label(label_data, options)
    root = ET.fromstring(result["svg"])
    outline = root.find(".//{http://www.w3.org/2000/svg}clipPath/{http://www.w3.org/2000/svg}rect")
    assert float(outline.attrib["rx"]) == result["scene"]["corner_radius_mm"] > 0
    png = Image.open(
        BytesIO(export_label(label_data, LabelExportOptions(label=options, format="png")))
    ).convert("RGBA")
    assert png.getpixel((0, 0))[3] == 0
    assert png.getpixel((png.width // 2, 0)) == (255, 255, 255, 255)


@pytest.mark.parametrize("media,dimensions", [("a4", (210, 297)), ("letter", (215.9, 279.4))])
def test_label_sheet_positions_and_pdf_have_exact_physical_size(label_data, media, dimensions):
    options = LabelExportOptions(media=media, copies=2, start_position=3, format="pdf")
    rendered = render_label(label_data, options.label)
    svg, width, height, capacity = sheet_svg(rendered, options)
    assert (width, height) == dimensions
    root = ET.fromstring(svg)
    cells = root.findall("{http://www.w3.org/2000/svg}use")
    assert len(cells) == 2 and capacity >= 4
    assert float(cells[0].attrib["x"]) == 109
    assert float(cells[0].attrib["y"]) == 5
    pdf = export_label(label_data, options)
    streams = [pdf]
    for stream in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", pdf, re.S):
        try:
            streams.append(zlib.decompress(stream[1]))
        except zlib.error:
            continue
    box = re.search(rb"/MediaBox\s*\[\s*0\s+0\s+([\d.]+)\s+([\d.]+)", b"\n".join(streams))
    assert box is not None
    assert float(box[1]) == pytest.approx(width * 72 / 25.4, abs=0.001)
    assert float(box[2]) == pytest.approx(height * 72 / 25.4, abs=0.001)


def test_label_unicode_and_logo_are_self_contained(label_data):
    data = replace(
        label_data, brand="品牌", name="石墨黑", fields=(("nozzle", "喷嘴", "235–255\u00a0°C"),)
    )
    assert measure_text("石墨黑", 2, True) > 0
    output = BytesIO()
    Image.new("RGB", (300, 50), "red").save(output, format="PNG")
    options = LabelOptions(color_mode="color", locale="zh")
    rendered = render_label(data, options, output.getvalue())
    assert "data:image/png;base64," in rendered["svg"]
    assert "<text" not in rendered["svg"]
    assert (
        len(export_label(data, LabelExportOptions(label=options, format="pdf"), output.getvalue()))
        > 1000
    )
    for uri in ("https://localhost/private", "file:///etc/passwd", "data:image/svg+xml,anything"):
        with pytest.raises(ValueError):
            _fetch_embedded(uri, "image")


def test_label_rejects_unsafe_density_and_overfull_sheet(label_data):
    with pytest.raises(LabelDoesNotFit):
        export_label(label_data, LabelExportOptions(label=LabelOptions(width_mm=40, height_mm=12)))
    with pytest.raises(LabelDoesNotFit):
        sheet_svg(
            render_label(label_data, LabelOptions()),
            LabelExportOptions(media="a4", start_position=499),
        )


def test_label_print_threshold_tolerates_dot_grid_roundoff(label_data, monkeypatch):
    from app.services import label_renderer

    compose = label_renderer.compose_label
    monkeypatch.setattr(
        label_renderer,
        "compose_label",
        lambda *args: replace(compose(*args), dots_per_module=4 - 1e-12),
    )
    rendered = render_label(label_data, LabelOptions(dpi=203))
    assert rendered["scene"]["dots_per_module"] == pytest.approx(4)
    assert rendered["printable"] and not rendered["proof_required"]


def test_label_mark_matches_canonical_public_asset():
    root = Path(__file__).resolve().parents[2]
    assert (root / "backend/app/assets/labels/fh-mark.svg").read_text(encoding="utf-8") == (
        root / "frontend/public/logo.svg"
    ).read_text(encoding="utf-8")


async def test_label_public_endpoints_are_read_only_and_cannot_override_identity(
    client, db_session
):
    brand = Brand(name="Label proof", slug="label-proof", verified=True, active=True)
    db_session.add(brand)
    await db_session.flush()
    filament = Filament(
        brand_id=brand.id,
        name="Arctic Graphite",
        slug="arctic-graphite",
        material_type="PETG",
        active=True,
        qr_code="FH-PROOF",
    )
    db_session.add(filament)
    await db_session.commit()
    endpoint = f"/api/v1/labels/filaments/{filament.id}"
    response = await client.get(endpoint)
    assert response.status_code == 200
    request = {"label": {"width_mm": 150, "height_mm": 100, "comment": "My local print"}}
    response = await client.post(f"{endpoint}/preview", json=request)
    assert response.status_code == 200 and response.json()["printable"]
    response = await client.post(f"{endpoint}/export", json={**request, "format": "svg"})
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    rejected = await client.post(
        f"{endpoint}/preview", json={"label": {"sku": "someone-else", "spool_id": 123}}
    )
    assert rejected.status_code == 422
    await db_session.refresh(filament)
    assert filament.name == "Arctic Graphite" and filament.qr_code == "FH-PROOF"
    assert await db_session.scalar(select(func.count()).select_from(UserSpool)) == 0
    brand.verified = False
    await db_session.commit()
    assert (await client.get(endpoint)).status_code == 200
    filament.qr_code = None
    await db_session.commit()
    assert (await client.get(endpoint)).status_code == 403
