"""Checks that must stop a plugin release before the owner is asked anything.

Each test loads only the PowerShell function definitions of the release
script and replaces network access, so no tag, release or request is made.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[2]
RELEASE_SCRIPT = ROOT / "scripts/publish-plugin-releases.ps1"
LOAD_FUNCTIONS = r"""
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$tokens = $null
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $env:RELEASE_SCRIPT, [ref]$tokens, [ref]$errors
)
if ($errors.Count) { throw ($errors | Out-String) }
foreach ($statement in $ast.EndBlock.Statements) {
    if ($statement -is [System.Management.Automation.Language.FunctionDefinitionAst]) {
        . ([scriptblock]::Create($statement.Extent.Text))
    }
}
$script:Remote = 'origin'
$script:OrcaCloudOutcome = $null
function Write-Host { }
"""


def run_ps(tmp_path: Path, body: str, **environment: str):
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if not shell:
        pytest.skip("PowerShell is required")
    runner = tmp_path / "run.ps1"
    runner.write_text(LOAD_FUNCTIONS + body, encoding="utf-8-sig")
    result = subprocess.run(
        [shell, "-NoProfile", "-NonInteractive", "-File", str(runner)],
        capture_output=True, text=True, encoding="utf-8", timeout=120,
        env={**os.environ, "RELEASE_SCRIPT": str(RELEASE_SCRIPT), **environment},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


def git(path: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(path), *args], check=True, capture_output=True, text=True,
        env={**os.environ, **isolated_git()},
    ).stdout.strip()


def isolated_git() -> dict[str, str]:
    return {"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull}


def repository(path: Path, commits: int = 1) -> Path:
    path.mkdir()
    git(path, "init", "-q")
    for index in range(commits):
        (path / "file.txt").write_text(str(index), encoding="utf-8")
        git(path, "add", "file.txt")
        git(path, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
            "commit", "-qm", f"commit {index}")
    return path


@pytest.mark.parametrize("required,live,planned,expected", [
    (1, 1, 0, False),
    (1, 3, 0, False),
    (2, 1, 2, True),
    (2, 1, 0, r".\scripts\release.ps1 -Item site,orcaslicer"),
    (3, 1, 2, "PLUGIN_API_LEVEL"),
])
def test_plugin_waits_for_a_site_that_serves_its_required_level(tmp_path, required, live, planned, expected):
    result = run_ps(tmp_path, rf"""
$failure = $null; $needsSite = $null
try {{
    $needsSite = Test-SiteServesPlugin -Id 'orcaslicer' -Name 'Fixture' -Required {required} -Live {live} -Planned {planned}
}} catch {{ $failure = $_.Exception.Message }}
@{{ error = $failure; needsSite = $needsSite }} | ConvertTo-Json -Compress
""")

    if isinstance(expected, bool):
        assert result == {"error": None, "needsSite": expected}
    else:
        assert expected in result["error"]
        assert "Исправить:" in result["error"]


@pytest.mark.parametrize("health,expected", [
    ({"status": "ok"}, 1),
    ({"status": "ok", "plugin_api_level": 4}, 4),
    ({"status": "degraded", "plugin_api_level": 4}, "error"),
    (None, "error"),
])
def test_live_site_level_comes_from_health_and_fails_closed(tmp_path, health, expected):
    result = run_ps(tmp_path, r"""
function Invoke-RestMethod {
    param($Uri, $Method, $TimeoutSec)
    if (-not $env:HEALTH) { throw 'connection refused' }
    return $env:HEALTH | ConvertFrom-Json
}
$failure = $null; $level = $null
try { $level = Get-SitePluginApiLevel -BaseUrl 'https://example.invalid' } catch { $failure = $_.Exception.Message }
@{ error = $failure; level = $level } | ConvertTo-Json -Compress
""", HEALTH=json.dumps(health) if health else "")

    if expected == "error":
        assert result["level"] is None
        assert "Исправить:" in result["error"]
    else:
        assert result == {"error": None, "level": expected}


def test_missing_git_identity_is_reported_with_an_exact_command(tmp_path):
    main = repository(tmp_path / "main")
    git(main, "config", "user.name", "Owner Name")
    git(main, "config", "user.email", "owner@example.invalid")
    other = repository(tmp_path / "other")
    body = r"""
