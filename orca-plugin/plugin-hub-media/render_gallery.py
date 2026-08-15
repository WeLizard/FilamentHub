from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from textwrap import wrap

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parent
SOURCE_DIR = ROOT / "source"
OUTPUT_DIR = ROOT / "final"
LOGO_PATH = ROOT.parent.parent / "frontend" / "public" / "favicon-dark-120.png"
FONT_REGULAR = Path("C:/Windows/Fonts/segoeui.ttf")
FONT_SEMIBOLD = Path("C:/Windows/Fonts/seguisb.ttf")

CANVAS_SIZE = (1600, 900)
SCREENSHOT_BOX = (72, 195, 1528, 850)


@dataclass(frozen=True)
class Slide:
    filename: str
    source: str
    title: str
    subtitle: str
    accent: tuple[int, int, int]
    crop: tuple[int, int, int, int] | None = None


SLIDES = (
    Slide(
        "01-find-a-profile.png",
        "catalog-full.png",
        "Find the right filament profile",
        "Browse by brand, material or printer without leaving OrcaSlicer.",
        (196, 80, 255),
    ),
    Slide(
        "02-sync-on-your-terms.png",
        "preset-sync-full.png",
        "Sync on your terms",
        "Choose the managed profiles you want. Local edits are never silently overwritten.",
        (50, 214, 255),
    ),
    Slide(
        "03-native-orcaslicer-presets.png",
        "native-presets-full.png",
        "Use profiles natively in OrcaSlicer",
        "FilamentHub profiles keep their colour and appear in the normal filament selector.",
        (0, 190, 170),
        (0, 35, 640, 323),
    ),
    Slide(
        "04-real-spools-and-material-systems.png",
        "material-system-full.png",
        "Connect profiles to real spools",
        "Track inventory and preview Bambu AMS or Happy Hare assignments before applying them.",
        (52, 211, 153),
    ),
)


def font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(path), size)


def vertical_gradient(
    size: tuple[int, int],
    top: tuple[int, int, int],
    bottom: tuple[int, int, int],
) -> Image.Image:
    width, height = size
    image = Image.new("RGB", size)
    pixels = image.load()
    for y in range(height):
        ratio = y / max(height - 1, 1)
        colour = tuple(round(a + (b - a) * ratio) for a, b in zip(top, bottom, strict=True))
        for x in range(width):
            pixels[x, y] = colour
    return image


def add_glow(canvas: Image.Image, centre: tuple[int, int], colour: tuple[int, int, int]) -> None:
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    x, y = centre
    draw.ellipse((x - 360, y - 360, x + 360, y + 360), fill=(*colour, 105))
    layer = layer.filter(ImageFilter.GaussianBlur(150))
    canvas.paste(layer, (0, 0), layer)


def rounded_screenshot(source: Image.Image, size: tuple[int, int]) -> Image.Image:
    fitted = ImageOps.fit(source.convert("RGB"), size, method=Image.Resampling.LANCZOS)
    radius = 24
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size[0], size[1]), radius=radius, fill=255)
    result = Image.new("RGBA", size, (0, 0, 0, 0))
    result.paste(fitted, (0, 0), mask)
    return result


def draw_wrapped(
    draw: ImageDraw.ImageDraw,
    text: str,
    position: tuple[int, int],
    text_font: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int],
    width: int,
    spacing: int = 8,
) -> None:
    average_character_width = max(text_font.getlength("ABCDEFGHIJKLMNOPQRSTUVWXYZ") / 26, 1)
    line_width = max(int(width / average_character_width), 1)
    draw.multiline_text(
        position,
        "\n".join(wrap(text, width=line_width)),
        font=text_font,
        fill=fill,
        spacing=spacing,
    )


def render(slide: Slide, index: int) -> Path:
    canvas = vertical_gradient(CANVAS_SIZE, (10, 13, 31), (31, 15, 61)).convert("RGBA")
    add_glow(canvas, (1340, 150), slide.accent)
    add_glow(canvas, (220, 860), tuple(max(channel - 35, 0) for channel in slide.accent))

    left, top, right, bottom = SCREENSHOT_BOX
    panel_size = (right - left, bottom - top)
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_draw.rounded_rectangle(
        (left - 8, top + 12, right + 8, bottom + 28),
        radius=32,
        fill=(0, 0, 0, 150),
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(28))
    canvas.alpha_composite(shadow)

    source = Image.open(SOURCE_DIR / slide.source).convert("RGB")
    if slide.crop is not None:
        source = source.crop(slide.crop)
    screenshot = rounded_screenshot(source, panel_size)
    canvas.alpha_composite(screenshot, (left, top))

    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle(
        (left, top, right - 1, bottom - 1),
        radius=24,
        outline=(255, 255, 255, 58),
        width=2,
    )

    draw.text((72, 55), slide.title, font=font(FONT_SEMIBOLD, 52), fill=(255, 255, 255))
    draw_wrapped(
        draw,
        slide.subtitle,
        (74, 128),
        font(FONT_REGULAR, 25),
        (198, 202, 222),
        1440,
    )

    marker = f"{index}/{len(SLIDES)}"
    marker_font = font(FONT_SEMIBOLD, 18)
    marker_box = draw.textbbox((0, 0), marker, font=marker_font)
    marker_width = marker_box[2] - marker_box[0]
    draw.rounded_rectangle(
        (right - marker_width - 36, bottom - 54, right - 12, bottom - 12),
        radius=21,
        fill=(9, 12, 27, 190),
    )
    draw.text((right - marker_width - 24, bottom - 45), marker, font=marker_font, fill=(225, 228, 242))

    brand_layer = Image.new("RGBA", CANVAS_SIZE, (0, 0, 0, 0))
    brand_draw = ImageDraw.Draw(brand_layer)
    logo = Image.open(LOGO_PATH).convert("RGBA").resize((48, 48), Image.Resampling.LANCZOS)
    brand_layer.alpha_composite(logo, (1280, 48))
    brand_draw.text(
        (1340, 55),
        "FilamentHub",
        font=font(FONT_SEMIBOLD, 27),
        fill=(248, 249, 255),
    )

    canvas.alpha_composite(brand_layer)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output = OUTPUT_DIR / slide.filename
    canvas.convert("RGB").save(output, format="PNG", optimize=True)
    return output


def main() -> None:
    missing = [slide.source for slide in SLIDES if not (SOURCE_DIR / slide.source).is_file()]
    if missing:
        raise SystemExit(f"Missing source screenshots: {', '.join(missing)}")
    if not LOGO_PATH.is_file():
        raise SystemExit(f"Missing FilamentHub logo: {LOGO_PATH}")
    for index, slide in enumerate(SLIDES, start=1):
        print(render(slide, index))


if __name__ == "__main__":
    main()
