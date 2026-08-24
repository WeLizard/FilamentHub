"""Check whether the tracked Orca catalog source trails its upstream ref."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_LOCK = (
    PROJECT_ROOT / "backend" / "data" / "catalog_sources" / "orca" / "source-lock.json"
)
SOURCE_LOCK_FORMAT = "filamenthub.catalog-source-lock"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-lock", type=Path, default=DEFAULT_SOURCE_LOCK)
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser.parse_args()


def _read_source_lock(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("format") != SOURCE_LOCK_FORMAT:
        raise ValueError("invalid Orca catalog source lock format")
    for field in (
        "repository",
        "ref",
        "commit",
        "profiles_tree",
        "content_sha256",
        "bundle_sha256",
        "field_inventory_sha256",
        "preset_field_inventory",
    ):
        if not value.get(field):
            raise ValueError(f"Orca catalog source lock is missing {field}")
    return value


def _github_repository(value: str) -> str:
    parsed = urllib.parse.urlparse(value.removesuffix(".git"))
    parts = parsed.path.strip("/").split("/")
    if len(parts) < 2 or parsed.netloc.lower() != "github.com":
        raise ValueError("manifest repository is not a GitHub repository")
    return "/".join(parts[:2])


def _github_json(url: str) -> Any:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "FilamentHub-OrcaCatalogCheck/1",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        url,
        headers=headers,
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def _latest_profiles_commit(repository: str, ref: str) -> dict[str, Any]:
    query = urllib.parse.urlencode(
        {"path": "resources/profiles", "sha": ref, "per_page": 1}
    )
    payload = _github_json(f"https://api.github.com/repos/{repository}/commits?{query}")
    if not isinstance(payload, list) or not payload:
        raise ValueError("GitHub returned no commits for resources/profiles")
    return payload[0]


def _profiles_tree(repository: str, commit: str) -> str:
    commit_payload = _github_json(
        f"https://api.github.com/repos/{repository}/git/commits/{commit}"
    )
    tree_sha = str(commit_payload["tree"]["sha"])
    root_tree = _github_json(
        f"https://api.github.com/repos/{repository}/git/trees/{tree_sha}"
    )
    resources = next(
        entry for entry in root_tree["tree"] if entry.get("path") == "resources"
    )
    resources_tree = _github_json(
        f"https://api.github.com/repos/{repository}/git/trees/{resources['sha']}"
    )
    profiles = next(
        entry for entry in resources_tree["tree"] if entry.get("path") == "profiles"
    )
    return str(profiles["sha"])


def main() -> int:
    args = _parse_args()
    try:
        source_lock = _read_source_lock(args.source_lock.resolve())
        repository = _github_repository(str(source_lock["repository"]))
        ref = str(source_lock.get("ref") or "main")
        upstream = _latest_profiles_commit(repository, ref)
        upstream_commit = str(upstream["sha"])
        upstream_tree = _profiles_tree(repository, upstream_commit)
        tracked_tree = str(source_lock["profiles_tree"])
        fresh = tracked_tree == upstream_tree
        result = {
            "fresh": fresh,
            "repository": repository,
            "ref": ref,
            "tracked_commit": source_lock["commit"],
            "tracked_profiles_tree": tracked_tree,
            "upstream_profiles_commit": upstream_commit,
            "upstream_profiles_tree": upstream_tree,
            "upstream_commit_url": upstream.get("html_url"),
        }
    except (
        OSError,
        KeyError,
        StopIteration,
        ValueError,
        json.JSONDecodeError,
        urllib.error.URLError,
    ) as exc:
        if args.as_json:
            print(
                json.dumps(
                    {"fresh": None, "error": str(exc)}, ensure_ascii=False, indent=2
                )
            )
        else:
            print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif fresh:
        print(f"Orca catalog source is current: {tracked_tree}")
    else:
        print(
            "Orca catalog source is stale: "
            f"tracked_tree={tracked_tree} upstream_tree={upstream_tree}"
        )
    return 0 if fresh else 2


if __name__ == "__main__":
    raise SystemExit(main())
