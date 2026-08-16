"""The refresh report is the only thing consulted before enriching the printer
catalog, so it has to name models correctly or an update silently never happens.
"""

from __future__ import annotations

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


def _bundle(path: Path, *, tree: str, vendors: dict[str, list[str]]) -> Path:
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


def test_report_separates_content_only_changes_from_new_models(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Upstream edits profile values far more often than it adds printers, and
    those two cases lead to opposite decisions."""
    current = _bundle(tmp_path / "current.zip", tree="old", vendors={"BBL": ["Bambu Lab A1"]})
    fresh = _bundle(tmp_path / "fresh.zip", tree="new", vendors={"BBL": ["Bambu Lab A1"]})

    assert refresh._report(current, fresh) is True

    out = capsys.readouterr().out
    assert "No printer models change" in out
    assert "added" not in out


def test_report_reports_nothing_to_import_for_an_identical_tree(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    current = _bundle(tmp_path / "current.zip", tree="same", vendors={"BBL": ["Bambu Lab A1"]})
    fresh = _bundle(tmp_path / "fresh.zip", tree="same", vendors={"BBL": ["Bambu Lab A1"]})

    assert refresh._report(current, fresh) is False
    assert "nothing to import" in capsys.readouterr().out
