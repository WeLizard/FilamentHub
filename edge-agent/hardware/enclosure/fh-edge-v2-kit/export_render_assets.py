"""Meshes of the supplied ESP32-C3 model for the pictures, one file per material.

    uv run --no-project --python 3.12 --with cadquery python export_render_assets.py

Reads CAD/ESP32-C3-positioned.brep (run build_model.py first) and writes
render/esp-*.stl in the assembly's own coordinates. The board is the real
supplied CAD model, so its LEDs sit exactly under the light pipes; the split
follows the colours of the review assembly in build_model.py.
"""
from pathlib import Path

import cadquery as cq

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "render"
OUT.mkdir(exist_ok=True)

solids = cq.Shape.importBrep(str(ROOT / "CAD" / "ESP32-C3-positioned.brep")).Solids()
groups = {"pcb": [], "metal": [], "led-red": [], "led-blue": [], "copper": [], "dark": []}
for index, solid in enumerate(solids):
    if index == 0:
        groups["pcb"].append(solid)
    elif index in (59, 60):
        groups["led-red"].append(solid)
    elif index in (61, 62):
        groups["led-blue"].append(solid)
    elif index == 116:
        groups["copper"].append(solid)
    elif 72 <= index <= 115:
        groups["metal"].append(solid)
    else:
        groups["dark"].append(solid)
for name, members in groups.items():
    cq.exporters.export(
        cq.Compound.makeCompound(members), str(OUT / f"esp-{name}.stl"),
        tolerance=0.03, angularTolerance=0.2,
    )
    print(name, len(members))
