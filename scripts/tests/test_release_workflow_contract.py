from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[2]


def run_offline_publication(tmp_path: Path, mode: str, scenario: str) -> dict:
    """Exercise the release functions with local assets and no external commands."""
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if not shell:
        pytest.skip("PowerShell is required for the offline publication contract")
    wheel_name = "filamenthub-1.2.3-py3-none-any.whl"
    approved_bytes = b"approved candidate fixture"
    expected_sha = hashlib.sha256(approved_bytes).hexdigest()
    assets = {wheel_name: approved_bytes}
    if scenario == "replaced_wheel_and_checksums":
        assets[wheel_name] = b"replacement candidate fixture"
    elif scenario == "wrong_version":
        assets = {"filamenthub-9.9.9-py3-none-any.whl": approved_bytes}
    elif scenario == "wrong_platform":
        assets = {"filamenthub-1.2.3-py2-none-any.whl": approved_bytes}
    elif scenario == "extra_matching_wheel":
        assets["filamenthub-1.2.3-py2-none-any.whl"] = approved_bytes
    elif scenario in {"extra_wheel", "unlisted_extra_wheel"}:
        assets["unrelated-1.2.3-py3-none-any.whl"] = approved_bytes
    fixture_dir = tmp_path / "release-assets"
    fixture_dir.mkdir()
    checksums = []
    for name, content in assets.items():
        (fixture_dir / name).write_bytes(content)
        if scenario == "unlisted_extra_wheel" and name.startswith("unrelated-"):
            continue
        checksums.append(f"{hashlib.sha256(content).hexdigest()}  {name}")
    (fixture_dir / "SHA256SUMS").write_text("\n".join(checksums), encoding="utf-8")
    if scenario == "manifest_mismatch":
        (fixture_dir / "SHA256SUMS").write_text(f"{'0' * 64}  {wheel_name}", encoding="utf-8")
    runner = tmp_path / "exercise-release.ps1"
    runner.write_text(
        r"""
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$script:Remote = 'origin'
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $env:RELEASE_SCRIPT, [ref]$tokens, [ref]$parseErrors
)
if ($parseErrors.Count) { throw ($parseErrors | Out-String) }
# Load function definitions only: the owner-run entry point must never execute.
foreach ($statement in $ast.EndBlock.Statements) {
    if ($statement -is [System.Management.Automation.Language.FunctionDefinitionAst]) {
        . ([scriptblock]::Create($statement.Extent.Text))
    }
}
$script:edits = [System.Collections.Generic.List[string]]::new()
$global:offlinePrompts = [System.Collections.Generic.List[string]]::new()
$global:menuCalls = [System.Collections.Generic.List[object]]::new()
$script:waits = 0
$script:release = [pscustomobject]@{
    tagName = 'v1.2.3'; isDraft = ($env:RELEASE_MODE -eq 'normal')
    isPrerelease = $false; publishedAt = '2026-01-01T00:00:00Z'
    url = 'https://example.invalid/release'
    assets = @(Get-ChildItem -LiteralPath $env:RELEASE_FIXTURES | ForEach-Object {
        [pscustomobject]@{ name = $_.Name }
    })
}
function Invoke-Checked {
    param($FilePath, $Arguments, $WorkingDirectory, [switch]$Capture)
    if ($FilePath -eq 'gh' -and $Arguments[0] -eq 'release') {
        if ($Arguments[1] -eq 'download') {
            $destination = $Arguments[[array]::IndexOf($Arguments, '--dir') + 1]
            Get-ChildItem -LiteralPath $env:RELEASE_FIXTURES | Copy-Item -Destination $destination
            return
        }
        if ($Arguments[1] -eq 'edit') {
            $script:edits.Add($Arguments[-1])
            $script:release.isDraft = $Arguments[-1] -eq '--draft'
            return
        }
    }
    if ($FilePath -eq 'git') {
        if ($Arguments -contains 'rev-parse' -or $Arguments -contains 'rev-list') {
            return 'approved-commit'
        }
        if ($Arguments -contains '--list') { return 'v1.2.3' }
    }
    throw "Unexpected external command: $FilePath $Arguments"
}
function Get-Release { param($Repository, $Tag) return $script:release }
function Wait-ForRelease {
    param($Repository, $Workflow, $TagCommit, $Tag, [switch]$AllowDraft, [switch]$RequireWorkflow)
    return $script:release
}
function Get-RemoteTagCommit { param($RepositoryPath, $RemoteName, $Tag) return 'approved-commit' }
function Ensure-LocalTag { param($RepositoryPath, $RemoteName, $Tag) }
function Assert-TrustedPublishRepairable { param($Name, $RepositoryPath, $Tag, $WorkflowPath) }
function Wait-ForWorkflowRun {
    param($Repository, $Workflow, $Event, $TagCommit, $Tag, $NotBefore)
    $script:waits += 1
}
# Retain temporary verification data under pytest's directory for inspection.
function Remove-Item { param($LiteralPath, [switch]$Recurse, [switch]$Force, $ErrorAction) }
function Read-OwnerApprovalKey {
    $global:offlinePrompts.Add('Confirm target-app test')
    switch ($env:RELEASE_SCENARIO) {
        'wrong_approval' { return 'n' }
        'malformed_approval' { return '?' }
        'empty_approval' { return [char]13 }
        'russian_approval' { return 'Д' }
        'changed_during_approval' {
            [IO.File]::WriteAllText(
                (Join-Path $env:RELEASE_FIXTURES 'filamenthub-1.2.3-py3-none-any.whl'),
                'changed while the owner was confirming'
            )
            return 'Y'
        }
        default { return 'Y' }
    }
}
$parameters = @{
    Name = 'Offline fixture'; RepositoryPath = $env:RELEASE_FIXTURES
    Repository = 'offline/fixture'; Tag = 'v1.2.3'
    TrustedPublishWorkflow = 'publish-orcacloud.yml'
    RequiredPatterns = @('^filamenthub-\d+\.\d+\.\d+-.*\.whl$', '^SHA256SUMS$')
    ForbiddenPatterns = @('^printers-', '^octoprint[-_]filamenthubbridge-')
}
if ($env:RELEASE_SCENARIO -ne 'missing_approval') {
    $parameters.ExpectedSha256 = $env:RELEASE_EXPECTED_SHA
    $parameters.ExpectedAssetPattern = '^filamenthub-1\.2\.3-py3-none-any\.whl$'
}
$failure = $null
$script:candidates = @()
try {
    if ($env:RELEASE_MODE -in @('preflight', 'menu')) {
        $script:candidates = @(
            [pscustomobject]@{
                Id = 'orcaslicer'; Name = 'Normal fixture'; Needed = $true; Repair = $false
                CandidateWheel = Join-Path $env:RELEASE_FIXTURES 'filamenthub-1.2.3-py3-none-any.whl'
                CandidateChecksums = Join-Path $env:RELEASE_FIXTURES 'SHA256SUMS'
            },
            [pscustomobject]@{
                Id = 'print-farm'; Name = 'Repair fixture'; Needed = $false; Repair = $true
                CandidateWheel = Join-Path $env:RELEASE_FIXTURES 'filamenthub-1.2.3-py3-none-any.whl'
                CandidateChecksums = Join-Path $env:RELEASE_FIXTURES 'SHA256SUMS'
            }
        )
        $approvals = @{ orcaslicer = $env:RELEASE_EXPECTED_SHA; 'print-farm' = $env:RELEASE_EXPECTED_SHA }
        switch ($env:RELEASE_SCENARIO) {
            'missing_approval' { $approvals = @{} }
            'missing_repair_approval' { $approvals.Remove('print-farm') }
            'wrong_approval' { $approvals['print-farm'] = '0' * 64 }
            'malformed_approval' { $approvals['print-farm'] = 'not-a-sha256' }
            'empty_approval' { $approvals['print-farm'] = '' }
            'noop' {
                foreach ($candidate in $script:candidates) {
                    $candidate.Needed = $false
                    $candidate.Repair = $false
                }
            }
        }
        if ($env:RELEASE_MODE -eq 'menu') {
            # Use the real parameter and approval entry-point statements, omitting
            # unrelated repository discovery, network calls and publication.
            $approvalStatement = @($ast.EndBlock.Statements | Where-Object {
                $_.Extent.Text -like 'Assert-OwnerApprovedCandidates -Plans*'
            })
            if ($approvalStatement.Count -ne 1) { throw 'Missing canonical approval entry point' }
            $dryRunStatement = @($ast.EndBlock.Statements | Where-Object {
                $_.Extent.Text.StartsWith('if ($DryRun)')
            })
            $global:offlineCandidates = $script:candidates
            $entryPoint = $ast.ParamBlock.Extent.Text + @'

$global:menuCalls.Add([pscustomobject]@{
    dryRun = [bool]$DryRun
    prompt = [bool]$PSBoundParameters['PromptForOwnerApproval']
    components = @($Component)
})
$plans = $global:offlineCandidates

'@ + $dryRunStatement[0].Extent.Text + "`n" + $approvalStatement[0].Extent.Text
            $entryPath = Join-Path $PSScriptRoot 'publish-plugin-releases.ps1'
            [System.IO.File]::WriteAllText($entryPath, $entryPoint, [System.Text.UTF8Encoding]::new($true))
            $menuAst = [System.Management.Automation.Language.Parser]::ParseFile(
                $env:MENU_SCRIPT, [ref]$tokens, [ref]$parseErrors
            )
            if ($parseErrors.Count) { throw ($parseErrors | Out-String) }
            $menuFunction = $menuAst.EndBlock.Statements | Where-Object {
                $_ -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
                $_.Name -eq 'Invoke-PluginReleasePreparation'
            }
            $menuSlicePath = Join-Path $PSScriptRoot 'menu-slice.ps1'
            [System.IO.File]::WriteAllText($menuSlicePath, $menuFunction.Extent.Text, [System.Text.UTF8Encoding]::new($true))
            . $menuSlicePath
            function Confirm-Action { param($Question) return $true }
            function Test-DownloadPageRelease { return $true }
            Invoke-PluginReleasePreparation
        } else {
            Assert-OwnerApprovedCandidates -Plans $script:candidates -ApprovedSha256 $approvals
        }
    } elseif ($env:RELEASE_MODE -eq 'repair') {
        Repair-TrustedPublishComponent @parameters
    } else {
        $parameters.Workflow = 'release-filamenthub.yml'
        $parameters.OwnerPublishesDraft = $true
        Publish-Component @parameters
    }
} catch {
    $failure = $_.Exception.Message
}
[pscustomobject]@{
    error = $failure; edits = @($script:edits.ToArray()); waits = $script:waits
    candidates = @($script:candidates)
    prompts = @($global:offlinePrompts.ToArray()); menuCalls = @($global:menuCalls.ToArray())
} | ConvertTo-Json -Compress -Depth 4
""",
        encoding="utf-8-sig",
    )
    env = dict(os.environ)
    env.update(
        RELEASE_SCRIPT=str(ROOT / "scripts/publish-plugin-releases.ps1"),
        MENU_SCRIPT=str(ROOT / "scripts/deploy-server.ps1"),
        RELEASE_FIXTURES=str(fixture_dir),
        RELEASE_MODE=mode,
        RELEASE_SCENARIO=scenario,
        RELEASE_EXPECTED_SHA=expected_sha,
        TEMP=str(tmp_path),
        TMP=str(tmp_path),
        TMPDIR=str(tmp_path),
    )
    result = subprocess.run(
        [shell, "-NoProfile", "-NonInteractive", "-File", str(runner)],
        capture_output=True, text=True, encoding="utf-8", env=env, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize("mode", ["normal", "repair"])
def test_owner_publication_accepts_only_the_unchanged_approved_wheel(tmp_path, mode):
    result = run_offline_publication(tmp_path, mode, "approved")

    assert result["error"] is None, result
    assert result["edits"] == (["--draft", "--draft=false"] if mode == "repair" else ["--draft=false"])
    assert result["waits"] == 1


@pytest.mark.parametrize("mode", ["normal", "repair"])
@pytest.mark.parametrize("scenario", [
    "replaced_wheel_and_checksums", "wrong_version", "wrong_platform",
    "extra_matching_wheel", "extra_wheel", "unlisted_extra_wheel", "missing_approval",
])
def test_owner_publication_rejects_unapproved_artifacts_before_release_edits(tmp_path, mode, scenario):
    result = run_offline_publication(tmp_path, mode, scenario)

    assert result["error"], result
    assert result["edits"] == [], result
    assert result["waits"] == 0, result


def test_owner_preflight_binds_normal_and_repair_to_approved_hash_and_filename(tmp_path):
    result = run_offline_publication(tmp_path, "preflight", "approved")

    assert result["error"] is None, result
    assert len(result["candidates"]) == 2
    for candidate in result["candidates"]:
        assert candidate["CandidateSha256"] == hashlib.sha256(b"approved candidate fixture").hexdigest()
        assert candidate["CandidateAssetPattern"] == r"^filamenthub-1\.2\.3-py3-none-any\.whl$"
    assert result["edits"] == []
    assert result["waits"] == 0


@pytest.mark.parametrize("scenario", [
    "missing_approval", "missing_repair_approval", "wrong_approval",
    "malformed_approval", "empty_approval", "replaced_wheel_and_checksums",
])
def test_owner_preflight_rejects_missing_or_changed_approval(tmp_path, scenario):
    result = run_offline_publication(tmp_path, "preflight", scenario)

    assert result["error"], result
    assert result["edits"] == []
    assert result["waits"] == 0


@pytest.mark.parametrize("scenario", ["approved", "russian_approval", "noop"])
def test_release_menu_computes_hashes_and_requests_one_key_for_actionable_plans(tmp_path, scenario):
    result = run_offline_publication(tmp_path, "menu", scenario)

    assert result["error"] is None, result
    assert result["menuCalls"] == [
        {"dryRun": False, "prompt": True, "components": ["all"]},
    ]
    assert len(result["prompts"]) == (0 if scenario == "noop" else 2)
    if scenario != "noop":
        for candidate in result["candidates"]:
            assert candidate["CandidateSha256"] == hashlib.sha256(b"approved candidate fixture").hexdigest()
    assert result["edits"] == []
    assert result["waits"] == 0


@pytest.mark.parametrize("scenario", ["wrong_approval", "malformed_approval", "empty_approval"])
def test_release_menu_does_not_publish_without_explicit_acceptance(tmp_path, scenario):
    result = run_offline_publication(tmp_path, "menu", scenario)

    assert result["error"], result
    assert len(result["prompts"]) == 1, result
    assert result["edits"] == []
    assert result["waits"] == 0


@pytest.mark.parametrize("scenario,prompts", [("manifest_mismatch", 0), ("changed_during_approval", 1)])
def test_release_menu_checks_manifest_before_acceptance_and_identity_after_it(tmp_path, scenario, prompts):
    result = run_offline_publication(tmp_path, "menu", scenario)

    assert result["error"], result
    assert len(result["prompts"]) == prompts
    assert result["edits"] == []
    assert result["waits"] == 0


def test_filamenthub_build_leaves_a_draft_for_owner_validation() -> None:
    workflow = (ROOT / ".github/workflows/release-filamenthub.yml").read_text(
        encoding="utf-8"
    )

    assert "--draft" in workflow
    assert "--draft=false" not in workflow
    assert "gh workflow run publish-orcacloud.yml" not in workflow
    assert "sha256sum --check SHA256SUMS" in workflow
    assert 'filamenthub/RELEASE_NOTES.md' in workflow


def test_octoprint_build_leaves_the_exact_candidate_as_a_draft() -> None:
    workflow = (ROOT / ".github/workflows/release-octoprint.yml").read_text(
        encoding="utf-8"
    )

    assert "octoprint-plugin/build_package.py" in workflow
    assert "sha256sum --check SHA256SUMS" in workflow
    assert "--draft" in workflow
    assert "--draft=false" not in workflow


def test_legacy_bundle_release_cannot_publish() -> None:
    workflow = (ROOT / ".github/workflows/release-plugins.yml").read_text(
        encoding="utf-8"
    )

    assert "push:" not in workflow
    assert "permissions: {}" in workflow
    assert "Mixed plugins-v* releases are disabled" in workflow
    assert "scripts/publish-plugin-releases.ps1" in workflow
    assert "actions/checkout" not in workflow
    assert "gh release" not in workflow


def test_orcacloud_publish_uses_only_the_release_oidc_event() -> None:
    workflow = (ROOT / ".github/workflows/publish-orcacloud.yml").read_text(
        encoding="utf-8"
    )

    assert "types: [published]" in workflow
    assert "workflow_dispatch:" not in workflow
    assert "id-token: write" in workflow
    assert "github.event.release.tag_name" in workflow
    assert '--form-string "metadata=$metadata"' in workflow
    assert '-F "metadata=$metadata"' not in workflow
    assert '--pattern "SHA256SUMS"' in workflow
    assert "GitHub wheel does not match SHA256SUMS" in workflow
    assert "Runtime plugin version does not match the GitHub release" in workflow
    assert "Wheel metadata version does not match the GitHub release" in workflow


def test_owner_script_publishes_after_asset_validation_and_waits_for_oidc() -> None:
    script = (ROOT / "scripts/publish-plugin-releases.ps1").read_text(
        encoding="utf-8"
    )

    validate_at = script.index("Assert-ReleaseAssets `")
    checksum_at = script.index("Assert-ReleaseChecksums `")
    publish_at = script.index("'--draft=false'")
    trusted_publish_at = script.index("Wait-ForWorkflowRun `")

    assert validate_at < checksum_at < publish_at < trusted_publish_at
    assert "-Event 'release'" in script
    assert "-NotBefore ([datetime]$release.publishedAt).AddSeconds(-5)" in script


def test_owner_script_preflights_literal_orcacloud_metadata() -> None:
    script = (ROOT / "scripts/publish-plugin-releases.ps1").read_text(
        encoding="utf-8"
    )

    assert "Assert-OrcaCloudPublishWorkflow" in script
    assert '--form-string "metadata=$metadata"' in script
    assert '-F "metadata=$metadata"' in script


def test_owner_script_requires_the_exact_owner_tested_wheel_before_push() -> None:
    script = (ROOT / "scripts/publish-plugin-releases.ps1").read_text(
        encoding="utf-8"
    )

    approval_gate = script.index("Assert-OwnerApprovedCandidates -Plans $plans")
    branch_push = script.index("'push', $Remote, $Branch")
    publish_call = script.index("Publish-Component @publish", approval_gate)

    assert approval_gate < branch_push
    assert approval_gate < publish_call
    assert script.index("if ($DryRun)") < approval_gate
    assert "orca-plugin/dist/release-$version/wheels/filamenthub-$version" in script
    assert "octoprint-plugin/dist/release-$version/octoprint_filamenthubbridge-$version" in script
    assert "plugins/printers/dist/release-$version/wheels/printers-$version" in script
    assert script.count("OwnerPublishesDraft = $true") == 3
    assert "отличается от локального wheel, проверенного владельцем" in script


def test_owner_script_repairs_only_tags_with_a_safe_trusted_workflow() -> None:
    script = (ROOT / "scripts/publish-plugin-releases.ps1").read_text(
        encoding="utf-8"
    )

    assert "Test-TrustedPublishNeedsRepair" in script
    assert "Repair-TrustedPublishComponent" in script
    assert "Assert-TrustedPublishRepairable" in script
    assert (
        'git @(\n            \'-C\', $RepositoryPath, \'show\', '
        '"${Tag}:$WorkflowPath"'
    ) in script
    assert "ПОВТОРИТЬ ORCACLOUD" in script
    repair = script.split("function Repair-TrustedPublishComponent", 1)[1].split(
        "\nAssert-Command git", 1
    )[0]
    validate_at = repair.index("Assert-ReleaseAssets `")
    checksum_at = repair.index("Assert-ReleaseChecksums `")
    tagged_workflow_at = repair.index("Assert-TrustedPublishRepairable `")
    draft_at = repair.index("'--draft'")
    republish_at = repair.index("'--draft=false'")
    wait_at = repair.index("Wait-ForWorkflowRun `")

    assert validate_at < checksum_at < tagged_workflow_at < draft_at < republish_at < wait_at
    assert "-ExpectedSha256 $ExpectedSha256 -ExpectedAssetPattern $ExpectedAssetPattern" in repair
    assert "-NotBefore $triggerStartedAt.AddSeconds(-5)" in repair

    classification = script.split("function Test-TrustedPublishNeedsRepair", 1)[
        1
    ].split("\nfunction Assert-CleanPaths", 1)[0]
    assert classification.index("$needsRepair") < classification.index(
        "Assert-TrustedPublishRepairable `"
    )


def test_print_farm_publish_contract_test_does_not_force_a_plugin_version() -> None:
    script = (ROOT / "scripts/publish-plugin-releases.ps1").read_text(
        encoding="utf-8"
    )

    assert "-IgnoredPaths @('plugins/printers/test_release_workflow.py', 'plugins/printers/build_package.py')" in script


def test_owner_script_uses_the_same_trusted_release_order_for_print_farm() -> None:
    script = (ROOT / "scripts/publish-plugin-releases.ps1").read_text(
        encoding="utf-8"
    )
    print_farm_case = script.rsplit("'print-farm' {", 1)[1].split("\n        }", 1)[0]

    assert "OwnerPublishesDraft = $true" in print_farm_case
    assert "TrustedPublishWorkflow = 'publish-orcacloud.yml'" in print_farm_case
    assert "Publish-Component @publish" in print_farm_case
