"""Render the pictures of the C3 kit's enclosure used on the site, from the exported STL files.

    $env:BLENDER_USER_RESOURCES = "F:/Temp/blender-user-isolated"
    blender -b --factory-startup -P render_preview.py

Keep the separate user folder: started with factory settings in the normal
user folder, Blender removes the Python packages installed there for add-ons.

Reads ./out/*.stl and ./out/kit.json (run edge_tag_station.py first) and writes
transparent WebP pictures to ./out/site: the finished kit, its back, the kit
seen through, and the three assembly steps. The colours, materials and lights
are the ones of the other Edge cases (render_studio.py); the ESP32-C3 SuperMini
and the PN5180 are modelled in render_parts.py. Copy the pictures to
frontend/public/edge-kit/ when they change.
"""

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import render_parts as parts  # noqa: E402
import render_studio as studio  # noqa: E402
from render_studio import MM  # noqa: E402

HEIGHT = 15.2
POSTS = [(sx * 51.75, sy * 18.75) for sx in (-1, 1) for sy in (-1, 1)]

studio.setup()
KIT = json.loads((studio.OUT / "kit.json").read_text(encoding="utf-8"))
M = studio.MATERIALS


def screw(parent, x, y):
    """A pan-head screw in the device's own frame: head under the base, shank going in."""
    head = parts.cyl(parent, M["screw"], 2.3, 1.6, (x, y, -1.6), segments=32, bevel=0.3)
    shank = parts.cyl(parent, M["screw"], 1.2, 8.0, (x, y, 0.0), segments=20)
    # A cross recess on the head, so it reads as a screw and moves with it.
    for angle in (0.0, math.pi / 2):
        parts.box(head, studio.PARTS["chip"], (2.4, 0.5, 0.5), (0.0, 0.0, -0.05), rot=(0, 0, angle))
    return head, shank


device = parts.group(None, "Device")
device.scale = (MM, MM, MM)
shell = studio.load(device, "edge_tag_station_shell.stl", M["body"])
mark = studio.load(device, "edge_tag_station_mark.stl", M["mark"])
base = studio.load(device, "edge_tag_station_base.stl", M["base"])
boards = [parts.place(device, studio.PARTS, item) for item in KIT["inside"]]
screws = [part for x, y in POSTS for part in screw(device, x, y)]


def show(objects, visible):
    """Hide or show objects with everything parented to them."""
    for obj in objects:
        for item in [obj, *obj.children_recursive]:
            item.hide_render = not visible


show(screws, False)

# The finished device on a desk, its back with the USB-C opening, and the kit seen through.
studio.render("kit-front.webp", (1.35, -1.9, 1.2), (0.0, 0.0, 0.05))
studio.render("kit-back.webp", (-1.55, 2.25, 1.15), (0.0, 0.0, 0.05), size=(1200, 800))
shell.data.materials[0] = M["ghost"]
mark.data.materials[0] = M["ghost_mark"]
studio.render("kit-inside.webp", (1.0, -1.4, 1.95), (0.0, 0.0, 0.05), cyan=0.6, top=0.35, key=0.45)
shell.data.materials[0] = M["body"]
mark.data.materials[0] = M["mark"]

# Assembly happens with the shell lying on its top face. Turned over, the
# device's own "up" points down: moving a part by +z in its frame lowers it.
device.rotation_euler = (math.pi, 0.0, 0.0)
device.location.z = HEIGHT * MM

# 1. The two printed parts, the base lying in front of the shell.
show([mark, *boards], False)
base.location = (0.0, 62.0, 13.2)
studio.render("step-print.webp", (1.55, -2.75, 2.1), (0.0, -0.3, 0.05), size=(1200, 800))

# 2. Boards in place: their component sides face up out of the open shell.
show([base], False)
show(boards, True)
studio.render("step-boards.webp", (1.25, -1.8, 1.75), (0.0, 0.0, 0.08), size=(1200, 800))

# 3. Base plate and screws going on.
show([base], True)
base.location = (0.0, 0.0, -24.0)
show(screws, True)
for part in screws:
    part.location.z -= 44.0
studio.render("step-close.webp", (1.65, -2.4, 2.2), (0.0, 0.0, 0.3), size=(1200, 800))
