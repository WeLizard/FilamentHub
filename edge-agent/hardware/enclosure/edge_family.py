"""Printable enclosures for the designed Edge builds, one per ready build.

Each case is made for exactly the parts of its build on the site (the presets
in frontend/src/components/edge/edgeBuilds.ts): a screen window only where the
build has a screen, an LED window and buzzer holes only with light and sound, a
cell bay, charging port and switch only on battery, a 24 V inlet only on
printer power, a vented pocket only with the climate sensor. The C3 kit keeps
its own case in edge_tag_station.py.

The FilamentHub mark sits over the reader's antenna, inlaid flush: print it in
a second colour, or leave it as an engraving.

    uv run --no-project --python 3.12 --with build123d python edge_family.py

writes STL and STEP files and preview bodies to ./out.

Every part size is a catalogue figure. Measure your parts and correct the
values below before printing; none of these cases has been printed yet.
Small modules (charger, step-up, step-down, buzzer, expander, sensor) are held
with double-sided foam tape; boards and screens sit in printed frames.
"""

import json
from pathlib import Path

from build123d import (
    Axis,
    Box,
    Cylinder,
    Pos,
    Rot,
    chamfer,
    export_step,
    export_stl,
    extrude,
    fillet,
    import_svg,
)

from edge_tag_station import (
    FIT,
    FOOT_D,
    FOOT_DEPTH,
    LED_SKIN,
    MARK_DEPTH,
    PN_ANTENNA_FROM_FAR_END,
    PN_L,
    PN_T,
    PN_W,
    ESP_L,
    ESP_T,
    ESP_W,
    POST_D,
    POST_HOLE,
    SCREW_CLEAR,
    SCREW_HEAD,
    frame,
    slab,
)

# --- BOARDS AND PARTS (catalogue values, verify) ----------------------------
S3_L, S3_W, S3_T = 69.0, 25.4, 1.6          # ESP32-S3-DevKitC-1 outline and PCB thickness
S3_SPINE_H = 9.0                            # underside of the board above the base: room for its header pins
S3_USB_ABOVE_PCB = 1.63                     # USB-C axis above the board's top face
S3_USB_SLOT = (23.0, 7.5)                   # one slot for both USB-C sockets
OLED_L, OLED_W, OLED_PCB = 35.4, 33.5, 1.2  # 1.3" SH1106 module, its long side along the device
OLED_GLASS = 1.8
OLED_VIEW = (31.0, 16.0)                    # window along x and y
TOUCH_PCB = (86.0, 50.0)                    # 2.8" ILI9341 + XPT2046 module
TOUCH_STACK = 5.6                           # glass and backlight on the board
TOUCH_VIEW = (58.0, 44.0)
TOUCH_VIEW_SHIFT = -4.0                     # the glass sits off the board's centre, away from the header
SHT40_W = 25.4                              # sensor board, stood on edge against the vented wall
KEY_HOLE, KEY_CAP, KEY_CAP_ABOVE = 14.6, 14.0, 2.0
SWITCH, SWITCH_H = 12.4, 7.3                # pocket for a 12 x 12 x 7.3 mm tactile switch
SWITCH_LEG_PITCH = 12.5
CAP_SOCKET_D, CAP_SOCKET_DEPTH = 3.8, 2.5   # the cap presses onto the switch's stem
LED_TUBE_R = 5.2                            # round WS2812B boards up to 10 mm
HOLDER_L, HOLDER_W, HOLDER_H = 77.0, 21.0, 19.0  # single 18650 holder
TP4056 = (28.0, 17.0)
USB_PLUG = (13.0, 7.0)                      # a USB-C plug with its overmould

WALL, TOP, BASE = 2.0, 1.6, 2.0
EDGE_RADIUS = 3.0                           # rounded top edges; more would thin the wall below 1.2 mm
PLINTH, REVEAL = 1.6, 1.2                   # the dark base stands below the shell, set in: a shadow line

