from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from alembic.config import Config
from alembic.script import ScriptDirectory


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"


class MigrationGraphTest(unittest.TestCase):
    def test_graph_has_exactly_one_resolvable_head(self) -> None:
        original_cwd = Path.cwd()
        sys.path.insert(0, str(BACKEND))
        try:
            # Migrations may import application modules. Run from an empty
            # directory with a minimal environment so a developer's local
            # backend/.env cannot affect the graph check or leak into CI logs.
            with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
                os.environ,
                {"SECRET_KEY": "ci-secret-key"},
                clear=True,
            ):
                os.chdir(temp_dir)
                try:
                    config = Config(str(BACKEND / "alembic.ini"))
                    config.set_main_option("script_location", str(BACKEND / "alembic"))
                    script = ScriptDirectory.from_config(config)

                    heads = script.get_heads()
                    self.assertEqual(
                        len(heads), 1, f"expected exactly one head, found {heads}"
                    )

                    revisions = list(script.walk_revisions())
                    revision_ids = {revision.revision for revision in revisions}
                    missing: list[tuple[str, str]] = []
                    for revision in revisions:
                        dependencies = revision.down_revision or ()
                        if isinstance(dependencies, str):
                            dependencies = (dependencies,)
                        for dependency in dependencies:
                            if dependency not in revision_ids:
                                missing.append((revision.revision, dependency))

                    self.assertEqual(
                        missing, [], f"missing Alembic dependencies: {missing}"
                    )
                finally:
                    os.chdir(original_cwd)
        finally:
            sys.path.remove(str(BACKEND))


if __name__ == "__main__":
    unittest.main()
