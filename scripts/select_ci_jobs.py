#!/usr/bin/env python3
"""Select CI components without forgetting changes from failed or unfinished runs."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
COMPONENTS = ("backend", "frontend", "edge", "plugins")


def select_components(paths: list[str]) -> set[str]:
    selected: set[str] = set()
    for path in paths:
        if path.startswith(("backend/", "content/")):
            selected.add("backend")
        elif path.startswith("frontend/"):
            selected.add("frontend")
            # The label-renderer contract compares its mark with the website's SVG.
            if path == "frontend/public/logo.svg":
                selected.add("backend")
        elif path.startswith("edge-agent/") or path == "repository.yaml":
            selected.add("edge")
        elif path.startswith(("orca-plugin/", "octoprint-plugin/")):
            selected.add("plugins")
        elif path != "README.md":
            # Scripts, workflows, infrastructure and new/unclassified paths can
            # affect multiple components. They always receive the full checks.
            return set(COMPONENTS)
    return selected


def git(*arguments: str) -> str:
    return subprocess.check_output(["git", *arguments], cwd=ROOT, stderr=subprocess.PIPE).decode(
        "utf-8"
    )


def is_ancestor(base: str, head: str) -> bool:
    if not re.fullmatch(r"[0-9a-f]{40}", base):
        return False
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", base, head],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def successful_base(runs: list[dict], head: str, branch: str) -> str | None:
    for run in runs:
        sha = run.get("head_sha", "")
        if (
            run.get("event") == "push"
            and run.get("status") == "completed"
            and run.get("conclusion") == "success"
            and run.get("head_branch") == branch
            and run.get("path") == ".github/workflows/ci.yml"
            and sha != head
            and is_ancestor(sha, head)
        ):
            return sha
    return None


def load_successful_runs(repository: str, branch: str, token: str) -> list[dict]:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("Invalid repository name")
    query = urlencode({"event": "push", "status": "success", "branch": branch, "per_page": 100})
    request = Request(
        f"https://api.github.com/repos/{repository}/actions/workflows/ci.yml/runs?{query}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urlopen(request, timeout=20) as response:
        return json.load(response)["workflow_runs"]


def changed_paths(base: str, head: str) -> list[str]:
    # Disable rename detection so moves across component boundaries select both.
    return [
        path
        for path in git("diff", "--name-only", "--no-renames", "-z", base, head, "--").split("\0")
        if path
    ]


def select_for_event(event_name: str, event: dict, env: dict) -> tuple[set[str], str]:
    head = git("rev-parse", "HEAD").strip()
    if event_name == "pull_request":
        pull_request = event["pull_request"]
        base_sha = pull_request["base"]["sha"]
        head_sha = pull_request["head"]["sha"]
        if not all(re.fullmatch(r"[0-9a-f]{40}", sha) for sha in (base_sha, head_sha)):
            raise ValueError("Invalid pull request revisions")
        base = git("merge-base", base_sha, head_sha).strip()
    elif event_name == "push":
        branch = env["GITHUB_REF_NAME"]
        runs = load_successful_runs(env["GITHUB_REPOSITORY"], branch, env["GH_TOKEN"])
        base = successful_base(runs, head, branch)
        if base is None:
            return set(COMPONENTS), "No successful ancestor CI run; run all components."
    else:
        return set(COMPONENTS), "Full verification requested."

    paths = changed_paths(base, head)
    return select_components(paths), f"Compared {len(paths)} changed paths against {base}."


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base", help="Local dry-run: compare this commit with HEAD instead of querying CI."
    )
    args = parser.parse_args()
    try:
        if args.base:
            base = git("rev-parse", "--verify", "--end-of-options", args.base + "^{commit}").strip()
            paths = changed_paths(base, "HEAD")
            selected, reason = (
                select_components(paths),
                f"Local comparison: {len(paths)} changed paths.",
            )
        else:
            event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
            selected, reason = select_for_event(os.environ["GITHUB_EVENT_NAME"], event, os.environ)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        # Failure to obtain a trustworthy diff must never produce a green skip.
        selected = set(COMPONENTS)
        reason = f"Selection unavailable ({type(error).__name__}); run all components."

    outputs = {component: str(component in selected).lower() for component in COMPONENTS}
    print(json.dumps({"components": outputs, "reason": reason}, indent=2))
    if not args.base and os.environ.get("GITHUB_OUTPUT"):
        with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as output:
            output.writelines(f"{key}={value}\n" for key, value in outputs.items())
    if not args.base and os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as summary:
            summary.write(f"## CI selection\n\n{reason}\n\n")
            summary.writelines(
                f"- {key}: {'run' if value == 'true' else 'unchanged'}\n"
                for key, value in outputs.items()
            )
            summary.write("- operations: always run\n")


if __name__ == "__main__":
    main()
