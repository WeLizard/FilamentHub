"""Pack the printed parts into one 3MF for the slicer.

    python make_print_3mf.py

Reads ./STL (run build_model.py first) and writes FH-Edge-v2-PRINT.3mf: the
shell with the FilamentHub mark as ONE object made of two parts, so the mark
can be given its own filament, and the lid and two light pipes as objects
beside it. Everything lies as it is printed. Plain 3MF core, no slicer
settings: filaments, colours and print settings are chosen in the slicer.
"""
import struct
import zipfile
from pathlib import Path
from xml.sax.saxutils import quoteattr

ROOT = Path(__file__).resolve().parent
STL = ROOT / "STL"
OUT = ROOT / "FH-Edge-v2-PRINT.3mf"
# The layout of build_model.py's print set, moved onto the bed.
BED_X, BED_Y = 90.0, 60.0
LID_Y, PIPE_Y = 58.0, -34.0
PIPES = (("PWR", -6.0), ("IO8", 6.0))


def read_stl(path):
    """Vertices and triangles of a binary STL, with shared vertices merged."""
    data = path.read_bytes()
    count = struct.unpack_from("<I", data, 80)[0]
    if len(data) != 84 + 50 * count:
        raise ValueError(f"{path.name} is not a binary STL")
    index, vertices, triangles = {}, [], []
    for n in range(count):
        corners = struct.unpack_from("<9f", data, 84 + 50 * n + 12)
        triangle = []
        for k in range(3):
            key = tuple(round(value, 5) for value in corners[3 * k : 3 * k + 3])
            if key not in index:
                index[key] = len(vertices)
                vertices.append(key)
            triangle.append(index[key])
        if len(set(triangle)) == 3:
            triangles.append(triangle)
    return vertices, triangles


def mesh_object(number, name, path):
    vertices, triangles = read_stl(path)
    lines = [f'<object id="{number}" type="model" name={quoteattr(name)}><mesh><vertices>']
    lines += [f'<vertex x="{x:.5f}" y="{y:.5f}" z="{z:.5f}"/>' for x, y, z in vertices]
    lines.append("</vertices><triangles>")
    lines += [f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in triangles]
    lines.append("</triangles></mesh></object>")
    return "\n".join(lines)


def place(x, y):
    return f"1 0 0 0 1 0 0 0 1 {BED_X + x:.3f} {BED_Y + y:.3f} 0"


def main():
    objects = [
        mesh_object(1, "shell", STL / "fh-edge-kit-shell.stl"),
        mesh_object(2, "FilamentHub mark", STL / "fh-edge-kit-mark.stl"),
        '<object id="3" type="model" name="FH Edge shell with mark"><components>'
        '<component objectid="1"/><component objectid="2"/></components></object>',
        mesh_object(4, "FH Edge lid", STL / "fh-edge-kit-base.stl"),
    ]
    items = [f'<item objectid="3" transform="{place(0, 0)}"/>',
             f'<item objectid="4" transform="{place(0, LID_Y)}"/>']
    for number, (name, x) in enumerate(PIPES, start=5):
        objects.append(mesh_object(number, f"FH Edge light pipe {name}", STL / f"fh-edge-kit-lightpipe-{name}.stl"))
        items.append(f'<item objectid="{number}" transform="{place(x, PIPE_Y)}"/>')
    model = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<model unit="millimeter" xml:lang="en-US" '
        'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">\n'
        '<metadata name="Title">FH Edge v2 print set</metadata>\n'
        '<metadata name="Designer">FilamentHub</metadata>\n'
        "<resources>\n" + "\n".join(objects) + "\n</resources>\n"
        "<build>\n" + "\n".join(items) + "\n</build>\n</model>\n"
    )
    types = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>'
        "</Types>\n"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Target="/3D/3dmodel.model" Id="rel0" '
        'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>'
        "</Relationships>\n"
    )
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as package:
        package.writestr("[Content_Types].xml", types)
        package.writestr("_rels/.rels", rels)
        package.writestr("3D/3dmodel.model", model)
    print(OUT.name, OUT.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
