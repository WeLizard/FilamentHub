"""Render the site pictures of the designed Edge cases from the STL files.

    $env:BLENDER_USER_RESOURCES = "F:/Temp/blender-user-isolated"
    blender -b --factory-startup -P render_family.py

Run edge_family.py first. Writes transparent WebP pictures to ./out/site;
copy them to frontend/public/edge-kit/ when they change.
"""

import json
from pathlib import Path

import bpy
from mathutils import Vector

OUT = Path(__file__).parent / "out"
SITE = OUT / "site"
SITE.mkdir(exist_ok=True)
MM = 0.01


def srgb(hex_color):
    """Brand colours are sRGB; Blender wants linear values."""
    values = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    return tuple(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in values)


def material(name, color, roughness=0.5, metallic=0.0, coat=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    shader = mat.node_tree.nodes["Principled BSDF"]
    shader.inputs["Base Color"].default_value = (*color, 1.0)
    shader.inputs["Roughness"].default_value = roughness
    shader.inputs["Metallic"].default_value = metallic
    shader.inputs["Coat Weight"].default_value = coat
    return mat


def aim(obj, target):
    obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()


def light(name, location, energy, size):
    data = bpy.data.lights.new(name, "AREA")
    data.energy = energy
    data.size = size
    obj = bpy.data.objects.new(name, data)
    obj.location = location
    bpy.context.collection.objects.link(obj)
    aim(obj, Vector((0, 0, 0.05)))
    return obj


bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.samples = 160
scene.cycles.use_denoising = True
scene.render.film_transparent = True
scene.render.image_settings.file_format = "WEBP"
scene.render.image_settings.color_mode = "RGBA"
scene.render.image_settings.quality = 88

world = bpy.data.worlds.new("World")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.75, 0.72, 0.9, 1.0)
world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.4
scene.world = world

camera = bpy.data.objects.new("Camera", bpy.data.cameras.new("Camera"))
scene.collection.objects.link(camera)
scene.camera = camera

bpy.ops.mesh.primitive_plane_add(size=60, location=(0, 0, 0))
bpy.context.object.is_shadow_catcher = True

MATERIALS = {
    "body": material("Body", (0.80, 0.79, 0.77), 0.45),
    "mark": material("Mark", srgb("#3B0764"), 0.4),
    "accent": material("Accent", srgb("#7C3AED"), 0.35, coat=0.3),
    "base": material("Base", (0.04, 0.04, 0.05), 0.5),
    "glass": material("Glass", (0.01, 0.01, 0.015), 0.08, coat=1.0),
}
SCENE = json.loads((OUT / "scene.json").read_text(encoding="utf-8"))


def glow(name, color, strength):
    mat = material(name, (0.0, 0.0, 0.0), 0.5)
    shader = mat.node_tree.nodes["Principled BSDF"]
    shader.inputs["Emission Color"].default_value = (*color, 1.0)
    shader.inputs["Emission Strength"].default_value = strength
    return mat


def lit(device, led_colors, lines):
    """Light the LED windows and put two lines of text on the screen."""
    info = SCENE[device]
    lift = info["plinth"]
    for index, (x, y) in enumerate(info["leds"]):
        color = srgb(led_colors[index % len(led_colors)])
        bpy.ops.mesh.primitive_cylinder_add(radius=2.5 * MM, depth=0.02 * MM, location=(x * MM, y * MM, (info["top"] + lift + 0.02) * MM))
        bpy.context.object.data.materials.append(glow(f"LED{index}", color, 5.0))
    if not lines:
        return
    sx, sy = info["screen"]
    view_h = info["view"][1]
    for text, size, dy in lines:
        bpy.ops.object.text_add(location=(sx * MM, (sy + dy * view_h) * MM, (info["ceiling"] + lift + 0.05) * MM))
        obj = bpy.context.object
        obj.data.body = text
        obj.data.size = size * view_h * MM
        obj.data.align_x = "CENTER"
        obj.data.align_y = "CENTER"
        obj.data.materials.append(glow("Screen", (0.92, 0.95, 1.0), 2.5))


def load(filename, mat_key, lift):
    bpy.ops.wm.stl_import(filepath=str(OUT / filename))
    obj = bpy.context.selected_objects[0]
    obj.scale = (MM, MM, MM)
    obj.location.z = lift * MM
    obj.data.materials.append(MATERIALS[mat_key])
    return obj


def clear_parts():
    for obj in list(bpy.data.objects):
        if obj.type in {"MESH", "FONT"} and not obj.is_shadow_catcher:
            bpy.data.objects.remove(obj, do_unlink=True)


def shot(name, device, parts, location, target, leds, lines, lens=60, size=(1600, 1000)):
    clear_parts()
    for filename, mat_key in parts:
        load(filename, mat_key, SCENE[device]["plinth"])
    lit(device, leds, lines)
    lights = [
        light("Key", (location[0] * 1.1, location[1] * 0.9, location[2] * 2.0), 75 * (location[2] / 1.2) ** 2, 2.0),
        light("Fill", (-location[0] * 1.6, location[1] * 0.4, location[2] * 1.2), 24 * (location[2] / 1.2) ** 2, 2.5),
        light("Rim", (0.2, -location[1] * 1.2, location[2] * 1.3), 55 * (location[2] / 1.2) ** 2, 1.5),
    ]
    camera.location = location
    camera.data.lens = lens
    aim(camera, Vector(target))
    scene.render.resolution_x, scene.render.resolution_y = size
    scene.render.filepath = str(SITE / name)
    bpy.ops.render.render(write_still=True)
    for obj in lights:
        bpy.data.objects.remove(obj, do_unlink=True)
    print("rendered", name)


def build(name, accent_leds, lines, screen=True, caps=False):
    """Pictures each case from the same angle, the camera backed off by its length."""
    parts = [(f"fh-edge-{name}-shell.stl", "body"), (f"fh-edge-{name}-base.stl", "base"), (f"fh-edge-{name}-mark.stl", "mark")]
    if screen:
        parts.append((f"preview-{name}-screen.stl", "glass"))
    if caps:
        parts.append((f"preview-{name}-caps.stl", "accent"))
    k = SCENE[name]["length"] / 132.0
    shot(f"{name}-front.webp", name, parts, (1.55 * k, -2.15 * k, 1.35 * k + 0.1 * (k - 1)), (0.0, 0.0, 0.06), accent_leds, lines)


SPOOLS = ["#F97316", "#FFFFFF", "#7C3AED", "#0EA5E9", "#22C55E", "#EF4444", "#EAB308", "#EC4899"]
TWO_LINES = (0.275, 0.125), (0.175, -0.275)


def two(first, second):
    return [(first, *TWO_LINES[0]), (second, *TWO_LINES[1])]


build("tag-s3", ["#7C3AED"], two("PETG HF", "Jade White · 812 g"))
build("portable-s3", ["#22C55E"], two("Shelf B2", "4 spools scanned"), caps=True)
build("portable-c3", ["#22C55E"], None, screen=False)
build("touch-s3", ["#7C3AED"], [
    ("PETG HF", 0.2, 0.24), ("Jade White · 812 g", 0.11, 0.0), ("Put in slot 3?", 0.11, -0.26),
])
build("station-c3", SPOOLS, None, screen=False, caps=True)
build("station-s3", SPOOLS, two("Slot 3", "PLA Matte · 640 g"), caps=True)
