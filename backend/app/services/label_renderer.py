"""Trusted SVG scenes with bounded PNG/PDF conversion and no network resources."""

import base64
from dataclasses import asdict, replace
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree as ET

import qrcode
from PIL import Image, ImageOps

from app.schemas.label import LabelExportOptions, LabelOptions
from app.services.label_fonts import measure_text, text_paths
from app.services.label_layout import (
    Box,
    LabelData,
    LabelDoesNotFit,
    LabelSheet,
    compose_label,
    compose_sheet,
    rule_stroke_mm,
    sheet_cut_lines,
    sheet_positions,
)
from app.services.qr_mark import MARK_VIEWBOX, mark_paths
from app.services.qr_service import _qr_target_url

RENDERER_REVISION = "label-scene-6"
MAX_OUTPUT_PIXELS = 36_000_000
MAX_SVG_BYTES = 4_000_000


class LabelBrandLogoUnavailable(ValueError):
    """A mark-only brand signature requires an actual printable logo."""


@lru_cache(maxsize=1)
def _mark_paths() -> tuple[str, ...]:
    root = ET.parse(Path(__file__).resolve().parents[1] / "assets/labels/fh-mark.svg").getroot()
    return tuple(node.attrib["d"] for node in root.findall("{http://www.w3.org/2000/svg}path"))


def _mark(box: Box, color: str) -> str:
    scale = min(box.width / 358.41, box.height / 289.05)
    x = box.x + (box.width - 358.41 * scale) / 2
    y = box.y + (box.height - 289.05 * scale) / 2
    return (
        f'<g fill="{color}" transform="translate({x:.6f} {y:.6f}) scale({scale:.9f})">'
        + "".join(f'<path d="{path}"/>' for path in _mark_paths())
        + "</g>"
    )


def _logo_image(content: bytes, mono: bool) -> str:
    with Image.open(BytesIO(content), formats=["PNG", "JPEG", "WEBP"]) as source:
        if source.width * source.height > 2_000_000:
            raise ValueError("Brand logo exceeds the pixel budget")
        source.load()
        rgba = source.convert("RGBA")
        flattened = Image.new("RGBA", rgba.size, "white")
        flattened.alpha_composite(rgba)
        result = flattened.convert("RGB")
        if mono:
            result = ImageOps.grayscale(result).convert("1")
        output = BytesIO()
        result.save(output, format="PNG")
    return base64.b64encode(output.getvalue()).decode("ascii")


def _matrix(sku: str, branded: bool):
    qr = qrcode.QRCode(
        error_correction=(
            qrcode.constants.ERROR_CORRECT_H if branded else qrcode.constants.ERROR_CORRECT_M
        ),
        border=0,
    )
    qr.add_data(_qr_target_url(sku))
    qr.make(fit=True)
    return qr.get_matrix()


def _matrix_path(matrix: list[list[bool]], window: int) -> str:
    """Trace filled regions without internal cell edges that can rasterize as seams."""
    size = len(matrix)
    start = (size - window) // 2

    def filled(x: int, y: int) -> bool:
        return (
            0 <= x < size
            and 0 <= y < size
            and matrix[y][x]
            and not (window and start <= x < start + window and start <= y < start + window)
        )

    # Clockwise edges keep black on their right; hole boundaries run the other way.
    edges: dict[tuple[int, int, int], None] = {}
    directions = ((1, 0), (0, 1), (-1, 0), (0, -1))
    for y in range(size):
        for x in range(size):
            if not filled(x, y):
                continue
            for nx, ny, edge in (
                (x, y - 1, (x, y, 0)),
                (x + 1, y, (x + 1, y, 1)),
                (x, y + 1, (x + 1, y + 1, 2)),
                (x - 1, y, (x, y + 1, 3)),
            ):
                if not filled(nx, ny):
                    edges[edge] = None

    paths = []
    for x, y, direction in tuple(edges):
        if (x, y, direction) not in edges:
            continue
        origin = (x, y)
        path = [f"M{x} {y}"]
        while True:
            del edges[x, y, direction]
            dx, dy = directions[direction]
            x, y = x + dx, y + dy
            if (x, y) == origin:
                break
            path.append(f"L{x} {y}")
            # At diagonal contacts, turn right to keep the contours separate.
            direction = next(
                turn
                for turn in ((direction + 1) % 4, direction, (direction - 1) % 4)
                if (x, y, turn) in edges
            )
        paths.append("".join(path) + "z")
    return "".join(paths)


