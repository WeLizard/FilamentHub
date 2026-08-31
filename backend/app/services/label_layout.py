"""Physical label composition; all coordinates and typography are millimetres.

The layout consumes measured text, never browser/CSS dimensions. The resulting
scene is shared by preview and every export backend.
"""

import math
import re
from dataclasses import dataclass, field
from typing import Callable

from app.schemas.label import LabelOptions

MeasureText = Callable[[str, float, bool], float]


class LabelDoesNotFit(ValueError):
    """No readable layout exists for the selected content and media."""


@dataclass(frozen=True)
class Box:
    x: float
    y: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height


@dataclass(frozen=True)
class LabelText:
    text: str
    box: Box
    size: float
    role: str
    bold: bool = False
    color: str = "#111111"


@dataclass(frozen=True)
class LabelData:
    sku: str
    brand: str
    material: str
    name: str
    fields: tuple[tuple[str, str, str], ...]
    ral: str = ""
    color_hex: str = ""
    comment_heading: str = ""
    has_brand_logo: bool = False


@dataclass
class LabelScene:
    width_mm: float
    height_mm: float
    margin_mm: float
    qr: Box
    quiet_zone_mm: float
    texts: list[LabelText] = field(default_factory=list)
    rules: list[Box] = field(default_factory=list)
    brand_logo: Box | None = None
    attribution: Box | None = None
    swatch: Box | None = None
    body_size_mm: float = 0
    dots_per_module: float = 0
    corner_radius_mm: float = 0


def _wrap(
    text: str, width: float, size: float, measure: MeasureText, bold: bool = False
) -> list[str]:
    # Keep Latin words and numeric/unit groups intact; CJK can break by character.
    tokens = re.findall(
        r"[\u2e80-\u9fff\uf900-\ufaff]|[^ \t\n\u2e80-\u9fff\uf900-\ufaff]+|[ \t]+|\n", text
    )
    lines: list[str] = []
    current = ""
    for token in tokens:
        if token == "\n":
            lines.append(current.rstrip())
            current = ""
            continue
        candidate = current + token
        if measure(candidate.rstrip(), size, bold) <= width:
            current = candidate
        elif token.isspace():
            continue
        else:
            if current.strip():
                lines.append(current.rstrip())
            current = token.lstrip()
            if measure(current, size, bold) > width:
                raise LabelDoesNotFit("Unbreakable text exceeds its zone")
    if current.strip():
        lines.append(current.rstrip())
    return lines or [""]


