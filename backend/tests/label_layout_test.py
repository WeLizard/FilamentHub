"""Guard physical regressions observed while designing printed labels."""

import unicodedata
from functools import lru_cache

import pytest
from PIL import ImageFont

from app.schemas.label import LabelOptions
from app.services.label_layout import Box, LabelData, LabelDoesNotFit, compose_label, rule_stroke_mm


@pytest.fixture(scope="module")
def measure_text():
    # Both supported test hosts have these system fonts. Measure real glyphs,
    # rather than assuming that every character has the same width.
    fonts = None
    for regular, bold in (
        ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf"),
        ("arial.ttf", "arialbd.ttf"),
    ):
        try:
            fonts = (ImageFont.truetype(regular, 1000), ImageFont.truetype(bold, 1000))
            break
        except OSError:
            continue
    assert fonts is not None, "Physical layout tests require installed Unicode fonts"

    @lru_cache(maxsize=4096)
    def width(text: str, bold: bool) -> float:
        return fonts[int(bold)].getlength(text) / 1000

    return lambda text, size, bold: width(text, bold) * size


@pytest.fixture
def material():
    return LabelData(
        sku="FH-P7C41A",
        brand="OlgaCraft",
        material="PETG-CF",
        name="Arctic Graphite",
        fields=(
            ("nozzle", "Сопло", "235–255\u00a0°C"),
            ("bed", "Стол", "75–90\u00a0°C"),
            ("drying", "Сушка", "65\u00a0°C · 6\u00a0ч"),
            ("abrasiveness", "Абразивность", "Закалённое сопло"),
            ("diameter", "Диаметр", "1,75\u00a0мм"),
            ("density", "Плотность", "1,25\u00a0г/см³"),
        ),
        ral="RAL 7016",
        color_hex="#364152",
        comment_heading="Комментарий производителя",
        has_brand_logo=True,
    )


def overlaps(a: Box, b: Box) -> bool:
    return (
        min(a.right, b.right) - max(a.x, b.x) > 1e-6
        and min(a.bottom, b.bottom) - max(a.y, b.y) > 1e-6
    )


