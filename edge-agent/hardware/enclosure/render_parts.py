"""Boards and modules of the Edge builds, modelled in Blender for the site pictures.

Imported by render_family.py and render_preview.py. Every part is built in
millimetres around its own origin: the PCB's lower face at z = 0, components
on its upper face, the long side along x. `place()` puts a part where the case
scripts recorded it (the "inside" lists of out/scene.json and out/kit.json):

    pn5180      reader, z = its face against the top wall, components hanging down,
                header towards -x, antenna centre 21 mm from the +x end
    c3, s3      board on the base's spine, z = lower face of the PCB,
                USB end towards +x (direction +1) or -x (direction -1)
    c3_hanging  the kit's C3 under the top wall, z = upper face, USB towards +y
    oled        z = the top of its glass, against the top wall
    touch       x = centre of the glass, z = the top of its glass
    ws2812      z = the top of the LED, under its thin skin in the top wall
    switch      z = the lower face of the tactile switch
    sht40       board standing against the back wall, z = its centre height
    buzzer, cell, mt3608, buck, pcf8574
                z = the base's upper face
    tp4056      z = the PCB's lower face, USB-C towards -x
    slide       z = its centre height, actuator through the back wall

Sizes follow catalogue drawings; small passives are placed for looks, not to a
real layout.
"""

import math

import bmesh
import bpy


def srgb(hex_color):
    """Brand colours are sRGB; Blender wants linear values."""
    values = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    return tuple(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in values)