def _body(
    data: LabelData,
    options: LabelOptions,
    box: Box,
    size: float,
    measure: MeasureText,
) -> tuple[list[LabelText], list[Box], Box | None, Box | None]:
    texts: list[LabelText] = []
    rules: list[Box] = []
    y = box.y
    gap = size * 0.4
    logo = None
    swatch = None

    def text_block(
        text: str,
        x: float,
        width: float,
        font_size: float,
        role: str,
        bold: bool = False,
        color: str = "#111111",
    ) -> float:
        nonlocal y
        if role == "material":
            x += font_size * 0.15
            width -= font_size * 0.3
        lines = _wrap(text, width, font_size, measure, bold)
        for line in lines:
            texts.append(
                LabelText(
                    line,
                    Box(x, y, measure(line, font_size, bold), font_size * 1.2),
                    font_size,
                    role,
                    bold,
                    color,
                )
            )
            y += font_size * 1.2
        return len(lines) * font_size * 1.2

    logo_size = size * 1.35 if options.brand_logo and data.has_brand_logo else 0
    brand_width = measure(data.brand, size, True) + (logo_size + gap if logo_size else 0)
    material_width = measure(data.material, size, True) + size * 0.5
    compact = options.width_mm / options.height_mm >= 2.5
    if compact and brand_width + material_width + gap < box.width:
        if logo_size:
            logo = Box(box.right - brand_width, y, logo_size, logo_size)
        brand_x = box.right - measure(data.brand, size, True)
        texts.append(
            LabelText(
                data.brand, Box(brand_x, y, box.right - brand_x, size * 1.2), size, "brand", True
            )
        )
        text_block(data.material, box.x, material_width, size, "material", True)
    else:
        if logo_size:
            logo = Box(box.x, y, logo_size, logo_size)
        brand_x = box.x + (logo_size + gap if logo_size else 0)
        brand_y = y
        text_block(data.brand, brand_x, box.right - brand_x, size, "brand", True)
        y = max(y, brand_y + logo_size) + gap
        text_block(data.material, box.x, box.width, size, "material", True)
    y += gap
    text_block(data.name, box.x, box.width, size * 1.65, "name", True)
    if data.ral or (options.color_mode == "color" and data.color_hex):
        y += gap * 0.4
        if options.color_mode == "color" and data.color_hex:
            swatch = Box(box.x, y, size * 0.75, size * 0.75)
        text_block(
            data.ral,
            box.x + (size if swatch else 0),
            box.width - (size if swatch else 0),
            size * 0.8,
            "ral",
        )
    if options.comment.strip():
        y += gap
        text_block(data.comment_heading, box.x, box.width, size * 0.65, "comment_heading")
        text_block(options.comment.strip(), box.x, box.width, size, "comment")
    selected = [entry for key in options.fields for entry in data.fields if entry[0] == key]
    if selected:
        y += gap
        rules.append(Box(box.x, y, box.width, 0))
        y += gap
        candidates = []
        for columns in range(1, len(selected) + 1):
            cell_width = (box.width - gap * (columns - 1)) / columns
            cells = []
            try:
                for key, heading, value in selected:
                    title_lines = _wrap(heading, cell_width, size * 0.65, measure)
                    value_lines = _wrap(value, cell_width, size, measure)
                    cells.append((key, title_lines, value_lines))
            except LabelDoesNotFit:
                continue
            row_heights = [
                max(
                    len(c[1]) * size * 0.8 + len(c[2]) * size * 1.2
                    for c in cells[start : start + columns]
                )
                for start in range(0, len(cells), columns)
            ]
            total = sum(row_heights) + gap * (len(row_heights) - 1)
            candidates.append((total, columns, cells, row_heights, cell_width))
        if not candidates:
            raise LabelDoesNotFit("Selected characteristics exceed the text zone")
        total, columns, cells, row_heights, cell_width = min(candidates, key=lambda item: item[0])
        if y + total > box.bottom + 1e-6:
            raise LabelDoesNotFit("Content exceeds its text zone")
        # Small, proportional breathing room; do not spread rows across empty space.
        for index, (key, headings, values) in enumerate(cells):
            column = index % columns
            row = index // columns
            cell_y = y + sum(row_heights[:row]) + gap * row
            cell_x = box.x + column * (cell_width + gap)
            for line in headings:
                texts.append(
                    LabelText(
                        line,
                        Box(cell_x, cell_y, cell_width, size * 0.8),
                        size * 0.65,
                        f"{key}_heading",
                    )
                )
                cell_y += size * 0.8
            for line in values:
                texts.append(
                    LabelText(line, Box(cell_x, cell_y, cell_width, size * 1.2), size, key)
                )
                cell_y += size * 1.2
        y += total
    if y > box.bottom + 1e-6:
        raise LabelDoesNotFit("Content exceeds its text zone")
    return texts, rules, logo, swatch


