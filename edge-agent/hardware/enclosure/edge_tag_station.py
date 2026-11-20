"""Printable enclosure for the Edge NFC kit: ESP32-C3 SuperMini + PN5180 reader.

A low bar that lies on the desk. The reader's antenna sits directly under the
top face, below the ring mark; the USB-C socket faces the back. Two printed
parts: the shell (printed top face down, no supports) and a base plate held by
four M2.5 x 8 self-tapping screws. The ring mark is also exported on its own,
for printers that can fill it with a second colour.

    uv run --no-project --python 3.12 --with build123d python edge_tag_station.py

writes STL and STEP files to ./out.

Every board dimension below is a catalogue figure, not a measurement of the
owner's boards. Measure with calipers and correct the BOARDS block before
printing: generic PN5180 modules are sold as 69-70 x 37-39 mm and the position
of the antenna on them is assumed.
"""

import json
from pathlib import Path

from build123d import (
    Axis,
    Box,
    Circle,
    Cylinder,
    Pos,
    RectangleRounded,
    Rot,
    chamfer,
    export_step,
    export_stl,
    extrude,
    loft,
)

# --- BOARDS (catalogue values, verify) --------------------------------------
PN_L, PN_W, PN_T = 70.0, 39.0, 1.6          # PN5180 module outline and PCB thickness
PN_ANTENNA_FROM_FAR_END = 21.0              # antenna centre, measured from the end without the header
ESP_L, ESP_W, ESP_T = 22.52, 18.0, 1.2      # ESP32-C3 SuperMini outline and PCB thickness
USB_C_AXIS_BELOW_PCB = 1.63                 # socket centre below the PCB face it is soldered to

# --- ENCLOSURE --------------------------------------------------------------
FIT = 0.4                                   # clearance around a board
WALL, TOP, BASE = 2.0, 1.2, 2.0
INNER_H = 12.0                              # between the base plate and the top wall
IN_L, IN_W = 112.0, 46.0                    # interior footprint
CORNER = 8.0
ESP_DROP = 1.0                              # the ESP hangs this far below the top wall, for the plug
USB_W, USB_H = 13.0, 7.0                    # opening for a USB-C plug with its overmould
POST_D, POST_HOLE = 6.5, 2.1                # screw posts for M2.5 self-tapping screws
SCREW_CLEAR, SCREW_HEAD = 2.9, 5.2
RIB = 1.2                                   # locating ribs around the boards
RING_D, RING_W, MARK_DEPTH = 30.0, 1.4, 0.4
LED_SKIN = 0.4                              # top wall left above the ESP's LED so it shines through
FOOT_D, FOOT_DEPTH = 8.5, 0.6
PORT_CHAMFER = 0.8                          # 45-degree flare on the outer edge of an opening

OUT_L, OUT_W = IN_L + 2 * WALL, IN_W + 2 * WALL
H = BASE + INNER_H + TOP
Z_CEILING = H - TOP                         # inner face of the top wall


def at(x, y):
    """Interior coordinates (origin in the front-left inner corner) to model coordinates."""
    return x - IN_L / 2, y - IN_W / 2


# Where things sit, in interior coordinates.
POSTS = [at(4.25, 4.25), at(4.25, IN_W - 4.25), at(IN_L - 4.25, 4.25), at(IN_L - 4.25, IN_W - 4.25)]
ESP_X0, ESP_Y1 = 9.0, IN_W - 0.2            # left edge, and the USB edge against the back wall
ESP_CX, ESP_CY = at(ESP_X0 + FIT + ESP_W / 2, ESP_Y1 - ESP_L / 2)
PN_X0 = 30.0
PN_CX, PN_CY = at(PN_X0 + FIT + PN_L / 2, IN_W / 2)
ANTENNA_X, ANTENNA_Y = at(PN_X0 + FIT + PN_L - PN_ANTENNA_FROM_FAR_END, IN_W / 2)


