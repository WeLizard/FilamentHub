"""Render the kit's pictures for the site, in the studio of the other Edge cases.

    $env:BLENDER_USER_RESOURCES = "F:/Temp/blender-user-isolated"
    blender -b --factory-startup -P render_site.py

Keep the separate user folder: started with factory settings in the normal
user folder, Blender removes the Python packages installed there for add-ons.

Reads ./STL, ./render (export_render_assets.py) and parameters.json, and writes
transparent WebP pictures to ./preview: the finished kit, its back, the kit
seen through, and the three assembly steps. Copy them to
frontend/public/edge-kit/ when they change.

The ESP32-C3 is the supplied CAD model in its place. The PN5180 is the studio's
module (../render_parts.py), drawn from a photograph of the board and placed in
the reader's envelope: the kit has no vendor model of it.
"""
import json
import math
import sys
from pathlib import Path

import bpy

KIT = Path(__file__).resolve().parent
sys.path.insert(0, str(KIT.parent))
import render_parts as parts  # noqa: E402
import render_studio as studio  # noqa: E402
from render_studio import MM  # noqa: E402

HEIGHT = 15.2
PN_TOP = 12.6  # the reader's antenna face, against the top wall's pads
PN_X = 9.4
PARAMETERS = json.loads((KIT / "parameters.json").read_text(encoding="utf-8"))
POSTS = PARAMETERS["screw_centres"]

studio.setup()
studio.OUT = KIT / "STL"
studio.SITE = KIT / "preview"
M = studio.MATERIALS
P = studio.PARTS
PIPE = parts.material("Light pipe", parts.srgb("#e0f2fe"), 0.12)


def screw(parent, x, y):
    """A pan-head Torx screw in the device's own frame: head under the base, shank going in."""
    head = parts.cyl(parent, M["screw"], 2.3, 1.6, (x, y, -1.6), segments=32, bevel=0.3)
    shank = parts.cyl(parent, M["screw"], 1.2, 8.0, (x, y, 0.0), segments=20)
    # A Torx recess: three bars make its six lobes.
    for lobe in range(3):
        parts.box(head, P["chip"], (2.1, 0.75, 0.5), (0.0, 0.0, -0.05), rot=(0, 0, lobe * math.pi / 3))
    return head, shank


def face_up(obj):
    """A part exported as it is printed, face down, turned back into the device."""
    obj.rotation_euler = (math.pi, 0.0, 0.0)
    obj.location = (0.0, 0.0, HEIGHT)
    return obj


def load_from(folder, filename, material):
    studio.OUT = folder
    obj = studio.load(device, filename, material)
    studio.OUT = KIT / "STL"
    return obj


device = parts.group(None, "Device")
device.scale = (MM, MM, MM)
shell = face_up(studio.load(device, "fh-edge-kit-shell.stl", M["body"]))
mark = face_up(studio.load(device, "fh-edge-kit-mark.stl", M["mark"]))
base = studio.load(device, "fh-edge-kit-base.stl", M["base"])

# Light pipes: each is exported standing on its head at the origin.
pipes = []
for name, (x, y, _z) in zip(("PWR", "IO8"), PARAMETERS["led_centres"]):
    pipe = studio.load(device, f"fh-edge-kit-lightpipe-{name}.stl", PIPE)
    pipe.rotation_euler = (math.pi, 0.0, 0.0)
    pipe.location = (x, y, HEIGHT)
    pipes.append(pipe)

esp = [
    load_from(KIT / "render", f"esp-{name}.stl", P[material])
    for name, material in (
        ("pcb", "pcb_black"), ("metal", "steel"), ("dark", "chip"),
        ("led-red", "led_red"), ("led-blue", "led_blue"), ("copper", "brass"),
    )
]
reader = parts.pn5180(device, P)
reader.location = (PN_X, 0.0, PN_TOP)
reader.rotation_euler = (math.pi, 0.0, 0.0)
boards = [*esp, reader]
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

# 1. The printed parts: the shell with its mark, the base lying in front of it.
show(boards, False)
base.location = (0.0, 62.0, 13.2)
studio.render("step-print.webp", (1.55, -2.75, 2.1), (0.0, -0.3, 0.05), size=(1200, 800))

# 2. Boards in place in the open shell.
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
