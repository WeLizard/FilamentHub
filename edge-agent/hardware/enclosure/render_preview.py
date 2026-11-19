"""Render the pictures of the enclosure used on the site, from the exported STL files.

    $env:BLENDER_USER_RESOURCES = "F:/Temp/blender-user-isolated"
    blender -b --factory-startup -P render_preview.py

Keep the separate user folder: started with factory settings in the normal
user folder, Blender removes the Python packages installed there for add-ons.

Reads ./out/*.stl (run edge_tag_station.py first) and writes transparent WebP
pictures to ./out/site. Copy them to frontend/public/edge-kit/ when they change.
"""

import math
from pathlib import Path

import bpy
from mathutils import Vector

OUT = Path(__file__).parent / "out"
SITE = OUT / "site"
SITE.mkdir(exist_ok=True)
MM = 0.01  # one millimetre becomes one centimetre: a comfortable scene size
HEIGHT = 15.2 * MM
POSTS = [(sx * 51.75 * MM, sy * 18.75 * MM) for sx in (-1, 1) for sy in (-1, 1)]


def material(name, color, roughness=0.5, metallic=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    shader = mat.node_tree.nodes["Principled BSDF"]
    shader.inputs["Base Color"].default_value = (*color, 1.0)
    shader.inputs["Roughness"].default_value = roughness
    shader.inputs["Metallic"].default_value = metallic
    return mat


def load(filename, mat, parent):
    bpy.ops.wm.stl_import(filepath=str(OUT / filename))
    obj = bpy.context.selected_objects[0]
    obj.scale = (MM, MM, MM)
    obj.data.materials.append(mat)
    obj.parent = parent
    return obj


def screw(mat, parent, x, y):
    """A pan-head screw in the device's own frame: head under the base, shank going in."""
    bpy.ops.mesh.primitive_cylinder_add(radius=2.3 * MM, depth=1.6 * MM, location=(x, y, -0.8 * MM))
    head = bpy.context.object
    bpy.ops.mesh.primitive_cylinder_add(radius=1.2 * MM, depth=8.0 * MM, location=(x, y, 4.0 * MM))
    shank = bpy.context.object
    for part in (head, shank):
        part.data.materials.append(mat)
        part.parent = parent
    return head, shank


def light(name, location, energy, size):
    data = bpy.data.lights.new(name, "AREA")
    data.energy = energy
    data.size = size
    obj = bpy.data.objects.new(name, data)
    obj.location = location
    bpy.context.collection.objects.link(obj)
    aim(obj, Vector((0, 0, 0.05)))


def aim(obj, target):
    obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()


def shot(name, location, target, lens=60, size=(1600, 1000)):
    camera.location = location
    camera.data.lens = lens
    aim(camera, Vector(target))
    scene.render.resolution_x, scene.render.resolution_y = size
    scene.render.filepath = str(SITE / name)
    bpy.ops.render.render(write_still=True)
    print("rendered", name)


bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.samples = 128
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

bpy.ops.mesh.primitive_plane_add(size=40, location=(0, 0, 0))
bpy.context.object.is_shadow_catcher = True

light("Key", (1.6, -1.8, 2.4), 75, 2.0)
light("Fill", (-2.2, -0.8, 1.4), 24, 2.5)
light("Rim", (0.2, 2.4, 1.6), 55, 1.5)

body = material("Body", (0.80, 0.79, 0.77), 0.48)
violet = material("Mark", (0.202, 0.042, 0.847), 0.4)
dark = material("Base", (0.04, 0.04, 0.05), 0.5)
steel = material("Screw", (0.55, 0.56, 0.58), 0.3, metallic=1.0)

device = bpy.data.objects.new("Device", None)
scene.collection.objects.link(device)
shell = load("edge_tag_station_shell.stl", body, device)
mark = load("edge_tag_station_mark.stl", violet, device)
base = load("edge_tag_station_base.stl", dark, device)
reader = load("preview_reader_board.stl", material("Reader", (0.02, 0.10, 0.36), 0.35), device)
esp = load("preview_esp_board.stl", material("ESP", (0.015, 0.015, 0.02), 0.4), device)
screws = [part for x, y in POSTS for part in screw(steel, device, x, y)]
for part in screws:
    part.hide_render = True

# The finished device on a desk, and its back with the USB-C opening.
shot("kit-front.webp", (1.35, -1.9, 1.2), (0.0, 0.0, 0.05))
shot("kit-back.webp", (-1.55, 2.25, 1.15), (0.0, 0.0, 0.05), size=(1200, 800))

# Assembly happens with the shell lying on its top face. Turned over, the
# device's own "up" points down: moving a part by +z in its frame lowers it.
device.rotation_euler = (math.pi, 0.0, 0.0)
device.location.z = HEIGHT

# 1. The two printed parts, the base lying in front of the shell.
for part in (mark, reader, esp):
    part.hide_render = True
base.location = (0.0, 62.0 * MM, 13.2 * MM)
shot("step-print.webp", (1.55, -2.75, 2.1), (0.0, -0.3, 0.05), size=(1200, 800))

# 2. Boards in place.
base.hide_render = True
reader.hide_render = esp.hide_render = False
shot("step-boards.webp", (1.45, -2.05, 1.75), (0.0, 0.0, 0.08), size=(1200, 800))

# 3. Base plate and screws going on.
base.hide_render = False
base.location = (0.0, 0.0, -24.0 * MM)
for part in screws:
    part.hide_render = False
    part.location.z -= 44.0 * MM
shot("step-close.webp", (1.65, -2.4, 2.2), (0.0, 0.0, 0.3), size=(1200, 800))