def _qr_composition(
    data: LabelData,
    options: LabelOptions,
    zone: Box,
    margin: float,
    modules: int,
    measure: MeasureText,
) -> tuple[Box, float, LabelText, Box | None, LabelText | None]:
    sku = f"SKU · {data.sku}"
    sku_width_at_one = measure(sku, 1, False)
    caption_width_at_one = measure("FilamentHub", 1, True)

    def dimensions(side: float) -> tuple[float, float, float, float, float]:
        quiet = side * 4 / modules
        sku_size = max(0.85, side * 0.92 / sku_width_at_one)
        caption_size = max(0.85, side * 0.94 / (caption_width_at_one + 1.6))
        if options.attribution == "full":
            top = 2 * max(margin, quiet) + caption_size * 1.3
        elif options.attribution == "mark" and options.width_mm >= options.height_mm:
            top = margin + max(1.1, side * 0.15) + quiet
        else:
            top = max(margin, quiet)
        bottom = 2 * max(margin, quiet) + sku_size * 1.2
        return quiet, sku_size, caption_size, top, bottom

    low, high = 0.0, min(zone.width - 2 * margin, zone.width * modules / (modules + 8))
    for _ in range(22):
        side = (low + high) / 2
        _, _, _, top, bottom = dimensions(side)
        if top + side + bottom <= zone.height:
            low = side
        else:
            high = side
    # Use the available physical width, not whole-dot steps: rounding 3.8 dots
    # down to 3 needlessly shrinks the QR, attribution and SKU together.
    # Only at the two-dot minimum do we snap to a uniform grid; subpixel edges
    # at that density can consume a significant part of an individual module.
    dot_mm = 25.4 / options.dpi
    dots = math.floor(low / modules / dot_mm + 1e-6)
    side = dots * dot_mm * modules if dots == 2 else low
    quiet, sku_size, caption_size, top, bottom = dimensions(side)
    if sku_width_at_one * sku_size > zone.width - 2 * margin:
        raise LabelDoesNotFit("The complete SKU does not fit")
    if (
        options.attribution == "full"
        and caption_size * (caption_width_at_one + 1.6) > zone.width - 2 * margin
    ):
        raise LabelDoesNotFit("The attribution does not fit")
    qr = Box(
        zone.x + (zone.width - side) / 2,
        zone.y + top + (zone.height - top - side - bottom) / 2,
        side,
        side,
    )
    sku_width = sku_width_at_one * sku_size
    sku_text = LabelText(
        sku,
        Box(
            qr.x + (side - sku_width) / 2,
            (qr.bottom + zone.bottom) / 2 - sku_size * 0.6,
            sku_width,
            sku_size * 1.2,
        ),
        sku_size,
        "sku",
    )
    mark = None
    caption = None
    if options.attribution == "mark":
        mark_size = max(1.1, side * 0.15)
        mark = Box(
            options.width_mm - margin - mark_size,
            margin,
            mark_size,
            mark_size * 289.05 / 358.41,
        )
    elif options.attribution == "full":
        mark_size = caption_size * 1.3
        total_width = caption_size * (caption_width_at_one + 1.6)
        x = qr.x + (side - total_width) / 2
        y = (zone.y + qr.y) / 2 - mark_size / 2
        mark = Box(x, y, mark_size, mark_size)
        caption = LabelText(
            "FilamentHub",
            Box(x + caption_size * 1.6, y, caption_size * caption_width_at_one, mark_size),
            caption_size,
            "attribution",
            True,
        )
    return qr, quiet, sku_text, mark, caption


