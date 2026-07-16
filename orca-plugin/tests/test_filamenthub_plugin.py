from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_PATH = PLUGIN_ROOT / "filamenthub_plugin.py"
BUILD_PATH = PLUGIN_ROOT / "build_package.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def plugin_module():
    fake_orca = ModuleType("orca")
    fake_orca.base = object
    fake_orca.plugin = lambda cls: cls
    fake_orca.register_capability = lambda _capability: None
    fake_orca.script = SimpleNamespace(ScriptPluginCapabilityBase=object)
    fake_orca.host = SimpleNamespace(ui=SimpleNamespace())
    fake_orca.ExecutionResult = SimpleNamespace(success=lambda message: message)
    previous = sys.modules.get("orca")
    sys.modules["orca"] = fake_orca
    try:
        yield _load_module(PLUGIN_PATH, "filamenthub_plugin_under_test")
    finally:
        if previous is None:
            sys.modules.pop("orca", None)
        else:
            sys.modules["orca"] = previous


def test_pep723_and_runtime_versions_match(plugin_module):
    builder = _load_module(BUILD_PATH, "filamenthub_build_under_test")
    source = PLUGIN_PATH.read_text(encoding="utf-8")
    metadata = builder.extract_metadata(source)
    assert metadata["tool"]["orcaslicer"]["plugin"]["version"] == plugin_module.PLUGIN_VERSION
    assert metadata["tool"]["orcaslicer"]["plugin"]["network"] == [
        "filamenthub.ru",
        "*.filamenthub.ru",
    ]
    assert metadata["dependencies"] == []


def test_shell_accepts_messages_only_from_catalog_frame(plugin_module):
    assert "event.source !== frame.contentWindow" in plugin_module.PAGE
    assert "event.origin !== SITE_ORIGIN" in plugin_module.PAGE


def test_safe_filename_handles_windows_names_and_bounds(plugin_module):
    assert plugin_module.safe_filename("CON") == "_CON"
    assert plugin_module.safe_filename('bad<>:"/\\|?* name. ') == "bad_________ name"
    assert len(plugin_module.safe_filename("x" * 500)) == plugin_module.MAX_FILENAME_LENGTH


def test_preset_paths_are_stable_and_collision_resistant(plugin_module, tmp_path):
    # The file stem is the preset's display name in OrcaSlicer — a free name
    # stays clean, and re-resolving for the same id returns the same path.
    first = plugin_module.preset_file_path(str(tmp_path), "Generic PLA", 10)
    assert first.endswith("Generic PLA.json")
    (tmp_path / "Generic PLA.json").write_text(
        json.dumps({"bundle_id": "filamenthub:10"}), encoding="utf-8"
    )
    assert plugin_module.preset_file_path(str(tmp_path), "Generic PLA", 10) == first
    # A name owned by a different preset (another FilamentHub id or a foreign
    # user preset) is never overwritten — the new file gets a stable suffix.
    second = plugin_module.preset_file_path(str(tmp_path), "Generic PLA", 11)
    assert second.endswith("Generic PLA (FH-11).json")
    (tmp_path / "User PETG.json").write_text(json.dumps({"name": "User PETG"}), encoding="utf-8")
    foreign = plugin_module.preset_file_path(str(tmp_path), "User PETG", 12)
    assert foreign.endswith("User PETG (FH-12).json")


def test_stale_preset_files_are_removed_after_rename(plugin_module, tmp_path):
    plugin_module.remove_host_filament = lambda name: False
    (tmp_path / "Old Name__fh_10.json").write_text(
        json.dumps({"bundle_id": "filamenthub:10"}), encoding="utf-8"
    )
    (tmp_path / "Old Name__fh_10.info").write_text("meta", encoding="utf-8")
    keep = plugin_module.preset_file_path(str(tmp_path), "New Name", 10)
    plugin_module.write_json_atomic(keep, {"bundle_id": "filamenthub:10", "name": "New Name"})
    plugin_module.remove_stale_preset_files(str(tmp_path), 10, keep)
    remaining = sorted(p.name for p in tmp_path.iterdir())
    assert remaining == ["New Name.json"]


def test_profile_payload_must_be_an_object(plugin_module):
    with pytest.raises(ValueError, match="JSON object"):
        plugin_module.validate_filament_profile([])
    with pytest.raises(ValueError, match="non-empty string"):
        plugin_module.validate_filament_profile({"name": ""})
    profile = {"name": "PLA", "inherits": "Generic PLA"}
    assert plugin_module.validate_filament_profile(profile) is profile


def test_atomic_json_write_replaces_complete_file(plugin_module, tmp_path):
    target = tmp_path / "state.json"
    plugin_module.write_json_atomic(str(target), {"version": 1})
    plugin_module.write_json_atomic(str(target), {"version": 2, "name": "FilamentHub"})
    assert json.loads(target.read_text(encoding="utf-8")) == {
        "version": 2,
        "name": "FilamentHub",
    }
    assert list(tmp_path.glob("*.tmp.*")) == []


def test_build_produces_single_file_package_and_checksum(plugin_module, tmp_path):
    builder = _load_module(BUILD_PATH, "filamenthub_build_package_test")
    package_dir = builder.build(tmp_path)
    package = package_dir / "filamenthub_plugin.py"
    metadata = json.loads((package_dir / "package-metadata.json").read_text(encoding="utf-8"))
    digest = hashlib.sha256(package.read_bytes()).hexdigest()
    assert metadata["version"] == plugin_module.PLUGIN_VERSION
    assert metadata["network"] == ["filamenthub.ru", "*.filamenthub.ru"]
    assert metadata["sha256"] == digest
    assert (package_dir / "SHA256SUMS").read_text(encoding="utf-8") == (
        f"{digest}  filamenthub_plugin.py\n"
    )