# The FilamentHub mark doubles as the antenna target: its outer arc is the ring
# a spool is held to. Inlaid flush, it can be printed in a second colour.
LOGO = Path(__file__).parent / "filamenthub-mark.svg"
LOGO_ARC = 288.0                            # the outer arc's diameter in the SVG's units
LOGO_RING_D = 32.0


def logo_mark(depth):
    # The SVG import carries a placement (a y-flip and an offset) that scale()
    # keeps, so centre on the scaled inner ring rather than on raw coordinates.
    faces = [face.scale(LOGO_RING_D / LOGO_ARC) for face in import_svg(str(LOGO))]
    centre = faces[0].bounding_box().center()
    body = None
    for face in faces:
        solid = extrude(Pos(-centre.X, -centre.Y, -centre.Z) * face, depth)
        body = solid if body is None else body + solid
    return body


class Case:
    """A hollow box open at the bottom; the base plate drops into it."""

    def __init__(self, in_l, in_w, inner_h, corner):
        self.in_l, self.in_w, self.inner_h, self.corner = in_l, in_w, inner_h, corner
        self.h = BASE + inner_h + TOP
        self.ceiling = self.h - TOP
        outer = slab(in_l + 2 * WALL, in_w + 2 * WALL, self.h, corner)
        outer = fillet(outer.edges().group_by(Axis.Z)[-1], EDGE_RADIUS)
        outer = chamfer(outer.edges().group_by(Axis.Z)[0], 0.6)  # no elephant's foot on the first layer
        self.shell = outer - slab(in_l, in_w, self.ceiling, corner - WALL)
        self.base = slab(in_l - 0.5, in_w - 0.5, BASE, corner - WALL - 0.25)
        self.base += slab(in_l + 2 * WALL - 2 * REVEAL, in_w + 2 * WALL - 2 * REVEAL, PLINTH, corner - REVEAL, z0=-PLINTH)
        self.leds = []
        self.screen = None
        self.marks = []
        self.posts = []
        self.preview_caps = []
        self.preview_cell = None
        self.preview_screen = None
        self.view = None

    def add_posts(self, points):
        self.posts += points
        for x, y in points:
            self.shell += Pos(x, y, BASE + self.inner_h / 2) * Cylinder(POST_D / 2, self.inner_h)
            self.shell -= Pos(x, y, BASE + 4.5) * Cylinder(POST_HOLE / 2, 9.0)
            self.base -= Pos(x, y, (BASE - PLINTH) / 2) * Cylinder(SCREW_CLEAR / 2, BASE + PLINTH + 0.2)
            self.base -= Pos(x, y, -PLINTH + (PLINTH + 0.6) / 2 - 0.1) * Cylinder(SCREW_HEAD / 2, PLINTH + 0.8)

    def corner_posts(self, inset=4.25):
        dx, dy = self.in_l / 2 - inset, self.in_w / 2 - inset
        self.add_posts([(sx * dx, sy * dy) for sx in (-1, 1) for sy in (-1, 1)])

    def reader(self, cx, cy, pillars=True):
        """Reader against the top wall, header towards -x; the mark sits over the antenna."""
        self.shell += frame(cx, cy, PN_L, PN_W, 3.0, self.ceiling)
        ax = cx + PN_L / 2 - PN_ANTENNA_FROM_FAR_END
        mark = Pos(ax, cy, self.h - MARK_DEPTH) * logo_mark(MARK_DEPTH)
        self.shell -= mark
        self.marks.append(mark)
        if pillars:
            height = self.ceiling - PN_T - 0.3 - BASE
            for sx in (-1, 1):
                for sy in (-1, 1):
                    self.base += Pos(cx + sx * (PN_L / 2 - 3.0), cy + sy * (PN_W / 2 - 3.0), BASE + height / 2) * Cylinder(2.0, height)
        self.preview_reader = Pos(cx, cy, self.ceiling - PN_T / 2) * Box(PN_L, PN_W, PN_T)

    def oled(self, cx, cy, window=True):
        """The glass lies against the top wall; brackets hold the board's outline."""
        self.shell += frame(cx, cy, OLED_L, OLED_W, OLED_GLASS + OLED_PCB + 0.8, self.ceiling)
        self.screen, self.view = (cx, cy), OLED_VIEW
        if window:
            vx, vy = OLED_VIEW
            self.shell -= Pos(cx, cy, self.ceiling + TOP / 2) * Box(vx, vy, TOP + 0.4)
            self.shell -= Pos(cx, cy, self.h) * Box(vx + 3.0, vy + 3.0, 1.0)
        self.preview_screen = (
            Pos(cx, cy, self.ceiling - OLED_GLASS - OLED_PCB / 2) * Box(OLED_L, OLED_W, OLED_PCB)
            + Pos(cx, cy, self.ceiling - OLED_GLASS / 2) * Box(OLED_L - 1.0, OLED_VIEW[1] + 4.0, OLED_GLASS)
        )

    def touch(self, cx, cy):
        """The touch screen's glass against the top wall, touched through the window."""
        self.shell += frame(cx, cy, TOUCH_PCB[0], TOUCH_PCB[1], TOUCH_STACK + 0.8, self.ceiling)
        vx, vy = TOUCH_VIEW
        wx = cx + TOUCH_VIEW_SHIFT
        self.shell -= Pos(wx, cy, self.ceiling + TOP / 2) * Box(vx, vy, TOP + 0.4)
        self.shell -= Pos(wx, cy, self.h) * Box(vx + 3.0, vy + 3.0, 1.0)
        self.screen, self.view = (wx, cy), TOUCH_VIEW
        self.preview_screen = Pos(wx, cy, self.ceiling - TOUCH_STACK / 2) * Box(vx + 6.0, vy + 4.0, TOUCH_STACK)

    def led(self, x, y):
        """A thin skin over a round LED board: the light shows through the print."""
        self.leds.append((x, y))
        tube = Cylinder(LED_TUBE_R + 1.2, 3.0) - Cylinder(LED_TUBE_R, 3.0)
        self.shell += Pos(x, y, self.ceiling - 1.5) * tube
        self.shell -= Pos(x, y, self.ceiling + (TOP - LED_SKIN) / 2) * Cylinder(2.5, TOP - LED_SKIN)

    def key(self, x, y):
        """A cup for a tactile switch dropped in from the top, its cap pressed on the stem."""
        floor_z = self.ceiling + 0.3 + CAP_SOCKET_DEPTH - SWITCH_H
        cup_h = self.ceiling - floor_z + 1.2
        cup = Pos(x, y, self.ceiling - cup_h / 2) * Box(SWITCH + 2.4, SWITCH + 2.4, cup_h)
        cup -= Pos(x, y, (self.ceiling + floor_z) / 2 + 0.1) * Box(SWITCH, SWITCH, self.ceiling - floor_z + 0.2)
        # The switch's legs run down its sides and out through the floor.
        for sx in (-1, 1):
            cup -= Pos(x + sx * SWITCH_LEG_PITCH / 2, y, self.ceiling - cup_h / 2) * Box(1.4, 7.0, cup_h + 0.2)
        self.shell += cup
        self.shell -= Pos(x, y, self.ceiling + TOP / 2) * Box(KEY_HOLE, KEY_HOLE, TOP + 0.4)
        return Pos(x, y, self.ceiling + 0.3) * keycap()

    def board(self, mcu, x_usb_wall, direction):
        """The board on a spine of the base between its pin rows, USB end against an end wall."""
        length, width, pcb = (S3_L, S3_W, S3_T) if mcu == "s3" else (ESP_L, ESP_W, ESP_T)
        x0 = x_usb_wall - direction * (length / 2 + 0.3)
        self.base += Pos(x0, 0, BASE + S3_SPINE_H / 2) * Box(length - 6.0, 4.0, S3_SPINE_H)
        usb_z = BASE + S3_SPINE_H + pcb + S3_USB_ABOVE_PCB
        slot = S3_USB_SLOT if mcu == "s3" else USB_PLUG  # the S3 has two sockets side by side
        self.shell -= Pos(x_usb_wall + direction * WALL / 2, 0, usb_z) * Box(WALL + 2.0, *slot)
        return x0

    def climate(self, x):
        """Slots in the back wall and two guides that stand the sensor board against them."""
        z = BASE + 9.0
        for i in range(-2, 3):
            self.shell -= Pos(x + 3.2 * i, self.in_w / 2 + WALL / 2, z) * Box(1.4, WALL + 2.0, 9.0)
        for sx in (-1, 1):
            self.shell += Pos(x + sx * (SHT40_W / 2 + FIT + 0.6), self.in_w / 2 - 1.5, z) * Box(1.2, 3.0, 12.0)

    def buzzer(self, x, y):
        """Sound holes in the base under the buzzer module."""
        for i in (-1, 0, 1):
            for j in (-1, 0, 1):
                self.base -= Pos(x + 4.0 * i, y + 4.0 * j, (BASE - PLINTH) / 2) * Cylinder(1.0, BASE + PLINTH + 0.2)

    def feet(self, dx, dy):
        for sx in (-1, 1):
            for sy in (-1, 1):
                self.base -= Pos(sx * dx, sy * dy, -PLINTH + FOOT_DEPTH / 2 - 0.05) * Cylinder(FOOT_D / 2, FOOT_DEPTH + 0.1)

    def side_hole(self, x, wall_sign, z, width, height):
        """A rectangular opening in a long wall (+1 back, -1 front)."""
        self.shell -= Pos(x, wall_sign * (self.in_w / 2 + WALL / 2), z) * Box(width, WALL + 2.0, height)

    def end_hole(self, y, wall_sign, z, width, height):
        """A rectangular opening in an end wall (+1 right, -1 left)."""
        self.shell -= Pos(wall_sign * (self.in_l / 2 + WALL / 2), y, z) * Box(WALL + 2.0, width, height)


