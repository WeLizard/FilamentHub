import ast
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND_ORIGINS = ROOT / "frontend" / "src" / "data" / "siteOrigins.json"
BACKEND_SITE = ROOT / "backend" / "app" / "core" / "site.py"


def _backend_origins() -> dict[str, str]:
    module = ast.parse(BACKEND_SITE.read_text(encoding="utf-8"))
    for node in module.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "SITE_ORIGINS"
            for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError("SITE_ORIGINS is missing from app/core/site.py")


class SiteOriginContractTest(unittest.TestCase):
    def test_pages_and_sitemap_agree_on_each_language_host(self) -> None:
        # A page that names one canonical host while the sitemap lists another
        # makes search engines treat the two hosts as duplicates.
        frontend = json.loads(FRONTEND_ORIGINS.read_text(encoding="utf-8"))

        self.assertEqual(frontend, _backend_origins())


if __name__ == "__main__":
    unittest.main()
