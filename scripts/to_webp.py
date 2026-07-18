#!/usr/bin/env python3
"""Convert images to WebP.

Improved drop-in for converter.py: any input format, files or folders as
arguments, quality/lossless/resize control, and a size-savings report.

Examples
--------
    python to_webp.py                        # every image in this folder
    python to_webp.py shot1.png screenshots/ # specific files and/or folders
    python to_webp.py -q 92 *.png            # higher quality
    python to_webp.py --lossless ui/         # lossless (best for text/arrows)
    python to_webp.py --max-width 1600 imgs/ # downscale wide images
    python to_webp.py -r assets/             # recurse into subfolders

Notes
-----
- Output is written next to the source as <name>.webp and never overwrites an
  existing .webp unless you pass --overwrite.
- Alpha/transparency is preserved; EXIF rotation is applied.
- Animated GIFs are converted as a single (first) frame.
- Sources that are already .webp are skipped.
"""

import argparse
import os
import sys

try:
    from PIL import Image, ImageOps, features
except ImportError:
    sys.exit("Pillow is required:  pip install Pillow")

# Formats we accept as input (lowercase extensions, no dot).
INPUT_EXTS = {"png", "jpg", "jpeg", "bmp", "gif", "tif", "tiff", "ppm", "pgm"}


def human(size):
    """Bytes -> short human string (e.g. 1.6 MB)."""
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


def gather(paths, recursive):
    """Expand the given files/folders into a de-duplicated list of image files."""
    found = []
    seen = set()

    def add(fp):
        real = os.path.abspath(fp)
        ext = os.path.splitext(fp)[1].lower().lstrip(".")
        if ext in INPUT_EXTS and real not in seen:
            seen.add(real)
            found.append(fp)

    for p in paths:
        if os.path.isdir(p):
            if recursive:
                for root, _dirs, files in os.walk(p):
                    for f in files:
                        add(os.path.join(root, f))
            else:
                for f in sorted(os.listdir(p)):
                    fp = os.path.join(p, f)
                    if os.path.isfile(fp):
                        add(fp)
        elif os.path.isfile(p):
            add(p)
        else:
            print(f"Skipping {p}: not a file or folder.")
    return found


def prepare(im, max_width, max_height):
    """Apply EXIF rotation, flatten mode for WebP, and optional downscale."""
    im = ImageOps.exif_transpose(im)
    if im.mode in ("RGBA", "LA"):
        pass
    elif im.mode == "P":
        im = im.convert("RGBA" if "transparency" in im.info else "RGB")
    elif im.mode not in ("RGB", "L"):
        im = im.convert("RGB")

    if max_width or max_height:
        w, h = im.size
        limit_w = max_width or w
        limit_h = max_height or h
        if w > limit_w or h > limit_h:
            scale = min(limit_w / w, limit_h / h)
            im = im.resize((max(1, round(w * scale)), max(1, round(h * scale))),
                           Image.LANCZOS)
    return im


def main():
    parser = argparse.ArgumentParser(
        description="Convert images to WebP.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("paths", nargs="*", default=["."],
                        help="Image files and/or folders (default: current folder).")
    parser.add_argument("-q", "--quality", type=int, default=82,
                        help="WebP quality 1..100 (default 82). Under --lossless "
                             "this is the compression effort.")
    parser.add_argument("--lossless", action="store_true",
                        help="Lossless WebP — best for UI screenshots / sharp text.")
    parser.add_argument("--max-width", type=int, default=0,
                        help="Downscale so width <= N px (0 = no resize).")
    parser.add_argument("--max-height", type=int, default=0,
                        help="Downscale so height <= N px (0 = no resize).")
    parser.add_argument("--method", type=int, default=6, choices=range(0, 7),
                        metavar="0-6",
                        help="Compression effort 0..6 (default 6 = smallest/slowest).")
    parser.add_argument("-r", "--recursive", action="store_true",
                        help="Recurse into subfolders.")
    parser.add_argument("--overwrite", action="store_true",
                        help="Re-encode even if the .webp already exists.")
    args = parser.parse_args()

    if not features.check("webp"):
        sys.exit("This Pillow build has no WebP support.")
    if not 1 <= args.quality <= 100:
        sys.exit("--quality must be between 1 and 100.")

    images = gather(args.paths, args.recursive)
    if not images:
        print("No images found to convert.")
        return

    print(f"Found {len(images)} image(s) to convert"
          f"{' (lossless)' if args.lossless else f' (quality {args.quality})'}.")

    total_in = total_out = converted = skipped = failed = 0
    for src in images:
        if src.lower().endswith(".webp"):
            print(f"Skipping {src}: already WebP.")
            skipped += 1
            continue
        dst = os.path.splitext(src)[0] + ".webp"
        if os.path.exists(dst) and not args.overwrite:
            print(f"Skipping {src}: {os.path.basename(dst)} already exists "
                  f"(use --overwrite).")
            skipped += 1
            continue
        try:
            with Image.open(src) as im:
                im = prepare(im, args.max_width, args.max_height)
                im.save(dst, "WEBP", quality=args.quality,
                        lossless=args.lossless, method=args.method)
        except Exception as exc:  # noqa: BLE001 - report and continue
            print(f"FAILED {src}: {exc}")
            failed += 1
            continue

        size_in = os.path.getsize(src)
        size_out = os.path.getsize(dst)
        total_in += size_in
        total_out += size_out
        converted += 1
        pct = (1 - size_out / size_in) * 100 if size_in else 0
        print(f"  {os.path.basename(src)} -> {os.path.basename(dst)}   "
              f"{human(size_in)} -> {human(size_out)}  (-{pct:.0f}%)")

    print("-" * 48)
    print(f"Converted {converted}, skipped {skipped}, failed {failed}.")
    if converted:
        saved = (1 - total_out / total_in) * 100 if total_in else 0
        print(f"Total: {human(total_in)} -> {human(total_out)}  (-{saved:.0f}%)")


if __name__ == "__main__":
    main()
