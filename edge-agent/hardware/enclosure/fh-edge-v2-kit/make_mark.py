"""Turn the official FilamentHub mark (SVG) into the outline build_model.py inlays.

    uv run --no-project --python 3.12 --with build123d python make_mark.py

Reads source/filamenthub-mark.svg and writes source/filamenthub-mark.brep: the
mark's flat faces in the SVG's own units, upright, centred on the inner ring.
Nothing is redrawn or re-proportioned. Run it again whenever the SVG changes,
then rebuild the model. CadQuery, which builds the model, has no SVG reader and
cannot share an environment with build123d, hence the separate step.
"""
from pathlib import Path

from build123d import Compound, Pos, export_brep, import_svg

SRC = Path(__file__).resolve().parent / "source"

# The SVG import carries a placement (a y-flip and an offset); centre on the
# inner ring, the first path, so the model can place the mark by its middle.
faces = list(import_svg(str(SRC / "filamenthub-mark.svg")))
centre = faces[0].bounding_box().center()
moved = [Pos(-centre.X, -centre.Y, -centre.Z) * face for face in faces]
export_brep(Compound(children=moved), str(SRC / "filamenthub-mark.brep"))
box = Compound(children=moved).bounding_box()
print("faces", len(moved), "width", round(box.size.X, 2), "height", round(box.size.Y, 2))
