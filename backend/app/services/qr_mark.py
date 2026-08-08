"""Знак FilamentHub для встраивания в QR-код.

Геометрия снята с `orca-plugin/filamenthub.svg`, но нарисована контурами и
толще: там знак живёт на экране в 20 пикселей, здесь он попадает на упаковку.
Толщина 2.2 при поле 20 — это 11% ширины знака; тоньше пропадает при печати,
толще смыкает просвет между дугой и перекладиной.

Рисуется кодом, а не берётся из SVG: растеризатора в образе нет, а фигур всего
пять.
"""

import math

from PIL import Image, ImageDraw

_VIEWBOX = 20.0
_CENTER = 10.0
_RADIUS = 8.0
_WIDTH = 2.2

# Кольцо разорвано сверху и снизу — там проходит вертикаль монограммы.
_LEFT_ARC = (146.0, 257.0)
_RIGHT_ARC = (-30.0, 34.0)

_VERTICAL_X = 10.95
_VERTICAL = (2.15, 17.85)
_BAR_Y = 10.0
# Перекладина упирается в дугу, а не пробивает её: круглый конец, поставленный
# на радиус кольца, приходится ровно на его внешний край.
_LEFT_BAR = (_CENTER - _RADIUS, 8.19)
_RIGHT_BAR = (10.95, 18.0)

_SUPERSAMPLE = 8

MARK_COLOR = (17, 17, 17)
MARK_COLOR_HEX = "#111111"


def _point(radius: float, degrees: float) -> tuple[float, float]:
    angle = math.radians(degrees)
    return _CENTER + radius * math.cos(angle), _CENTER + radius * math.sin(angle)


def _arc_path(start: float, end: float) -> str:
    """Дуга заданной толщины с полукруглыми концами — одним контуром."""
    outer, inner, cap = _RADIUS + _WIDTH / 2, _RADIUS - _WIDTH / 2, _WIDTH / 2
    large = 1 if abs(end - start) > 180 else 0
    ox0, oy0 = _point(outer, start)
    ox1, oy1 = _point(outer, end)
    ix1, iy1 = _point(inner, end)
    ix0, iy0 = _point(inner, start)
    return (
        f"M{ox0:.3f},{oy0:.3f} "
        f"A{outer:.3f},{outer:.3f} 0 {large} 1 {ox1:.3f},{oy1:.3f} "
        f"A{cap:.3f},{cap:.3f} 0 0 1 {ix1:.3f},{iy1:.3f} "
        f"A{inner:.3f},{inner:.3f} 0 {large} 0 {ix0:.3f},{iy0:.3f} "
        f"A{cap:.3f},{cap:.3f} 0 0 1 {ox0:.3f},{oy0:.3f} Z"
    )


def _bar_path(x0: float, y0: float, x1: float, y1: float) -> str:
    """Отрезок толщины _WIDTH со скруглёнными концами."""
    cap = _WIDTH / 2
    if abs(y1 - y0) < 1e-6:
        return (
            f"M{x0:.3f},{y0 - cap:.3f} L{x1:.3f},{y0 - cap:.3f} "
            f"A{cap:.3f},{cap:.3f} 0 0 1 {x1:.3f},{y0 + cap:.3f} "
            f"L{x0:.3f},{y0 + cap:.3f} "
            f"A{cap:.3f},{cap:.3f} 0 0 1 {x0:.3f},{y0 - cap:.3f} Z"
        )
    return (
        f"M{x0 - cap:.3f},{y0:.3f} L{x0 - cap:.3f},{y1:.3f} "
        f"A{cap:.3f},{cap:.3f} 0 0 0 {x0 + cap:.3f},{y1:.3f} "
        f"L{x0 + cap:.3f},{y0:.3f} "
        f"A{cap:.3f},{cap:.3f} 0 0 0 {x0 - cap:.3f},{y0:.3f} Z"
    )


def mark_paths() -> list[str]:
    """Знак как контуры в собственных координатах (поле 20×20).

    Тот же источник геометрии, что и у растра: вектор для типографии и картинка
    для экрана не должны расходиться.
    """
    return [
        _arc_path(*_LEFT_ARC),
        _arc_path(*_RIGHT_ARC),
        _bar_path(_VERTICAL_X, _VERTICAL[0], _VERTICAL_X, _VERTICAL[1]),
        _bar_path(_LEFT_BAR[0], _BAR_Y, _LEFT_BAR[1], _BAR_Y),
        _bar_path(_RIGHT_BAR[0], _BAR_Y, _RIGHT_BAR[1], _BAR_Y),
    ]


MARK_VIEWBOX = _VIEWBOX


def draw_mark(size: int, color: tuple[int, int, int] = MARK_COLOR) -> Image.Image:
    """Знак заданного размера на прозрачном фоне."""
    px = max(1, size) * _SUPERSAMPLE
    scale = px / _VIEWBOX
    stroke = _WIDTH * scale
    cap = stroke / 2
    rgba = (*color, 255)

    image = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    for start, end in (_LEFT_ARC, _RIGHT_ARC):
        # Толщина у PIL ложится внутрь габарита, поэтому габарит берётся по
        # внешнему краю — иначе полоса сядет не на тот радиус.
        outer = _RADIUS + _WIDTH / 2
        box = [
            (_CENTER - outer) * scale,
            (_CENTER - outer) * scale,
            (_CENTER + outer) * scale,
            (_CENTER + outer) * scale,
        ]
        draw.arc(box, start, end, fill=rgba, width=round(stroke))
        for angle in (start, end):
            x = (_CENTER + _RADIUS * math.cos(math.radians(angle))) * scale
            y = (_CENTER + _RADIUS * math.sin(math.radians(angle))) * scale
            draw.ellipse([x - cap, y - cap, x + cap, y + cap], fill=rgba)

    segments = (
        (_VERTICAL_X, _VERTICAL[0], _VERTICAL_X, _VERTICAL[1]),
        (_LEFT_BAR[0], _BAR_Y, _LEFT_BAR[1], _BAR_Y),
        (_RIGHT_BAR[0], _BAR_Y, _RIGHT_BAR[1], _BAR_Y),
    )
    for x0, y0, x1, y1 in segments:
        draw.line(
            [x0 * scale, y0 * scale, x1 * scale, y1 * scale],
            fill=rgba,
            width=round(stroke),
        )
        for x, y in ((x0 * scale, y0 * scale), (x1 * scale, y1 * scale)):
            draw.ellipse([x - cap, y - cap, x + cap, y + cap], fill=rgba)

    return image.resize((max(1, size), max(1, size)), Image.LANCZOS)
