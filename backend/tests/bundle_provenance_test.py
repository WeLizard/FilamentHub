"""Validation of the trusted Orca catalog source archive."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from uuid import uuid4

import pytest

from app.models.bundle import Bundle, BundleSource, BundleStatus
from app.services.bundle_service import BundleService


async def _validate(db_session, tmp_path: Path, payload: bytes) -> Bundle:
    archive = tmp_path / f"{uuid4()}.zip"
    archive.write_bytes(payload)
    bundle = Bundle(
        id=1,
        source=BundleSource.ORCA,
        uploaded_by_user_id=None,
        filename="orca.zip",
        storage_path=str(archive),
        sha256="0" * 64,
        size_bytes=len(payload),
        status=BundleStatus.PENDING,
    )
    await BundleService(db_session)._validate(bundle)
    return bundle


def _archive(*, manifest: dict | None, vendor: dict | None, extra_name: str | None = None) -> bytes:
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        if manifest is not None:
            archive.writestr("filamenthub-source.json", json.dumps(manifest))
        if vendor is not None:
            archive.writestr("Vendor.json", json.dumps(vendor))
        if extra_name is not None:
            archive.writestr(extra_name, "unsafe")
    return payload.getvalue()


def _manifest() -> dict:
    return {
        "format": "filamenthub.catalog-source",
        "source": "orca",
        "commit": "a" * 40,
        "profiles_tree": "b" * 40,
        "dirty": False,
    }


@pytest.mark.asyncio
async def test_orca_bundle_requires_source_provenance(db_session, tmp_path):
    bundle = await _validate(
        db_session,
        tmp_path,
        _archive(manifest=None, vendor={"name": "Vendor", "version": "1"}),
    )

    assert bundle.status == BundleStatus.FAILED
    assert "filamenthub-source.json" in (bundle.rejection_reason or "")


@pytest.mark.asyncio
async def test_orca_bundle_rejects_unsafe_archive_paths(db_session, tmp_path):
    bundle = await _validate(
        db_session,
        tmp_path,
        _archive(
            manifest=_manifest(),
            vendor={"name": "Vendor", "version": "1"},
            extra_name="folder\\..\\outside.json",
        ),
    )

    assert bundle.status == BundleStatus.FAILED
    assert "unsafe paths" in (bundle.rejection_reason or "")


@pytest.mark.asyncio
async def test_orca_bundle_records_verified_source_manifest(db_session, tmp_path):
    manifest = _manifest()
    bundle = await _validate(
        db_session,
        tmp_path,
        _archive(
            manifest=manifest,
            vendor={"name": "Vendor", "version": "1"},
        ),
    )

    assert bundle.status == BundleStatus.VALIDATED
    assert bundle.validation_summary == {
        "total_files": 2,
        "vendor_count": 1,
        "source_manifest": manifest,
    }