$script:MainRepositoryRoot = $env:MAIN
$failures = @(foreach ($path in @($env:MAIN, $env:OTHER)) {
    try { Assert-GitIdentity -Name 'Fixture' -RepositoryPath $path; $null } catch { $_.Exception.Message }
})
@{ main = $failures[0]; other = $failures[1] } | ConvertTo-Json -Compress
"""
    result = run_ps(tmp_path, body, MAIN=str(main), OTHER=str(other), **isolated_git())

    assert result["main"] is None
    assert f'git -C "{other}" config user.name "Owner Name"' in result["other"]


@pytest.mark.parametrize("scenario", ["remote_elsewhere", "stale_local", "same_commit", "free"])
def test_version_tag_conflicts_are_found_before_any_question(tmp_path, scenario):
    repo = repository(tmp_path / "repo", commits=2)
    first, release = git(repo, "rev-list", "--reverse", "HEAD").splitlines()
    if scenario == "stale_local":
        git(repo, "tag", "v1.2.3", first)
    if scenario == "same_commit":
        git(repo, "tag", "v1.2.3", release)
    remote = {"remote_elsewhere": first, "same_commit": release}.get(scenario, "")
    result = run_ps(tmp_path, r"""
function Get-RemoteTagCommit { param($RepositoryPath, $RemoteName, $Tag) if ($env:REMOTE_TAG) { $env:REMOTE_TAG } else { $null } }
$failure = $null; $remote = $null
try {
    $remote = Assert-TagAvailable -Name 'Fixture' -RepositoryPath $env:REPO -Tag 'v1.2.3' -ReleaseCommit $env:RELEASE
} catch { $failure = $_.Exception.Message }
@{ error = $failure; remote = $remote } | ConvertTo-Json -Compress
""", REPO=str(repo), RELEASE=release, REMOTE_TAG=remote)

    if scenario == "remote_elsewhere":
        assert "следующая версия" in result["error"]
    elif scenario == "stale_local":
        assert f'git -C "{repo}" tag -d v1.2.3' in result["error"]
    elif scenario == "same_commit":
        assert result == {"error": None, "remote": release}
    else:
        assert result == {"error": None, "remote": None}


def test_stale_package_is_rejected_by_rebuilding_from_source(tmp_path):
    repo = tmp_path / "plugin"
    repo.mkdir()
    (repo / "builder.py").write_text(
        "import pathlib, sys\n"
        "out = pathlib.Path(sys.argv[sys.argv.index('--output') + 1])\n"
        "(out / 'wheels').mkdir(parents=True)\n"
        "(out / 'wheels' / 'fixture.whl').write_bytes(b'built from source')\n",
        encoding="utf-8",
    )
    candidate = repo / "candidate.whl"
    body = r"""
$realPython = (Get-Command python -CommandType Application | Select-Object -First 1).Source
function python {
    if ($args[0] -eq '-m') { $global:LASTEXITCODE = 0; return }
    & $realPython @args
}
$plan = [pscustomobject]@{
    Name = 'Fixture'; Version = '1.2.3'; RepositoryPath = $env:REPO
    CandidateWheel = $env:CANDIDATE; Builder = 'builder.py'; BuiltWheelRelative = 'wheels/fixture.whl'
}
$failure = $null
try { Assert-CandidateMatchesSource -Plan $plan } catch { $failure = $_.Exception.Message }
@{ error = $failure } | ConvertTo-Json -Compress
"""
    candidate.write_bytes(b"built from source")
    assert run_ps(tmp_path, body, REPO=str(repo), CANDIDATE=str(candidate)) == {"error": None}

    candidate.write_bytes(b"built from an older source")
    assert "устарел" in run_ps(tmp_path, body, REPO=str(repo), CANDIDATE=str(candidate))["error"]


GH_LOG_MOCK = r"""
function gh {
    if ($args[0] -eq 'run' -and $args[1] -eq 'view') {
        $global:LASTEXITCODE = 0
        if ($env:HELD) { return 'publish  {"status":"held_for_review","release":{"version":"1.2.3"}}' }
        return 'publish  {"error":"rejected"}'
    }
    if ($args[0] -eq 'run' -and $args[1] -eq 'watch') {
        $global:LASTEXITCODE = [int]$env:WATCH_EXIT
        return
    }
    throw "unexpected gh $args"
}
"""


@pytest.mark.parametrize("held,watch_exit,expected", [
    ("1", "1", "held_for_review"),
    ("", "1", "error"),
    ("", "0", "accepted"),
])
def test_orcacloud_moderation_hold_is_a_finished_upload(tmp_path, held, watch_exit, expected):
    result = run_ps(tmp_path, GH_LOG_MOCK + r"""
