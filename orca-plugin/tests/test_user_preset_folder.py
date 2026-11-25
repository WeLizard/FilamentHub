"""Where the managed bundle is written: the folder OrcaSlicer loads bundles from."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from .filamenthub_plugin_test_support import remove_host_attr, set_host_attr

ACCOUNT = "3141592653"


@pytest.fixture
def orca_data(plugin_module, monkeypatch, tmp_path):
    """OrcaSlicer's data folder with a signed-in account and no saved user preset."""
    plugin = plugin_module
    (tmp_path / "user" / "default").mkdir(parents=True)
    (tmp_path / "user" / ACCOUNT / "filament").mkdir(parents=True)
    state = SimpleNamespace(active=ACCOUNT, asked=0, logs=[])
    monkeypatch.setattr(plugin, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(plugin, "_user_preset_folder", None)
    monkeypatch.setattr(plugin, "_user_preset_folder_source", None)
    monkeypatch.setattr(plugin, "fh_log", state.logs.append)

    def list_ids():
        # As the host does: bundles of the active folder only, read from disk now.
        state.asked += 1
        local = tmp_path / "user" / state.active / "_local"
        if not local.is_dir():
            return []
        return sorted(
            entry.name for entry in local.iterdir()
            if (entry / "bundle_metadata.json").is_file()
            and json.loads((entry / "bundle_metadata.json").read_text(encoding="utf-8"))["id"]
            == entry.name
        )

    set_host_attr(monkeypatch, plugin.orca.host, "preset.bundles.list_ids", list_ids)
    return SimpleNamespace(plugin=plugin, root=tmp_path, state=state)


def _everything_under(root: Path) -> list[str]:
    return sorted(str(path.relative_to(root)).replace("\\", "/") for path in root.rglob("*"))


def test_stock_profiles_and_a_signed_in_account_still_get_their_presets(orca_data):
    # The reported case: nothing names the folder, the guess is "default", and
    # OrcaSlicer loads from the account's folder. Presets were written and never shown.
    plugin = orca_data.plugin
    before = _everything_under(orca_data.root)

    assert plugin.confirm_user_preset_folder() == ACCOUNT

    assert Path(plugin.user_bundle_dir()) == orca_data.root / "user" / ACCOUNT / "_local" / "filamenthub"
    # Asking leaves nothing behind in either folder.
    assert _everything_under(orca_data.root) == before
    # The folder's name is an account identifier: it is not written to the log.
    assert all(ACCOUNT not in line for line in orca_data.state.logs)


def test_signed_out_keeps_the_default_folder(orca_data):
    orca_data.state.active = "default"

    assert orca_data.plugin.confirm_user_preset_folder() == "default"


def test_another_account_signed_in_later_is_followed(orca_data):
    plugin = orca_data.plugin
    assert plugin.confirm_user_preset_folder() == ACCOUNT

    (orca_data.root / "user" / "2718281828").mkdir()
    orca_data.state.active = "2718281828"

    assert plugin.confirm_user_preset_folder() == "2718281828"


def test_a_saved_user_preset_decides_and_the_host_is_not_asked(orca_data, monkeypatch):
    plugin = orca_data.plugin
    saved = SimpleNamespace(
        is_user=lambda: True,
        file=str(orca_data.root / "user" / "default" / "filament" / "My PLA.json"),
    )
    collection = SimpleNamespace(size=lambda: 1, preset=lambda _index: saved)
    empty = SimpleNamespace(size=lambda: 0, preset=lambda _index: None)
    set_host_attr(
        monkeypatch, plugin.orca.host, "preset_bundle",
        lambda: SimpleNamespace(filaments=collection, printers=empty, prints=empty),
    )
    plugin.refresh_user_preset_folder()

    assert plugin.confirm_user_preset_folder() == "default"
    assert orca_data.state.asked == 0


def test_a_host_that_cannot_list_bundles_keeps_the_guess(orca_data, monkeypatch):
    plugin = orca_data.plugin
    remove_host_attr(monkeypatch, plugin.orca.host, "preset.bundles.list_ids")
    before = _everything_under(orca_data.root)

    assert plugin.confirm_user_preset_folder() == "default"
    assert _everything_under(orca_data.root) == before


def test_a_check_cut_short_earlier_is_cleared_away(orca_data):
    plugin = orca_data.plugin
    stale = orca_data.root / "user" / "default" / "_local" / "filamenthub-folder-check-deadbeef"
    stale.mkdir(parents=True)
    (stale / "bundle_metadata.json").write_text("{}", encoding="utf-8")

    plugin.confirm_user_preset_folder()

    assert not stale.exists()
