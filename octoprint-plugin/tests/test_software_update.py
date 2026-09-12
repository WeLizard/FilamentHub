from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import octoprint_filamenthub_bridge as bridge
import pytest
from octoprint.plugins.softwareupdate.version_checks import python_checker

ROOT = Path(__file__).resolve().parents[1]
REGISTRATION_DRAFT = ROOT / "extras" / "filamenthub_bridge.md"


class FakeResponse:
    def __init__(self, payload: object) -> None:
        self._payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self, size: int = -1) -> bytes:
        return self._payload[:size]


class ReleaseOpener:
    def __init__(self, pages: dict[int, object]) -> None:
        self.pages = pages
        self.requests = []

    def __call__(self, request, timeout: int):
        self.requests.append((request, timeout))
        page = int(parse_qs(urlparse(request.full_url).query)["page"][0])
        return FakeResponse(self.pages.get(page, []))


def release(
    tag: str,
    *,
    draft: bool = False,
    prerelease: bool = False,
    archive: bool = True,
) -> dict:
    version = tag.removeprefix(bridge.BRIDGE_RELEASE_TAG_PREFIX)
    archive_name = f"octoprint_filamenthubbridge-{version}.tar.gz"
    assets = []
    if archive:
        assets.append(
            {
                "name": archive_name,
                "browser_download_url": (
                    "https://github.com/WeLizard/FilamentHub/releases/download/"
                    f"{tag}/{archive_name}"
                ),
            }
        )
    return {
        "tag_name": tag,
        "name": f"Bridge {version}",
        "draft": draft,
        "prerelease": prerelease,
        "html_url": f"https://github.com/WeLizard/FilamentHub/releases/tag/{tag}",
        "assets": assets,
    }


def test_update_hook_uses_component_specific_checker_and_archive() -> None:
    update = bridge.FilamentHubBridgePlugin().get_update_information()

    assert set(update) == {"filamenthub_bridge"}
    check = update["filamenthub_bridge"]
    assert check == {
        "displayName": "FilamentHub Bridge",
        "displayVersion": bridge.PLUGIN_VERSION,
        "type": "python_checker",
        "python_checker": bridge.BRIDGE_RELEASE_CHECKER,
        "current": bridge.PLUGIN_VERSION,
        "pip": (
            "https://github.com/WeLizard/FilamentHub/releases/download/"
            "octoprint-v{target_version}/"
            "octoprint_filamenthubbridge-{target_version}.tar.gz"
        ),
    }
    assert (
        bridge.__plugin_hooks__["octoprint.plugin.softwareupdate.check_config"]()
        == update
    )


def test_checker_implements_octoprint_python_checker_contract() -> None:
    check = {
        "current": "0.1.5",
        "python_checker": bridge.BridgeReleaseChecker(
            opener=ReleaseOpener({1: [release("octoprint-v0.1.6")]})
        ),
    }

    information, is_current = python_checker.get_latest(
        "filamenthub_bridge", check, full_data=True, online=True
    )

    assert information["local"]["value"] == "0.1.5"
    assert information["remote"]["value"] == "0.1.6"
    assert is_current is False


def test_release_checker_ignores_other_components_and_uninstallable_releases() -> None:
    opener = ReleaseOpener(
        {
            1: [
                release("v9.0.0"),
                release("octoprint-v0.1.9", draft=True),
                release("octoprint-v0.1.8", prerelease=True),
                release("octoprint-v0.1.7", archive=False),
                release("octoprint-v0.2"),
                release("octoprint-v0.1.6"),
                release("octoprint-v0.1.5"),
            ]
        }
    )
    checker = bridge.BridgeReleaseChecker(opener=opener)

    information, is_current = checker.get_latest(
        "filamenthub_bridge", {"current": "0.1.5"}
    )

    assert information["remote"] == {
        "name": "Bridge 0.1.6",
        "value": "0.1.6",
        "release_notes": (
            "https://github.com/WeLizard/FilamentHub/releases/tag/octoprint-v0.1.6"
        ),
    }
    assert information["needs_online"] is True
    assert is_current is False
    assert len(opener.requests) == 1
    request, timeout = opener.requests[0]
    assert timeout == 15
    assert request.headers["User-agent"] == (
        f"OctoPrint-FilamentHubBridge/{bridge.PLUGIN_VERSION}"
    )


def test_release_checker_reads_later_pages_before_selecting_latest() -> None:
    unrelated = [release(f"v1.0.{index}") for index in range(100)]
    opener = ReleaseOpener({1: unrelated, 2: [release("octoprint-v0.1.6")]})

    information, is_current = bridge.BridgeReleaseChecker(opener=opener).get_latest(
        "filamenthub_bridge", {"current": "0.1.5"}
    )

    assert information["remote"]["value"] == "0.1.6"
    assert is_current is False
    assert [
        parse_qs(urlparse(request.full_url).query)["page"][0]
        for request, _timeout in opener.requests
    ] == ["1", "2"]


def test_release_checker_does_not_request_network_when_offline() -> None:
    def unexpected_request(*args, **kwargs):
        raise AssertionError("offline update check requested the network")

    information, is_current = bridge.BridgeReleaseChecker(
        opener=unexpected_request
    ).get_latest("filamenthub_bridge", {"current": "0.1.5"}, online=False)

    assert information["remote"]["value"] == "?"
    assert information["needs_online"] is True
    assert is_current is True


def test_release_checker_fails_closed_without_installable_bridge_release() -> None:
    opener = ReleaseOpener(
        {1: [release("v8.0.0"), release("octoprint-v0.1.6", archive=False)]}
    )

    information, is_current = bridge.BridgeReleaseChecker(opener=opener).get_latest(
        "filamenthub_bridge", {"current": "0.1.5"}
    )

    assert information["remote"] == {
        "name": "-",
        "value": None,
        "release_notes": None,
    }
    assert is_current is True


def test_release_checker_rejects_invalid_current_version() -> None:
    with pytest.raises(ValueError, match="Invalid current version"):
        bridge.BridgeReleaseChecker().get_latest(
            "filamenthub_bridge", {"current": "dev"}, online=False
        )


def test_control_and_registration_metadata_match_package() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]
    draft = REGISTRATION_DRAFT.read_text(encoding="utf-8")
    front_matter = draft.split("---", 2)[1]

    assert bridge.__plugin_author__ == project["authors"][0]["name"]
    assert bridge.__plugin_url__ == project["urls"]["Homepage"]
    assert bridge.__plugin_privacypolicy__ == project["urls"]["Privacy"]
    assert bridge.__plugin_license__ == project["license"]
    assert bridge.__plugin_pythoncompat__ == project["requires-python"]
    assert bridge.__plugin_version__ == project["version"]
    assert re.search(r"(?m)^id: filamenthub_bridge$", front_matter)
    assert re.search(
        rf"(?m)^archive: .*/octoprint-v{re.escape(bridge.PLUGIN_VERSION)}/"
        rf"octoprint_filamenthubbridge-{re.escape(bridge.PLUGIN_VERSION)}\.tar\.gz$",
        front_matter,
    )
    assert f"privacypolicy: {bridge.PLUGIN_PRIVACY_POLICY_URL}" in front_matter
    assert 'python: ">=3.9,<4"' in front_matter
    assert "/releases/latest/" not in draft
    assert "It does not upload G-code." in draft
