"""The refresh report is the only thing consulted before enriching the printer
catalog, so it has to name models correctly or an update silently never happens.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import zipfile
from pathlib import Path

import pytest

SCRIPT_PATH = (
    Path(__file__).resolve().parents[2] / "scripts" / "refresh_orca_catalog_source.py"
)
SPEC = importlib.util.spec_from_file_location("refresh_orca_catalog_source", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
refresh = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(refresh)


def _bundle(
    path: Path,
    *,
    tree: str,
    vendors: dict[str, list[str]],
    machine_profiles: dict[str, dict[str, dict]] | None = None,
) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            refresh.MANIFEST_NAME,
            json.dumps(
                {
                    "commit": f"commit-{tree}",
                    "commit_date": "2026-08-16T00:00:00+00:00",
                    "profiles_tree": tree,
                }
            ),
        )
        for vendor, models in vendors.items():
            archive.writestr(
                f"{vendor}.json",
                json.dumps(
                    {
                        "name": vendor,
                        "version": "01.00.00.00",
                        "machine_model_list": [
                            {"name": model, "sub_path": f"machine/{model}.json"}
                            for model in models
                        ],
                    }
                ),
            )
        for vendor, profiles in (machine_profiles or {}).items():
            for name, payload in profiles.items():
                archive.writestr(f"{vendor}/machine/{name}.json", json.dumps(payload))
    return path


def test_report_names_added_and_retired_printer_models(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    current = _bundle(
        tmp_path / "current.zip",
        tree="old",
        vendors={"BBL": ["Bambu Lab A1"], "Prusa": ["MK4S"]},
    )
    fresh = _bundle(
        tmp_path / "fresh.zip",
        tree="new",
        vendors={"BBL": ["Bambu Lab A1", "Bambu Lab H2D"], "Elegoo": ["Centauri"]},
    )

    assert refresh._report(current, fresh) is True

    out = capsys.readouterr().out
    assert "new vendors (1): Elegoo" in out
    assert "+ BBL · Bambu Lab H2D" in out
    assert "+ Elegoo · Centauri" in out
    assert "- Prusa · MK4S" in out
    assert "vendors gone (1): Prusa" in out


def test_report_shows_edited_printer_settings_when_no_model_is_added(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Nozzle, bed and speed values live inside the profiles, so an update is
    worth importing even when the model list stays the same."""
    current = _bundle(
        tmp_path / "current.zip",
        tree="old",
        vendors={"BBL": ["Bambu Lab A1"]},
        machine_profiles={"BBL": {"Bambu Lab A1 0.4 nozzle": {"speed": "100"}}},
    )
    fresh = _bundle(
        tmp_path / "fresh.zip",
        tree="new",
        vendors={"BBL": ["Bambu Lab A1"]},
        machine_profiles={"BBL": {"Bambu Lab A1 0.4 nozzle": {"speed": "120"}}},
    )

    assert refresh._report(current, fresh) is True

    out = capsys.readouterr().out
    assert "printer models: no change" in out
    assert "BBL · machine: 1 modified" in out
    assert "Bambu Lab A1 0.4 nozzle" in out


def test_report_reports_nothing_to_import_for_an_identical_tree(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    current = _bundle(tmp_path / "current.zip", tree="same", vendors={"BBL": ["Bambu Lab A1"]})
    fresh = _bundle(tmp_path / "fresh.zip", tree="same", vendors={"BBL": ["Bambu Lab A1"]})

    assert refresh._report(current, fresh) is False
    assert "nothing to import" in capsys.readouterr().out


def test_registry_mismatch_is_reported_when_the_archive_is_replaced(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The field registry is pinned to a bundle checksum, and the bundle is no
    longer versioned — without this warning a stale registry surfaces only as a
    failing test, long after whoever refreshed the source has moved on."""
    bundle = _bundle(tmp_path / "fresh.zip", tree="new", vendors={"BBL": ["Bambu Lab A1"]})
    registry = tmp_path / "orca_field_registry.py"
    registry.write_text(
        'ORCA_FIELD_REGISTRY_VERSION = (\n    "bundle-sha256:' + "0" * 64 + '"\n)\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(refresh, "FIELD_REGISTRY", registry)

    refresh._warn_if_registry_trails(bundle)

    out = capsys.readouterr().out
    assert "реестр полей OrcaSlicer отстал" in out
    assert "test_registry_version_matches_bundled_orca_catalog" in out


def test_registry_in_step_with_the_archive_stays_quiet(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = _bundle(tmp_path / "fresh.zip", tree="new", vendors={"BBL": ["Bambu Lab A1"]})
    digest = hashlib.sha256(bundle.read_bytes()).hexdigest()
    registry = tmp_path / "orca_field_registry.py"
    registry.write_text(
        f'ORCA_FIELD_REGISTRY_VERSION = (\n    "bundle-sha256:{digest}"\n)\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(refresh, "FIELD_REGISTRY", registry)

    refresh._warn_if_registry_trails(bundle)

    assert capsys.readouterr().out == ""
