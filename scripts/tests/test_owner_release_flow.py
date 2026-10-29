"""Offline regressions for the owner's single release entry point.

Only PowerShell function definitions are loaded; the site deploy, the plugin
release script and every owner answer are replaced by recorders, so nothing
reaches GitHub, the server or the terminal.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[2]
COMMIT = "c" * 40
RUNNER = r"""
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$script:WaitingPrefix = 'ОЖИДАНИЕ:'
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

$global:events = [System.Collections.Generic.List[string]]::new()
$global:plugins = $env:PLUGINS | ConvertFrom-Json
$global:keys = [System.Collections.Generic.Queue[string]]::new()
foreach ($key in @($env:KEYS -split ',' | Where-Object { $_ })) { $global:keys.Enqueue($key) }

function Write-Host { }
function Get-SiteReleasePlan {
    param([switch]$RebuildAll)
    $global:events.Add('site-check')
    if ($env:SITE_CHECK_FAILS) {
        Stop-WithFix -Problem 'site is not ready' -Fix 'fix the site'
    }
    [pscustomobject]@{
        Sha = 'b' * 40; ShortSha = 'bbbbbbbb'; CiUrl = 'https://example.invalid/ci'
        PluginApiLevel = [int]$env:SITE_LEVEL
        PreviousAttemptFailed = [bool]$env:SITE_PREVIOUS_FAILED
        AlreadyDeployed = $false
    }
}
function Invoke-PluginReleaseScript {
    param([string]$Id, [hashtable]$Arguments = @{})
    $spec = $global:plugins.$Id
    $wheel = Join-Path $env:WHEELS "$Id.whl"
    if ($Arguments['DryRun']) {
        $planned = if ($Arguments.ContainsKey('PlannedSiteApiLevel')) { $Arguments.PlannedSiteApiLevel } else { '' }
        $global:events.Add("check:${Id}:planned=$planned")
        if ($spec.status -eq 'FAIL') {
            Stop-WithFix -Problem "$Id is broken" -Fix "fix $Id"
        }
        if ($spec.status -eq 'CURRENT') {
            return [pscustomobject]@{ FilamentHubPluginReleaseResult = $true; Status = 'CURRENT'; Detail = 'nothing new' }
        }
        $hash = (Get-FileHash -LiteralPath $wheel -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($spec.PSObject.Properties['staleHash'] -and $spec.staleHash) { $hash = '0' * 64 }
        return [pscustomobject]@{
            FilamentHubPluginReleaseResult = $true; Status = 'READY'; Detail = 'ready'
            Id = $Id; Name = $Id; Version = '1.2.3'; Tag = 'v1.2.3'
            Repair = $false
            NeedsSiteDeploy = [bool]($spec.PSObject.Properties['needsSite'] -and $spec.needsSite)
            ReleaseCommit = $env:COMMIT; CandidateWheel = $wheel
            CandidateChecksums = "$wheel.sums"; Sha256 = $hash
        }
    }
    $global:events.Add("publish:${Id}:sha=$($Arguments.OwnerApprovedSha256[$Id]):commit=$($Arguments.ExpectedReleaseCommit)")
    if ($spec.PSObject.Properties['publishFails'] -and $spec.publishFails) { throw "$Id release failed" }
    return [pscustomobject]@{ FilamentHubPluginReleaseResult = $true; Status = 'RELEASED'; Detail = 'released' }
}
function Confirm-Action {
    param([string]$Question)
    $global:events.Add('confirm-site')
    return $env:SITE_ANSWER -ne 'no'
}
function Read-OwnerKey {
    $global:events.Add('key')
    $key = $global:keys.Dequeue()
    if ($key -eq 'CHANGE') {
        [IO.File]::WriteAllText((Join-Path $env:WHEELS 'orcaslicer.whl'), 'changed while confirming')
        return 'Y'
    }
    if ($key -eq 'ENTER') { return [char]13 }
    return $key
}
function Invoke-DurableProductionDeploy {
    param([string]$Revision, [switch]$RebuildAll, [switch]$RestartFailed)
    $global:events.Add("deploy:restart=$([bool]$RestartFailed)")
    if ($env:DEPLOY_FAILS) { throw 'deploy failed' }
}
function Show-ReleaseSummary {
    param([object[]]$States, [string]$Title)
    $global:summary = @($States | ForEach-Object {
        [pscustomobject]@{ id = $_.Id; status = $_.Status; fix = $_.Fix; detail = $_.Detail }
    })
}
function Test-DownloadPageRelease {
    param([string[]]$Plugins)
    $global:events.Add("download:$($Plugins -join ',')")
    return $true
}

$items = @($env:ITEMS -split ',' | Where-Object { $_ })
Invoke-Release -Items $items -CheckOnly:([bool]$env:CHECK_ONLY) | Out-Null
@{ events = @($global:events.ToArray()); summary = @($global:summary) } | ConvertTo-Json -Compress -Depth 4
"""


def run_release_with_summary(tmp_path: Path, items: str, plugins: dict, **environment: str) -> dict:
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if not shell:
        pytest.skip("PowerShell is required")
    wheels = tmp_path / "wheels"
    wheels.mkdir()
    for plugin in plugins:
        (wheels / f"{plugin}.whl").write_bytes(f"{plugin} candidate".encode())
    runner = tmp_path / "run.ps1"
    runner.write_text(RUNNER, encoding="utf-8-sig")
    result = subprocess.run(
        [shell, "-NoProfile", "-NonInteractive", "-File", str(runner)],
        capture_output=True, text=True, encoding="utf-8", timeout=60,
        env={
            **os.environ,
            "CONSOLE_SCRIPT": str(ROOT / "scripts/deploy-server.ps1"),
            "ITEMS": items,
            "PLUGINS": json.dumps(plugins),
            "WHEELS": str(wheels),
            "COMMIT": COMMIT,
            "SITE_LEVEL": "2",
            **environment,
        },
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


def run_release(tmp_path: Path, items: str, plugins: dict, **environment: str) -> list[str]:
    return run_release_with_summary(tmp_path, items, plugins, **environment)["events"]


def sha(plugin: str) -> str:
    return hashlib.sha256(f"{plugin} candidate".encode()).hexdigest()


def outcome(state: dict) -> dict:
    return {key: state[key] for key in ("id", "status", "fix")}


@pytest.mark.parametrize("key", ["Y", "y", "Д", "н", "L"])
def test_plugin_alone_asks_one_key_then_releases_the_checked_package(tmp_path, key):
    events = run_release(tmp_path, "orcaslicer", {"orcaslicer": {"status": "READY"}}, KEYS=key)

    assert events == [
        "check:orcaslicer:planned=",
        "key",
        f"publish:orcaslicer:sha={sha('orcaslicer')}:commit={COMMIT}",
        "download:orcaslicer",
    ]


@pytest.mark.parametrize("key", ["n", "ENTER", "?"])
def test_plugin_is_not_released_without_explicit_acceptance(tmp_path, key):
    events = run_release(tmp_path, "orcaslicer", {"orcaslicer": {"status": "READY"}}, KEYS=key)

    assert events == ["check:orcaslicer:planned=", "key"]


def test_package_changed_during_the_question_is_not_released(tmp_path):
    events = run_release(tmp_path, "orcaslicer", {"orcaslicer": {"status": "READY"}}, KEYS="CHANGE")

    assert not [event for event in events if event.startswith("publish:")]


def test_package_changed_after_the_check_is_never_offered(tmp_path):
    events = run_release(
        tmp_path, "orcaslicer", {"orcaslicer": {"status": "READY", "staleHash": True}}, KEYS="Y"
    )

    assert events == ["check:orcaslicer:planned="]


def test_nothing_new_asks_nothing(tmp_path):
    events = run_release(tmp_path, "orcaslicer", {"orcaslicer": {"status": "CURRENT"}})

    assert events == ["check:orcaslicer:planned="]


def test_unfinished_plugin_does_not_block_a_ready_one_and_unselected_ones_are_untouched(tmp_path):
    result = run_release_with_summary(
        tmp_path,
        "orcaslicer,octoprint",
        {"orcaslicer": {"status": "FAIL"}, "octoprint": {"status": "READY"}, "print-farm": {"status": "FAIL"}},
        KEYS="Y",
    )
    events = result["events"]

    assert events == [
        "check:orcaslicer:planned=",
        "check:octoprint:planned=",
        "key",
        f"publish:octoprint:sha={sha('octoprint')}:commit={COMMIT}",
        "download:octoprint",
    ]
    assert not [event for event in events if "print-farm" in event]
    assert [outcome(state) for state in result["summary"]] == [
        {"id": "orcaslicer", "status": "ERROR", "fix": "fix orcaslicer"},
        {"id": "octoprint", "status": "DONE", "fix": ""},
    ]


def test_site_goes_first_and_every_question_comes_before_any_change(tmp_path):
    events = run_release(
        tmp_path, "site,orcaslicer", {"orcaslicer": {"status": "READY", "needsSite": True}}, KEYS="Y"
    )

    assert events == [
        "site-check",
        "check:orcaslicer:planned=2",
        "confirm-site",
        "key",
        "deploy:restart=False",
        f"publish:orcaslicer:sha={sha('orcaslicer')}:commit={COMMIT}",
        "download:orcaslicer",
    ]


def test_plugin_needing_the_site_waits_when_the_site_is_declined(tmp_path):
    events = run_release(
        tmp_path, "site,orcaslicer", {"orcaslicer": {"status": "READY", "needsSite": True}},
        KEYS="Y", SITE_ANSWER="no",
    )

    assert events == ["site-check", "check:orcaslicer:planned=2", "confirm-site"]


def test_plugin_waiting_for_the_site_gets_the_exact_rerun_command(tmp_path):
    result = run_release_with_summary(
        tmp_path, "site,orcaslicer", {"orcaslicer": {"status": "READY", "needsSite": True}},
        KEYS="Y", SITE_ANSWER="no",
    )

    assert outcome(result["summary"][1]) == {
        "id": "orcaslicer", "status": "SKIPPED", "fix": r".\scripts\release.ps1 -Item site,orcaslicer",
    }


def test_failed_deploy_holds_back_only_plugins_that_need_the_new_site(tmp_path):
    events = run_release(
        tmp_path,
        "site,orcaslicer,octoprint",
        {"orcaslicer": {"status": "READY", "needsSite": True}, "octoprint": {"status": "READY"}},
        KEYS="Y,Y", DEPLOY_FAILS="1",
    )

    assert "deploy:restart=False" in events
    assert not [event for event in events if event.startswith("publish:orcaslicer")]
    assert f"publish:octoprint:sha={sha('octoprint')}:commit={COMMIT}" in events
    assert events.index("deploy:restart=False") > max(
        index for index, event in enumerate(events) if event in {"key", "confirm-site"}
    )


def test_failed_site_check_does_not_promise_a_new_site_to_plugins(tmp_path):
    events = run_release(
        tmp_path, "site,orcaslicer", {"orcaslicer": {"status": "READY"}},
        KEYS="Y", SITE_CHECK_FAILS="1",
    )

    assert events[:2] == ["site-check", "check:orcaslicer:planned="]
    assert not [event for event in events if event.startswith("deploy:")]


def test_previous_failed_deploy_is_restarted_only_through_the_upfront_question(tmp_path):
    events = run_release(tmp_path, "site", {}, SITE_PREVIOUS_FAILED="1")

    assert events == ["site-check", "confirm-site", "deploy:restart=True"]


def test_check_only_never_asks_or_changes_anything(tmp_path):
    events = run_release(
        tmp_path, "site,orcaslicer", {"orcaslicer": {"status": "READY"}}, CHECK_ONLY="1"
    )

    assert events == ["site-check", "check:orcaslicer:planned=2"]


def test_selection_menu_accepts_several_items_and_rejects_unknown_numbers(tmp_path):
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if not shell:
        pytest.skip("PowerShell is required")
    runner = tmp_path / "menu.ps1"
    runner.write_text(
        RUNNER.split("$global:events =", 1)[0]
        + r"""
function Write-Host { }
$global:answers = [System.Collections.Generic.Queue[string]]::new()
foreach ($answer in @('7', '2, 4', '0')) { $global:answers.Enqueue($answer) }
function Read-Host { param($Prompt) return $global:answers.Dequeue() }
$first = @(Read-ReleaseSelection)
$second = @(Read-ReleaseSelection)
@{ first = $first; second = $second } | ConvertTo-Json -Compress
""",
        encoding="utf-8-sig",
    )
    result = subprocess.run(
        [shell, "-NoProfile", "-NonInteractive", "-File", str(runner)],
        capture_output=True, text=True, encoding="utf-8", timeout=60,
        env={**os.environ, "CONSOLE_SCRIPT": str(ROOT / "scripts/deploy-server.ps1")},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    selection = json.loads(result.stdout.strip().splitlines()[-1])

    assert selection == {"first": ["orcaslicer", "print-farm"], "second": []}


def test_site_preflight_keeps_dry_run_output_out_of_the_plan(tmp_path):
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if not shell:
        pytest.skip("PowerShell is required")
    runner = tmp_path / "site-preflight.ps1"
    runner.write_text(
        RUNNER.split("$global:events =", 1)[0]
        + r"""
$global:hostOutput = [System.Collections.Generic.List[string]]::new()
function Out-Host { process { $global:hostOutput.Add([string]$_) } }
function Get-DeploymentCandidate {
    return [pscustomobject]@{
        Sha = 'c' * 40; ShortSha = 'cccccccc'; CiUrl = 'https://example.invalid/ci'
    }
}
function Invoke-RemoteWorker { 'server dry-run passed' }
function Invoke-DurableDeployCommand { return [pscustomobject]@{ Status = 'running' } }
function Get-ServerTarget { return 'server' }
function Invoke-Checked { return 'PLUGIN_API_LEVEL = 3' }
$plan = @(Get-SiteReleasePlan)
@{ count = $plan.Count; plan = $plan[0]; hostOutput = @($global:hostOutput) } |
    ConvertTo-Json -Compress -Depth 4
""",
        encoding="utf-8-sig",
    )
    temp_dir = str(tmp_path)
    result = subprocess.run(
        [shell, "-NoProfile", "-NonInteractive", "-File", str(runner)],
        capture_output=True, text=True, encoding="utf-8", timeout=60,
        env={
            **os.environ,
            "CONSOLE_SCRIPT": str(ROOT / "scripts/deploy-server.ps1"),
            "TEMP": temp_dir,
            "TMP": temp_dir,
        },
    )
    assert result.returncode == 0, result.stdout + result.stderr
    result_data = json.loads(result.stdout.strip().splitlines()[-1])

    assert result_data["count"] == 1
    assert result_data["plan"]["AlreadyDeployed"] is False
    assert result_data["plan"]["PluginApiLevel"] == 3
    assert result_data["hostOutput"] == ["server dry-run passed"]
