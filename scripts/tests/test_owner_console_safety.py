"""Offline regressions for owner-console publication and cleanup safety.

These tests load only PowerShell function definitions.  They use temporary Git
repositories and never invoke the publication function or a network remote.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[2]
LOAD_FUNCTIONS = r"""
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$tokens = $null
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $env:CONSOLE_SCRIPT, [ref]$tokens, [ref]$errors
)
if ($errors.Count) { throw ($errors | Out-String) }
foreach ($statement in $ast.EndBlock.Statements) {
    if ($statement -is [System.Management.Automation.Language.FunctionDefinitionAst]) {
        . ([scriptblock]::Create($statement.Extent.Text))
    }
}
"""


def run_ps(tmp_path: Path, body: str, **environment: str) -> dict:
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if not shell:
        pytest.skip("PowerShell is required")
    runner = tmp_path / "run.ps1"
    runner.write_text(LOAD_FUNCTIONS + body, encoding="utf-8-sig")
    result = subprocess.run(
        [shell, "-NoProfile", "-NonInteractive", "-File", str(runner)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        env={
            **os.environ,
            "CONSOLE_SCRIPT": str(ROOT / "scripts/deploy-server.ps1"),
            **environment,
        },
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


def git(path: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(path), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def repository(tmp_path: Path, commits: list[dict]) -> tuple[Path, str, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "base-main")
    git(repo, "config", "user.email", "tests@example.invalid")
    git(repo, "config", "user.name", "Offline Tests")
    for commit in commits:
        files = commit.get("files", [commit])
        for file in files:
            target = repo / file["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            if file.get("delete"):
                git(repo, "rm", "-q", "--", file["path"])
            else:
                target.write_text(file.get("content", "x"), encoding="utf-8")
                git(repo, "add", "--", file["path"])
        git(repo, "commit", "-q", "-m", commit["message"])
    base, head = git(repo, "rev-list", "--reverse", "HEAD").splitlines()[0], git(
        repo, "rev-parse", "HEAD"
    )
    git(repo, "switch", "-c", "main")
    git(repo, "update-ref", "refs/remotes/origin/main", base)
    return repo, base, head


def publication_check(
    tmp_path: Path, repo: Path, base: str, target: str, allowed: list[str]
) -> dict:
    return run_ps(
        tmp_path,
        r"""