def keycap():
    """A square cap with a socket for the switch's stem; printed top face down."""
    cap_h = KEY_CAP_ABOVE + TOP - 0.3
    cap = Pos(0, 0, cap_h / 2) * Box(KEY_CAP, KEY_CAP, cap_h)
    cap = chamfer(cap.edges().group_by(Axis.Z)[-1], 0.6)
    cap -= Pos(0, 0, CAP_SOCKET_DEPTH / 2) * Cylinder(CAP_SOCKET_D / 2, CAP_SOCKET_DEPTH)
    return cap


# --- THE BUILDS ---------------------------------------------------------------
# One case per ready build on the site, made for exactly the parts in its list
# (frontend/src/components/edge/edgeBuilds.ts, EDGE_PRESETS). A part that is
# not in a build leaves no opening, frame or pocket in its case.

def tag_s3():
    """S3 · OLED · LED and buzzer · USB."""
    case = Case(128.0, 46.0, 22.0, 8.0)
    case.corner_posts()
    case.reader(-25.0, 0.0)
    case.led(18.0, 0.0)
    case.oled(40.75, 0.0)
    case.board("s3", case.in_l / 2, +1)
    case.buzzer(-40.0, 0.0)
    case.feet(case.in_l / 2 - 16.0, case.in_w / 2 - 9.0)
    return case


