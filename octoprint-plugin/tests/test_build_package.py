from __future__ import annotations

import csv
import hashlib
import importlib.util
import io
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILD_PATH = ROOT / "build_package.py"


def _load_builder():
    spec = importlib.util.spec_from_file_location("octoprint_build_under_test", BUILD_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_bridge_wheel_is_reproducible_and_self_consistent(tmp_path: Path) -> None:
    builder = _load_builder()
    first_wheel, _ = builder.build(tmp_path / "first")
    second_wheel, _ = builder.build(tmp_path / "second")

    assert first_wheel.read_bytes() == second_wheel.read_bytes()
    version = builder.current_version()
    dist_info = f"octoprint_filamenthubbridge-{version}.dist-info"
    with zipfile.ZipFile(first_wheel) as archive:
        names = set(archive.namelist())
        metadata = archive.read(f"{dist_info}/METADATA")
        wheel_metadata = archive.read(f"{dist_info}/WHEEL")
        record = list(
            csv.reader(
                io.StringIO(
                    archive.read(f"{dist_info}/RECORD").decode("utf-8")
                )
            )
        )
        assert {entry.compress_type for entry in archive.infolist()} == {
            zipfile.ZIP_STORED
        }
        assert {entry.date_time for entry in archive.infolist()} == {
            builder.FIXED_ZIP_TIMESTAMP
        }
    assert f"Version: {version}\n".encode() in metadata
    assert b"Tag: py3-none-any\n" in wheel_metadata
    assert {row[0] for row in record} == names
    assert {
        "octoprint_filamenthub_bridge/translations/ru/LC_MESSAGES/messages.mo",
        "octoprint_filamenthub_bridge/translations/zh_CN/LC_MESSAGES/messages.mo",
    }.issubset(names)


def test_bridge_release_bundle_has_versioned_path_notes_and_hashes(
    tmp_path: Path,
) -> None:
    builder = _load_builder()
    version = builder.current_version()
    assert builder.default_release_output_root() == (
        ROOT / "dist" / f"release-{version}"
    )
    output_root = tmp_path / f"release-{version}"
    wheel, sdist = builder.build(output_root)
    notes, checksums = builder.stage_release_metadata(output_root, wheel, sdist)

    assert notes.read_text(encoding="utf-8").startswith(
        f"## FilamentHub Bridge for OctoPrint {version}\n"
    )
    expected = "".join(
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n"
        for path in (wheel, sdist)
    )
    assert checksums.read_text(encoding="utf-8") == expected
