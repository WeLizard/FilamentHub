"""Sheet count, preview placement and vector PDF must describe the same copies."""

import re
import zlib
from xml.etree import ElementTree as ET

import pytest
from pydantic import ValidationError

from app.api.v1.endpoints.labels import _render
from app.schemas.label import LabelExportOptions, LabelOptions
from app.services.label_layout import LabelData, LabelDoesNotFit, compose_sheet, sheet_positions
from app.services.label_renderer import export_label, render_label, sheet_svg


@pytest.fixture
def sheet_data():
    return LabelData("FH-001", "OlgaCraft", "PETG-CF", "Arctic Graphite", ())


@pytest.mark.parametrize(
    "media,width,height,margin,gap,columns,rows",
    [
        ("a4", 50, 30, 5, 2, 3, 9),
        ("letter", 50, 30, 5, 2, 3, 8),
        ("a4", 30, 50, 5, 2, 6, 5),
        ("a4", 40, 12, 5, 2, 4, 20),
        ("letter", 63.5, 38.1, 5, 2, 3, 6),
        ("a4", 8, 8, 0, 0, 26, 37),
    ],
)
def test_sheet_grid_matches_client_contract(media, width, height, margin, gap, columns, rows):
    sheet = compose_sheet(
        LabelExportOptions(
            media=media,
            label=LabelOptions(width_mm=width, height_mm=height),
            page_margin_mm=margin,
            gap_mm=gap,
        )
    )
    assert (sheet.columns, sheet.rows, sheet.capacity) == (columns, rows, columns * rows)


@pytest.mark.parametrize(
    "media,capacity,expected_counts", [("a4", 27, [1, 27, 22]), ("letter", 24, [1, 24, 24, 1])]
)
def test_partial_first_sheet_is_not_repeated_on_later_pages(
    sheet_data, media, capacity, expected_counts
):
    options = LabelExportOptions(media=media, copies=50, start_position=capacity)
    sheet = compose_sheet(options)
    assert sheet.page_count == len(expected_counts)
    rendered = render_label(sheet_data, options.label)
    for page, count in enumerate(expected_counts, start=1):
        positions = sheet_positions(options, sheet, page)
        assert len(positions) == count
        assert positions[0] == ((109, 5 + (sheet.rows - 1) * 32) if page == 1 else (5, 5))
        svg = sheet_svg(rendered, options, page)[0]
        cells = ET.fromstring(svg).findall("{http://www.w3.org/2000/svg}use")
        assert [(float(cell.attrib["x"]), float(cell.attrib["y"])) for cell in cells] == positions
        preview = _render(sheet_data, options, None, False, page)
        assert preview["sheet"]["page_count"] == len(expected_counts)
        assert (preview["page_number"], preview["page_copies"]) == (page, count)
        assert preview["page_svg"] == svg
        assert "pages" not in preview  # Never duplicate every page's vector payload in a response.
    with pytest.raises(LabelDoesNotFit):
        sheet_svg(rendered, options, sheet.page_count + 1)


def pdf_streams(pdf):
    return [
        zlib.decompress(match[1]) for match in re.finditer(rb"stream\n(.*?)\nendstream", pdf, re.S)
    ]


@pytest.mark.parametrize("copies,start,pages", [(27, 1, 1), (28, 1, 2), (28, 27, 2), (50, 27, 3)])
@pytest.mark.parametrize("crop_marks", [False, True])
def test_vector_pdf_contains_every_copy_without_a_trailing_blank_page(
    sheet_data, copies, start, pages, crop_marks
):
    options = LabelExportOptions(
        media="a4",
        copies=copies,
        start_position=start,
        format="pdf",
        crop_marks=crop_marks,
        label=LabelOptions(border=crop_marks),
    )
    pdf = export_label(sheet_data, options)
    streams = pdf_streams(pdf)
    content = pdf + b"\n".join(streams)
    assert len(re.findall(rb"/Type /Page\b", content)) == pages
    assert b"/Subtype /Image" not in content
    from cairosvg.surface import PDFSurface

    rendered = render_label(sheet_data, options.label)
    sheet = compose_sheet(options)
    # Compare every drawing stream with the standalone conversion of that
    # page's preview: coordinates, path sizes and copy counts must all match.
    drawing_streams = [stream for stream in streams if b" cm\n" in stream]
    assert len(drawing_streams) == pages
    for page, drawing in enumerate(drawing_streams, start=1):
        svg = sheet_svg(rendered, options, page)[0]
        expected = PDFSurface.convert(bytestring=svg.encode(), dpi=96)
        assert drawing in pdf_streams(expected)
    assert sum(len(sheet_positions(options, sheet, page)) for page in range(1, pages + 1)) == copies