@pytest.mark.parametrize(
    "dimensions",
    [(40, 30), (50, 30), (62, 29), (54, 25), (63.5, 38.1), (40, 12), (220, 220), (100, 150)],
)
@pytest.mark.parametrize("rotated", [False, True])
@pytest.mark.parametrize("attribution", ["full", "mark", "none"])
@pytest.mark.parametrize(
    "brand_options",
    [
        {"brand_logo": False},
        {"brand_logo": True},
        {"brand_mode": "none"},
        {"brand_mode": "mark"},
        {"brand_mode": "full"},
    ],
)
def test_selected_content_and_qr_stay_inside_their_zones(
    material, measure_text, dimensions, rotated, attribution, brand_options
):
    width, height = dimensions[::-1] if rotated else dimensions
    options = LabelOptions(
        width_mm=width, height_mm=height, attribution=attribution, **brand_options
    )
    scene = compose_label(material, options, 33, measure_text)
    assert scene.qr.width > 0
    quiet = scene.quiet_zone_mm
    protected = Box(
        scene.qr.x - quiet,
        scene.qr.y - quiet,
        scene.qr.width + 2 * quiet,
        scene.qr.height + 2 * quiet,
    )
    assert protected.x >= -1e-6 and protected.y >= -1e-6
    assert protected.right <= width + 1e-6 and protected.bottom <= height + 1e-6
    roles = {text.role for text in scene.texts}
    assert ("brand" in roles) == options.show_brand_name
    assert (scene.brand_logo is not None) == options.show_brand_logo
    if scene.brand_logo:
        assert not overlaps(scene.brand_logo, protected)
        assert not any(overlaps(scene.brand_logo, text.box) for text in scene.texts)
    assert set(options.fields) <= roles
    for text in scene.texts:
        assert text.box.x >= scene.margin_mm - 1e-6
        assert text.box.y >= scene.margin_mm - 1e-6
        assert text.box.right <= width - scene.margin_mm + 1e-6
        assert text.box.bottom <= height - scene.margin_mm + 1e-6
        assert not overlaps(text.box, protected), text.role
        assert measure_text(text.text, text.size, text.bold) <= text.box.width + 1e-6
    for index, text in enumerate(scene.texts):
        assert not any(overlaps(text.box, other.box) for other in scene.texts[index + 1 :])
    half_stroke = rule_stroke_mm(scene.margin_mm) / 2
    for rule in scene.rules:
        ink = Box(
            rule.x - half_stroke,
            rule.y - half_stroke,
            rule.width + 2 * half_stroke,
            rule.height + 2 * half_stroke,
        )
        assert not overlaps(ink, protected)
    sku = next(text for text in scene.texts if text.role == "sku")
    assert sku.text == material.sku
    assert sku.box.x + sku.box.width / 2 == pytest.approx(scene.qr.x + scene.qr.width / 2)
    # Centre in the gap when possible; otherwise the QR's white field wins.
    assert any(
        abs(actual - expected) < 1e-5
        for actual, expected in (
            (sku.box.y + sku.box.height / 2, (scene.qr.bottom + height) / 2),
            (sku.box.y, protected.bottom),
            (sku.box.bottom, height - scene.margin_mm),
        )
    )
    if attribution == "mark":
        mark = scene.attribution
        assert mark is not None
        assert mark.y == pytest.approx(scene.margin_mm)
        assert width - mark.right == pytest.approx(scene.margin_mm)
        assert not overlaps(mark, protected)
        assert not any(overlaps(mark, text.box) for text in scene.texts)
    elif attribution == "full":
        mark = scene.attribution
        assert mark is not None
        qr_zone_top = (
            0
            if width >= height
            else next(rule.y for rule in scene.rules if rule.x == 0) + half_stroke
        )
        assert any(
            abs(actual - expected) < 1e-5
            for actual, expected in (
                (mark.y + mark.height / 2, (qr_zone_top + scene.qr.y) / 2),
                (mark.bottom, protected.y),
                (mark.y, qr_zone_top + scene.margin_mm),
            )
        )
        assert not overlaps(mark, protected)
    else:
        assert scene.attribution is None
    assert scene.swatch is None


def test_comment_and_characteristics_share_size_without_truncation(material, measure_text):
    comment = "Печатайте закалённым соплом. После вскрытия храните материал в сухом боксе. " * 2
    options = LabelOptions(width_mm=150, height_mm=100, comment=comment)
    scene = compose_label(material, options, 33, measure_text)
    lines = [text for text in scene.texts if text.role == "comment"]
    assert " ".join(text.text for text in lines) == comment.strip()
    assert {text.size for text in lines} == {scene.body_size_mm}
    assert {text.size for text in scene.texts if text.role in options.fields} == {
        scene.body_size_mm
    }


@pytest.mark.parametrize("comment", ["W" * 200, "Ш" * 200, "и\u0306" * 100])
@pytest.mark.parametrize("dimensions", [(150, 100), (100, 150), (220, 220)])
def test_long_comment_wraps_without_losing_characters_or_splitting_accents(
    material, measure_text, comment, dimensions
):
    width, height = dimensions
    scene = compose_label(
        material, LabelOptions(width_mm=width, height_mm=height, comment=comment), 33, measure_text
    )
    lines = [text for text in scene.texts if text.role == "comment"]
    assert len(lines) > 1
    assert "".join(text.text for text in lines) == comment
    assert all(not unicodedata.combining(text.text[0]) for text in lines)
    assert all(measure_text(text.text, text.size, text.bold) <= text.box.width for text in lines)
    assert {text.size for text in lines} == {scene.body_size_mm}
    assert set(LabelOptions().fields) <= {text.role for text in scene.texts}


