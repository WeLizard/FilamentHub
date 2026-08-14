from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.render_plugin_release_notes import (
    extract_changelog_section,
    render_bridge_release_notes,
    render_orca_release_notes,
    render_release_notes,
)


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

    def test_component_notes_do_not_mix_products(self) -> None:
        orca_notes = render_orca_release_notes()
        bridge_notes = render_bridge_release_notes()

        self.assertIn("## FilamentHub for OrcaSlicer", orca_notes)
        self.assertNotIn("OctoPrint", orca_notes)
        self.assertIn("## FilamentHub Bridge for OctoPrint", bridge_notes)
        self.assertNotIn("## FilamentHub for OrcaSlicer", bridge_notes)

    def test_combined_notes_include_one_checksum_footer(self) -> None:
        notes = render_release_notes()

        self.assertIn("## FilamentHub for OrcaSlicer", notes)
        self.assertIn("## FilamentHub Bridge for OctoPrint", notes)
        self.assertEqual(notes.count("Package checksums are available"), 1)


if __name__ == "__main__":
    unittest.main()