def battery_bay(case, x0, y0):
    """An 18650 holder between two rails on the base."""
    for y in (y0 - 0.6 - FIT, y0 + HOLDER_W + 0.6 + FIT):
        case.base += Pos(x0 + HOLDER_L / 2, y, BASE + 2.0) * Box(HOLDER_L - 10.0, 1.2, 4.0)
    case.preview_cell = Pos(x0 + HOLDER_L / 2, y0 + HOLDER_W / 2, BASE + HOLDER_H / 2) * Box(HOLDER_L, HOLDER_W, HOLDER_H)


def charger_port(case, y):
    """The TP4056 lies on the base against the front wall; its USB-C goes through it."""
    case.end_hole(y, -1, BASE + 1.0 + 1.6 + 1.63, *USB_PLUG)


def portable_s3():
    """S3 · OLED · scan key · LED and buzzer · 18650."""
    case = Case(156.0, 54.0, 23.0, 10.0)
    case.corner_posts()
    case.reader(-39.0, 0.0, pillars=False)  # the cell holder sits right under it
    case.oled(20.75, 0.0)
    case.preview_caps = [case.key(51.0, 0.0)]
    case.led(66.0, 0.0)
    case.board("s3", case.in_l / 2, +1)
    battery_bay(case, -70.0, -25.0)
    charger_port(case, 2.0 + TP4056[1] / 2)
    case.side_hole(-6.0, +1, BASE + 6.0, 9.5, 4.5)  # power switch
    case.buzzer(40.0, 20.0)
    case.feet(case.in_l / 2 - 18.0, case.in_w / 2 - 10.0)
    return case


