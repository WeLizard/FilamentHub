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
            value = rest.split(b"\0", 2)[2]  # after the language and translated key
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


def test_the_card_keeps_its_video_and_hosted_pictures():
    # Each release replaces the card's text with this file, so media missing
    # here disappears from the card.
    text = DESCRIPTION.read_text(encoding="utf-8")
    assert re.search(r"^https://youtu\.be/xtKIKNYYaAk$", text, re.M)
    for media in (
        "36cc1c18-b99c-4acd-b19c-c9beeb77bef4", "3b89760e-c9f7-4575-901a-a8e2bd3dc066",
        "3823bfcd-fbd7-4c27-9945-94f7fc9fac2a", "3064ff05-e5c0-4f7c-ab58-5528e95a34cd",
        "3f5d7ba8-d90f-48b0-b5aa-b212a2f99203", "3266072f-2d25-4ef9-a03d-a16629f58f5d",
        "31beaab3-a3a6-463c-ac73-58b5c9663e45", "3c3709cf-bbf0-404a-b8b0-6277e7b5cf15",
    ):
        assert f"https://api.orcaslicer.com/api/v1/bundles/media/{media}/content" in text, media


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
