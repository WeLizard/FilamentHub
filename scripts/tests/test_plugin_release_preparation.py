"""Regressions for independent release checks and published-version reuse."""

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
    $env:RELEASE_SCRIPT, [ref]$tokens, [ref]$errors
)
if ($errors.Count) { throw ($errors | Out-String) }
foreach ($statement in $ast.EndBlock.Statements) {
    if ($statement -is [System.Management.Automation.Language.FunctionDefinitionAst]) {
        . ([scriptblock]::Create($statement.Extent.Text))
    }
}
"""


def run_ps(tmp_path, body, **environment):
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if not shell:
        pytest.skip("PowerShell is required")
    runner = tmp_path / "run.ps1"
    runner.write_text(LOAD_FUNCTIONS + body, encoding="utf-8-sig")
    result = subprocess.run(
        [shell, "-NoProfile", "-NonInteractive", "-File", str(runner)],
        capture_output=True, text=True, encoding="utf-8", timeout=30,
        env={**os.environ, "RELEASE_SCRIPT": str(ROOT / "scripts/publish-plugin-releases.ps1"), **environment},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize("mode", ["dry", "publish", "publication_failure"])
def test_batch_checks_every_component_and_only_publishes_successful_ones(tmp_path, mode):
    result = run_ps(tmp_path, r"""
$global:events = [System.Collections.Generic.List[string]]::new()
# Keep the actual dispatch entry point, replacing only each component's I/O.
$selectedStatement = @($ast.EndBlock.Statements | Where-Object {
    $_.Extent.Text.StartsWith('$selected =')
})[0]
$dispatch = @($ast.EndBlock.Statements | Where-Object {
    $_.Extent.Text.StartsWith('if ($selected.Count -gt 1)')
})[0]
$batch = $ast.EndBlock.Statements | Where-Object {
    $_ -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
    $_.Name -eq 'Invoke-ReleaseBatch'
}
$entry = $ast.ParamBlock.Extent.Text + "`n" + $batch.Extent.Text + "`n" +
    $selectedStatement.Extent.Text + "`n" + $dispatch.Extent.Text + @'

$phase = if ($DryRun) { 'check' } else { 'publish' }
$global:events.Add("${phase}:$($Component[0])")
if ($Component[0] -eq 'octoprint') { throw 'version must change' }
if (-not $DryRun -and $Component[0] -eq 'orcaslicer' -and $env:BATCH_MODE -eq 'publication_failure') {
    throw 'build workflow failed'
}
'@
$entryPath = Join-Path $PSScriptRoot 'entry.ps1'
[IO.File]::WriteAllText($entryPath, $entry, [Text.UTF8Encoding]::new($true))
$failure = $null
try { & $entryPath -DryRun:($env:BATCH_MODE -eq 'dry') } catch { $failure = $_.Exception.Message }
@{ error = $failure; events = @($global:events.ToArray()) } | ConvertTo-Json -Compress
""", BATCH_MODE=mode)
    assert result["error"]
    expected = ["check:orcaslicer", "check:octoprint", "check:print-farm"]
    if mode != "dry":
        expected += ["publish:orcaslicer", "publish:print-farm"]
    assert result["events"] == expected


@pytest.mark.parametrize("current,published,changed,expected", [
    ("1.2.3", "1.2.3", "plugin/runtime.py", "error"),
    ("1.2.4", "1.2.3", "plugin/runtime.py", True),
    ("1.2.3", "1.2.3", "plugin/tests/test_runtime.py", False),
    ("1.2.3", "1.2.4", "", "error"),
    ("0.1.0", "", "plugin/runtime.py", True),
])
def test_version_choice_preserves_unpublished_candidates_and_rejects_reuse(
    tmp_path, current, published, changed, expected,
):
    result = run_ps(tmp_path, r"""
function Ensure-LocalTag { param($RepositoryPath, $RemoteName, $Tag) }
function Invoke-Checked {
    param($FilePath, $Arguments, [switch]$Capture)
    if ($Arguments -contains 'diff') {
        if ($Arguments -contains 'v1.2.3..HEAD') { throw 'working tree was ignored' }
        return ''
    }
    if ($Arguments -contains 'ls-files') { return $env:CHANGED_PATH }
    throw 'Unexpected command'
}
$published = if ($env:PUBLISHED_VERSION) {
    [pscustomobject]@{ Version = $env:PUBLISHED_VERSION; Tag = 'v1.2.3' }
} else { $null }
$value = $null
$failure = $null
try {
    $value = Test-ComponentNeedsRelease -Name Fixture -CurrentVersion $env:CURRENT_VERSION `
        -Published $published -RepositoryPath $PSScriptRoot -RemoteName origin -SourcePaths @('plugin')
} catch { $failure = $_.Exception.Message }
@{ value = $value; error = $failure } | ConvertTo-Json -Compress
""", CURRENT_VERSION=current, PUBLISHED_VERSION=published, CHANGED_PATH=changed)
    if expected == "error":
        assert result["error"]
    else:
        assert result == {"value": expected, "error": None}


@pytest.mark.parametrize("scenario", ["pages", "network", "empty", "missing_wheel"])
def test_release_lookup_reads_all_pages_and_fails_closed(tmp_path, scenario):
    result = run_ps(tmp_path, r"""
function Invoke-Checked {
    param($FilePath, $Arguments, [switch]$Capture)
    if ($Arguments -notcontains '--paginate' -or $Arguments -notcontains '--slurp') {
        throw 'Pagination is required'
    }
    switch ($env:LOOKUP_CASE) {
        'network' { throw 'GitHub is unavailable' }
        'empty' { return '[[]]' }
        'missing_wheel' {
            return '[[{"draft":false,"prerelease":false,"tag_name":"v1.2.3","assets":[]}]]'
        }
        default {
            return '[[{"draft":false,"prerelease":false,"tag_name":"v1.2.3","html_url":"https://example.invalid/old","published_at":"2026-01-02","assets":[{"name":"fixture-1.2.3-py3-none-any.whl"}]}],[{"draft":false,"prerelease":false,"tag_name":"v1.2.4","html_url":"https://example.invalid/new","published_at":"2026-01-01","assets":[{"name":"fixture-1.2.4-py3-none-any.whl"}]}]]'
        }
    }
}
$release = $null
$failure = $null
try {
    $release = Get-PublishedComponent -Repository fixture/repo `
        -AssetPattern '^fixture-(?<version>\d+\.\d+\.\d+)-.*\.whl$' -TagPatterns @('^v\d+\.\d+\.\d+$')
} catch { $failure = $_.Exception.Message }
@{ release = $release; error = $failure } | ConvertTo-Json -Compress
""", LOOKUP_CASE=scenario)
    if scenario in {"network", "missing_wheel"}:
        assert result["error"]
    else:
        assert result["error"] is None
        if scenario == "empty":
            assert result["release"] is None
        else:
            assert result["release"]["Version"] == "1.2.4"


def test_plugin_release_never_pushes_a_branch() -> None:
    script = (ROOT / "scripts/publish-plugin-releases.ps1").read_text(encoding="utf-8")

    assert "'push', $Remote, $Branch" not in script
    assert "Assert-ReleaseCommitPublished" in script


def test_batch_summary_distinguishes_current_ready_and_released_components() -> None:
    script = (ROOT / "scripts/publish-plugin-releases.ps1").read_text(encoding="utf-8")

    for status in ("CURRENT", "READY", "RELEASED"):
        assert f"Status = '{status}'" in script
    assert "Status = 'OK'; Detail = 'выпуск'" not in script