def port_cutter(width, height, depth, chamfer=PORT_CHAMFER, radius=None):
    """An opening `depth` deep along +z, flared at its outer end (z = depth).

    A stadium unless `radius` is given. The flare guides a plug in and gives the
    opening a chamfered edge instead of a sharp cut.
    """
    r = min(width, height) / 2 - 0.01 if radius is None else radius
    grow = chamfer + 0.5
    hole = extrude(RectangleRounded(width, height, r), depth)
    flare = loft([
        Pos(0, 0, depth - chamfer) * RectangleRounded(width, height, r),
        Pos(0, 0, depth + 0.5) * RectangleRounded(width + 2 * grow, height + 2 * grow, r + grow),
    ])
    return hole + flare


def slab(length, width, height, radius, z0=0.0):
    return Pos(0, 0, z0) * extrude(RectangleRounded(length, width, radius), height)


def frame(cx, cy, length, width, height, z_top):
    """Four corner brackets that locate a board against the top wall."""
    parts = None
    arm = 6.0
    for sx in (-1, 1):
        for sy in (-1, 1):
            x_edge = cx + sx * (length / 2 + FIT + RIB / 2)
            y_edge = cy + sy * (width / 2 + FIT + RIB / 2)
            along_y = Pos(x_edge, cy + sy * (width / 2 + FIT - arm / 2 + RIB / 2), z_top - height / 2) * Box(RIB, arm + RIB, height)
            along_x = Pos(cx + sx * (length / 2 + FIT - arm / 2 + RIB / 2), y_edge, z_top - height / 2) * Box(arm + RIB, RIB, height)
            parts = along_y + along_x if parts is None else parts + along_y + along_x
    return parts


def build_shell():
    outer = slab(OUT_L, OUT_W, H, CORNER)
    outer = chamfer(outer.edges().group_by(Axis.Z)[-1], 1.2)
    shell = outer - slab(IN_L, IN_W, Z_CEILING, CORNER - WALL)

    for x, y in POSTS:
        shell += Pos(x, y, BASE + INNER_H / 2) * Cylinder(POST_D / 2, INNER_H)
        shell -= Pos(x, y, BASE + 4.5) * Cylinder(POST_HOLE / 2, 9.0)

    # The reader lies against the top wall; the ESP hangs a little lower on two rails.
    shell += frame(PN_CX, PN_CY, PN_L, PN_W, 3.0, Z_CEILING)
    for dx in (-ESP_W / 2 + 1.0, ESP_W / 2 - 1.0):
        shell += Pos(ESP_CX + dx, ESP_CY - 2.0, Z_CEILING - ESP_DROP / 2) * Box(1.2, ESP_L - 6.0, ESP_DROP)
    shell += frame(ESP_CX, ESP_CY - 0.6, ESP_W, ESP_L - 1.2, ESP_DROP + ESP_T + 1.0, Z_CEILING)

    # USB-C plug through the back wall, level with the socket.
    usb_z = Z_CEILING - ESP_DROP - ESP_T - USB_C_AXIS_BELOW_PCB
    shell -= Pos(ESP_CX, IN_W / 2 - 1.0, usb_z) * Rot(-90, 0, 0) * port_cutter(USB_W, USB_H, WALL + 1.0)

    # A thin spot above the ESP lets its LED show; a ring marks the antenna.
    shell -= Pos(ESP_CX, ESP_CY - 4.0, Z_CEILING + (TOP - LED_SKIN) / 2) * Cylinder(2.5, TOP - LED_SKIN)
    ring = extrude(Circle(RING_D / 2) - Circle(RING_D / 2 - RING_W), MARK_DEPTH)
    dot = extrude(Circle(1.6), MARK_DEPTH)
    shell -= Pos(ANTENNA_X, ANTENNA_Y, H - MARK_DEPTH) * (ring + dot)
    return shell


