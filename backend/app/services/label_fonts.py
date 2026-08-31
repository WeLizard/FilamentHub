"""Bundled font outlines: identical glyphs and measurements on every renderer."""

import unicodedata
from functools import lru_cache
from pathlib import Path

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont

FONT_ROOT = Path(__file__).resolve().parents[1] / "assets" / "labels" / "fonts"


class UnsupportedLabelText(ValueError):
    """The bundled fonts cannot represent a requested character."""


@lru_cache(maxsize=4)
def _font(cjk: bool, bold: bool):
    family = "NotoSansCJKsc" if cjk else "NotoSans"
    suffix = "otf" if cjk else "ttf"
    font = TTFont(FONT_ROOT / f"{family}-{'Bold' if bold else 'Regular'}.{suffix}")
    return font, font.getBestCmap(), font.getGlyphSet(), font["head"].unitsPerEm


@lru_cache(maxsize=4096)
def _glyph(character: str, bold: bool):
    for cjk in (False, True):
        font, cmap, glyphs, units = _font(cjk, bold)
        name = cmap.get(ord(character))
        if name is None:
            continue
        glyph = glyphs[name]
        pen = SVGPathPen(glyphs)
        bounds = BoundsPen(glyphs)
        glyph.draw(pen)
        glyph.draw(bounds)
        return pen.getCommands(), glyph.width / units, units, bounds.bounds
    raise UnsupportedLabelText("Unsupported label character")


@lru_cache(maxsize=2048)
def _run(text: str, bold: bool):
    glyphs = []
    advance = 0.0
    left = bottom = 0.0
    right = top = 0.0
    for character in unicodedata.normalize("NFC", text):
        path, width, units, bounds = _glyph(character, bold)
        if bounds:
            x0, y0, x1, y1 = bounds
            left = min(left, advance + x0 / units)
            right = max(right, advance + x1 / units)
            bottom = min(bottom, y0 / units)
            top = max(top, y1 / units)
        glyphs.append((advance, units, path))
        advance += width
    return tuple(glyphs), left, max(right, advance), bottom, top


def measure_text(text: str, size: float, bold: bool = False) -> float:
    _, left, right, _, _ = _run(text, bold)
    return (right - left) * size


def text_paths(
    text: str, x: float, y: float, height: float, size: float, bold: bool, color: str
) -> str:
    glyphs, left, _, bottom, top = _run(text, bold)
    baseline = y + (height - (top - bottom) * size) / 2 + top * size
    paths = []
    for advance, units, path in glyphs:
        if path:
            paths.append(
                f'<path transform="translate({x + (advance - left) * size:.6f} {baseline:.6f}) '
                f'scale({size / units:.9f} {-size / units:.9f})" d="{path}"/>'
            )
    return f'<g fill="{color}">' + "".join(paths) + "</g>"
