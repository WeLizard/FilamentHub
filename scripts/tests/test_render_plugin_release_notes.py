from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.render_plugin_release_notes import extract_changelog_section


class ChangelogSectionTest(unittest.TestCase):
    def test_extracts_only_current_release(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            changelog = Path(temp) / "CHANGELOG.md"
            changelog.write_text(
                "# Changelog\n\n## 1.2.3\n- Current change.\n\n"
                "## 1.2.2\n- Previous change.\n",
                encoding="utf-8",
            )

            self.assertEqual(
                extract_changelog_section(changelog, "1.2.3"),
                "- Current change.",
            )

    def test_rejects_stale_top_section(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            changelog = Path(temp) / "CHANGELOG.md"
            changelog.write_text(
                "# Changelog\n\n## 1.2.2\n- Previous change.\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "expected 1.2.3"):
                extract_changelog_section(changelog, "1.2.3")


if __name__ == "__main__":
    unittest.main()