function Invoke-Checked {
    param($FilePath, $Arguments, $WorkingDirectory, [switch]$Capture)
    return '[{"databaseId":7,"headBranch":"v1.2.3","headSha":"aaaa","createdAt":"2030-01-01T00:00:00Z","url":"u"}]'
}
$RunDiscoveryTimeoutSeconds = 15
$failure = $null
try {
    Wait-ForWorkflowRun -Repository 'o/r' -Workflow 'publish-orcacloud.yml' -Event 'release' `
        -TagCommit 'aaaa' -Tag 'v1.2.3' -NotBefore ([datetime]'2029-01-01')
} catch { $failure = $_.Exception.Message }
@{ error = $failure; outcome = $script:OrcaCloudOutcome } | ConvertTo-Json -Compress
""", HELD=held, WATCH_EXIT=watch_exit)

    if expected == "error":
        assert result["error"]
    else:
        assert result == {"error": None, "outcome": expected}


@pytest.mark.parametrize("held,repair", [("1", False), ("", True)])
def test_held_upload_is_never_offered_for_another_upload(tmp_path, held, repair):
    result = run_ps(tmp_path, GH_LOG_MOCK + r"""
function Ensure-LocalTag { param($RepositoryPath, $RemoteName, $Tag) }
function Invoke-Checked { param($FilePath, $Arguments, $WorkingDirectory, [switch]$Capture) return 'aaaa' }
function Get-TrustedPublishRun {
    param($Repository, $Workflow, $Tag, $TagCommit, $NotBefore)
    [pscustomobject]@{ databaseId = 7; status = 'completed'; conclusion = 'failure'; url = 'u' }
}
function Assert-TrustedPublishRepairable { param($Name, $RepositoryPath, $Tag, $WorkflowPath) }
$published = [pscustomobject]@{ Tag = 'v1.2.3'; PublishedAt = [datetime]'2030-01-01' }
$repair = Test-TrustedPublishNeedsRepair -Name 'Fixture' -RepositoryPath '.' -RemoteName 'origin' `
    -Repository 'o/r' -Workflow 'publish-orcacloud.yml' -Published $published
@{ repair = $repair } | ConvertTo-Json -Compress
""", HELD=held, WATCH_EXIT="0")

    assert result == {"repair": repair}


def test_every_release_blocker_is_checked_before_the_dry_run_result_and_the_approval() -> None:
    script = RELEASE_SCRIPT.read_text(encoding="utf-8")
    dry_run = script.index("\nif ($DryRun) {")
    approval = script.index("Assert-OwnerApprovedCandidates -Plans $plans")

    for gate in (
        "Assert-ReleaseRights -Name $plan.Name",
        "Assert-GitIdentity -Name $plan.Name",
        "Assert-TagAvailable `",
        "Assert-TagPushAllowed `",
        "Assert-CandidateMatchesSource -Plan $plan",
        "Test-SiteServesPlugin `",
        "$ExpectedReleaseCommit -and $plan.ReleaseCommit -ne $ExpectedReleaseCommit",
    ):
        assert script.index(gate) < dry_run < approval, gate
    # A real release must see the deployed site, never the planned one.
    assert "-Planned $(if ($DryRun) { $PlannedSiteApiLevel } else { 0 })" in script
    # Release notes are rendered even when the owner hides them.
    notes = script.index("'scripts/render_plugin_release_notes.py', '--component', $componentName")
    assert notes < script.index("if (-not $HideReleaseNotes) {", notes) < dry_run


def test_plugin_requirements_never_exceed_what_the_site_code_provides() -> None:
    config = (ROOT / "backend/app/core/config.py").read_text(encoding="utf-8")
    # The owner console reads the deploy revision with this same pattern.
    console = (ROOT / "scripts/deploy-server.ps1").read_text(encoding="utf-8")
    pattern = r"(?m)^PLUGIN_API_LEVEL\s*=\s*(?<level>\d+)\s*$"
    assert pattern in console
    match = re.search(pattern.replace("?<level>", "?P<level>"), config)
    assert match
    site_level = int(match.group("level"))
    requirements = json.loads((ROOT / "scripts/plugin-required-api-level.json").read_text(encoding="utf-8"))

    # Print Farm talks to printers, not to the FilamentHub server.
    assert set(requirements) == {"orcaslicer", "octoprint"}
    for level in requirements.values():
        assert isinstance(level, int) and 1 <= level <= site_level
