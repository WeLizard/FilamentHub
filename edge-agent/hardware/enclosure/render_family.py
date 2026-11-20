"""Render the site pictures of the designed Edge cases from the STL files.

    $env:BLENDER_USER_RESOURCES = "F:/Temp/blender-user-isolated"
    blender -b --factory-startup -P render_family.py [-- tag-s3 station-s3 ...]

Run edge_family.py first. For every build it writes two transparent WebP
pictures to ./out/site: `<build>-front.webp`, the closed case in the site's
colours, and `<build>-inside.webp`, the same case seen through, with the boards
and modules of its parts list in their places (render_parts.py). Copy them to
frontend/public/edge-kit/ when they change.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import render_parts as parts  # noqa: E402
import render_studio as studio  # noqa: E402
from render_studio import MM  # noqa: E402

studio.setup()
SCENE = json.loads((studio.OUT / "scene.json").read_text(encoding="utf-8"))


def build(name, led_colors, lines, caps=False):
    """The closed case, then the same case seen through with its parts inside."""
    studio.clear_device()
    info = SCENE[name]
    root = parts.group(None, "Device", location=(0, 0, info["plinth"] * MM))
    root.scale = (MM, MM, MM)
    shell = studio.load(root, f"fh-edge-{name}-shell.stl", studio.MATERIALS["body"])
    mark = studio.load(root, f"fh-edge-{name}-mark.stl", studio.MATERIALS["mark"])
    studio.load(root, f"fh-edge-{name}-base.stl", studio.MATERIALS["base"])
    if caps:
        studio.load(root, f"preview-{name}-caps.stl", studio.MATERIALS["accent"])
    for item in info["inside"]:
        parts.place(root, studio.PARTS, item)
    studio.lit(root, info, led_colors, lines)

    k = info["length"] / 132.0
    studio.render(f"{name}-front.webp", (1.55 * k, -2.15 * k, 1.35 * k + 0.1 * (k - 1)), (0.0, 0.0, 0.06))

    shell.data.materials[0] = studio.MATERIALS["ghost"]
    mark.data.materials[0] = studio.MATERIALS["ghost_mark"]
    studio.render(f"{name}-inside.webp", (1.05 * k, -1.45 * k, 2.25 * k), (0.0, 0.0, 0.05), cyan=0.6, top=0.35, key=0.45)


SPOOLS = ["#F97316", "#FFFFFF", "#7C3AED", "#0EA5E9", "#22C55E", "#EF4444", "#EAB308", "#EC4899"]
TWO_LINES = (0.275, 0.125), (0.175, -0.275)


def two(first, second):
    return [(first, *TWO_LINES[0]), (second, *TWO_LINES[1])]


BUILDS = {
    "tag-s3": lambda: build("tag-s3", ["#7C3AED"], two("PETG HF", "Jade White · 812 g")),
    "portable-s3": lambda: build("portable-s3", ["#22C55E"], two("Shelf B2", "4 spools scanned"), caps=True),
    "portable-c3": lambda: build("portable-c3", ["#22C55E"], None),
    "touch-s3": lambda: build("touch-s3", ["#7C3AED"], [
        ("PETG HF", 0.2, 0.24), ("Jade White · 812 g", 0.11, 0.0), ("Put in slot 3?", 0.11, -0.26),
    ]),
    "station-c3": lambda: build("station-c3", SPOOLS, None, caps=True),
    "station-s3": lambda: build("station-s3", SPOOLS, two("Slot 3", "PLA Matte · 640 g"), caps=True),
}

wanted = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else list(BUILDS)
for key in wanted:
    BUILDS[key]()