def portable_c3():
    """C3 · LED and buzzer · 18650; no screen, no key: the switch turns it on."""
    case = Case(112.0, 54.0, 23.0, 10.0)
    case.corner_posts()
    case.reader(-15.0, 0.0, pillars=False)
    case.led(42.0, 0.0)
    case.board("c3", case.in_l / 2, +1)
    battery_bay(case, -48.0, -25.0)
    charger_port(case, 2.0 + TP4056[1] / 2)
    case.side_hole(15.0, +1, BASE + 6.0, 9.5, 4.5)
    case.buzzer(42.0, 19.0)
    case.feet(case.in_l / 2 - 16.0, case.in_w / 2 - 10.0)
    return case


def touch_s3():
    """S3 · 2.8" touch screen · LED and buzzer · USB."""
    case = Case(178.0, 56.0, 20.0, 8.0)
    case.corner_posts()
    case.reader(-50.0, 0.0)
    case.led(-8.0, 0.0)
    case.touch(42.0, 0.0)
    case.board("s3", -case.in_l / 2, -1)
    case.buzzer(60.0, 0.0)
    case.feet(case.in_l / 2 - 18.0, case.in_w / 2 - 10.0)
    return case


KEY_ROWS = (10.5, -10.5)
LED_OFFSET = 13.5
CLIP_SCREWS = 44.0


def keys_and_leds(case, columns):
    caps = []
    for y in KEY_ROWS:
        for x in columns:
            caps.append(case.key(x, y))
            case.led(x, y + (LED_OFFSET if y > 0 else -LED_OFFSET))
    case.preview_caps = caps


def clip_bosses(case, xs):
    for x in xs:
        for y in (-CLIP_SCREWS / 2, CLIP_SCREWS / 2):
            case.base += Pos(x, y, BASE + 2.5) * Cylinder(3.0, 5.0)
            case.base -= Pos(x, y, (BASE + 5.0 - PLINTH) / 2) * Cylinder(POST_HOLE / 2, BASE + 5.0 + PLINTH + 0.2)


def station_c3():
    """C3 · 8 keys with LEDs · buzzer · printer 24 V through a step-down module."""
    case = Case(168.0, 62.0, 20.0, 8.0)
    case.corner_posts()
    case.add_posts([(0.0, sy * (case.in_w / 2 - 4.25)) for sy in (-1, 1)])
    case.reader(-45.0, 0.0)
    keys_and_leds(case, (16.0, 35.0, 54.0, 73.0))
    case.board("c3", -case.in_l / 2, -1)
    # The printer's 24 V comes in through the back wall to the step-down module.
    case.shell -= Pos(-40.0, case.in_w / 2 + WALL / 2, BASE + 5.0) * Rot(90, 0, 0) * Cylinder(3.0, WALL + 2.0)
    clip_bosses(case, (-55.0, 55.0))
    case.buzzer(45.0, 0.0)
    case.feet(case.in_l / 2 - 20.0, case.in_w / 2 - 10.0)
    return case


def station_s3():
    """S3 · OLED · 8 keys with LEDs · buzzer · temperature and humidity · USB."""
    case = Case(208.0, 62.0, 20.0, 8.0)
    case.corner_posts()
    case.add_posts([(15.0, sy * (case.in_w / 2 - 4.25)) for sy in (-1, 1)])
    case.reader(-65.0, 0.0)
    case.oled(-5.25, 0.0)
    keys_and_leds(case, (31.0, 50.0, 69.0, 88.0))
    case.board("s3", -case.in_l / 2, -1)
    case.climate(-5.0)
    clip_bosses(case, (-70.0, 70.0))
    case.buzzer(60.0, 0.0)
    case.feet(case.in_l / 2 - 20.0, case.in_w / 2 - 10.0)
    return case