def material(name, color, roughness=0.5, metallic=0.0, coat=0.0, emission=None, strength=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    shader = mat.node_tree.nodes["Principled BSDF"]
    shader.inputs["Base Color"].default_value = (*color, 1.0)
    shader.inputs["Roughness"].default_value = roughness
    shader.inputs["Metallic"].default_value = metallic
    shader.inputs["Coat Weight"].default_value = coat
    if emission is not None:
        shader.inputs["Emission Color"].default_value = (*emission, 1.0)
        shader.inputs["Emission Strength"].default_value = strength
    return mat


def part_materials():
    return {
        # No coat on solder mask: a coat mirrors the case's ribs in a board seen through it.
        "pcb_black": material("PCB black", srgb("#16161a"), 0.5),
        "pcb_blue": material("PCB blue", srgb("#123f96"), 0.5),
        "pcb_reader": material("PCB reader", srgb("#0b2766"), 0.5),
        "pcb_red": material("PCB red", srgb("#9f1d22"), 0.5),
        "pcb_green": material("PCB green", srgb("#1d5c3a"), 0.5),
        "trace_blue": material("Trace blue", srgb("#2a63c9"), 0.3),
        "trace_reader": material("Trace reader", srgb("#2659bd"), 0.3),
        "gold": material("ENIG", srgb("#d9a441"), 0.22, metallic=1.0),
        "tin": material("Solder", srgb("#c9ccd1"), 0.18, metallic=1.0),
        "steel": material("Steel", srgb("#b9bec6"), 0.22, metallic=1.0),
        "shield": material("Shield", srgb("#c3c7cc"), 0.32, metallic=1.0),
        "chip": material("Chip", srgb("#1b1b1f"), 0.55),
        "plastic": material("Plastic black", srgb("#121214"), 0.5),
        "plastic_white": material("Plastic white", srgb("#ecebe6"), 0.45),
        "ceramic": material("Ceramic", srgb("#b4885a"), 0.5),
        "ceramic_grey": material("Ceramic grey", srgb("#8d8f94"), 0.45),
        "resistor": material("Resistor", srgb("#202022"), 0.5),
        "silk": material("Silkscreen", srgb("#f2f2f0"), 0.6),
        "laser": material("Laser mark", srgb("#6f7378"), 0.5, metallic=0.4),
        "glass": material("Display glass", srgb("#050507"), 0.06, coat=1.0),
        "flex": material("Flex", srgb("#c77d1a"), 0.35, coat=0.4),
        "pot_blue": material("Trimmer", srgb("#2b5fd9"), 0.4),
        "brass": material("Brass", srgb("#c8a24a"), 0.3, metallic=1.0),
        "cell_wrap": material("Cell wrap", srgb("#0f766e"), 0.25, coat=0.6),
        "insulator": material("Insulator", srgb("#ecebe6"), 0.6),
        "jumper": material("Jumper", srgb("#e7b416"), 0.45),
        "jst": material("JST", srgb("#f1efe6"), 0.5),
        "led_red": material("LED red", srgb("#ff3b3b"), 0.3, emission=srgb("#ff3b3b"), strength=2.0),
        "led_blue": material("LED blue", srgb("#3b82f6"), 0.3, emission=srgb("#3b82f6"), strength=2.0),
        "led_lens": material("LED lens", srgb("#f8f7f0"), 0.15, coat=0.8),
        "wire_red": material("Wire red", srgb("#d6312f"), 0.4),
        "wire_black": material("Wire black", srgb("#1a1a1c"), 0.45),
        "wire_yellow": material("Wire yellow", srgb("#e5b81f"), 0.4),
        "wire_green": material("Wire green", srgb("#2fa35a"), 0.4),
        "wire_blue": material("Wire blue", srgb("#2f6fd6"), 0.4),
        "wire_white": material("Wire white", srgb("#e9e7e2"), 0.45),
    }


# --- primitives ---------------------------------------------------------------

def _link(name, mesh, mat, parent, bevel, smooth_angle=None):
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj.data.materials.append(mat)
    obj.parent = parent
    if bevel:
        mod = obj.modifiers.new("Bevel", "BEVEL")
        mod.width = bevel
        mod.segments = 2
        mod.limit_method = "ANGLE"
    if smooth_angle is not None:
        mesh.shade_smooth()
        mesh.set_sharp_from_angle(angle=smooth_angle)
    return obj


def box(parent, mat, size, at, bevel=0.0, name="box", rot=None):
    """A box of `size` (x, y, z) with its lower face centred on `at`."""
    sx, sy, sz = size
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for vert in bm.verts:
        vert.co.x = vert.co.x * sx
        vert.co.y = vert.co.y * sy
        vert.co.z = (vert.co.z + 0.5) * sz
    bm.to_mesh(mesh)
    bm.free()
    obj = _link(name, mesh, mat, parent, min(bevel, 0.45 * min(size)) if bevel else 0.0)
    obj.location = at
    if rot:
        obj.rotation_euler = rot
    return obj


def cyl(parent, mat, radius, height, at, segments=24, name="cyl", rot=None, bevel=0.0, radius2=None):
    """A cylinder (or cone, with `radius2` on top) standing on `at`."""
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cone(
        bm, cap_ends=True, segments=segments,
        radius1=radius, radius2=radius if radius2 is None else radius2, depth=height,
    )
    for vert in bm.verts:
        vert.co.z += height / 2
    bm.to_mesh(mesh)
    bm.free()
    obj = _link(name, mesh, mat, parent, bevel, smooth_angle=0.7)
    obj.location = at
    if rot:
        obj.rotation_euler = rot
    return obj


def label(parent, mat, text, at, size, rot=(0.0, 0.0, 0.0), align="CENTER"):
    """Flat text lying on a face: silkscreen and laser marking."""
    curve = bpy.data.curves.new(f"text {text}", "FONT")
    curve.body = text
    curve.size = size
    curve.align_x = align
    curve.align_y = "CENTER"
    obj = bpy.data.objects.new(f"text {text}", curve)
    bpy.context.scene.collection.objects.link(obj)
    obj.data.materials.append(mat)
    obj.parent = parent
    obj.location = at
    obj.rotation_euler = rot
    return obj


def group(parent, name, location=(0.0, 0.0, 0.0), rotation=(0.0, 0.0, 0.0)):
    empty = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(empty)
    empty.parent = parent
    empty.location = location
    empty.rotation_euler = rotation
    return empty


def arrayed(obj, count, step):
    """Repeat an object `count` times, `step` (x, y, z) mm apart."""
    mod = obj.modifiers.new("Array", "ARRAY")
    mod.count = count
    mod.use_relative_offset = False
    mod.use_constant_offset = True
    mod.constant_offset_displace = step
    # The array is applied before the bevel, so both stay correct.
    if "Bevel" in obj.modifiers:
        obj.modifiers.move(len(obj.modifiers) - 1, 0)
    return obj


# --- common details -----------------------------------------------------------

def smd(g, m, x, y, z, kind="cap", turn=False):
    """An 0603 passive: ceramic body or black resistor with tinned ends."""
    length, width, height = 1.6, 0.8, 0.5
    rot = (0.0, 0.0, math.pi / 2) if turn else None
    body = m["ceramic"] if kind == "cap" else m["resistor"]
    box(g, body, (length * 0.62, width, height), (x, y, z), bevel=0.05, rot=rot)
    for side in (-1, 1):
        dx, dy = (0.0, side * length * 0.4) if turn else (side * length * 0.4, 0.0)
        box(g, m["tin"], (length * 0.2, width, height) if not turn else (width, length * 0.2, height), (x + dx, y + dy, z), bevel=0.05)


def ic(g, m, size, x, y, z, legs=None, text=None, rot=0.0):
    """A packaged chip; `legs` = (per side, pitch) for gull-wing packages on two sides."""
    sx, sy, sz = size
    box(g, m["chip"], size, (x, y, z), bevel=0.12, rot=(0, 0, rot))
    if legs:
        count, pitch = legs
        for side in (-1, 1):
            leg = box(g, m["tin"], (0.35, 1.1, 0.25), (0, 0, 0), bevel=0.04)
            first = -(count - 1) * pitch / 2
            if rot:
                leg.rotation_euler = (0, 0, rot)
                leg.location = (x + side * (sy / 2 + 0.35), y + first, z + 0.05)
                arrayed(leg, count, (0.0, pitch, 0.0))
            else:
                leg.location = (x + first, y + side * (sy / 2 + 0.35), z + 0.05)
                arrayed(leg, count, (pitch, 0.0, 0.0))
    if text:
        label(g, m["laser"], text, (x, y, z + sz + 0.01), min(sx, sy) * 0.22, rot=(0, 0, rot))


def _stadium(width, height, segments=10):
    """Points of a stadium outline in the (y, z) plane, centred on the origin."""
    r = height / 2
    c = width / 2 - r
    points = []
    for side, start in ((1, -math.pi / 2), (-1, math.pi / 2)):
        for i in range(segments + 1):
            angle = start + math.pi * i / segments
            points.append((side * c + r * math.cos(angle), r * math.sin(angle)))
    return points


def stadium_shell(parent, mat, width, height, wall, length, at, toward=+1, name="shell"):
    """A hollow stadium tube along x, open at its mouth (towards `toward`), closed at the back."""
    outer = _stadium(width, height)
    inner = _stadium(width - 2 * wall, height - 2 * wall)
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    x_mouth, x_back = toward * length / 2, -toward * length / 2
    loops = {
        key: [bm.verts.new((x, py, pz)) for py, pz in shape]
        for key, (x, shape) in {
            "om": (x_mouth, outer), "ob": (x_back, outer), "im": (x_mouth, inner), "ib": (x_back + toward * wall, inner),
        }.items()
    }
    count = len(outer)
    for i in range(count):
        j = (i + 1) % count
        bm.faces.new((loops["om"][i], loops["om"][j], loops["ob"][j], loops["ob"][i]))
        bm.faces.new((loops["im"][j], loops["im"][i], loops["ib"][i], loops["ib"][j]))
        bm.faces.new((loops["om"][j], loops["om"][i], loops["im"][i], loops["im"][j]))
    bm.faces.new(list(reversed(loops["ob"])))
    bm.faces.new(loops["ib"])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(mesh)
    bm.free()
    obj = _link(name, mesh, mat, parent, 0.0, smooth_angle=0.6)
    obj.location = at
    return obj


def usb_c(g, m, x, y, z, toward=+1):
    """A mid-mount USB-C receptacle on the board, its mouth towards +x (or -x).

    The real part: a seamless steel shell 8.94 x 3.26 mm, 7.35 mm deep, and in it
    a plastic tongue 6.7 x 0.7 mm with twelve contacts on each face.
    """
    length, width, height = 7.35, 8.94, 3.26
    cz = z + height / 2
    stadium_shell(g, m["steel"], width, height, 0.25, length, (x, y, cz), toward, name="usb-c")
    tongue_len = length - 1.6
    tongue_x = x - toward * 0.8
    box(g, m["plastic"], (tongue_len, 6.7, 0.7), (tongue_x, y, cz - 0.35), bevel=0.12, name="usb-c tongue")
    pitch = 0.5
    first = -5.5 * pitch
    for face_z in (cz + 0.35, cz - 0.37):
        contact = box(g, m["gold"], (1.6, 0.25, 0.02), (x + toward * (length / 2 - 2.2), y + first, face_z), name="usb-c pins")
        arrayed(contact, 12, (0.0, pitch, 0.0))
    # Through-hole legs of the shell, soldered at the board's edge.
    for sy in (-1, 1):
        box(g, m["steel"], (1.2, 0.5, 1.4), (x - toward * 1.6, y + sy * (width / 2 + 0.05), z - 0.6))


def tact(g, m, x, y, z, size=(3.0, 4.0)):
    sx, sy = size
    box(g, m["plastic"], (sx, sy, 0.9), (x, y, z), bevel=0.15)
    box(g, m["steel"], (sx, sy, 0.15), (x, y, z + 0.9))
    cyl(g, m["ceramic"], 0.75, 0.5, (x, y, z + 1.05), segments=16)


def header_row(g, m, count, x, y, z, along="x", down=True, length=6.0, strip=True):
    """A row of 2.54 mm pins: plastic strip under the board, gold pins, solder on top."""
    pitch = 2.54
    first = -(count - 1) * pitch / 2
    step = (pitch, 0.0, 0.0) if along == "x" else (0.0, pitch, 0.0)
    start = (x + first, y, z) if along == "x" else (x, y + first, z)
    span = count * pitch
    if strip:
        size = (span, 2.5, 2.5) if along == "x" else (2.5, span, 2.5)
        box(g, m["plastic"], size, (x, y, (-2.5 if down else z)), bevel=0.2)
    pin_z = -length if down else z
    arrayed(box(g, m["gold"], (0.64, 0.64, length + (1.6 if down else 0.0)), (start[0], start[1], pin_z), bevel=0.08), count, step)
    arrayed(cyl(g, m["gold"], 0.9, 0.04, start, segments=16), count, step)
    if down:
        arrayed(cyl(g, m["tin"], 0.75, 0.55, start, segments=16, radius2=0.35), count, step)


def pads(g, m, count, x, y, z, along="x", size=(1.4, 1.6)):
    pitch = 2.54
    first = -(count - 1) * pitch / 2
    if along == "x":
        arrayed(box(g, m["gold"], (size[0], size[1], 0.05), (x + first, y, z)), count, (pitch, 0.0, 0.0))
    else:
        arrayed(box(g, m["gold"], (size[1], size[0], 0.05), (x, y + first, z)), count, (0.0, pitch, 0.0))


def holes(g, m, points, z, radius=1.6):
    for x, y in points:
        cyl(g, m["gold"], radius, 0.06, (x, y, z), segments=24)
        cyl(g, m["plastic"], radius * 0.62, 0.08, (x, y, z), segments=20)


def rect_loop(g, mat, cx, cy, lx, ly, width, z, height=0.035):
    """One rectangular turn of a trace."""
    box(g, mat, (lx, width, height), (cx, cy + ly / 2, z))
    box(g, mat, (lx, width, height), (cx, cy - ly / 2, z))
    box(g, mat, (width, ly, height), (cx + lx / 2, cy, z))
    box(g, mat, (width, ly, height), (cx - lx / 2, cy, z))


# --- the parts ----------------------------------------------------------------

def esp32_s3_devkitc(parent, m):
    """ESP32-S3-DevKitC-1 N16R8: 69 x 25.4 mm, WROOM-1 module at -x, two USB-C at +x."""
    g = group(parent, "ESP32-S3-DevKitC-1")
    L, W, T = 69.0, 25.4, 1.6
    box(g, m["pcb_black"], (L, W, T), (0, 0, 0), bevel=0.25)
    for side in (-1, 1):
        header_row(g, m, 22, 0.0, side * 11.43, T, along="x")
    # The module: its own PCB, the RF shield and the printed antenna at the board's end.
    mx0 = -L / 2
    box(g, m["pcb_black"], (25.5, 18.0, 0.8), (mx0 + 12.75, 0, T), bevel=0.1)
    box(g, m["shield"], (17.6, 16.4, 2.3), (mx0 + 6.6 + 17.6 / 2, 0, T + 0.8), bevel=0.3)
    label(g, m["laser"], "ESP32-S3-WROOM-1", (mx0 + 6.6 + 8.8, 2.4, T + 3.11), 1.25)
    label(g, m["laser"], "N16R8", (mx0 + 6.6 + 8.8, -0.4, T + 3.11), 1.1)
    for i in range(6):
        y = -6.0 + i * 2.4
        box(g, m["gold"], (4.4, 0.45, 0.04), (mx0 + 3.2, y, T + 0.8))
        if i < 5:
            box(g, m["gold"], (0.45, 2.4, 0.04), (mx0 + 1.2 + (i % 2) * 4.0, y + 1.2, T + 0.8))
    # USB and UART sockets, buttons, the bridge chip, the regulator and the RGB LED.
    for y in (-5.6, 5.6):
        usb_c(g, m, L / 2 - 3.2, y, T, toward=+1)
    label(g, m["silk"], "USB", (L / 2 - 8.6, -5.6, T + 0.01), 1.0, rot=(0, 0, math.pi / 2))
    label(g, m["silk"], "UART", (L / 2 - 8.6, 5.6, T + 0.01), 1.0, rot=(0, 0, math.pi / 2))
    for y, text in ((-6.2, "BOOT"), (6.2, "RST")):
        tact(g, m, 22.5, y, T, size=(3.6, 2.8))
        label(g, m["silk"], text, (22.5, y - 2.6 if y < 0 else y + 2.6, T + 0.01), 0.9)
    ic(g, m, (4.0, 4.0, 0.85), 13.0, 3.2, T, text="CH343")
    ic(g, m, (6.5, 3.5, 1.6), 9.0, -5.0, T, text="1117")
    box(g, m["tin"], (6.5, 1.2, 0.3), (9.0, -7.6, T))
    box(g, m["plastic_white"], (2.0, 2.0, 0.9), (3.0, 6.8, T), bevel=0.15)
    cyl(g, m["led_lens"], 0.55, 0.1, (3.0, 6.8, T + 0.9), segments=16)
    for x, y, kind, turn in (
        (17.5, -2.0, "cap", True), (17.5, 2.0, "res", True), (4.5, -1.5, "cap", False), (4.5, 1.5, "res", False),
        (0.0, -6.5, "cap", False), (0.0, 3.5, "res", True), (14.0, -6.5, "cap", False), (27.5, 0.0, "res", True),
        (-6.0, -6.0, "cap", False), (-6.0, 6.0, "cap", False),
    ):
        smd(g, m, x, y, T, kind, turn)
    label(g, m["silk"], "ESP32-S3-DevKitC-1", (2.5, 0.0, T + 0.01), 1.35)
    return g


def esp32_c3_supermini(parent, m):
    """ESP32-C3 SuperMini: 22.52 x 18 mm, chip antenna at -x, USB-C at +x."""
    g = group(parent, "ESP32-C3 SuperMini")
    L, W, T = 22.52, 18.0, 1.2
    box(g, m["pcb_blue"], (L, W, T), (0, 0, 0), bevel=0.2)
    for side in (-1, 1):
        pads(g, m, 8, -1.0, side * (W / 2 - 0.9), T, along="x", size=(1.3, 1.8))
        arrayed(cyl(g, m["plastic"], 0.5, T + 0.02, (-1.0 - 3.5 * 2.54, side * (W / 2 - 0.4), -0.01), segments=12), 8, (2.54, 0.0, 0.0))
    usb_c(g, m, L / 2 - 3.0, 0.0, T, toward=+1)
    ic(g, m, (5.0, 5.0, 0.85), -1.2, 0.8, T, text="C3")
    box(g, m["steel"], (3.2, 2.5, 0.8), (3.8, -4.2, T), bevel=0.15)
    box(g, m["ceramic_grey"], (1.6, 5.2, 1.1), (-9.4, 0.0, T), bevel=0.12)
    box(g, m["tin"], (0.4, 5.2, 1.1), (-10.0, 0.0, T), bevel=0.05)
    for y in (-5.0, 5.0):
        tact(g, m, 5.6, y, T, size=(2.6, 3.2))
    ic(g, m, (2.9, 1.6, 1.1), -5.6, -4.6, T)
    box(g, m["led_red"], (1.6, 0.8, 0.5), (-5.2, 4.2, T), bevel=0.05)
    box(g, m["led_blue"], (1.6, 0.8, 0.5), (-7.4, 4.2, T), bevel=0.05)
    for x, y, kind, turn in ((-4.2, -1.6, "cap", True), (2.2, 4.6, "res", False), (1.2, -4.8, "cap", False), (-7.0, -2.2, "res", True)):
        smd(g, m, x, y, T, kind, turn)
    label(g, m["silk"], "C3 SuperMini", (-1.0, -6.6, T + 0.01), 0.9)
    return g


def arc(g, mat, cx, cy, radius, start, end, width, z, segments=20):
    """A flat arc of silk-screen, `start`..`end` in degrees from +x, lying at height z."""
    mesh = bpy.data.meshes.new("arc")
    bm = bmesh.new()
    inner, outer = [], []
    for step in range(segments + 1):
        angle = math.radians(start + (end - start) * step / segments)
        for ring, r in ((inner, radius - width / 2), (outer, radius + width / 2)):
            ring.append(bm.verts.new((cx + r * math.cos(angle), cy + r * math.sin(angle), z)))
    for step in range(segments):
        bm.faces.new((inner[step], outer[step], outer[step + 1], inner[step + 1]))
    bm.to_mesh(mesh)
    bm.free()
    return _link("arc", mesh, mat, g, 0.0)


PN5180_PINS = ("+5V", "+3.3V", "RST", "NSS", "MOSI", "MISO", "SCK", "BUSY", "GND", "GPIO", "IRQ", "AUX", "REQ")


def pn5180(parent, m):
    """PN5180-NFC module R1.1, 70 x 39 mm, drawn from the board itself.

    The wire pads are at -x and the antenna is centred 21.5 mm from +x. The
    component side carries the wave mark over the antenna, the chip with its
    passives and the labelled pads; wires are soldered to the pads, there is no
    pin header. Positions are read off a photograph of the board: `at(u, v)`
    takes millimetres from the board's left edge and from its antenna end.
    """
    g = group(parent, "PN5180")
    L, W, T = 70.0, 39.0, 1.6
    box(g, m["pcb_reader"], (L, W, T), (0, 0, 0), bevel=0.25)

    def at(u, v):
        return L / 2 - v, W / 2 - u

    ax, ay = at(19.5, 21.5)
    # The antenna is a trace round the top of the board, on both faces.
    for z in (T, -0.035):
        for turn in range(2):
            rect_loop(g, m["trace_reader"], L / 2 - 20.0, 0.0, 36.0 - turn * 2.0, 35.0 - turn * 2.0, 0.7, z)
    # The wave mark: a dot, a small ring and five arcs to each side.
    cyl(g, m["silk"], 0.55, 0.03, (ax, ay, T), segments=16)
    arc(g, m["silk"], ax, ay, 1.7, 0.0, 360.0, 0.3, T + 0.02, segments=32)
    for index in range(5):
        radius = 4.2 + index * 3.1
        spread = 38.0 + index * 4.0
        for middle in (90.0, -90.0):
            arc(g, m["silk"], ax, ay, radius, middle - spread, middle + spread, 0.42, T + 0.02)
    # Four mounting holes: two inside the antenna, two at the edges below it.
    for face in (T, -0.06):
        holes(g, m, [at(6.8, 7.1), at(32.2, 7.1), at(3.2, 44.3), at(35.8, 44.3)], face, radius=1.9)
    # The chip, its crystal and the passives around them.
    cx, cy = at(22.8, 56.3)
    ic(g, m, (6.0, 6.0, 0.85), cx, cy, T, text="PN5180")
    box(g, m["steel"], (2.5, 3.2, 0.7), (*at(22.6, 63.0), T), bevel=0.2)
    grid = (
        [(u, v) for v in (46.3, 48.6) for u in (12.6, 14.9, 17.2, 19.5, 21.8, 24.1, 26.4, 28.7)]
        + [(u, v) for u in (3.6, 6.1) for v in (51.4, 53.7, 56.0, 58.3, 60.6)]
        + [(u, v) for u in (9.4, 12.0, 14.6) for v in (51.8, 54.1, 56.4, 58.7, 61.0)]
        + [(29.6, 52.4), (32.2, 52.4), (29.6, 55.6), (32.2, 58.8), (29.6, 61.4), (18.0, 51.6), (26.6, 62.2)]
    )
    for index, (u, v) in enumerate(grid):
        smd(g, m, *at(u, v), T, "res" if index % 3 == 0 else "cap", turn=index % 2 == 0)
    # Thirteen labelled pads for the wires.
    pad_x = L / 2 - 66.6
    for index, name in enumerate(PN5180_PINS):
        y = (6 - index) * 2.54
        for face in (T, -0.06):
            cyl(g, m["gold"], 0.95, 0.06, (pad_x, y, face), segments=20)
            cyl(g, m["plastic"], 0.45, 0.08, (pad_x, y, face), segments=14)
        label(g, m["silk"], name, (pad_x + 2.3, y, T + 0.01), 0.72, rot=(0, 0, -math.pi / 2))
    label(g, m["silk"], "PN5180-NFC", (*at(35.3, 55.5), T + 0.01), 2.1)
    label(g, m["silk"], "R1.1-170710", (*at(37.3, 58.5), T + 0.01), 0.8)
    label(g, m["silk"], "179", (*at(33.0, 46.8), T + 0.01), 1.5)
    return g


def oled(parent, m, total=3.0):
    """1.3" SH1106 module: 35.4 x 33.5 mm board, glass on top, header along +y."""
    g = group(parent, "OLED 1.3")
    L, W, T = 35.4, 33.5, 1.2
    box(g, m["pcb_blue"], (L, W, T), (0, 0, 0), bevel=0.2)
    holes(g, m, [(sx * (L / 2 - 2.0), sy * (W / 2 - 2.0)) for sx in (-1, 1) for sy in (-1, 1)], T, radius=1.3)
    box(g, m["glass"], (34.4, 22.0, total - T), (0, -0.8, T), bevel=0.15)
    box(g, m["flex"], (12.0, 3.4, 0.15), (0, -13.4, T))
    pads(g, m, 4, 0.0, W / 2 - 1.8, T, along="x", size=(1.6, 1.6))
    for i, text in enumerate(("GND", "VCC", "SCL", "SDA")):
        label(g, m["silk"], text, ((i - 1.5) * 2.54, W / 2 - 4.2, T + 0.01), 0.8)
    return g


def touch(parent, m):
    """2.8" ILI9341 + XPT2046 module: glass centred on the origin, 86 x 50 mm board shifted to +x."""
    g = group(parent, "ILI9341")
    board_x = 4.0
    L, W, T = 86.0, 50.0, 1.6
    box(g, m["pcb_red"], (L, W, T), (board_x, 0, 0), bevel=0.25)
    holes(g, m, [(board_x + sx * (L / 2 - 2.8), sy * (W / 2 - 2.8)) for sx in (-1, 1) for sy in (-1, 1)], T, radius=1.5)
    box(g, m["steel"], (69.2, 49.6, 3.2), (0, 0, T), bevel=0.4)
    box(g, m["plastic_white"], (68.4, 48.8, 0.25), (0, 0, T + 3.2))
    box(g, m["glass"], (69.2, 49.6, 0.55), (0, 0, T + 3.45), bevel=0.2)
    # The pins point to the back of the module, away from the glass.
    header_row(g, m, 14, board_x + L / 2 - 2.0, 0.0, T, along="y", down=True, length=6.0, strip=True)
    ic(g, m, (6.5, 3.5, 1.6), board_x + L / 2 - 8.5, 14.0, T, rot=math.pi / 2)
    return g


def ws2812(parent, m):
    g = group(parent, "WS2812B")
    cyl(g, m["pcb_black"], 5.0, 1.0, (0, 0, 0), segments=40, bevel=0.15)
    box(g, m["plastic_white"], (5.0, 5.0, 1.6), (0, 0, 1.0), bevel=0.25)
    cyl(g, m["led_lens"], 1.9, 0.05, (0, 0, 2.6), segments=24)
    for angle in (0.0, 2.1, 4.2):
        box(g, m["gold"], (1.4, 1.0, 0.05), (3.6 * math.cos(angle), 3.6 * math.sin(angle), 1.0))
    return g


def tact_switch(parent, m):
    """12 x 12 x 7.3 mm tactile switch, lower face at z = 0."""
    g = group(parent, "Tact 12x12")
    box(g, m["plastic"], (12.0, 12.0, 3.6), (0, 0, 0), bevel=0.3)
    box(g, m["steel"], (12.0, 12.0, 0.3), (0, 0, 3.6))
    for sx in (-1, 1):
        for sy in (-1, 1):
            box(g, m["steel"], (0.7, 2.0, 1.0), (sx * 6.0, sy * 4.5, 1.2))
    cyl(g, m["plastic"], 1.75, 3.4, (0, 0, 3.9), segments=24)
    return g


def sht40(parent, m):
    g = group(parent, "SHT40")
    L, W, T = 25.4, 17.8, 1.6
    box(g, m["pcb_black"], (L, W, T), (0, 0, 0), bevel=0.2)
    box(g, m["plastic_white"], (1.5, 1.5, 0.5), (0, 2.0, T), bevel=0.1)
    for sx in (-1, 1):
        box(g, m["jst"], (6.0, 4.2, 2.9), (sx * 8.0, 4.5, T), bevel=0.2)
    pads(g, m, 4, 0.0, -W / 2 + 1.8, T, along="x", size=(1.5, 1.5))
    holes(g, m, [(sx * (L / 2 - 2.5), W / 2 - 2.5) for sx in (-1, 1)], T, radius=1.25)
    label(g, m["silk"], "SHT40", (0, -3.0, T + 0.01), 1.4)
    return g


def buzzer(parent, m):
    g = group(parent, "Buzzer")
    box(g, m["pcb_black"], (18.0, 13.0, 1.6), (0, 0, 0), bevel=0.2)
    cyl(g, m["plastic"], 6.0, 9.0, (1.5, 0, 1.6), segments=40, bevel=0.3)
    cyl(g, m["plastic_white"], 1.0, 0.05, (1.5, 0, 10.6), segments=20)
    header_row(g, m, 3, -7.6, 0.0, 1.6, along="y", down=False, length=5.0, strip=True)
    ic(g, m, (2.9, 1.6, 1.0), -4.0, 4.5, 1.6)
    return g


def cell(parent, m):
    """18650 cell in a single holder, 77 x 21 mm, lying along x."""
    g = group(parent, "18650")
    box(g, m["plastic"], (77.0, 21.0, 1.5), (0, 0, 0), bevel=0.3)
    for sy in (-1, 1):
        box(g, m["plastic"], (60.0, 1.4, 9.0), (0, sy * 9.8, 1.5), bevel=0.3)
    for sx in (-1, 1):
        box(g, m["plastic"], (2.0, 21.0, 16.0), (sx * 37.5, 0, 1.5), bevel=0.3)
        box(g, m["steel"], (0.4, 8.0, 8.0), (sx * 36.2, 0, 7.0))
    cyl(g, m["cell_wrap"], 9.25, 64.0, (-32.0, 0, 10.8), segments=48, rot=(0, math.pi / 2, 0))
    cyl(g, m["steel"], 7.6, 0.6, (32.0, 0, 10.8), segments=40, rot=(0, math.pi / 2, 0))
    cyl(g, m["insulator"], 9.3, 0.4, (31.0, 0, 10.8), segments=48, rot=(0, math.pi / 2, 0))
    return g


def tp4056(parent, m):
    """TP4056 charger with protection, USB-C at +x: 28 x 17 mm."""
    g = group(parent, "TP4056")
    L, W, T = 28.0, 17.0, 1.6
    box(g, m["pcb_blue"], (L, W, T), (0, 0, 0), bevel=0.2)
    usb_c(g, m, L / 2 - 3.2, 0.0, T, toward=+1)
    ic(g, m, (4.9, 3.9, 1.5), 1.0, 2.5, T, legs=(4, 1.27), text="TP4056")
    ic(g, m, (2.9, 1.6, 1.0), -4.5, -4.5, T, text="DW01")
    ic(g, m, (3.0, 4.4, 1.0), -0.5, -4.8, T, legs=(4, 0.65))
    box(g, m["led_red"], (1.6, 0.8, 0.5), (6.0, 6.2, T), bevel=0.05)
    box(g, m["led_blue"], (1.6, 0.8, 0.5), (6.0, -6.2, T), bevel=0.05)
    for y, text in ((5.5, "B+"), (-5.5, "B-")):
        box(g, m["gold"], (2.6, 2.6, 0.05), (-L / 2 + 2.0, y, T))
        label(g, m["silk"], text, (-L / 2 + 5.0, y, T + 0.01), 1.0)
    for x, y, turn in ((5.0, 2.0, True), (-6.0, 2.0, False), (-8.0, 5.5, False)):
        smd(g, m, x, y, T, "res", turn)
    return g


def mt3608(parent, m):
    """MT3608 step-up: 36 x 17 mm with the blue multi-turn trimmer."""
    g = group(parent, "MT3608")
    L, W, T = 36.0, 17.0, 1.6
    box(g, m["pcb_blue"], (L, W, T), (0, 0, 0), bevel=0.2)
    box(g, m["pot_blue"], (9.5, 4.8, 10.0), (-6.0, 4.5, T), bevel=0.3)
    cyl(g, m["brass"], 1.1, 0.8, (-10.4, 4.5, T + 8.2), segments=16, rot=(0, -math.pi / 2, 0))
    cyl(g, m["plastic"], 2.9, 4.5, (5.0, -2.5, T), segments=32, bevel=0.2)
    ic(g, m, (2.9, 1.6, 1.0), 9.5, 4.0, T)
    for x, y, kind in ((12.5, -3.0, "cap"), (-12.0, -3.5, "cap"), (13.0, 5.0, "res")):
        smd(g, m, x, y, T, kind, True)
    for sx in (-1, 1):
        for sy in (-1, 1):
            box(g, m["gold"], (2.4, 2.4, 0.05), (sx * (L / 2 - 2.0), sy * (W / 2 - 2.5), T))
    return g


def buck(parent, m):
    """24 V to 5 V step-down, 22 x 17 mm."""
    g = group(parent, "Step-down")
    L, W, T = 22.0, 17.0, 1.6
    box(g, m["pcb_green"], (L, W, T), (0, 0, 0), bevel=0.2)
    box(g, m["plastic"], (7.0, 7.0, 4.0), (-3.5, 2.5, T), bevel=0.8)
    ic(g, m, (4.9, 3.9, 1.5), 4.5, 3.0, T, legs=(4, 1.27))
    box(g, m["pot_blue"], (3.2, 3.2, 1.6), (5.0, -4.5, T), bevel=0.3)
    for x in (-6.0, -2.0):
        box(g, m["ceramic"], (3.2, 1.6, 1.3), (x, -5.0, T), bevel=0.1)
    for sx in (-1, 1):
        for sy in (-1, 1):
            box(g, m["gold"], (2.2, 2.2, 0.05), (sx * (L / 2 - 1.7), sy * (W / 2 - 1.9), T))
    return g


def pcf8574(parent, m):
    """PCF8574 key expander: 40 x 18 mm, address jumpers in the middle."""
    g = group(parent, "PCF8574")
    L, W, T = 40.0, 18.0, 1.6
    box(g, m["pcb_blue"], (L, W, T), (0, 0, 0), bevel=0.2)
    ic(g, m, (10.0, 4.0, 1.5), -4.0, 3.0, T, legs=(8, 1.27), text="PCF8574")
    for i in range(3):
        x = 5.5 + i * 3.0
        box(g, m["plastic"], (2.5, 7.6, 2.5), (x, -3.5, T), bevel=0.2)
        box(g, m["jumper"], (2.4, 5.0, 6.0), (x, -2.2, T + 2.5), bevel=0.3)
    header_row(g, m, 5, -L / 2 + 1.5, 0.0, T, along="y", down=False, length=5.0, strip=True)
    pads(g, m, 5, L / 2 - 1.5, 0.0, T, along="y", size=(1.5, 1.5))
    for x, y in ((-12.0, -5.5), (-9.0, -5.5), (-6.0, -5.5)):
        smd(g, m, x, y, T, "res", False)
    return g


def slide(parent, m):
    """SS12D00 slide switch, its actuator towards +y."""
    g = group(parent, "Slide switch")
    box(g, m["steel"], (8.6, 3.6, 3.5), (0, 0, -1.75), bevel=0.2)
    box(g, m["plastic"], (2.0, 4.0, 1.8), (0.8, 3.4, -0.9), bevel=0.3)
    return g


BUILDERS = {
    "s3": esp32_s3_devkitc, "c3": esp32_c3_supermini, "c3_hanging": esp32_c3_supermini,
    "pn5180": pn5180, "oled": oled, "touch": touch, "ws2812": ws2812, "switch": tact_switch,
    "sht40": sht40, "buzzer": buzzer, "cell": cell, "tp4056": tp4056, "mt3608": mt3608,
    "buck": buck, "pcf8574": pcf8574, "slide": slide,
}


def place(parent, m, info):
    """Build one recorded part and put it in its place in the case."""
    kind = info["kind"]
    obj = BUILDERS[kind](parent, m)
    x, y, z = info["x"], info["y"], info["z"]
    if kind in {"s3", "c3"}:
        obj.location = (x, y, z)
        if info.get("direction", 1) < 0:
            obj.rotation_euler = (0, 0, math.pi)
    elif kind == "c3_hanging":
        obj.location = (x, y, z)
        obj.rotation_euler = (math.pi, 0, math.pi / 2)
    elif kind == "pn5180":
        obj.location = (x, y, z)
        obj.rotation_euler = (math.pi, 0, 0)
    elif kind == "oled":
        obj.location = (x, y, z - 3.0)
    elif kind == "touch":
        obj.location = (x, y, z - 5.6)
    elif kind == "ws2812":
        obj.location = (x, y, z - 2.6)
    elif kind == "sht40":
        obj.location = (x, y + 0.2, z)
        obj.rotation_euler = (math.pi / 2, 0, 0)
    elif kind == "tp4056":
        obj.location = (x, y, z)
        obj.rotation_euler = (0, 0, math.pi)
    elif kind == "slide":
        obj.location = (x, y - 3.4, z)
    else:
        obj.location = (x, y, z)
    return obj
