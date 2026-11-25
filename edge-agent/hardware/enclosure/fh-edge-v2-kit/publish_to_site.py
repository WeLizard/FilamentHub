"""Copy the kit's printable files and pictures to the site, under the site's names.

    python publish_to_site.py

Run after build_model.py, make_print_3mf.py and render_site.py. Writes to
frontend/public/edge-kit/: the parts one by one, the print set, the pictures
and fh-edge-kit.zip with everything a person needs to print the case.
"""
import shutil
import zipfile
from pathlib import Path

KIT = Path(__file__).resolve().parent
SITE = KIT.parents[3] / "frontend" / "public" / "edge-kit"

FILES = {
    "STL/fh-edge-kit-shell.stl": "fh-edge-kit-shell.stl",
    "STL/fh-edge-kit-base.stl": "fh-edge-kit-base.stl",
    "STL/fh-edge-kit-mark.stl": "fh-edge-kit-mark.stl",
    "STL/fh-edge-kit-lightpipe-PWR.stl": "fh-edge-kit-lightpipe-pwr.stl",
    "STL/fh-edge-kit-lightpipe-IO8.stl": "fh-edge-kit-lightpipe-io8.stl",
    "STL/test/USB-fit-coupon.stl": "fh-edge-kit-usb-coupon.stl",
    "CAD/fh-edge-kit-shell.step": "fh-edge-kit-shell.step",
    "CAD/fh-edge-kit-base.step": "fh-edge-kit-base.step",
    "CAD/fh-edge-kit-mark.step": "fh-edge-kit-mark.step",
    "CAD/FH-Edge-v2-PRINT.step": "fh-edge-kit-print.step",
    "FH-Edge-v2-PRINT.3mf": "fh-edge-kit-print.3mf",
}
PICTURES = ("kit-front.webp", "kit-back.webp", "kit-inside.webp",
            "step-print.webp", "step-boards.webp", "step-close.webp")
# The archive: what is printed, the same parts as STEP, and how to use them.
ARCHIVE = "fh-edge-kit.zip"
ARCHIVE_EXTRA = {"README_RU.md": "README_RU.md", "preview/kit-front.webp": "kit-front.webp"}


def main():
    for source, name in FILES.items():
        shutil.copyfile(KIT / source, SITE / name)
    for name in PICTURES:
        shutil.copyfile(KIT / "preview" / name, SITE / name)
    with zipfile.ZipFile(SITE / ARCHIVE, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for source, name in {**FILES, **ARCHIVE_EXTRA}.items():
            archive.write(KIT / source, f"fh-edge-kit/{name}")
    for name in (*FILES.values(), *PICTURES, ARCHIVE):
        print(f"{(SITE / name).stat().st_size:>9}  {name}")


if __name__ == "__main__":
    main()
