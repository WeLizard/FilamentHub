from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_filamenthub_build_leaves_a_draft_for_owner_validation() -> None:
    workflow = (ROOT / ".github/workflows/release-filamenthub.yml").read_text(
        encoding="utf-8"
    )

    assert "--draft" in workflow
    assert "--draft=false" not in workflow
    assert "gh workflow run publish-orcacloud.yml" not in workflow


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


def test_owner_script_publishes_after_asset_validation_and_waits_for_oidc() -> None:
    script = (ROOT / "scripts/publish-plugin-releases.ps1").read_text(
        encoding="utf-8"
    )

    validate_at = script.index("Assert-ReleaseAssets `")
    publish_at = script.index("'--draft=false'")
    trusted_publish_at = script.index("Wait-ForWorkflowRun `")

    assert validate_at < publish_at < trusted_publish_at
    assert "-Event 'release'" in script
    assert "-NotBefore ([datetime]$release.publishedAt).AddSeconds(-5)" in script


def test_owner_script_preflights_literal_orcacloud_metadata() -> None:
    script = (ROOT / "scripts/publish-plugin-releases.ps1").read_text(
        encoding="utf-8"
    )

    assert "Assert-OrcaCloudPublishWorkflow" in script
    assert '--form-string "metadata=$metadata"' in script
    assert '-F "metadata=$metadata"' in script


def test_owner_script_repairs_a_failed_trusted_release_without_a_version_bump() -> None:
    script = (ROOT / "scripts/publish-plugin-releases.ps1").read_text(
        encoding="utf-8"
    )

    assert "Test-TrustedPublishNeedsRepair" in script
    assert "Repair-TrustedPublishComponent" in script
    assert "ПОВТОРИТЬ ORCACLOUD" in script
    repair = script.split("function Repair-TrustedPublishComponent", 1)[1].split(
        "\nAssert-Command git", 1
    )[0]
    validate_at = repair.index("Assert-ReleaseAssets `")
    draft_at = repair.index("'--draft'")
    republish_at = repair.index("'--draft=false'")
    wait_at = repair.index("Wait-ForWorkflowRun `")

    assert validate_at < draft_at < republish_at < wait_at
    assert "-NotBefore $triggerStartedAt.AddSeconds(-5)" in repair


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
