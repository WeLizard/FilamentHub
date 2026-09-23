"""Prevent CI from silently skipping changed or previously failed components."""

from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import select_ci_jobs as ci


class ComponentSelectionTest(unittest.TestCase):
    def test_component_changes_keep_their_full_job(self) -> None:
        cases = {
            "backend/alembic/versions/new_revision.py": {"backend"},
            "backend/data/catalog_sources/orca/bundle.zip": {"backend"},
            "content/legal/en/privacy.md": {"backend"},
            "frontend/src/pages/AboutPage.tsx": {"frontend"},
            "frontend/package-lock.json": {"frontend"},
            "frontend/public/logo.svg": {"backend", "frontend"},
            "edge-agent/Dockerfile": {"edge"},
            "repository.yaml": {"edge"},
            "orca-plugin/description.md": {"plugins"},
            "octoprint-plugin/pyproject.toml": {"plugins"},
        }
        for path, expected in cases.items():
            with self.subTest(path=path):
                self.assertEqual(ci.select_components([path]), expected)

    def test_shared_and_unknown_changes_cannot_skip_any_component(self) -> None:
        for path in (
            ".github/workflows/ci.yml",
            "scripts/select_ci_jobs.py",
            "scripts/check_postgres_runtime.py",
            "scripts/publish-plugin-releases.ps1",
            "docker-compose.yml",
            ".env.template",
            ".gitattributes",
            "new-component/runtime.py",
        ):
            with self.subTest(path=path):
                self.assertEqual(ci.select_components([path]), set(ci.COMPONENTS))

    def test_rename_across_components_checks_old_and_new_paths(self) -> None:
        # Use a real Git diff: rename detection must not hide the deleted path.
        root = Path(tempfile.mkdtemp(prefix="filamenthub-ci-selection-"))

        def run(*args: str) -> str:
            return subprocess.check_output(
                ["git", *args], cwd=root, stderr=subprocess.PIPE, text=True
            ).strip()

        run("init", "--quiet")
        old = root / "frontend" / "file with spaces.ts"
        old.parent.mkdir()
        old.write_text("export const value = 1;\n", encoding="utf-8")
        run("add", "frontend/file with spaces.ts")
        run(
            "-c",
            "user.name=CI test",
            "-c",
            "user.email=ci@example.invalid",
            "commit",
            "-qm",
            "fixture",
        )
        base = run("rev-parse", "HEAD")
        new = root / "backend" / "file with spaces.ts"
        new.parent.mkdir()
        old.rename(new)
        run("add", "frontend/file with spaces.ts", "backend/file with spaces.ts")
        run(
            "-c",
            "user.name=CI test",
            "-c",
            "user.email=ci@example.invalid",
            "commit",
            "-qm",
            "move fixture",
        )
        with patch.object(ci, "ROOT", root):
            paths = ci.changed_paths(base, "HEAD")
        self.assertEqual(
            set(paths), {"frontend/file with spaces.ts", "backend/file with spaces.ts"}
        )
        self.assertEqual(ci.select_components(paths), {"backend", "frontend"})


class BaselineSelectionTest(unittest.TestCase):
    head = "a" * 40
    base = "b" * 40
    env = {"GITHUB_REF_NAME": "main", "GITHUB_REPOSITORY": "owner/repo", "GH_TOKEN": "test-only"}

    def run_record(self, sha: str, **overrides: str) -> dict:
        return {
            "head_sha": sha,
            "head_branch": "main",
            "event": "push",
            "status": "completed",
            "conclusion": "success",
            "path": ".github/workflows/ci.yml",
            **overrides,
        }

    def test_failed_unfinished_unrelated_and_non_ancestor_runs_are_not_baselines(self) -> None:
        runs = [
            self.run_record(self.head),
            self.run_record("c" * 40, conclusion="failure"),
            self.run_record("d" * 40, conclusion=None),
            self.run_record("3" * 40, status="in_progress"),
            self.run_record("e" * 40, event="pull_request"),
            self.run_record("f" * 40, path=".github/workflows/release-edge.yml"),
            self.run_record("1" * 40, head_branch="other"),
            self.run_record("2" * 40),
            self.run_record(self.base),
        ]
        with patch.object(ci, "is_ancestor", side_effect=lambda sha, head: sha == self.base):
            self.assertEqual(ci.successful_base(runs, self.head, "main"), self.base)

    def test_doc_push_after_failed_backend_keeps_backend_in_the_diff(self) -> None:
        with (
            patch.object(ci, "git", return_value=self.head),
            patch.object(ci, "load_successful_runs", return_value=[self.run_record(self.base)]),
            patch.object(ci, "is_ancestor", return_value=True),
            patch.object(
                ci, "changed_paths", return_value=["backend/app/main.py", "README.md"]
            ) as diff,
        ):
            selected, _ = ci.select_for_event("push", {"before": "c" * 40}, self.env)
        self.assertEqual(selected, {"backend"})
        diff.assert_called_once_with(self.base, self.head)

    def test_no_trusted_baseline_runs_everything(self) -> None:
        with (
            patch.object(ci, "git", return_value=self.head),
            patch.object(ci, "load_successful_runs", return_value=[]),
        ):
            selected, _ = ci.select_for_event("push", {}, self.env)
        self.assertEqual(selected, set(ci.COMPONENTS))

    def test_manual_run_is_full_and_does_not_depend_on_api(self) -> None:
        with (
            patch.object(ci, "git", return_value=self.head),
            patch.object(ci, "load_successful_runs") as api,
        ):
            selected, _ = ci.select_for_event("workflow_dispatch", {}, {})
        self.assertEqual(selected, set(ci.COMPONENTS))
        api.assert_not_called()

    def test_pull_request_checks_merge_result_including_base_branch_changes(self) -> None:
        event = {"pull_request": {"base": {"sha": "c" * 40}, "head": {"sha": "d" * 40}}}
        with (
            patch.object(ci, "git", side_effect=[self.head, self.base]) as git,
            patch.object(
                ci, "changed_paths", return_value=["frontend/src/App.tsx", "backend/app/main.py"]
            ) as diff,
        ):
            selected, _ = ci.select_for_event("pull_request", event, {})
        self.assertEqual(selected, {"frontend", "backend"})
        self.assertEqual(git.call_args.args, ("merge-base", "c" * 40, "d" * 40))
        diff.assert_called_once_with(self.base, self.head)

    def test_api_failure_emits_run_outputs_for_every_component(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="filamenthub-ci-fallback-"))
        event_path, output_path = root / "event.json", root / "output.txt"
        event_path.write_text("{}", encoding="utf-8")
        env = {
            **self.env,
            "GITHUB_EVENT_NAME": "push",
            "GITHUB_EVENT_PATH": str(event_path),
            "GITHUB_OUTPUT": str(output_path),
        }
        with (
            patch.dict(os.environ, env, clear=True),
            patch("sys.argv", ["select_ci_jobs.py"]),
            patch.object(ci, "git", return_value=self.head),
            patch.object(ci, "load_successful_runs", side_effect=TimeoutError),
            contextlib.redirect_stdout(io.StringIO()) as stdout,
        ):
            ci.main()
        self.assertEqual(
            json.loads(stdout.getvalue())["components"], dict.fromkeys(ci.COMPONENTS, "true")
        )
        self.assertEqual(
            set(output_path.read_text(encoding="utf-8").splitlines()),
            {f"{name}=true" for name in ci.COMPONENTS},
        )


if __name__ == "__main__":
    unittest.main()
