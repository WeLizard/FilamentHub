from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


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

    approval_gate = script.index("Get-LocalCandidateSha256 `")
    branch_push = script.index("'push', $Remote, $Branch")
    publish_call = script.index("Publish-Component @publish", approval_gate)

    assert approval_gate < branch_push
    assert approval_gate < publish_call
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
    tagged_workflow_at = repair.index("Assert-TrustedPublishRepairable `")
    draft_at = repair.index("'--draft'")
    republish_at = repair.index("'--draft=false'")
    wait_at = repair.index("Wait-ForWorkflowRun `")

    assert validate_at < tagged_workflow_at < draft_at < republish_at < wait_at
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

    assert "-IgnoredPaths @('plugins/printers/test_release_workflow.py')" in script


def test_owner_script_uses_the_same_trusted_release_order_for_print_farm() -> None:
    script = (ROOT / "scripts/publish-plugin-releases.ps1").read_text(
        encoding="utf-8"
    )
    print_farm_case = script.rsplit("'print-farm' {", 1)[1].split("\n        }", 1)[0]

    assert "OwnerPublishesDraft = $true" in print_farm_case
    assert "TrustedPublishWorkflow = 'publish-orcacloud.yml'" in print_farm_case
    assert "Publish-Component @publish" in print_farm_case