def test_fewer_fields_increase_available_type_size(material, measure_text):
    all_fields = compose_label(material, LabelOptions(), 33, measure_text)
    two_fields = compose_label(material, LabelOptions(fields=["nozzle", "bed"]), 33, measure_text)
    assert two_fields.body_size_mm >= all_fields.body_size_mm
    assert {text.role for text in two_fields.texts}.isdisjoint(
        {"drying", "abrasiveness", "density", "diameter"}
    )


def test_color_swatch_is_explicit_and_does_not_replace_real_ral(material, measure_text):
    scene = compose_label(material, LabelOptions(color_mode="color"), 33, measure_text)
    assert scene.swatch is not None
    assert next(text.text for text in scene.texts if text.role == "ral") == "RAL 7016"
    assert not any(text.text == material.color_hex for text in scene.texts)


def test_classic_is_only_square_qr_with_shared_white_clearance(material, measure_text):
    scene = compose_label(
        material,
        LabelOptions(kind="classic", width_mm=30, height_mm=30, qr_mark=True),
        41,
        measure_text,
    )
    assert not scene.texts and scene.attribution is None and not scene.rules
    assert scene.qr.width == scene.qr.height
    assert scene.qr.x == pytest.approx(max(scene.margin_mm, scene.quiet_zone_mm))


def test_impossible_content_has_explicit_failure_not_missing_qr(material, measure_text):
    options = LabelOptions(width_mm=8, height_mm=8)
    with pytest.raises(LabelDoesNotFit):
        compose_label(material, options, 33, measure_text)


@pytest.mark.parametrize("attribution", ["full", "mark", "none"])
@pytest.mark.parametrize("dpi", [203, 300, 600])
def test_qr_fills_existing_zone_with_shared_side_clearance(
    material, measure_text, attribution, dpi
):
    options = LabelOptions(width_mm=40, height_mm=30, attribution=attribution, dpi=dpi)
    scene = compose_label(material, options, 29, measure_text)
    divider = next(rule for rule in scene.rules if rule.width == 0)
    # Expanding the QR must not move the original text/QR division.
    assert divider.x == pytest.approx(40 * (1 - 0.44))
    clearance = scene.quiet_zone_mm
    assert scene.qr.x - divider.x - rule_stroke_mm(scene.margin_mm) / 2 == pytest.approx(
        clearance, abs=1e-5
    )
    assert 40 - scene.qr.right == pytest.approx(clearance, abs=1e-5)
    assert scene.qr.width > 13.7
    sku = next(text for text in scene.texts if text.role == "sku")
    assert sku.box.width <= scene.qr.width * 0.92 + 1e-6
    assert sku.size <= scene.qr.width / 6 + 1e-6


@pytest.mark.parametrize("dimensions", [(40, 12), (12, 40)])
def test_micro_label_gains_qr_space_without_external_attribution(
    material, measure_text, dimensions
):
    width, height = dimensions
    full = compose_label(material, LabelOptions(width_mm=width, height_mm=height), 29, measure_text)
    micro = compose_label(
        material,
        LabelOptions(width_mm=width, height_mm=height, attribution="none"),
        29,
        measure_text,
    )
    assert micro.qr.width >= full.qr.width
    if width > height:
        assert micro.qr.width > full.qr.width
    else:
        # Portrait may already be width-limited at the two-dot print grid.
        assert micro.body_size_mm >= full.body_size_mm
    assert micro.attribution is None
    assert any(text.role == "sku" for text in micro.texts)
    assert not any(text.role == "attribution" for text in micro.texts)


