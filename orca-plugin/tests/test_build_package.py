"""Plugin package and release artifact contracts."""

from .filamenthub_plugin_test_support import (
    base64,
    BUILD_PATH,
    csv,
    hashlib,
    io,
    json,
    _load_module,
    zipfile,
)


def test_build_packages_locale_catalogs_and_checksums(
    plugin_module, monkeypatch, tmp_path
):
    builder = _load_module(BUILD_PATH, "filamenthub_build_package_test")
    locale_source = tmp_path / "locale-source" / "filamenthub_locales"
    locale_source.mkdir(parents=True)
    for source_path in builder.LOCALES.glob("*.json"):
        (locale_source / source_path.name).write_bytes(source_path.read_bytes())
    cache_dir = locale_source / "__pycache__"
    cache_dir.mkdir()
    (cache_dir / "catalog.cpython-313.pyc").write_bytes(b"stale")
    (locale_source / "catalog.pyc").write_bytes(b"stale")
    monkeypatch.setattr(builder, "LOCALES", locale_source)

    stale_package = tmp_path / f"filamenthub-{plugin_module.PLUGIN_VERSION}"
    (stale_package / "__pycache__").mkdir(parents=True)
    (stale_package / "__pycache__" / "plugin.pyc").write_bytes(b"stale")
    (stale_package / "stale.txt").write_text("stale", encoding="utf-8")
    package_dir = builder.build(tmp_path)
    package = package_dir / "filamenthub_plugin.py"
    metadata = json.loads((package_dir / "package-metadata.json").read_text(encoding="utf-8"))
    digest = hashlib.sha256(package.read_bytes()).hexdigest()
    assert metadata["version"] == plugin_module.PLUGIN_VERSION
    assert metadata["network"] == ["filamenthub.ru", "*.filamenthub.ru"]
    assert metadata["sha256"] == digest
    expected_locales = sorted(plugin_module.ORCA_UI_LOCALES)
    assert metadata["locales"] == expected_locales
    locale_dir = package_dir / "filamenthub_locales"
    assert {path.name for path in locale_dir.glob("*.json")} == {
        f"{locale}.json" for locale in expected_locales
    }
    checksums = (package_dir / "SHA256SUMS").read_text(encoding="utf-8")
    assert f"{digest}  filamenthub_plugin.py\n" in checksums
    assert "filamenthub_locales/ru.json" in checksums
    assert not (package_dir / "stale.txt").exists()
    assert not any(path.name == "__pycache__" for path in package_dir.rglob("*"))
    assert not any(path.suffix in {".pyc", ".pyo"} for path in package_dir.rglob("*"))

    wheel = tmp_path / "wheels" / (
        f"filamenthub-{plugin_module.PLUGIN_VERSION}-py3-none-any.whl"
    )
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        wheel_source = archive.read("filamenthub_plugin.py")
        metadata_path = (
            f"filamenthub-{plugin_module.PLUGIN_VERSION}.dist-info/METADATA"
        )
        metadata_bytes = archive.read(metadata_path)
        record_rows = list(csv.reader(io.StringIO(
            archive.read(
                f"filamenthub-{plugin_module.PLUGIN_VERSION}.dist-info/RECORD"
            ).decode("utf-8"),
            newline="",
        )))
        top_level = archive.read(
            f"filamenthub-{plugin_module.PLUGIN_VERSION}.dist-info/top_level.txt"
        )
        wheel_metadata = archive.read(
            f"filamenthub-{plugin_module.PLUGIN_VERSION}.dist-info/WHEEL"
        )
        compression_types = {entry.compress_type for entry in archive.infolist()}
        timestamps = {entry.date_time for entry in archive.infolist()}
    assert b"\r" not in wheel_source
    assert b"_EMBEDDED_UI_COPY = {}" not in wheel_source
    assert b'os.environ.get("FILAMENTHUB_SITE_URL", "https://filamenthub.ru")' in wheel_source
    assert b"http://localhost:3000" not in wheel_source
    assert b"filamenthub.club" not in wheel_source
    assert b"\r" not in metadata_bytes
    metadata_row = next(row for row in record_rows if row[0] == metadata_path)
    expected_metadata_digest = base64.urlsafe_b64encode(
        hashlib.sha256(metadata_bytes).digest()
    ).rstrip(b"=").decode("ascii")
    assert metadata_row[1] == f"sha256={expected_metadata_digest}"
    assert metadata_row[2] == str(len(metadata_bytes))
    assert top_level == b"filamenthub_plugin\n"
    assert b"Generator: filamenthub build_package.py\n" in wheel_metadata
    assert compression_types == {zipfile.ZIP_STORED}
    assert timestamps == {(1980, 1, 1, 0, 0, 0)}
    assert not any(name.startswith("filamenthub_locales/") for name in names)

    second_root = tmp_path / "second-build"
    builder.build(second_root)
    second_wheel = second_root / "wheels" / wheel.name
    assert second_wheel.read_bytes() == wheel.read_bytes()

    standalone = tmp_path / "standalone_filamenthub_plugin.py"
    standalone.write_bytes(package.read_bytes())
    standalone_module = _load_module(standalone, "filamenthub_standalone_smoke")
    assert set(standalone_module.UI_COPY) == set(expected_locales)
    assert standalone_module.UI_COPY["ru"]["catalog"] == "Каталог"
    assert standalone_module.UI_COPY["de"]["catalog"] == "Katalog"

