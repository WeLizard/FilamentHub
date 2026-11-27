"""The OrcaCloud listing published from the repository with each release.

The publish workflow sends ``description.md`` as the plugin's description, and
OrcaCloud shows an image given by a path as it is at the release's commit. A
listing OrcaCloud would refuse, an image path that leads nowhere, or a roadmap
picture that no longer says what the site's About page says must not reach a
release.
"""

from __future__ import annotations

import json
import re
import struct
import zlib
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent
REPOSITORY = PLUGIN.parent
# The About page's roadmap; CI runs these tests when one of them changes.
CAPABILITIES = REPOSITORY / "frontend" / "src" / "data" / "capabilities.json"
FEATURE_TEXTS = REPOSITORY / "frontend" / "src" / "locales" / "en" / "features.json"
PAGE_TEXTS = REPOSITORY / "frontend" / "src" / "locales" / "en" / "translation.json"
DESCRIPTION = PLUGIN / "description.md"
ROADMAP = PLUGIN / "listing" / "09-what-is-coming.png"
ROADMAP_TEXT_KEY = "FilamentHub-roadmap"


def _png_texts(path):
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    position, texts = 8, {}
    while position < len(data):
        (length,) = struct.unpack(">I", data[position:position + 4])
        kind = data[position + 4:position + 8]
        body = data[position + 8:position + 8 + length]
        position += 12 + length
        if kind == b"tEXt":
            key, value = body.split(b"\0", 1)
            texts[key.decode("latin-1")] = value.decode("latin-1")
        elif kind == b"iTXt":
            key, rest = body.split(b"\0", 1)
            compressed, rest = rest[0], rest[2:]
            _language, _translated, value = rest.split(b"\0", 2)
            texts[key.decode("latin-1")] = (zlib.decompress(value) if compressed else value).decode("utf-8")
    return texts


def _site_roadmap():
    """The two columns of the About page, as the gallery script draws them."""
    capabilities = json.loads(CAPABILITIES.read_text(encoding="utf-8"))
    texts = json.loads(FEATURE_TEXTS.read_text(encoding="utf-8"))
    about = json.loads(PAGE_TEXTS.read_text(encoding="utf-8"))["aboutPage"]
    return [
        [
            about[status]["title"],
            [
                texts["capabilities"]["items"][item["id"]]
                for item in capabilities["items"]
                if item["status"] == status
            ],
        ]
        for status in ("progress", "next")
    ]


def test_the_description_fits_what_orcacloud_accepts():
    text = DESCRIPTION.read_text(encoding="utf-8").strip()
    assert 100 <= len(text) <= 10000, len(text)


def test_every_image_given_by_a_path_is_in_the_repository():
    paths = [
        target for target in re.findall(r"!\[[^\]]*\]\(([^)\s]+)\)", DESCRIPTION.read_text(encoding="utf-8"))
        if not re.match(r"[a-z]+://", target)
    ]
    assert paths, "the roadmap picture is expected by path"
    for target in paths:
        assert (PLUGIN / target).is_file(), target


def test_the_roadmap_picture_says_what_the_about_page_says():
    drawn = _png_texts(ROADMAP).get(ROADMAP_TEXT_KEY)
    assert drawn is not None, "rebuild it: python orca-plugin/plugin-hub-media/render_gallery.py 09"
    assert json.loads(drawn) == _site_roadmap(), (
        "the site's roadmap changed; rebuild the picture: "
        "python orca-plugin/plugin-hub-media/render_gallery.py 09"
    )
