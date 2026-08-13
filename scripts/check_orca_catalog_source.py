"""Check whether the committed Orca catalog source trails its tracked ref."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BUNDLE = PROJECT_ROOT / "backend" / "data" / "catalog_sources" / "orca" / "bundle.zip"
MANIFEST_NAME = "filamenthub-source.json"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser.parse_args()


def _read_manifest(bundle: Path) -> dict[str, Any]:
    with zipfile.ZipFile(bundle) as archive:
        return json.loads(archive.read(MANIFEST_NAME))


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
    payload = _github_json(
        f"https://api.github.com/repos/{repository}/commits?{query}"
    )
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
        manifest = _read_manifest(args.bundle.resolve())
        repository = _github_repository(str(manifest["repository"]))
        upstream = _latest_profiles_commit(repository, str(manifest.get("ref") or "main"))
        upstream_commit = str(upstream["sha"])
        upstream_tree = _profiles_tree(repository, upstream_commit)
        bundled_tree = str(manifest["profiles_tree"])
        fresh = bundled_tree == upstream_tree
        result = {
            "fresh": fresh,
            "repository": repository,
            "ref": manifest.get("ref") or "main",
            "bundled_commit": manifest["commit"],
            "bundled_profiles_tree": bundled_tree,
            "upstream_profiles_commit": upstream_commit,
            "upstream_profiles_tree": upstream_tree,
            "upstream_commit_url": upstream.get("html_url"),
        }
    except (
        OSError,
        KeyError,
        StopIteration,
        ValueError,
        zipfile.BadZipFile,
        urllib.error.URLError,
    ) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif fresh:
        print(f"Orca catalog source is current: {bundled_tree}")
    else:
        print(
            "Orca catalog source is stale: "
            f"bundle_tree={bundled_tree} upstream_tree={upstream_tree}"
        )
    return 0 if fresh else 2


if __name__ == "__main__":
    raise SystemExit(main())