def clip_2020():
    """Snaps into the slot of 2020 extrusion; screws to a station's base.

    Lies on its side as exported: print it that way, the barbs then flex along
    the layers instead of across them.
    """
    length, width, plate = CLIP_SCREWS + 10.0, 14.0, 3.0
    clip = Pos(0, 0, plate / 2) * Box(length, width, plate)
    for x in (-CLIP_SCREWS / 2, CLIP_SCREWS / 2):
        clip -= Pos(x, 0, plate / 2) * Cylinder(SCREW_CLEAR / 2, plate + 0.2)
        clip -= Pos(x, 0, plate - 0.6) * Cylinder(SCREW_HEAD / 2, 1.2)
    # Neck through the 6.2 mm slot opening, then a split barb that spreads under the lips.
    neck_h, head_h = 2.2, 4.0
    clip += Pos(0, 0, -neck_h / 2) * Box(width, 5.8, neck_h)
    barb = Pos(0, 0, -neck_h - head_h / 2) * Box(width, 9.2, head_h)
    barb = chamfer(barb.edges().group_by(Axis.Z)[0].filter_by(Axis.X), 2.0)
    clip += barb
    clip -= Pos(0, 0, -neck_h - head_h / 2 + 0.5) * Box(width + 1.0, 1.6, head_h + neck_h)
    return clip


def keycap_plate(count=8):
    caps = None
    for i in range(count):
        cap = Pos((i % 4 - 1.5) * 18.0, (i // 4 - 0.5) * 18.0, 0) * keycap()
        caps = cap if caps is None else caps + cap
    return caps


BUILDS = {
    "tag-s3": tag_s3,
    "portable-s3": portable_s3,
    "portable-c3": portable_c3,
    "touch-s3": touch_s3,
    "station-c3": station_c3,
    "station-s3": station_s3,
}


if __name__ == "__main__":
    out = Path(__file__).parent / "out"
    out.mkdir(exist_ok=True)

    def save(body, name, step=False):
        # 0.02 mm is far below what a printer resolves and keeps the files small.
        export_stl(body, str(out / f"{name}.stl"), tolerance=0.02, angular_tolerance=0.2)
        if step:
            export_step(body, str(out / f"{name}.step"))
        solids = len(body.solids())
        print(f"{name}: {solids} solid{'s' if solids != 1 else ''}, {body.volume / 1000:.1f} cm3")

    def union(bodies):
        result = bodies[0]
        for body in bodies[1:]:
            result += body
        return result

    scene = {}
    for name, build in BUILDS.items():
        case = build()
        save(case.shell, f"fh-edge-{name}-shell", step=True)
        save(case.base, f"fh-edge-{name}-base", step=True)
        save(case.marks[0], f"fh-edge-{name}-mark")
        if case.preview_screen is not None:
            save(case.preview_screen, f"preview-{name}-screen")
        if case.preview_caps:
            save(union(case.preview_caps), f"preview-{name}-caps")
        print(f"{name} outer: {case.in_l + 2 * WALL:.1f} x {case.in_w + 2 * WALL:.1f} x {case.h + PLINTH:.1f} mm")
        # Where the renderer puts the lit LEDs and the screen's text.
        scene[name] = {
            "top": case.h, "ceiling": case.ceiling, "plinth": PLINTH, "length": case.in_l + 2 * WALL,
            "leds": case.leds, "screen": case.screen, "view": case.view,
        }
    save(keycap(), "fh-edge-keycap")
    save(keycap_plate(), "fh-edge-station-keycaps")
    save(clip_2020(), "fh-edge-station-clip-2020")
    (out / "scene.json").write_text(json.dumps(scene, indent=2), encoding="utf-8")
