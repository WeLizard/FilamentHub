"""Read the exported STEP files back and record what a slicer or CAD will see.

    uv run --no-project --python 3.12 --with cadquery python check_step.py
"""
import json
from pathlib import Path

import cadquery as cq

ROOT = Path(__file__).resolve().parent
NAMES = (
    "fh-edge-kit-shell.step", "fh-edge-kit-base.step", "fh-edge-kit-mark.step",
    "FH-Edge-v2-PRINT.step", "FH-Edge-v2-assembly.step",
)
result = {}
for name in NAMES:
    shape = cq.importers.importStep(str(ROOT / "CAD" / name)).val()
    box = shape.BoundingBox()
    result[name] = {
        "valid": shape.isValid(),
        "solids": len(shape.Solids()),
        "bounds_mm": [box.xmin, box.xmax, box.ymin, box.ymax, box.zmin, box.zmax],
    }
# The print set: the shell with the mark in register, the lid and two light
# pipes beside it, everything on the bed and nothing touching anything else.
solids = cq.importers.importStep(str(ROOT / "CAD" / "FH-Edge-v2-PRINT.step")).val().Solids()
solids.sort(key=lambda solid: -solid.Volume())
shell = solids[0]
inside = lambda solid: abs(solid.BoundingBox().ymin) < 25.1 and abs(solid.BoundingBox().ymax) < 25.1
mark = [solid for solid in solids[1:] if inside(solid)]
others = [solid for solid in solids[1:] if not inside(solid)]
result["FH-Edge-v2-PRINT.step"].update(
    mark_solids=len(mark),
    mark_bottom_z_mm=min(solid.BoundingBox().zmin for solid in mark),
    mark_top_z_mm=max(solid.BoundingBox().zmax for solid in mark),
    mark_overlap_with_shell_mm3=sum(shell.intersect(solid).Volume() for solid in mark),
    other_parts=len(others),
    other_parts_bottom_z_mm=[round(solid.BoundingBox().zmin, 6) for solid in others],
    other_parts_overlap_with_shell_mm3=sum(shell.intersect(solid).Volume() for solid in others),
)
(ROOT / "step_roundtrip.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
print(json.dumps(result["FH-Edge-v2-PRINT.step"], indent=2))
