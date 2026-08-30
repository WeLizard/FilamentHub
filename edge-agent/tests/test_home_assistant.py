"""Protect discoverability, translated options and a least-privilege HA install."""

from __future__ import annotations

import json
import struct
from pathlib import Path
from unittest.mock import patch

import yaml

from filamenthub_edge.config import NodeConfig

EDGE_ROOT = Path(__file__).resolve().parents[1]
APP = EDGE_ROOT / "home-assistant/filamenthub_edge"


def test_repository_and_settings_are_usable_by_the_common_runtime(tmp_path):
    repository = yaml.safe_load((EDGE_ROOT.parent / "repository.yaml").read_text(encoding="utf-8"))
    assert repository == yaml.safe_load(
        (EDGE_ROOT / "home-assistant/repository.yaml").read_text(encoding="utf-8")
    )
    config = yaml.safe_load((APP / "config.yaml").read_text(encoding="utf-8"))
    assert config["slug"] == "filamenthub_edge"
    assert config["image"] == "ghcr.io/welizard/filamenthub-edge"
    assert set(config["arch"]) == {"amd64", "aarch64"}
    assert config["timeout"] >= 210
    assert config["backup"] == "cold"
    for permission in (
        "host_network",
        "hassio_api",
        "homeassistant_api",
        "docker_api",
        "full_access",
        "privileged",
        "map",
        "ports",
        "ingress",
    ):
        assert not config.get(permission), permission
    assert config.get("apparmor", True) is True

    options = config["options"]
    assert options["allow_insecure_cloud"] is False
    options["connections"] = [
        {"id": "mmu", "material_provider": "happy_hare", "moonraker_url": "http://mmu.invalid"},
        {"id": "direct", "material_provider": "legacy", "moonraker_url": "http://direct.invalid"},
    ]
    path = tmp_path / "options.json"
    path.write_text(json.dumps(options), encoding="utf-8")
    with patch.dict("os.environ", {"FH_EDGE_OPTIONS_FILE": str(path)}, clear=True):
        parsed = NodeConfig.load()
    assert [c.connection_id for c in parsed.connections] == ["mmu", "direct"]
    assert all(c.enabled and c.adapter == "moonraker" for c in parsed.connections)

    for language in ("en", "ru", "zh"):
        translated = yaml.safe_load((APP / f"translations/{language}.yaml").read_text("utf-8"))
        fields = translated["configuration"]
        assert fields.keys() == config["schema"].keys()
        assert fields["connections"]["fields"].keys() == config["schema"]["connections"][0].keys()
        for item in [*fields.values(), *fields["connections"]["fields"].values()]:
            assert item["name"] and item["description"]


def test_app_presentation_is_shipped_with_all_supported_languages():
    # A missing app-local README makes the local HA package show runtime-only instructions.
    for name in ("README.md", "DOCS.md"):
        content = (APP / name).read_text(encoding="utf-8")
        for heading in ("## Русский", "## English", "## 中文"):
            assert heading in content, (name, heading)
    for name in ("icon.png", "logo.png"):
        data = (APP / name).read_bytes()
        assert data[:8] == b"\x89PNG\r\n\x1a\n", name
        width, height = struct.unpack(">II", data[16:24])
        assert width > 0 and height > 0, name
        if name == "icon.png":
            assert width >= 128 and width == height