$failure = $null
try {
    Assert-PublicationPaths -Directory $env:REPO -BaseRevision $env:BASE `
        -TargetRevision $env:TARGET -AllowedPaths ($env:ALLOWED | ConvertFrom-Json)
} catch { $failure = $_.Exception.Message }
@{ error = $failure } | ConvertTo-Json -Compress
""",
        REPO=str(repo),
        BASE=base,
        TARGET=target,
        ALLOWED=json.dumps(allowed),
    )


def publication_integration(
    tmp_path: Path, repo: Path, allowed: list[str] | None
) -> dict:
    allowed_expression = (
        "-AllowedPaths @($env:ALLOWED | ConvertFrom-Json)"
        if allowed is not None
        else ""
    )
    remote_sha = git(repo, "rev-parse", "HEAD")
    return run_ps(
        tmp_path,
        f"""
$global:events = [System.Collections.Generic.List[string]]::new()
function Invoke-Checked {{
    param([string]$FilePath, [string[]]$Arguments, [switch]$Capture)
    if ($Arguments -contains 'fetch') {{ return '' }}
    if ($Arguments -contains 'push') {{ $global:events.Add('push'); return '' }}
    if ($Arguments -contains 'ls-remote') {{ return "$env:REMOTE_SHA`trefs/heads/main" }}
    $output = & $FilePath @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) {{ throw ($output -join "`n") }}
    if ($Capture) {{ return ($output -join "`n").Trim() }}
}}
function Read-Host {{ param($Prompt) return '1' }}
function Confirm-Action {{ param($Question) $global:events.Add('confirm'); return $true }}
$failure = $null
try {{
    Publish-RepositoryCommits -Directory $env:REPO -Title 'Fixture' {allowed_expression}
}} catch {{ $failure = $_.Exception.Message }}
@{{ error = $failure; events = @($global:events.ToArray()) }} | ConvertTo-Json -Compress
""",
        REPO=str(repo),
        ALLOWED=json.dumps(allowed or []),
        REMOTE_SHA=remote_sha,
    )


def test_publication_integration_blocks_before_confirmation_or_push(tmp_path: Path) -> None:
    repo, _, _ = repository(
        tmp_path,
        [
            {"path": "README.md", "message": "base"},
            {
                "message": "mixed",
                "files": [
                    {"path": "orca-plugin/runtime.py"},
                    {"path": "backend/app.py"},
                ],
            },
        ],
    )
    result = publication_integration(tmp_path, repo, ["orca-plugin/"])
    assert result["error"]
    assert result["events"] == []


def test_publication_integration_allows_plugin_commit_and_intercepts_push(
    tmp_path: Path,
) -> None:
    repo, _, _ = repository(
        tmp_path,
        [
            {"path": "README.md", "message": "base"},
            {"path": "orca-plugin/runtime.py", "message": "plugin"},
        ],
    )
    result = publication_integration(tmp_path, repo, ["orca-plugin/"])
    assert result == {"error": None, "events": ["confirm", "push"]}


def test_publication_integration_without_allowlist_keeps_generic_mode(tmp_path: Path) -> None:
    repo, _, _ = repository(
        tmp_path,
        [
            {"path": "README.md", "message": "base"},
            {"path": "backend/app.py", "message": "unrelated"},
        ],
    )
    result = publication_integration(tmp_path, repo, None)
    assert result == {"error": None, "events": ["confirm", "push"]}


def test_publication_path_guard_allows_plugin_only_commit(tmp_path: Path) -> None:
    repo, base, target = repository(
        tmp_path,
        [
            {"path": "README.md", "message": "base"},
            {"path": "orca-plugin/runtime.py", "message": "plugin"},
        ],
    )
    assert publication_check(tmp_path, repo, base, target, ["orca-plugin/"]) == {
        "error": None
    }


def test_publication_path_guard_blocks_mixed_commit_and_lists_path(tmp_path: Path) -> None:
    repo, base, target = repository(
        tmp_path,
        [
            {"path": "README.md", "message": "base"},
            {
                "message": "mixed",
                "files": [
                    {"path": "orca-plugin/runtime.py"},
                    {"path": "backend/app.py"},
                ],
            },
        ],
    )
    result = publication_check(tmp_path, repo, base, target, ["orca-plugin/"])
    assert result["error"]
    assert "backend/app.py" in result["error"]
    assert "mixed" in result["error"]


def test_publication_path_guard_blocks_reverted_unrelated_commit(tmp_path: Path) -> None:
    repo, base, _ = repository(
        tmp_path,
        [
            {"path": "README.md", "message": "base"},
            {"path": "backend/app.py", "message": "unrelated"},
            {"path": "orca-plugin/runtime.py", "message": "plugin"},
            {"path": "backend/app.py", "message": "revert", "delete": True},
        ],
    )
    target = git(repo, "rev-parse", "HEAD")
    result = publication_check(tmp_path, repo, base, target, ["orca-plugin/"])
    assert result["error"]
    assert "backend/app.py" in result["error"]


def test_publication_path_guard_blocks_rename_from_outside_allowlist(tmp_path: Path) -> None:
    repo, base, _ = repository(
        tmp_path,
        [{"path": "backend/legacy.py", "message": "base"}],
    )
    (repo / "orca-plugin").mkdir()
    (repo / "backend/legacy.py").rename(repo / "orca-plugin/legacy.py")
    git(repo, "add", "--", "orca-plugin/legacy.py")
    git(repo, "rm", "-q", "--", "backend/legacy.py")
    git(repo, "commit", "-q", "-m", "rename")
    target = git(repo, "rev-parse", "HEAD")
    result = publication_check(tmp_path, repo, base, target, ["orca-plugin/"])
    assert result["error"]
    assert "backend/legacy.py" in result["error"]


def test_publication_path_guard_blocks_unrelated_side_of_merge(tmp_path: Path) -> None:
    repo = tmp_path / "merge-repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "base-main")
    git(repo, "config", "user.email", "tests@example.invalid")
    git(repo, "config", "user.name", "Offline Tests")
    (repo / "README.md").write_text("base", encoding="utf-8")
    git(repo, "add", "README.md")
    git(repo, "commit", "-q", "-m", "base")
    base = git(repo, "rev-parse", "HEAD")
    git(repo, "switch", "-c", "main")
    (repo / "orca-plugin").mkdir()
    (repo / "orca-plugin/runtime.py").write_text("plugin", encoding="utf-8")
    git(repo, "add", "orca-plugin/runtime.py")
    git(repo, "commit", "-q", "-m", "plugin side")
    git(repo, "switch", "-c", "unrelated-side", base)
    (repo / "backend").mkdir()
    (repo / "backend/app.py").write_text("unrelated", encoding="utf-8")
    git(repo, "add", "backend/app.py")
    git(repo, "commit", "-q", "-m", "unrelated main")
    git(repo, "switch", "main")
    git(repo, "merge", "--no-ff", "-q", "unrelated-side", "-m", "merge unrelated")
    target = git(repo, "rev-parse", "HEAD")
    git(repo, "update-ref", "refs/remotes/origin/main", base)

    result = publication_check(tmp_path, repo, base, target, ["orca-plugin/"])
    assert result["error"]
    assert "backend/app.py" in result["error"]


@pytest.mark.parametrize(
    ("choice", "retention"),
    [("1", "168h"), ("2", "336h"), ("3", "1h")],
)
def test_build_cache_menu_passes_selected_retention_to_worker(
    tmp_path: Path, choice: str, retention: str
) -> None:
    result = run_ps(
        tmp_path,
        r"""
function Read-Host { param($Prompt) return $env:CHOICE }
function Confirm-Action { param($Question) $global:Question = $Question; return $true }
function Invoke-RemoteWorker {
    param([string[]]$Arguments, [switch]$UseDeployedRevision)
    $global:WorkerArguments = @($Arguments)
}
Start-BuildCacheCleanup
@{
    args = @($global:WorkerArguments)
    question_has_unexpanded_variable = $global:Question -match '\$retentionLabel\?'
} | ConvertTo-Json -Compress
""",
        CHOICE=choice,
    )
    assert result["args"] == [
        "--prune-build-cache",
        "--build-cache-retention",
        retention,
        "--yes",
    ]
    assert result["question_has_unexpanded_variable"] is False


def test_build_cache_menu_cancellation_does_not_invoke_worker(tmp_path: Path) -> None:
    result = run_ps(
        tmp_path,
        r"""
function Read-Host { param($Prompt) return '0' }
function Confirm-Action { param($Question) throw 'confirmation must not be requested' }
function Invoke-RemoteWorker { throw 'worker must not be invoked' }
Start-BuildCacheCleanup
@{ cancelled = $true } | ConvertTo-Json -Compress
""",
    )
    assert result == {"cancelled": True}