@pytest.mark.parametrize(
    "width,height,min_qr",
    [(30, 40, 13), (30, 50, 16.5), (29, 62, 19.5), (25, 54, 17), (38.1, 63.5, 21), (100, 150, 50)],
)
def test_vertical_qr_is_not_starved_by_the_information_block(width, height, min_qr):
    from app.services.label_fonts import measure_text

    data = LabelData(
        "FH-461",
        "Label Print Proof",
        "PETG-CF",
        "Arctic Graphite",
        (
            ("nozzle", "Сопло", "235–255\u00a0°C"),
            ("bed", "Стол", "75–90\u00a0°C"),
            ("drying", "Сушка", "65\u00a0°C · 6\u00a0ч"),
            ("abrasiveness", "Твёрдость сопла", "≥55\u00a0HRC"),
            ("diameter", "Диаметр", "1,75\u00a0мм"),
            ("density", "Плотность", "1,25\u00a0г/см³"),
        ),
        ral="RAL 7016",
    )
    options = LabelOptions(width_mm=width, height_mm=height)
    scene = compose_label(data, options, 29, measure_text)
    # Sub-dot type-fitting differences do not starve the QR's physical area.
    assert scene.qr.width >= min_qr - 25.4 / options.dpi
    assert scene.body_size_mm >= 0.95
    assert set(options.fields) <= {text.role for text in scene.texts}
    divider = next(rule for rule in scene.rules if rule.x == 0)
    body_bottom = max(
        text.box.bottom for text in scene.texts if text.role not in {"sku", "attribution"}
    )
    assert divider.y - body_bottom == pytest.approx(scene.margin_mm)
    sku = next(text for text in scene.texts if text.role == "sku")
    assert sku.text == data.sku
    assert sku.box.width <= scene.qr.width * 0.92 + 1e-6
    assert sku.size <= scene.qr.width / 6 + 1e-6
    assert scene.attribution is not None
    caption = next(text for text in scene.texts if text.role == "attribution")
    assert caption.box.right - scene.attribution.x <= scene.qr.width * 0.94 + 1e-6


@pytest.mark.parametrize("dimensions", [(50, 30), (62, 29), (54, 25), (63.5, 38.1)])
def test_qr_takes_available_space_before_enlarging_supporting_type(
    material, measure_text, dimensions
):
    width, height = dimensions
    scene = compose_label(
        material, LabelOptions(width_mm=width, height_mm=height), 29, measure_text
    )
    divider = next(rule for rule in scene.rules if rule.width == 0)
    available_width = width - divider.x - rule_stroke_mm(scene.margin_mm) / 2
    sku = next(text for text in scene.texts if text.role == "sku")
    caption = next(text for text in scene.texts if text.role == "attribution")
    if scene.qr.width + 2 * scene.quiet_zone_mm < available_width - 1e-5:
        assert (
            scene.qr.height
            + 2 * scene.quiet_zone_mm
            + 2 * scene.margin_mm
            + sku.box.height
            + scene.attribution.height
            == pytest.approx(height, abs=1e-5)
        )
        assert sku.size <= scene.body_size_mm + 1e-5
        assert caption.size <= scene.body_size_mm + 1e-5


@pytest.mark.parametrize("attribution", ["full", "mark", "none"])
@pytest.mark.parametrize("fields", [[], ["nozzle"], ["nozzle", "bed", "drying"]])
def test_vertical_fewer_fields_grow_both_qr_and_type(material, measure_text, attribution, fields):
    options = LabelOptions(width_mm=30, height_mm=50, attribution=attribution)
    full = compose_label(material, options, 29, measure_text)
    reduced = compose_label(
        material, options.model_copy(update={"fields": fields}), 29, measure_text
    )
    assert reduced.body_size_mm >= full.body_size_mm
    assert reduced.qr.width >= full.qr.width


@pytest.mark.parametrize("attribution", ["full", "mark", "none"])
def test_vertical_comment_uses_the_same_readable_scale_as_fields(
    material, measure_text, attribution
):
    comment = "Печатайте закалённым соплом. После вскрытия храните материал в сухом боксе. " * 2
    options = LabelOptions(width_mm=100, height_mm=150, comment=comment, attribution=attribution)
    scene = compose_label(material, options, 33, measure_text)
    lines = [text for text in scene.texts if text.role == "comment"]
    assert " ".join(text.text for text in lines) == comment.strip()
    assert {text.size for text in lines} == {scene.body_size_mm}
    assert {text.size for text in scene.texts if text.role in options.fields} == {
        scene.body_size_mm
    }
    assert scene.body_size_mm >= 0.95
    assert scene.qr.width >= 40
