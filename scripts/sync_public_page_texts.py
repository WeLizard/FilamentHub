"""Copy the interface strings that server-rendered pages need into the backend.

The catalogue and wiki pages get their title, description and visible text
from the backend (backend/app/services/public_page_render.py), while the
interface strings live in frontend/src/locales. This script copies the keys
the backend uses, so both say the same words.

    python scripts/sync_public_page_texts.py          # rewrite the backend copy
    python scripts/sync_public_page_texts.py --check  # fail if it is stale
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCALES_DIR = ROOT / "frontend" / "src" / "locales"
TARGET = ROOT / "backend" / "app" / "data" / "public_page_texts.json"
LOCALES = ("en", "ru", "zh")
KEYS = (
    "layout.nav_catalog",
    "catalogPage.tableMaterial",
    "filamentDetailPage.seoDescription",
    "filamentDetailPage.seoKeywords",
    "filamentDetailPage.brand",
    "filamentDetailPage.color",
    "brandDetailPage.seoDescription",
    "brandDetailPage.allMaterials",
    "wikiPage.seoTitle",
    "wikiPage.seoDescription",
    "wikiPage.seoKeywords",
    "wikiPage.categories",
    "wikiCategoryPage.seoSuffix",
    "wikiCategoryPage.seoDescription",
)
# Whole groups copied as they are: category names by slug.
GROUPS = ("wikiAuthoring.categories",)


def _lookup(tree: dict, key: str, kind: type = str):
    node = tree
    for part in key.split("."):
        node = node.get(part) if isinstance(node, dict) else None
    if not isinstance(node, kind) or not node:
        raise KeyError(f"{key} is missing from the interface strings")
    return node


def build() -> dict[str, dict[str, object]]:
    texts = {}
    for locale in LOCALES:
        tree = json.loads((LOCALES_DIR / locale / "translation.json").read_text(encoding="utf-8"))
        texts[locale] = {key: _lookup(tree, key) for key in KEYS}
        texts[locale].update({group: _lookup(tree, group, dict) for group in GROUPS})
    return texts


def render() -> str:
    return json.dumps(build(), ensure_ascii=False, indent=2) + "\n"


def main() -> int:
    expected = render()
    if "--check" in sys.argv[1:]:
        current = TARGET.read_text(encoding="utf-8") if TARGET.exists() else ""
        if current != expected:
            print(f"{TARGET.relative_to(ROOT)} is stale: run python scripts/sync_public_page_texts.py")
            return 1
        return 0
    TARGET.write_text(expected, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
