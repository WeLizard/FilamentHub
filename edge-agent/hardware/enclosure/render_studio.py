"""The studio shared by the site renders: palette, printed-plastic materials, lights.

Used by render_family.py and render_preview.py; the boards come from
render_parts.py. Call setup() first: it empties Blender and builds the scene.
"""

import math
from pathlib import Path

import bpy
from mathutils import Vector

import render_parts as parts

OUT = Path(__file__).parent / "out"
SITE = OUT / "site"
MM = 0.01  # one millimetre becomes one centimetre: a comfortable scene size
srgb = parts.srgb

# The site's palette: violet case, the dark panel colour for the base, a light mark.
SHELL = "#9333ea"
BASE = "#17112e"
MARK = "#ede9fe"
CAPS = "#c4b5fd"
RIM = "#67e8f9"


def use_gpu(scene):
    prefs = bpy.context.preferences.addons["cycles"].preferences
    for kind in ("OPTIX", "CUDA", "HIP", "ONEAPI"):
        try:
            prefs.compute_device_type = kind
        except TypeError:
            continue
        prefs.get_devices()
        devices = [d for d in prefs.devices if d.type == kind]
        if devices:
            for device in prefs.devices:
                device.use = device.type == kind
            scene.cycles.device = "GPU"
            print("rendering on", kind, [d.name for d in devices])
            return
    print("rendering on CPU")


