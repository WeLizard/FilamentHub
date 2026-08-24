"""BundleService — orchestrates upload/validate/import/rollback for catalog bundles.

Bundle is admin-only seed of the FilamentHub printer catalog from external slicer
bundles (OrcaSlicer today; PrusaSlicer / Cura / Bambu Studio in the future).
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Bundle,
    BundleImport,
    BundleImportStatus,
    BundleSource,
    BundleStatus,
    Printer,
    PrinterProfile,
    PrintProfile,
)

LOG = logging.getLogger(__name__)


def _backend_root() -> Path:
    # backend/app/services/bundle_service.py → parents[2] = backend, which inside
    # the container is /app: one level higher landed on /data, outside the working
    # directory and unwritable, so every upload failed there.
    return Path(__file__).resolve().parents[2]


UPLOAD_ROOT = _backend_root() / "data" / "uploaded_bundles"
ORCA_SOURCE_MANIFEST = "filamenthub-source.json"
ORCA_SOURCE_FORMAT = "filamenthub.catalog-source"


def _orca_archive_content_sha256(
    archive: zipfile.ZipFile, payload_names: list[str]
) -> str:
    digest = hashlib.sha256()
    for name in payload_names:
        encoded_name = name.encode("utf-8")
        payload = archive.read(name)
        digest.update(len(encoded_name).to_bytes(4, "big"))
        digest.update(encoded_name)
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


class BundleServiceError(Exception):
    """Domain error raised by BundleService."""

    def __init__(self, code: str, message: str, params: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.params = params or {}


class BundleService:
    """Lifecycle orchestration for catalog bundles."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── upload + auto-validate ──────────────────────────────────────────────
    async def upload(
        self,
        *,
        file_bytes: bytes,
        filename: str,
        source: str,
        uploaded_by_user_id: int,
    ) -> Bundle:
        """Persist uploaded archive on disk, create Bundle row, run inline validate."""
        if source not in BundleSource.ALL:
            raise BundleServiceError(
                "ERR_BUNDLE_SOURCE_UNSUPPORTED",
                f"Source '{source}' is not supported",
                {"source": source, "allowed": list(BundleSource.ALL)},
            )

        sha256 = hashlib.sha256(file_bytes).hexdigest()

        existing = await self.db.scalar(select(Bundle).where(Bundle.sha256 == sha256))
        if existing is not None:
            raise BundleServiceError(
                "ERR_BUNDLE_DUPLICATE",
                "Bundle with the same content already uploaded",
                {"bundle_id": existing.id, "sha256": sha256},
            )

        UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)

        bundle = Bundle(
            source=source,
            uploaded_by_user_id=uploaded_by_user_id,
            filename=filename,
            storage_path="",  # filled in after we know UUID
            sha256=sha256,
            size_bytes=len(file_bytes),
            status=BundleStatus.PENDING,
        )
        self.db.add(bundle)
        await self.db.flush()  # populates bundle.uuid + id from defaults

        storage_path = UPLOAD_ROOT / f"{bundle.uuid}.zip"
        storage_path.write_bytes(file_bytes)
        bundle.storage_path = str(storage_path)

        # Inline validate — fills validation_summary and updates status
        await self._validate(bundle)
        await self.db.flush()
        return bundle

    # ── validate ────────────────────────────────────────────────────────────
    async def revalidate(self, bundle_id: int) -> Bundle:
        """Re-run validation on an already-uploaded bundle."""
        bundle = await self._require_bundle(bundle_id)
        await self._validate(bundle)
        await self.db.flush()
        return bundle

    async def _validate(self, bundle: Bundle) -> None:
        path = Path(bundle.storage_path)
        if not path.exists():
            bundle.status = BundleStatus.FAILED
            bundle.rejection_reason = f"Storage file missing: {path}"
            return

        try:
            with zipfile.ZipFile(path) as zf:
                names = zf.namelist()
                unsafe_names = [
                    name
                    for name in names
                    if (
                        not name
                        or "\\" in name
                        or PurePosixPath(name).is_absolute()
                        or ".." in PurePosixPath(name).parts
                        or (PurePosixPath(name).parts and ":" in PurePosixPath(name).parts[0])
                    )
                ]
                if unsafe_names:
                    raise ValueError("archive contains unsafe paths")

                vendor_count = 0
                for name in names:
                    if not name.endswith(".json") or "/" in name or name == ORCA_SOURCE_MANIFEST:
                        continue
                    try:
                        value = json.loads(zf.read(name))
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        continue
                    if isinstance(value, dict) and value.get("name") and value.get("version"):
                        vendor_count += 1
                total_files = len(names)
                source_manifest = None
                if bundle.source == BundleSource.ORCA:
                    source_manifest = json.loads(zf.read(ORCA_SOURCE_MANIFEST))
                    payload_names = sorted(
                        name
                        for name in names
                        if name != ORCA_SOURCE_MANIFEST and not name.endswith("/")
                    )
                    if (
                        not isinstance(source_manifest, dict)
                        or source_manifest.get("format") != ORCA_SOURCE_FORMAT
                        or source_manifest.get("source") != BundleSource.ORCA
                        or not source_manifest.get("commit")
                        or not source_manifest.get("profiles_tree")
                        or source_manifest.get("dirty") is not False
                        or not source_manifest.get("content_sha256")
                    ):
                        raise ValueError("invalid Orca source manifest")
                    if any(not name.endswith(".json") for name in payload_names):
                        raise ValueError("archive contains an unexpected non-JSON payload")
                    if source_manifest.get("file_count") != len(payload_names):
                        raise ValueError("archive file_count does not match source manifest")
                    if vendor_count == 0:
                        raise ValueError("archive contains no Orca vendor manifests")
                    if source_manifest.get("vendor_count") != vendor_count:
                        raise ValueError("archive vendor_count does not match source manifest")
                    if (
                        _orca_archive_content_sha256(zf, payload_names)
                        != source_manifest["content_sha256"]
                    ):
                        raise ValueError("archive content digest does not match source manifest")
        except (KeyError, ValueError, zipfile.BadZipFile, json.JSONDecodeError) as exc:
            bundle.status = BundleStatus.FAILED
            bundle.rejection_reason = f"Invalid zip: {exc}"
            return

        bundle.validation_summary = {
            "total_files": total_files,
            "vendor_count": vendor_count,
            "source_manifest": source_manifest,
        }
        bundle.status = BundleStatus.VALIDATED
        bundle.rejection_reason = None

    # ── import ──────────────────────────────────────────────────────────────
    async def import_bundle(
        self,
        *,
        bundle_id: int,
        triggered_by_user_id: int,
    ) -> BundleImport:
        """Run the source-specific adapter, write audit log, return BundleImport row."""
        bundle = await self._require_bundle(bundle_id)
        if bundle.status not in (BundleStatus.VALIDATED, BundleStatus.IMPORTED):
            raise BundleServiceError(
                "ERR_BUNDLE_NOT_VALIDATED",
                "Bundle must be validated before import",
                {"bundle_id": bundle.id, "status": bundle.status},
            )
        if bundle.source == BundleSource.ORCA and not (
            isinstance(bundle.validation_summary, dict)
            and isinstance(bundle.validation_summary.get("source_manifest"), dict)
        ):
            # Bundles validated before provenance became mandatory must not
            # bypass the new rule merely because their old status is retained.
            raise BundleServiceError(
                "ERR_BUNDLE_NOT_VALIDATED",
                "Orca bundle provenance is required; revalidate or upload a current bundle",
                {"bundle_id": bundle.id, "status": bundle.status},
            )

        # Held as plain values: a failure rolls the session back, and reading them
        # off the expired objects afterwards raised in the error handler itself,
        # hiding whatever actually went wrong.
        known_bundle_id = bundle.id
        audit = BundleImport(
            bundle_id=known_bundle_id,
            started_by_user_id=triggered_by_user_id,
            status=BundleImportStatus.STARTED,
        )
        self.db.add(audit)
        await self.db.flush()
        known_audit_id = audit.id

        tmp_root = Path(tempfile.mkdtemp(prefix=f"bundle_{bundle.source}_"))
        try:
            with zipfile.ZipFile(bundle.storage_path) as zf:
                zf.extractall(tmp_root)

            summary = await self._run_adapter(
                bundle=bundle, extracted_root=tmp_root
            )

            audit.status = BundleImportStatus.SUCCESS
            audit.summary = summary
            audit.finished_at = datetime.now(timezone.utc)
            bundle.status = BundleStatus.IMPORTED
        except BundleServiceError:
            await self.db.rollback()
            audit = await self._record_failure(
                audit_id=known_audit_id, bundle_id=known_bundle_id
            )
            raise
        except Exception as exc:  # noqa: BLE001
            await self.db.rollback()
            LOG.exception("Bundle import failed (bundle_id=%s)", known_bundle_id)
            audit = await self._record_failure(
                audit_id=known_audit_id, bundle_id=known_bundle_id, error=str(exc)[:2000]
            )
            # Exception text stays in logs and the audit record, not in the HTTP detail
            raise BundleServiceError(
                "ERR_BUNDLE_IMPORT_FAILED",
                "Bundle import failed",
                {"bundle_id": known_bundle_id},
            ) from exc
        finally:
            shutil.rmtree(tmp_root, ignore_errors=True)

        await self.db.flush()
        return audit

    async def _run_adapter(
        self, *, bundle: Bundle, extracted_root: Path
    ) -> dict[str, Any]:
        if bundle.source == BundleSource.ORCA:
            from app.services.orca_bundle_importer import OrcaBundleImporter

            importer = OrcaBundleImporter(root_path=extracted_root)
            return await importer.import_all(self.db, bundle_id=bundle.id)

        raise BundleServiceError(
            "ERR_BUNDLE_SOURCE_NOT_IMPLEMENTED",
            f"Adapter for source '{bundle.source}' is not implemented yet",
            {"source": bundle.source},
        )

    async def _record_failure(
        self,
        *,
        audit_id: int,
        bundle_id: int,
        error: str | None = None,
    ) -> BundleImport:
        audit = await self.db.get(BundleImport, audit_id)
        if audit is None:
            audit = BundleImport(
                bundle_id=bundle_id,
                started_by_user_id=None,
                status=BundleImportStatus.FAILED,
            )
            self.db.add(audit)
        audit.status = BundleImportStatus.FAILED
        audit.error_text = error
        audit.finished_at = datetime.now(timezone.utc)

        bundle = await self.db.get(Bundle, bundle_id)
        if bundle is not None:
            bundle.status = BundleStatus.FAILED
            bundle.rejection_reason = error

        await self.db.flush()
        return audit

    # ── rollback ────────────────────────────────────────────────────────────
    async def rollback(
        self,
        *,
        bundle_id: int,
        triggered_by_user_id: int,
    ) -> dict[str, int]:
        """Detach catalog records linked to this bundle.

        SET NULL on created_from_bundle_id for printers / printer_profiles /
        print_profiles. Records are kept (per RFC §11.5) — explicit user
        action is required to delete them.
        """
        bundle = await self._require_bundle(bundle_id)

        printers_detached = await self._detach_table(Printer, bundle_id)
        printer_profiles_detached = await self._detach_table(PrinterProfile, bundle_id)
        print_profiles_detached = await self._detach_table(PrintProfile, bundle_id)

        bundle.status = BundleStatus.ROLLED_BACK

        last_import = await self.db.scalar(
            select(BundleImport)
            .where(BundleImport.bundle_id == bundle_id)
            .order_by(BundleImport.id.desc())
            .limit(1)
        )
        if last_import is not None and last_import.status == BundleImportStatus.SUCCESS:
            last_import.status = BundleImportStatus.ROLLED_BACK
            last_import.rolled_back_at = datetime.now(timezone.utc)
            last_import.rolled_back_by_user_id = triggered_by_user_id

        await self.db.flush()
        return {
            "printers_detached": printers_detached,
            "printer_profiles_detached": printer_profiles_detached,
            "print_profiles_detached": print_profiles_detached,
        }

    async def _detach_table(self, model: type, bundle_id: int) -> int:
        result = await self.db.execute(
            update(model)
            .where(model.created_from_bundle_id == bundle_id)
            .values(created_from_bundle_id=None)
        )
        return result.rowcount or 0

    # ── lookup helpers ──────────────────────────────────────────────────────
    async def _require_bundle(self, bundle_id: int) -> Bundle:
        bundle = await self.db.get(Bundle, bundle_id)
        if bundle is None:
            raise BundleServiceError(
                "ERR_BUNDLE_NOT_FOUND",
                f"Bundle {bundle_id} not found",
                {"bundle_id": bundle_id},
            )
        return bundle