def test_dev_build_is_single_file_with_localhost_and_embedded_locales(plugin_module, tmp_path):
    builder = _load_module(BUILD_PATH, "filamenthub_dev_build_package_test")
    dev_dir = tmp_path / f"filamenthub-{plugin_module.PLUGIN_VERSION}-dev"
    dev_dir.mkdir()
    (dev_dir / "stale.txt").write_text("stale", encoding="utf-8")

    dev_plugin = builder.build_dev(tmp_path)
    source = dev_plugin.read_text(encoding="utf-8")

    assert not (dev_dir / "stale.txt").exists()
    assert 'os.environ.get("FILAMENTHUB_SITE_URL", "http://localhost:3000")' in source
    assert "_EMBEDDED_UI_COPY = {}" not in source
    standalone_module = _load_module(dev_plugin, "filamenthub_dev_standalone_smoke")
    assert standalone_module.DEV_CONTOUR is True
    assert standalone_module.UI_COPY["ru"]["catalog"] == "Каталог"
    standalone_module._CACHED_UI_LANGUAGE = "ru"
    assert standalone_module.ui_text(
        "syncComplete",
        summary=standalone_module.ui_text("summaryCurrent", count=4),
        note="",
    ).strip() == "Синхронизация завершена: актуальны: 4."

def test_combined_build_keeps_dev_and_prod_in_parity(plugin_module, tmp_path):
    builder = _load_module(BUILD_PATH, "filamenthub_combined_build_package_test")

    package_dir, dev_plugin = builder.build_all(tmp_path, wheel=False)
    prod_source = (package_dir / "filamenthub_plugin.py").read_text(encoding="utf-8")
    dev_source = dev_plugin.read_text(encoding="utf-8")

    assert package_dir.name == f"filamenthub-{plugin_module.PLUGIN_VERSION}"
    assert dev_plugin.parent.name == f"filamenthub-{plugin_module.PLUGIN_VERSION}-dev"
    assert (
        dev_source.replace(builder.DEV_SITE_DEFAULT, builder.PROD_SITE_DEFAULT)
        == prod_source
    )

def test_default_build_output_is_one_versioned_release_bundle(
    plugin_module, monkeypatch, tmp_path
):
    builder = _load_module(BUILD_PATH, "filamenthub_default_output_test")
    monkeypatch.setattr(builder, "ROOT", tmp_path / "orca-plugin")

    assert builder.default_release_output_root() == (
        tmp_path
        / "orca-plugin"
        / "dist"
        / f"release-{plugin_module.PLUGIN_VERSION}"
    )

def test_release_bundle_metadata_covers_exact_wheel(plugin_module, tmp_path):
    builder = _load_module(BUILD_PATH, "filamenthub_release_metadata_test")
    output_root = tmp_path / f"release-{plugin_module.PLUGIN_VERSION}"
    wheel_path = output_root / "wheels" / (
        f"filamenthub-{plugin_module.PLUGIN_VERSION}-py3-none-any.whl"
    )
    wheel_path.parent.mkdir(parents=True)
    wheel_path.write_bytes(b"owner-test-candidate")

    notes_path, checksum_path = builder.stage_release_metadata(
        output_root, wheel_path
    )

    assert notes_path.read_text(encoding="utf-8").startswith(
        f"## FilamentHub for OrcaSlicer {plugin_module.PLUGIN_VERSION}\n"
    )
    expected_digest = hashlib.sha256(wheel_path.read_bytes()).hexdigest()
    assert checksum_path.read_text(encoding="utf-8") == (
        f"{expected_digest}  wheels/{wheel_path.name}\n"
    )
