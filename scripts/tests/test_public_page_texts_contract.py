import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "sync_public_page_texts", ROOT / "scripts" / "sync_public_page_texts.py"
)
assert SPEC is not None and SPEC.loader is not None
sync = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sync)


class PublicPageTextsContractTest(unittest.TestCase):
    def test_backend_copy_matches_interface_strings(self) -> None:
        # A server-rendered title that differs from the one the application
        # sets after loading shows search engines two titles for one page.
        self.assertEqual(
            sync.TARGET.read_text(encoding="utf-8"),
            sync.render(),
            "run python scripts/sync_public_page_texts.py",
        )


if __name__ == "__main__":
    unittest.main()