def compose_label(
    data: LabelData, options: LabelOptions, modules: int, measure: MeasureText
) -> LabelScene:
    width, height = options.width_mm, options.height_mm
    margin = max(0.6, min(width, height) * 0.035)
    corner_radius = min(width, height) * 0.04
    if options.kind == "classic":
        module = min(width / (modules + 8), (width - 2 * margin) / modules)
        side = modules * module
        return LabelScene(
            width,
            height,
            margin,
            Box((width - side) / 2, (height - side) / 2, side, side),
            module * 4,
            dots_per_module=module * options.dpi / 25.4,
            corner_radius_mm=corner_radius,
        )

    if width < height:
        return _compose_vertical(data, options, modules, measure, margin, corner_radius)

    short = min(width, height)
    candidates: list[tuple[float, LabelScene]] = []
    # Explore allocations instead of hardcoding a separate template per paper size.
    fractions = (
        (0.25, 0.28, 0.32, 0.36) if max(width, height) / short >= 2.5 else (0.44, 0.48, 0.52, 0.56)
    )
    for fraction in fractions:
        qr_zone = Box(width * (1 - fraction), 0, width * fraction, height)
        body = Box(margin, margin, qr_zone.x - 2 * margin, height - 2 * margin)
        try:
            qr, quiet, sku_text, attribution, caption = _qr_composition(
                data,
                options,
                qr_zone,
                margin,
                modules,
                measure,
            )
        except LabelDoesNotFit:
            continue
        if body.width <= 0 or body.height <= 0:
            continue
        low, high = 0.95, short * 0.3
        best = None
        for _ in range(17):
            size = (low + high) / 2
            try:
                best_trial = _body(data, options, body, size, measure)
            except LabelDoesNotFit:
                high = size
            else:
                low, best = size, best_trial
        if best is None:
            continue
        texts, rules, logo, swatch = best
        scene = LabelScene(
            width,
            height,
            margin,
            qr,
            quiet,
            texts,
            rules,
            logo,
            attribution=attribution,
            swatch=swatch,
            body_size_mm=low,
            dots_per_module=qr.width / modules * options.dpi / 25.4,
            corner_radius_mm=corner_radius,
        )
        scene.rules.append(Box(qr_zone.x, 0, 0, height))
        scene.texts.append(sku_text)
        if caption:
            scene.texts.append(caption)
        candidates.append((low, scene))
    if not candidates:
        raise LabelDoesNotFit("No readable allocation for all selected content")
    return max(candidates, key=lambda item: (item[1].dots_per_module >= 2 - 1e-6, item[0]))[1]


def _compose_vertical(
    data: LabelData,
    options: LabelOptions,
    modules: int,
    measure: MeasureText,
    margin: float,
    corner_radius: float,
) -> LabelScene:
    width, height = options.width_mm, options.height_mm
    max_qr_side = min(width - 2 * margin, width * modules / (modules + 8))
    body_top = margin
    if options.attribution == "mark":
        # The corner mark is outside the QR stack. Reserve its largest possible
        # height before fitting the body so it cannot overlap the brand.
        body_top += max(1.1, max_qr_side * 0.15) * 289.05 / 358.41 + margin * 0.5
    body = Box(margin, body_top, width - 2 * margin, height - body_top - margin)

    def trial(size: float) -> LabelScene:
        texts, rules, logo, swatch = _body(data, options, body, size, measure)
        body_bottom = max(
            [text.box.bottom for text in texts]
            + [box.bottom for box in (logo, swatch) if box is not None]
        )
        divider = body_bottom + margin
        qr_zone = Box(0, divider, width, height - divider)
        if qr_zone.height <= 0:
            raise LabelDoesNotFit("No room for the QR stack")
        qr, quiet, sku_text, attribution, caption = _qr_composition(
            data, options, qr_zone, margin, modules, measure
        )
        # One modular scale for both blocks: a QR spans twelve body ems until
        # the physical width caps it. Maximising text alone starves the QR;
        # maximising QR alone makes the characteristics unreadable.
        target_side = min(max_qr_side, size * 12)
        dot_mm = 25.4 / options.dpi
        target_dots = math.floor(target_side / modules / dot_mm + 1e-6)
        if target_dots == 2:
            target_side = target_dots * dot_mm * modules
        if qr.width < target_side and not math.isclose(
            qr.width, target_side, rel_tol=1e-6, abs_tol=1e-5
        ):
            raise LabelDoesNotFit("Body and QR do not fit at the same scale")
        rules.append(Box(0, divider, width, 0))
        texts.append(sku_text)
        if caption:
            texts.append(caption)
        return LabelScene(
            width,
            height,
            margin,
            qr,
            quiet,
            texts,
            rules,
            logo,
            attribution=attribution,
            swatch=swatch,
            body_size_mm=size,
            dots_per_module=qr.width / modules * options.dpi / 25.4,
            corner_radius_mm=corner_radius,
        )

    low, high = 0.95, width * 0.3
    best = trial(low)
    for _ in range(17):
        size = (low + high) / 2
        try:
            candidate = trial(size)
        except LabelDoesNotFit:
            high = size
        else:
            low, best = size, candidate
    return best