def printed(name, hex_color, roughness=0.42):
    """A printed part in satin PLA.

    The walls carry 0.2 mm layer ridges; a face that lay on the textured PEI
    sheet (the top of a shell printed upside down, the underside of a base)
    carries its fine grain instead.
    """
    mat = parts.material(name, srgb(hex_color), roughness)
    tree = mat.node_tree
    nodes, links = tree.nodes, tree.links

    def node(kind, **inputs):
        item = nodes.new(kind)
        for key, value in inputs.items():
            setattr(item, key, value)
        return item

    def math_node(operation, value=None):
        item = node("ShaderNodeMath", operation=operation)
        if value is not None:
            item.inputs[1].default_value = value
        return item

    coords = node("ShaderNodeTexCoord")
    split = node("ShaderNodeSeparateXYZ")
    links.new(coords.outputs["Object"], split.inputs[0])
    # Ridges: |sin| gives rounded beads with a crease between layers.
    phase = math_node("MULTIPLY", math.pi / 0.2)
    ridge = math_node("SINE")
    bead = math_node("ABSOLUTE")
    links.new(split.outputs["Z"], phase.inputs[0])
    links.new(phase.outputs[0], ridge.inputs[0])
    links.new(ridge.outputs[0], bead.inputs[0])
    # Faces looking straight up or down lay on the sheet.
    geometry = node("ShaderNodeNewGeometry")
    normal = node("ShaderNodeSeparateXYZ")
    links.new(geometry.outputs["Normal"], normal.inputs[0])
    flat = math_node("ABSOLUTE")
    links.new(normal.outputs["Z"], flat.inputs[0])
    sheet = math_node("GREATER_THAN", 0.97)
    links.new(flat.outputs[0], sheet.inputs[0])
    grain = node("ShaderNodeTexNoise")
    grain.inputs["Scale"].default_value = 2.2
    grain.inputs["Detail"].default_value = 6.0
    links.new(coords.outputs["Object"], grain.inputs["Vector"])
    mix = node("ShaderNodeMix", data_type="FLOAT")
    links.new(sheet.outputs[0], mix.inputs["Factor"])
    links.new(bead.outputs[0], mix.inputs["A"])
    links.new(grain.outputs["Fac"], mix.inputs["B"])
    bump = node("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.6
    bump.inputs["Distance"].default_value = 0.0012
    links.new(mix.outputs["Result"], bump.inputs["Height"])
    shader = nodes["Principled BSDF"]
    links.new(bump.outputs["Normal"], shader.inputs["Normal"])
    # The sheet side is a touch more matte than the walls.
    rough = node("ShaderNodeMapRange")
    rough.inputs["To Min"].default_value = roughness
    rough.inputs["To Max"].default_value = min(roughness + 0.18, 1.0)
    links.new(sheet.outputs[0], rough.inputs["Value"])
    links.new(rough.outputs["Result"], shader.inputs["Roughness"])
    return mat


def ghost(name, hex_color):
    """The case seen through: clear where it faces the camera, tinted at its edges."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    tree = mat.node_tree
    nodes, links = tree.nodes, tree.links
    shader = nodes["Principled BSDF"]
    shader.inputs["Base Color"].default_value = (*srgb(hex_color), 1.0)
    shader.inputs["Roughness"].default_value = 0.35
    clear = nodes.new("ShaderNodeBsdfTransparent")
    mix = nodes.new("ShaderNodeMixShader")
    facing = nodes.new("ShaderNodeLayerWeight")
    facing.inputs["Blend"].default_value = 0.2
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.03, 0.03, 0.03, 1.0)
    ramp.color_ramp.elements[1].color = (0.6, 0.6, 0.6, 1.0)
    links.new(facing.outputs["Facing"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], mix.inputs["Fac"])
    links.new(clear.outputs[0], mix.inputs[1])
    links.new(shader.outputs[0], mix.inputs[2])
    links.new(mix.outputs[0], nodes["Material Output"].inputs["Surface"])
    return mat


def aim(obj, target):
    obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()


def light(name, location, energy, size, color=(1.0, 1.0, 1.0)):
    data = bpy.data.lights.new(name, "AREA")
    data.energy = energy
    data.size = size
    data.color = color
    obj = bpy.data.objects.new(name, data)
    obj.location = location
    bpy.context.collection.objects.link(obj)
    aim(obj, Vector((0, 0, 0.05)))
    return obj


scene = camera = None
MATERIALS = PARTS = {}


def setup(samples=192):
    """Factory-empty Blender, then the render settings, a soft violet world, a camera and a shadow catcher."""
    global scene, camera, MATERIALS, PARTS
    SITE.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    use_gpu(scene)
    scene.cycles.samples = samples
    scene.cycles.use_denoising = True
    scene.cycles.transparent_max_bounces = 16
    scene.render.film_transparent = True
    # Standard keeps the brand colours as they are on the site; AgX turns violet blue.
    scene.view_settings.view_transform = "Standard"
    scene.render.image_settings.file_format = "WEBP"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.quality = 90

    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (*srgb("#a78bfa"), 1.0)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.35
    scene.world = world

    camera = bpy.data.objects.new("Camera", bpy.data.cameras.new("Camera"))
    scene.collection.objects.link(camera)
    scene.camera = camera

    bpy.ops.mesh.primitive_plane_add(size=60, location=(0, 0, 0))
    bpy.context.object.is_shadow_catcher = True

    MATERIALS = {
        "body": printed("Body", SHELL),
        "mark": printed("Mark", MARK, 0.5),
        "base": printed("Base", BASE, 0.55),
        "accent": printed("Caps", CAPS, 0.4),
        "ghost": ghost("Ghost body", "#c4b5fd"),
        "ghost_mark": ghost("Ghost mark", MARK),
        "screw": parts.material("Screw", srgb("#9ca3af"), 0.3, metallic=1.0),
    }
    PARTS = parts.part_materials()
    return scene


def glow(name, color, strength):
    mat = parts.material(name, (0.0, 0.0, 0.0), 0.5, emission=color, strength=strength)
    return mat


def lit(root, info, led_colors, lines):
    """Light the LED windows and put text on the screen."""
    for index, (x, y) in enumerate(info["leds"]):
        color = srgb(led_colors[index % len(led_colors)])
        disc = parts.cyl(root, glow(f"LED{index}", color, 5.0), 2.5, 0.02, (x, y, info["top"] + 0.02), segments=32)
        disc.name = f"LED glow {index}"
    if not lines:
        return
    sx, sy = info["screen"]
    view_h = info["view"][1]
    for text, size, dy in lines:
        obj = parts.label(root, glow("Screen", srgb("#e0f7ff"), 2.5), text, (sx, sy + dy * view_h, info["ceiling"] + 0.05), size * view_h)
        obj.name = f"screen {text}"


def load(root, filename, mat):
    bpy.ops.wm.stl_import(filepath=str(OUT / filename))
    obj = bpy.context.selected_objects[0]
    obj.data.materials.append(mat)
    obj.parent = root
    return obj


def clear_device():
    """Remove everything but the camera, the lights in use and the shadow catcher."""
    for obj in list(bpy.data.objects):
        if obj.type in {"MESH", "FONT", "EMPTY"} and not obj.is_shadow_catcher:
            bpy.data.objects.remove(obj, do_unlink=True)


def render(name, location, target, lens=60, size=(1600, 1000), cyan=1.0, top=0.0, key=1.0):
    k = max(location[2] / 1.2, 0.6)
    # Product lighting: a large softbox above and a little behind lights the top
    # and makes the chamfers glint, the walls fall off into a gradient, a weak
    # fill from the camera keeps them readable and a cyan rim draws the far edge.
    lights = [
        light("Key", (-0.25 * location[0], -0.55 * location[1], location[2] * 1.9), 140 * key * k ** 2, 2.6 * k),
        light("Fill", (location[0] * 1.3, location[1] * 1.2, location[2] * 0.5), 14 * k ** 2, 3.0, srgb("#c4b5fd")),
        light("Rim", (-1.2 * location[0], -0.2 * location[1], location[2] * 0.25), 55 * cyan * k ** 2, 1.2, srgb(RIM)),
    ]
    if top:
        # A softbox straight above lights the boards through the clear case.
        lights.append(light("Top", (0.0, 0.0, location[2] * 1.4), 60 * top * k ** 2, 1.6 * k))
    camera.location = location
    camera.data.lens = lens
    aim(camera, Vector(target))
    scene.render.resolution_x, scene.render.resolution_y = size
    scene.render.filepath = str(SITE / name)
    bpy.ops.render.render(write_still=True)
    for obj in lights:
        bpy.data.objects.remove(obj, do_unlink=True)
    print("rendered", name)