def render_label(data: LabelData, options: LabelOptions, logo: bytes | None = None) -> dict:
    if options.kind == "full" and options.brand_mode == "mark" and not logo:
        raise LabelBrandLogoUnavailable("Brand mark is unavailable")
    branded = options.kind == "classic" and options.qr_mark
    matrix = _matrix(data.sku, branded)
    modules = len(matrix)
    data = replace(data, has_brand_logo=bool(logo))
    scene = compose_label(data, options, modules, measure_text)
    outline = (
        f'<rect width="{scene.width_mm}" height="{scene.height_mm}" '
        f'rx="{scene.corner_radius_mm}"/>'
    )
    content = [f'<defs><clipPath id="label-outline">{outline}</clipPath></defs>']
    # Paint the background and edge together, outside the content clip. A white
    # background beneath a separately clipped stroke leaves a pale corner halo.
    if scene.border_width_mm:
        stroke = scene.border_width_mm
        content.append(
            f'<rect data-role="label-border" x="{stroke / 2}" y="{stroke / 2}" '
            f'width="{scene.width_mm - stroke}" height="{scene.height_mm - stroke}" '
            f'rx="{scene.corner_radius_mm - stroke / 2}" fill="white" '
            f'stroke="#111111" stroke-width="{stroke}"/>'
        )
    else:
        content.append(
            f'<rect width="{scene.width_mm}" height="{scene.height_mm}" '
            f'rx="{scene.corner_radius_mm}" fill="white"/>'
        )
    content.append('<g clip-path="url(#label-outline)">')
    for rule in scene.rules:
        content.append(
            f'<path d="M {rule.x} {rule.y} h {rule.width} v {rule.height}" stroke="#aaaaaa" stroke-width="{rule_stroke_mm(scene.margin_mm)}"/>'
        )
    for text in scene.texts:
        box = text.box
        color = "#111111"
        if text.role.endswith("_heading") or text.role in {"ral", "comment_heading"}:
            color = "#555555"
        if text.role == "material":
            chip_fill = "#111111" if options.color_mode == "mono" else "#263746"
            content.append(
                f'<rect x="{box.x - text.size * 0.15}" y="{box.y}" width="{box.width + text.size * 0.3}" height="{box.height}" rx="{text.size * 0.12}" fill="{chip_fill}"/>'
            )
            color = "white"
        if text.role == "attribution" and options.color_mode == "color":
            first = measure_text("Filament", text.size, True)
            content.append(
                text_paths("Filament", box.x, box.y, box.height, text.size, True, "#a78bfa")
            )
            content.append(
                text_paths("Hub", box.x + first, box.y, box.height, text.size, True, "#34d399")
            )
        else:
            content.append(
                text_paths(text.text, box.x, box.y, box.height, text.size, text.bold, color)
            )
    if scene.attribution:
        content.append(
            _mark(scene.attribution, "#111111" if options.color_mode == "mono" else "#a78bfa")
        )
    if scene.swatch:
        box = scene.swatch
        content.append(
            f'<circle cx="{box.x + box.width / 2}" cy="{box.y + box.height / 2}" r="{box.width / 2}" fill="{data.color_hex}"/>'
        )
    if scene.brand_logo and logo:
        box = scene.brand_logo
        image = _logo_image(logo, options.color_mode == "mono")
        content.append(
            f'<image x="{box.x}" y="{box.y}" width="{box.width}" height="{box.height}" preserveAspectRatio="xMidYMid meet" href="data:image/png;base64,{image}"/>'
        )
    module = scene.qr.width / modules
    mark_window = max(3, int(modules * 0.2)) if branded else 0
    if branded and (modules - mark_window) % 2:
        mark_window += 1
    window = mark_window + 4 if branded else 0
    start = (modules - window) // 2
    content.append(
        f'<path fill="black" shape-rendering="crispEdges" transform="translate({scene.qr.x:.6f} {scene.qr.y:.6f}) scale({module:.9f})" d="{_matrix_path(matrix, window)}"/>'
    )
    if branded:
        side = window * module
        x, y = scene.qr.x + start * module, scene.qr.y + start * module
        # Both the white frame and black inner padding are additional clearance;
        # neither shrinks the mark's original twenty-percent footprint.
        content.append(
            f'<rect data-role="qr-mark-frame" x="{x}" y="{y}" width="{side}" height="{side}" fill="white"/>'
        )
        x, y, side = x + module, y + module, side - 2 * module
        content.append(
            f'<rect data-role="qr-mark-background" x="{x}" y="{y}" width="{side}" height="{side}" fill="black"/>'
        )
        x, y, side = x + module, y + module, side - 2 * module
        content.append(
            f'<g data-role="qr-mark" fill="white" transform="translate({x:.6f} {y:.6f}) scale({side / MARK_VIEWBOX:.9f})">'
            + "".join(f'<path d="{path}"/>' for path in mark_paths())
            + "</g>"
        )
    content.append("</g>")
    body = "".join(content)
    svg = _svg(scene.width_mm, scene.height_mm, body)
    return {
        "svg": svg,
        "content": body,
        "scene": asdict(scene),
        "modules": modules,
        "revision": RENDERER_REVISION,
        "proof_required": branded or scene.dots_per_module < 4 - 1e-6,
        "printable": scene.dots_per_module >= 2 - 1e-6,
    }