def build_base():
    base = slab(IN_L - 0.5, IN_W - 0.5, BASE, CORNER - WALL - 0.25)
    for x, y in POSTS:
        base -= Pos(x, y, BASE / 2) * Cylinder(SCREW_CLEAR / 2, BASE)
        base -= Pos(x, y, 0.6) * Cylinder(SCREW_HEAD / 2, 1.2)
    # Pillars press the boards up against the shell.
    pn_pillar = Z_CEILING - PN_T - 0.3 - BASE
    for sx in (-1, 1):
        for sy in (-1, 1):
            base += Pos(PN_CX + sx * (PN_L / 2 - 3.0), PN_CY + sy * (PN_W / 2 - 3.0), BASE + pn_pillar / 2) * Cylinder(2.0, pn_pillar)
    esp_pillar = Z_CEILING - ESP_DROP - ESP_T - 0.3 - BASE
    for sx in (-1, 1):
        base += Pos(ESP_CX + sx * (ESP_W / 2 - 1.6), ESP_CY - ESP_L / 2 + 1.6, BASE + esp_pillar / 2) * Cylinder(1.2, esp_pillar)
    for sx in (-1, 1):
        for sy in (-1, 1):
            base -= Pos(sx * (IN_L / 2 - 16.0), sy * (IN_W / 2 - 9.0), FOOT_DEPTH / 2) * Cylinder(FOOT_D / 2, FOOT_DEPTH)
    return base


def build_mark():
    """The ring and dot as a body of their own: an inlay for a two-colour print."""
    ring = extrude(Circle(RING_D / 2) - Circle(RING_D / 2 - RING_W), MARK_DEPTH)
    dot = extrude(Circle(1.6), MARK_DEPTH)
    return Pos(ANTENNA_X, ANTENNA_Y, H - MARK_DEPTH) * (ring + dot)


def build_boards():
    """Stand-ins for the boards, for looking at the assembly only."""
    reader = Pos(PN_CX, PN_CY, Z_CEILING - PN_T / 2) * Box(PN_L, PN_W, PN_T)
    esp = Pos(ESP_CX, ESP_CY, Z_CEILING - ESP_DROP - ESP_T / 2) * Box(ESP_W, ESP_L, ESP_T)
    socket_z = Z_CEILING - ESP_DROP - ESP_T - USB_C_AXIS_BELOW_PCB
    esp += Pos(ESP_CX, ESP_CY + ESP_L / 2 - 3.2, socket_z) * Box(8.94, 7.3, 3.26)
    return reader, esp


if __name__ == "__main__":
    out = Path(__file__).parent / "out"
    out.mkdir(exist_ok=True)
    shell, base = build_shell(), build_base()
    reader, esp = build_boards()
    export_stl(shell, str(out / "edge_tag_station_shell.stl"))
    export_stl(base, str(out / "edge_tag_station_base.stl"))
    export_stl(build_mark(), str(out / "edge_tag_station_mark.stl"))
    export_stl(reader, str(out / "preview_reader_board.stl"))
    export_stl(esp, str(out / "preview_esp_board.stl"))
    export_step(shell, str(out / "edge_tag_station_shell.step"))
    export_step(base, str(out / "edge_tag_station_base.step"))
    # Where the renderer puts the boards (render_parts.py): the reader's top face
    # against the top wall, the ESP turned with its USB end to the back wall.
    (out / "kit.json").write_text(json.dumps({
        "top": H, "ceiling": Z_CEILING,
        "inside": [
            {"kind": "pn5180", "x": PN_CX, "y": PN_CY, "z": Z_CEILING},
            {"kind": "c3_hanging", "x": ESP_CX, "y": ESP_CY, "z": Z_CEILING - ESP_DROP},
        ],
    }, indent=2), encoding="utf-8")
    print("outer size: %.1f x %.1f x %.1f mm" % (OUT_L, OUT_W, H))
    print("shell volume: %.1f cm3, base volume: %.1f cm3" % (shell.volume / 1000, base.volume / 1000))
    print("shell is one solid:", len(shell.solids()) == 1, "| base is one solid:", len(base.solids()) == 1)