def test_pdf_is_bounded_to_fifty_total_copies_even_at_one_label_per_page(sheet_data):
    options = LabelExportOptions(
        media="a4", copies=50, format="pdf", label=LabelOptions(width_mm=150, height_mm=150)
    )
    assert compose_sheet(options).page_count == 50
    pdf = export_label(sheet_data, options)
    assert len(re.findall(rb"/Type /Page\b", pdf + b"\n".join(pdf_streams(pdf)))) == 50
    with pytest.raises(ValidationError):
        LabelExportOptions(media="a4", copies=51)


@pytest.mark.parametrize("format", ["svg", "png"])
def test_single_page_formats_reject_multi_page_exports_without_losing_copies(sheet_data, format):
    options = LabelExportOptions(media="a4", copies=28, format=format)
    with pytest.raises(LabelDoesNotFit, match="Multiple sheets require PDF"):
        export_label(sheet_data, options)


def test_sheet_rejects_nonexistent_first_cells_and_oversized_labels():
    for options in (
        LabelExportOptions(media="a4", start_position=28),
        LabelExportOptions(media="a4", label=LabelOptions(width_mm=220, height_mm=220)),
        LabelExportOptions(media="a4", crop_marks=True, page_margin_mm=1.49),
        LabelExportOptions(media="a4", crop_marks=True, gap_mm=0),
        LabelExportOptions(media="letter", crop_marks=True, gap_mm=10, page_margin_mm=5.49),
    ):
        with pytest.raises(LabelDoesNotFit):
            compose_sheet(options)


@pytest.mark.parametrize("media", ["a4", "letter"])
@pytest.mark.parametrize("gap", [0.5, 2, 10])
def test_cut_guides_share_gap_centers_without_changing_grid_or_entering_labels(
    sheet_data, media, gap
):
    plain = LabelExportOptions(media=media, copies=50, page_margin_mm=gap / 2 + 0.5, gap_mm=gap)
    # Exercise a nearly empty first page, complete sheets, and a partial last page.
    plain.start_position = compose_sheet(plain).capacity
    options = plain.model_copy(update={"crop_marks": True})
    sheet = compose_sheet(options)
    assert sheet == compose_sheet(plain)
    rendered = render_label(sheet_data, options.label)
    for page in range(1, sheet.page_count + 1):
        positions = sheet_positions(options, sheet, page)
        assert positions == sheet_positions(plain, sheet, page)
        svg, width, height, _ = sheet_svg(rendered, options, page)
        root = ET.fromstring(svg)
        path = root.find("{http://www.w3.org/2000/svg}path[@data-role='crop-marks']")
        assert path is not None
        assert path.attrib["stroke"] == "#888888"
        assert path.attrib["stroke-dasharray"] == "2 0.75 0.25 0.75"
        marks = re.findall(r"M([\d.]+) ([\d.]+) ([hv])([\d.]+)", path.attrib["d"])
        assert marks
        marked_x, marked_y = set(), set()
        actual_edges = set()
        stroke = float(path.attrib["stroke-width"])
        for sx, sy, direction, distance in marks:
            x, y, length = float(sx), float(sy), float(distance)
            right = x + (length if direction == "h" else 0)
            bottom = y + (length if direction == "v" else 0)
            assert 0 <= x <= right <= width
            assert 0 <= y <= bottom <= height
            (marked_x if direction == "v" else marked_y).add(x if direction == "v" else y)
            # Split merged lines back into cell edges to prove that shared edges
            # are printed once and empty cells do not acquire an extra grid.
            pitch = (
                options.label.width_mm + gap if direction == "h" else options.label.height_mm + gap
            )
            count = round(length / pitch)
            assert length == pytest.approx(count * pitch)
            for step in range(count):
                edge = (
                    round(x + (step * pitch if direction == "h" else 0), 6),
                    round(y + (step * pitch if direction == "v" else 0), 6),
                    direction,
                )
                assert edge not in actual_edges
                actual_edges.add(edge)
            for cx, cy in positions:
                assert (
                    right + stroke / 2 <= cx
                    or x - stroke / 2 >= cx + options.label.width_mm
                    or bottom + stroke / 2 <= cy
                    or y - stroke / 2 >= cy + options.label.height_mm
                )
        expected_edges = set()
        for x, y in positions:
            left, top = x - gap / 2, y - gap / 2
            right, bottom = (
                x + options.label.width_mm + gap / 2,
                y + options.label.height_mm + gap / 2,
            )
            for ex, ey, direction in (
                (left, top, "h"),
                (left, bottom, "h"),
                (left, top, "v"),
                (right, top, "v"),
            ):
                expected_edges.add((round(ex, 6), round(ey, 6), direction))
        assert actual_edges == expected_edges
        assert marked_x == {
            edge
            for x, _ in positions
            for edge in (x - gap / 2, x + options.label.width_mm + gap / 2)
        }
        assert marked_y == {
            edge
            for _, y in positions
            for edge in (y - gap / 2, y + options.label.height_mm + gap / 2)
        }
        plain_svg = sheet_svg(rendered, plain, page)[0]
        assert "crop-marks" not in plain_svg