def _svg(width: float, height: float, content: str) -> str:
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{width}mm" height="{height}mm" viewBox="0 0 {width} {height}">{content}</svg>'
    if len(svg.encode()) > MAX_SVG_BYTES:
        raise ValueError("Label exceeds the SVG budget")
    return svg


def sheet_svg(
    rendered: dict, options: LabelExportOptions, page: int = 1
) -> tuple[str, float, float, int]:
    sheet = compose_sheet(options)
    positions = sheet_positions(options, sheet, page)
    if options.media == "single":
        return rendered["svg"], options.label.width_mm, options.label.height_mm, 1
    width, height = sheet.width_mm, sheet.height_mm
    content = [
        f'<rect width="{width}" height="{height}" fill="white"/>',
        f'<defs><g id="label">{rendered["content"]}</g></defs>',
    ]
    for x, y in positions:
        content.append(f'<use xlink:href="#label" x="{x}" y="{y}"/>')
    if options.crop_marks:
        marks = [
            f"M{line.x} {line.y} " + (f"h{line.width}" if line.width else f"v{line.height}")
            for line in sheet_cut_lines(options, sheet, page)
        ]
        content.append(
            f'<path data-role="crop-marks" d="{" ".join(marks)}" fill="none" '
            'stroke="#888888" stroke-width="0.15" stroke-linecap="butt" '
            'stroke-dasharray="2 0.75 0.25 0.75"/>'
        )
    return _svg(width, height, "".join(content)), width, height, sheet.capacity


def _sheet_pdf(rendered: dict, options: LabelExportOptions, sheet: LabelSheet) -> bytes:
    from cairosvg.parser import Tree
    from cairosvg.surface import Surface, cairo

    output = BytesIO()
    points = 72 / 25.4
    document = cairo.PDFSurface(output, sheet.width_mm * points, sheet.height_mm * points)

    class SheetPage(Surface):
        def _create_surface(self, width, height):
            return document, width, height

    # Draw the exact preview SVG onto each physical PDF page. Drawing directly
    # avoids Cairo's raster fallback for translated, clipped recording surfaces.
    try:
        for page in range(1, sheet.page_count + 1):
            svg = sheet_svg(rendered, options, page)[0]
            surface = SheetPage(
                Tree(bytestring=svg.encode(), url_fetcher=_fetch_embedded), None, 96
            )
            surface.context.show_page()
    finally:
        document.finish()
    return output.getvalue()


def _fetch_embedded(url: str, resource_type: str) -> bytes:
    # Cairo receives only generated paths and bounded, normalized PNGs. Never
    # allow a renderer to turn a stored logo URL into network or filesystem IO.
    prefix = "data:image/png;base64,"
    if not url.startswith(prefix) or len(url) > 3_000_000:
        raise ValueError("External SVG resources are not permitted")
    return base64.b64decode(url[len(prefix) :], validate=True)


def export_label(data: LabelData, options: LabelExportOptions, logo: bytes | None = None) -> bytes:
    from cairosvg.surface import PDFSurface, PNGSurface

    rendered = render_label(data, options.label, logo)
    if not rendered["printable"]:
        raise LabelDoesNotFit("QR modules require a larger label or higher print resolution")
    sheet = compose_sheet(options)
    if options.format == "pdf" and options.media != "single":
        return _sheet_pdf(rendered, options, sheet)
    if sheet.page_count > 1:
        raise LabelDoesNotFit("Multiple sheets require PDF output")
    svg, width, height, _ = sheet_svg(rendered, options)
    if options.format == "svg":
        return svg.encode()
    if options.format == "pdf":
        return PDFSurface.convert(bytestring=svg.encode(), url_fetcher=_fetch_embedded)
    pixel_w = round(width * options.label.dpi / 25.4)
    pixel_h = round(height * options.label.dpi / 25.4)
    if pixel_w * pixel_h > MAX_OUTPUT_PIXELS:
        raise LabelDoesNotFit("Raster dimensions exceed the export budget")
    image = PNGSurface.convert(
        bytestring=svg.encode(),
        output_width=pixel_w,
        output_height=pixel_h,
        url_fetcher=_fetch_embedded,
    )
    # Preserve physical dimensions for print applications that read PNG pHYs.
    with Image.open(BytesIO(image)) as png:
        output = BytesIO()
        png.save(output, format="PNG", dpi=(options.label.dpi, options.label.dpi))
        return output.getvalue()
