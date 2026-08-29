"""Оркестратор синхронизации пресетов между OrcaSlicer и FilamentHub."""

import hashlib
import json
import logging
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.preset import Preset
from app.models.print_profile import PrintProfile
from app.models.printer_profile import PrinterProfile
from app.models.sync_device import SyncDevice
from app.models.sync_history import SyncHistory, SyncOperation, SyncPresetType, SyncStatus
from app.models.sync_preset_state import SyncPresetState
from app.models.sync_report import SyncReport, SyncReportChunk, SyncReportItem
from app.models.user_saved_preset import UserSavedPreset

logger = logging.getLogger(__name__)


class SyncReportConflictError(ValueError):
    """The device report does not match the next or latest accepted version."""


_OBSERVATION_STATUS = {
    "loaded": SyncStatus.SUCCESS,
    "on_disk": SyncStatus.SUCCESS,
    "pending_restart": SyncStatus.CONFLICT,
    "error": SyncStatus.ERROR,
    "removed": SyncStatus.SUCCESS,
}


def _observation_payload(state: str, error_code: str | None = None) -> str:
    payload = {"state": state}
    if error_code:
        payload["error_code"] = error_code
    return json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


def _decode_observation(
    observation: SyncHistory | SyncPresetState,
) -> tuple[str, str | None]:
    """Read new structured observations while keeping old history useful."""
    if observation.error_message:
        try:
            payload = json.loads(observation.error_message)
        except (TypeError, ValueError):
            payload = None
        if isinstance(payload, dict) and payload.get("state") in _OBSERVATION_STATUS:
            error_code = payload.get("error_code")
            return payload["state"], error_code if isinstance(error_code, str) else None

    if observation.status == SyncStatus.ERROR:
        return "error", "legacy_sync_error"
    if observation.status == SyncStatus.CONFLICT:
        return "pending_restart", None
    if observation.operation == SyncOperation.DELETE:
        return "removed", None
    # A historical SUCCESS only proved that a download completed. It never
    # proved that the running Orca host loaded the resulting profile.
    return "on_disk", None


class SyncOrchestrator:
    """Управляет синхронизацией пресетов между OrcaSlicer и FilamentHub."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_or_create_device(
        self,
        user_id: int,
        device_fingerprint: str,
        orcaslicer_version: str | None = None,
    ) -> SyncDevice:
        """Получить или создать устройство для синхронизации."""
        if not 1 <= len(device_fingerprint) <= 255:
            raise ValueError("device_fingerprint length is out of bounds")
        if orcaslicer_version is not None and not 1 <= len(orcaslicer_version) <= 50:
            raise ValueError("orcaslicer_version length is out of bounds")
        result = await self.db.execute(
            select(SyncDevice).where(
                and_(
                    SyncDevice.user_id == user_id,
                    SyncDevice.device_fingerprint == device_fingerprint,
                )
            )
        )
        device = result.scalar_one_or_none()

        if device:
            if orcaslicer_version:
                device.orcaslicer_version = orcaslicer_version
            await self.db.flush()
            return device

        device = SyncDevice(
            user_id=user_id,
            device_fingerprint=device_fingerprint,
            orcaslicer_version=orcaslicer_version,
            sync_version=0,
        )
        self.db.add(device)
        await self.db.flush()
        return device

    async def create_sync_plan(
        self,
        user_id: int,
        device_fingerprint: str,
        preset_type: str,
        force_full_sync: bool = False,
        orcaslicer_version: str | None = None,
        include_changes: bool = True,
        chunked_report: bool = False,
    ) -> dict:
        """
        Генерирует план синхронизации.

        Returns:
            {
                "sync_version": int,
                "device_id": str,
                "to_download": [...],
                "deleted_on_server": [...],
                "conflicts": [],
                "last_sync_at": str | None,
            }
        """
        device = await self.get_or_create_device(
            user_id=user_id,
            device_fingerprint=device_fingerprint,
            orcaslicer_version=orcaslicer_version,
        )
        report_id = None
        if chunked_report:
            report_id = await self._begin_chunked_report(user_id, device)

        # The active plugin already gets its desired payload from /auth/my-presets.
        # It can ask this endpoint only for the next device-scoped report version
        # instead of downloading the same list twice.
        if not include_changes:
            to_download = []
            deleted_on_server = []
        elif force_full_sync or device.sync_version == 0:
            to_download = await self._get_all_active_presets(user_id, preset_type)
            deleted_on_server = []
        else:
            to_download = await self._get_updated_presets(
                user_id, preset_type, device.last_sync_at
            )
            deleted_on_server = await self._detect_deleted_presets(
                user_id, device.id, preset_type, device.sync_version
            )

        return {
            "sync_version": device.sync_version + 1,
            "device_id": device.device_fingerprint,
            "to_download": to_download,
            "deleted_on_server": deleted_on_server,
            "conflicts": [],
            "last_sync_at": device.last_sync_at.isoformat() if device.last_sync_at else None,
            "report_id": report_id,
        }

    async def _begin_chunked_report(
        self,
        user_id: int,
        device: SyncDevice,
    ) -> str:
        """Start a fresh report without exposing any partial prior staging."""
        locked_result = await self.db.execute(
            select(SyncDevice)
            .where(
                and_(
                    SyncDevice.id == device.id,
                    SyncDevice.user_id == user_id,
                )
            )
            .with_for_update()
        )
        device = locked_result.scalar_one()
        sync_version = device.sync_version + 1
        existing_result = await self.db.execute(
            select(SyncReport).where(
                and_(
                    SyncReport.device_id == device.id,
                    SyncReport.sync_version == sync_version,
                )
            )
        )
        existing = existing_result.scalar_one_or_none()
        if existing is not None:
            if existing.completed_at is not None:
                raise SyncReportConflictError("next report version is already complete")
            await self._discard_report(existing.id)

        report_id = str(uuid4())
        self.db.add(
            SyncReport(
                user_id=user_id,
                device_id=device.id,
                report_id=report_id,
                sync_version=sync_version,
            )
        )
        await self.db.flush()
        return report_id

    async def complete_sync(
        self,
        user_id: int,
        device_fingerprint: str,
        sync_version: int,
        results: list[dict],
    ) -> tuple[SyncDevice, bool]:
        """
        Идемпотентно принять фактический результат устройства.

        Блокировка строки сериализует два одновременных ответа одного устройства.
        Повтор последнего идентичного отчёта не создаёт историю второй раз.
        """
        device_result = await self.db.execute(
            select(SyncDevice)
            .where(
                and_(
                    SyncDevice.user_id == user_id,
                    SyncDevice.device_fingerprint == device_fingerprint,
                )
            )
            .with_for_update()
        )
        device = device_result.scalar_one_or_none()
        if device is None:
            raise SyncReportConflictError("device has no sync plan")

        if sync_version == device.sync_version:
            if await self._report_matches_history(device, sync_version, results):
                return device, True
            raise SyncReportConflictError("latest report payload differs")
        if sync_version != device.sync_version + 1:
            raise SyncReportConflictError("unexpected sync version")

        observed_at = datetime.now(timezone.utc)
        for item in results:
            state = item["state"]
            history = SyncHistory(
                user_id=user_id,
                device_id=device.id,
                sync_version=sync_version,
                preset_type=SyncPresetType(item["preset_type"]),
                operation=SyncOperation(item["operation"]),
                preset_id=item["preset_id"],
                status=_OBSERVATION_STATUS[state],
                error_message=_observation_payload(state, item.get("error_code")),
                created_at=observed_at,
            )
            self.db.add(history)

        await self._publish_observations(
            user_id=user_id,
            device_id=device.id,
            sync_version=sync_version,
            results=results,
            observed_at=observed_at,
        )
        device.sync_version = sync_version
        device.last_sync_at = observed_at
        await self.db.flush()
        await self._prune_history(device.id, sync_version)
        return device, False

    async def accept_sync_report_chunk(
        self,
        *,
        user_id: int,
        device_fingerprint: str,
        sync_version: int,
        report_id: str,
        chunk_index: int,
        chunk_count: int,
        results: list[dict],
    ) -> dict:
        """Durably accept one chunk and publish only after the full report."""
        device_result = await self.db.execute(
            select(SyncDevice)
            .where(
                and_(
                    SyncDevice.user_id == user_id,
                    SyncDevice.device_fingerprint == device_fingerprint,
                )
            )
            .with_for_update()
        )
        device = device_result.scalar_one_or_none()
        if device is None:
            raise SyncReportConflictError("device has no sync plan")

        report_result = await self.db.execute(
            select(SyncReport).where(
                and_(
                    SyncReport.user_id == user_id,
                    SyncReport.device_id == device.id,
                    SyncReport.sync_version == sync_version,
                    SyncReport.report_id == report_id,
                )
            )
        )
        report = report_result.scalar_one_or_none()
        if report is None:
            raise SyncReportConflictError("chunk does not match the active report")
        if report.chunk_count is None:
            report.chunk_count = chunk_count
        elif report.chunk_count != chunk_count:
            raise SyncReportConflictError("report chunk count differs")

        payload_digest = self._chunk_digest(results)
        existing_chunk_result = await self.db.execute(
            select(SyncReportChunk).where(
                and_(
                    SyncReportChunk.report_pk == report.id,
                    SyncReportChunk.chunk_index == chunk_index,
                )
            )
        )
        existing_chunk = existing_chunk_result.scalar_one_or_none()

        if report.completed_at is not None:
            if device.sync_version != sync_version:
                raise SyncReportConflictError("completed report version differs")
            if (
                existing_chunk is None
                or existing_chunk.payload_digest != payload_digest
                or existing_chunk.item_count != len(results)
            ):
                raise SyncReportConflictError("completed chunk payload differs")
            return self._chunk_receipt(
                device=device,
                report=report,
                chunk_index=chunk_index,
                received_chunks=report.chunk_count,
                duplicate=True,
            )

        if sync_version != device.sync_version + 1:
            raise SyncReportConflictError("unexpected sync version")
        if existing_chunk is not None:
            if (
                existing_chunk.payload_digest != payload_digest
                or existing_chunk.item_count != len(results)
            ):
                raise SyncReportConflictError("chunk payload differs")
            received_chunks = await self._received_chunk_count(report.id)
            return self._chunk_receipt(
                device=device,
                report=report,
                chunk_index=chunk_index,
                received_chunks=received_chunks,
                duplicate=True,
            )

        await self._reject_cross_chunk_duplicates(report.id, results)
        chunk = SyncReportChunk(
            report_pk=report.id,
            chunk_index=chunk_index,
            item_count=len(results),
            payload_digest=payload_digest,
        )
        self.db.add(chunk)
        await self.db.flush()
        self.db.add_all(
            [
                SyncReportItem(
                    report_pk=report.id,
                    chunk_pk=chunk.id,
                    item_index=item_index,
                    preset_type=SyncPresetType(item["preset_type"]),
                    operation=SyncOperation(item["operation"]),
                    preset_id=item["preset_id"],
                    state=item["state"],
                    error_code=item.get("error_code"),
                )
                for item_index, item in enumerate(results)
            ]
        )
        await self.db.flush()

        received_chunks = await self._received_chunk_count(report.id)
        if received_chunks == chunk_count:
            await self._finalize_chunked_report(device, report)
        return self._chunk_receipt(
            device=device,
            report=report,
            chunk_index=chunk_index,
            received_chunks=received_chunks,
            duplicate=False,
        )

    @staticmethod
    def _chunk_digest(results: list[dict]) -> str:
        payload = json.dumps(
            results,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    async def _received_chunk_count(self, report_pk: int) -> int:
        result = await self.db.execute(
            select(func.count(SyncReportChunk.id)).where(
                SyncReportChunk.report_pk == report_pk
            )
        )
        return int(result.scalar_one())

    async def _reject_cross_chunk_duplicates(
        self,
        report_pk: int,
        results: list[dict],
    ) -> None:
        if not results:
            return
        preset_ids = {item["preset_id"] for item in results}
        existing_result = await self.db.execute(
            select(
                SyncReportItem.preset_type,
                SyncReportItem.operation,
                SyncReportItem.preset_id,
            ).where(
                and_(
                    SyncReportItem.report_pk == report_pk,
                    SyncReportItem.preset_id.in_(preset_ids),
                )
            )
        )
        existing = {
            (preset_type.value, operation.value, preset_id)
            for preset_type, operation, preset_id in existing_result.all()
        }
        incoming = {
            (item["preset_type"], item["operation"], item["preset_id"])
            for item in results
        }
        if existing & incoming:
            raise SyncReportConflictError("duplicate result across report chunks")

    async def _finalize_chunked_report(
        self,
        device: SyncDevice,
        report: SyncReport,
    ) -> None:
        """Publish staged rows in bounded batches inside the final transaction."""
        observed_at = datetime.now(timezone.utc)
        cursor = 0
        while True:
            page_result = await self.db.execute(
                select(SyncReportItem)
                .where(
                    and_(
                        SyncReportItem.report_pk == report.id,
                        SyncReportItem.id > cursor,
                    )
                )
                .order_by(SyncReportItem.id)
                .limit(1000)
            )
            page = list(page_result.scalars().all())
            if not page:
                break
            results = [
                {
                    "preset_type": item.preset_type.value,
                    "operation": item.operation.value,
                    "preset_id": item.preset_id,
                    "state": item.state,
                    "error_code": item.error_code,
                }
                for item in page
            ]
            self.db.add_all(
                [
                    SyncHistory(
                        user_id=report.user_id,
                        device_id=device.id,
                        sync_version=report.sync_version,
                        preset_type=item.preset_type,
                        operation=item.operation,
                        preset_id=item.preset_id,
                        status=_OBSERVATION_STATUS[item.state],
                        error_message=_observation_payload(item.state, item.error_code),
                        created_at=observed_at,
                    )
                    for item in page
                ]
            )
            await self._publish_observations(
                user_id=report.user_id,
                device_id=device.id,
                sync_version=report.sync_version,
                results=results,
                observed_at=observed_at,
            )
            cursor = page[-1].id
            await self.db.flush()

        device.sync_version = report.sync_version
        device.last_sync_at = observed_at
        report.completed_at = observed_at
        await self.db.execute(
            delete(SyncReportItem).where(SyncReportItem.report_pk == report.id)
        )
        await self.db.flush()
        await self._prune_history(device.id, report.sync_version)
        await self._prune_reports(device.id, report.sync_version)

    @staticmethod
    def _chunk_receipt(
        *,
        device: SyncDevice,
        report: SyncReport,
        chunk_index: int,
        received_chunks: int,
        duplicate: bool,
    ) -> dict:
        return {
            "sync_version": report.sync_version,
            "report_id": report.report_id,
            "chunk_index": chunk_index,
            "received_chunks": received_chunks,
            "chunk_count": report.chunk_count,
            "complete": report.completed_at is not None,
            "duplicate": duplicate,
            "last_sync_at": (
                device.last_sync_at.isoformat() if device.last_sync_at else None
            ),
        }

    async def record_sync_success(
        self,
        user_id: int,
        device_id: int,
        sync_version: int,
        preset_type: str,
        preset_id: int,
        operation: str = "download",
    ) -> SyncHistory:
        """Записать успешную операцию синхронизации (НЕ инкрементирует sync_version)."""
        history = SyncHistory(
            user_id=user_id,
            device_id=device_id,
            sync_version=sync_version,
            preset_type=SyncPresetType(preset_type),
            operation=SyncOperation(operation),
            preset_id=preset_id,
            status=SyncStatus.SUCCESS,
        )
        self.db.add(history)
        await self._publish_observations(
            user_id=user_id,
            device_id=device_id,
            sync_version=sync_version,
            results=[
                {
                    "preset_type": preset_type,
                    "operation": operation,
                    "preset_id": preset_id,
                    "state": "removed" if operation == "delete" else "on_disk",
                    "error_code": None,
                }
            ],
            observed_at=datetime.now(timezone.utc),
        )
        await self.db.flush()
        return history

    async def record_sync_error(
        self,
        user_id: int,
        device_id: int,
        sync_version: int,
        preset_type: str,
        preset_id: int,
        error_message: str,
        operation: str = "download",
    ) -> SyncHistory:
        """Записать ошибку синхронизации."""
        history = SyncHistory(
            user_id=user_id,
            device_id=device_id,
            sync_version=sync_version,
            preset_type=SyncPresetType(preset_type),
            operation=SyncOperation(operation),
            preset_id=preset_id,
            status=SyncStatus.ERROR,
            error_message=error_message,
        )
        self.db.add(history)
        await self._publish_observations(
            user_id=user_id,
            device_id=device_id,
            sync_version=sync_version,
            results=[
                {
                    "preset_type": preset_type,
                    "operation": operation,
                    "preset_id": preset_id,
                    "state": "error",
                    "error_code": "legacy_sync_error",
                }
            ],
            observed_at=datetime.now(timezone.utc),
        )
        await self.db.flush()
        return history

    async def get_deleted_presets(
        self,
        user_id: int,
        device_fingerprint: str,
        preset_type: str,
    ) -> list[dict]:
        """
        Возвращает пресеты удалённые на сервере с метаданными
        (was_created_by_user, was_saved_by_user).
        """
        device = await self.get_or_create_device(user_id, device_fingerprint)

        deleted_ids = await self._detect_deleted_presets(
            user_id, device.id, preset_type, device.sync_version
        )

        preset_ids = [item["id"] for item in deleted_ids]
        saved_ids: set[int] = set()
        if preset_ids:
            saved_result = await self.db.execute(
                select(UserSavedPreset.preset_id).where(
                    and_(
                        UserSavedPreset.user_id == user_id,
                        UserSavedPreset.preset_id.in_(preset_ids),
                    )
                )
            )
            saved_ids = set(saved_result.scalars().all())

        return [
            {
                "preset_id": item["id"],
                "name": item.get("name", ""),
                "was_created_by_user": item.get("user_id") == user_id,
                "was_saved_by_user": item["id"] in saved_ids,
            }
            for item in deleted_ids
        ]

    async def get_sync_status(
        self,
        user_id: int,
        device_fingerprint: str | None = None,
        *,
        device_limit: int = 50,
        device_cursor: int | None = None,
        preset_limit: int = 100,
        preset_cursor: int | None = None,
    ) -> dict:
        """Return bounded desired state and the selected device observation."""
        device_query = select(SyncDevice).where(SyncDevice.user_id == user_id)
        if device_cursor is not None:
            device_query = device_query.where(SyncDevice.id < device_cursor)
        devices_result = await self.db.execute(
            device_query.order_by(SyncDevice.id.desc()).limit(device_limit + 1)
        )
        devices_page = list(devices_result.scalars().all())
        has_more_devices = len(devices_page) > device_limit
        devices = devices_page[:device_limit]

        device: SyncDevice | None = None
        if device_fingerprint is not None:
            selected_result = await self.db.execute(
                select(SyncDevice).where(
                    and_(
                        SyncDevice.user_id == user_id,
                        SyncDevice.device_fingerprint == device_fingerprint,
                    )
                )
            )
            device = selected_result.scalar_one_or_none()
            if device is None:
                raise LookupError("sync device not found")
        else:
            selected_result = await self.db.execute(
                select(SyncDevice)
                .where(SyncDevice.user_id == user_id)
                .order_by(SyncDevice.last_sync_at.desc().nullslast(), SyncDevice.id.desc())
                .limit(1)
            )
            device = selected_result.scalar_one_or_none()

        saved_query = (
            select(UserSavedPreset)
            .join(Preset, Preset.id == UserSavedPreset.preset_id)
            .where(
                and_(
                    UserSavedPreset.user_id == user_id,
                    Preset.active.is_(True),
                    Preset.filament_id.isnot(None),
                )
            )
            .order_by(UserSavedPreset.preset_id)
        )
        if preset_cursor is not None:
            saved_query = saved_query.where(UserSavedPreset.preset_id > preset_cursor)
        saved_result = await self.db.execute(saved_query.limit(preset_limit + 1))
        saved_page = list(saved_result.scalars().all())
        has_more_presets = len(saved_page) > preset_limit
        saved_presets = saved_page[:preset_limit]

        latest_by_preset: dict[int, SyncPresetState] = {}
        preset_ids = [saved.preset_id for saved in saved_presets]
        if device is not None and preset_ids:
            projection_result = await self.db.execute(
                select(SyncPresetState).where(
                    and_(
                        SyncPresetState.device_id == device.id,
                        SyncPresetState.preset_type == SyncPresetType.FILAMENT,
                        SyncPresetState.preset_id.in_(preset_ids),
                    )
                )
            )
            latest_by_preset = {
                observation.preset_id: observation
                for observation in projection_result.scalars().all()
            }

        preset_statuses = []
        for saved in saved_presets:
            desired = bool(saved.sync)
            latest = latest_by_preset.get(saved.preset_id)
            state = "pending"
            operation = None
            error_code = None
            observed_at = None
            if latest is not None:
                observed_state, observed_error = _decode_observation(latest)
                operation = latest.operation.value
                observed_at = latest.observed_at.isoformat()
                if desired and latest.operation == SyncOperation.DOWNLOAD:
                    state = observed_state
                    error_code = observed_error
                elif not desired and latest.operation == SyncOperation.DELETE:
                    state = observed_state
                    error_code = observed_error

            preset_statuses.append(
                {
                    "preset_id": saved.preset_id,
                    "desired": desired,
                    "state": state,
                    "operation": operation,
                    "error_code": error_code,
                    "observed_at": observed_at,
                }
            )

        stats = {status: 0 for status in SyncStatus}
        if device is not None:
            stats_result = await self.db.execute(
                select(SyncHistory.status, func.count(SyncHistory.id))
                .where(
                    and_(
                        SyncHistory.device_id == device.id,
                        SyncHistory.sync_version == device.sync_version,
                    )
                )
                .group_by(SyncHistory.status)
            )
            stats.update(dict(stats_result.all()))
        total_count = sum(stats.values())

        return {
            "device_fingerprint": device.device_fingerprint if device else None,
            "sync_version": device.sync_version if device else 0,
            "last_sync_at": (
                device.last_sync_at.isoformat()
                if device is not None and device.last_sync_at
                else None
            ),
            "last_sync_stats": {
                "total": total_count,
                "success": stats[SyncStatus.SUCCESS],
                "errors": stats[SyncStatus.ERROR],
                "pending_restart": stats[SyncStatus.CONFLICT],
            },
            "devices": [
                {
                    "device_fingerprint": item.device_fingerprint,
                    "orcaslicer_version": item.orcaslicer_version,
                    "sync_version": item.sync_version,
                    "last_sync_at": item.last_sync_at.isoformat() if item.last_sync_at else None,
                }
                for item in devices
            ],
            "device_next_cursor": devices[-1].id if has_more_devices and devices else None,
            "presets": preset_statuses,
            "preset_next_cursor": (
                saved_presets[-1].preset_id
                if has_more_presets and saved_presets
                else None
            ),
        }

    async def get_sync_history(
        self,
        user_id: int,
        *,
        device_fingerprint: str | None = None,
        preset_type: str | None = None,
        limit: int = 100,
        cursor: int | None = None,
    ) -> dict:
        """Return a bounded keyset page of raw device outcomes."""
        query = (
            select(SyncHistory, SyncDevice.device_fingerprint)
            .join(SyncDevice, SyncDevice.id == SyncHistory.device_id)
            .where(SyncHistory.user_id == user_id)
        )
        if device_fingerprint is not None:
            query = query.where(SyncDevice.device_fingerprint == device_fingerprint)
        if preset_type is not None:
            query = query.where(SyncHistory.preset_type == SyncPresetType(preset_type))
        if cursor is not None:
            query = query.where(SyncHistory.id < cursor)

        result = await self.db.execute(
            query.order_by(SyncHistory.id.desc()).limit(limit + 1)
        )
        page = list(result.all())
        has_more = len(page) > limit
        rows = page[:limit]
        items = []
        for history, fingerprint in rows:
            state, error_code = _decode_observation(history)
            items.append(
                {
                    "id": history.id,
                    "device_fingerprint": fingerprint,
                    "sync_version": history.sync_version,
                    "preset_type": history.preset_type.value,
                    "operation": history.operation.value,
                    "preset_id": history.preset_id,
                    "state": state,
                    "error_code": error_code,
                    "observed_at": history.created_at.isoformat(),
                }
            )
        return {
            "items": items,
            "next_cursor": rows[-1][0].id if has_more and rows else None,
        }

    async def _publish_observations(
        self,
        *,
        user_id: int,
        device_id: int,
        sync_version: int,
        results: list[dict],
        observed_at: datetime,
    ) -> None:
        """Atomically refresh the latest-state projection for one report."""
        if not results:
            return

        preset_ids = {item["preset_id"] for item in results}
        current_result = await self.db.execute(
            select(SyncPresetState).where(
                and_(
                    SyncPresetState.device_id == device_id,
                    SyncPresetState.preset_id.in_(preset_ids),
                )
            )
        )
        current = {
            (item.preset_type.value, item.preset_id): item
            for item in current_result.scalars().all()
        }

        for result_item in results:
            preset_type = SyncPresetType(result_item["preset_type"])
            operation = SyncOperation(result_item["operation"])
            state = result_item["state"]
            key = (preset_type.value, result_item["preset_id"])
            projection = current.get(key)
            present = projection.present if projection is not None else False
            if operation == SyncOperation.DELETE and state == "removed":
                present = False
            elif operation == SyncOperation.DOWNLOAD and state != "error":
                present = True

            values = {
                "user_id": user_id,
                "device_id": device_id,
                "preset_type": preset_type,
                "preset_id": result_item["preset_id"],
                "sync_version": sync_version,
                "operation": operation,
                "status": _OBSERVATION_STATUS[state],
                "error_message": _observation_payload(
                    state, result_item.get("error_code")
                ),
                "present": present,
                "observed_at": observed_at,
            }
            if projection is None:
                projection = SyncPresetState(**values)
                self.db.add(projection)
                current[key] = projection
            else:
                for field, value in values.items():
                    setattr(projection, field, value)

    async def _prune_history(self, device_id: int, sync_version: int) -> None:
        """Retain a bounded number of complete report versions per device."""
        retention_versions = max(1, settings.ORCA_SYNC_HISTORY_RETENTION_VERSIONS)
        oldest_retained = sync_version - retention_versions + 1
        if oldest_retained <= 0:
            return
        await self.db.execute(
            delete(SyncHistory).where(
                and_(
                    SyncHistory.device_id == device_id,
                    SyncHistory.sync_version < oldest_retained,
                )
            )
        )

    async def _prune_reports(self, device_id: int, sync_version: int) -> None:
        retention_versions = settings.ORCA_SYNC_HISTORY_RETENTION_VERSIONS
        oldest_retained = sync_version - retention_versions + 1
        if oldest_retained <= 0:
            return
        stale_result = await self.db.execute(
            select(SyncReport.id).where(
                and_(
                    SyncReport.device_id == device_id,
                    SyncReport.sync_version < oldest_retained,
                )
            )
        )
        for report_pk in stale_result.scalars().all():
            await self._discard_report(report_pk)

    async def _discard_report(self, report_pk: int) -> None:
        """Delete staging in FK-safe order without relying on ORM cascades."""
        await self.db.execute(
            delete(SyncReportItem).where(SyncReportItem.report_pk == report_pk)
        )
        await self.db.execute(
            delete(SyncReportChunk).where(SyncReportChunk.report_pk == report_pk)
        )
        await self.db.execute(delete(SyncReport).where(SyncReport.id == report_pk))
        await self.db.flush()

    async def _report_matches_history(
        self,
        device: SyncDevice,
        sync_version: int,
        results: list[dict],
    ) -> bool:
        history_result = await self.db.execute(
            select(SyncHistory).where(
                and_(
                    SyncHistory.device_id == device.id,
                    SyncHistory.sync_version == sync_version,
                )
            )
        )
        history_entries = list(history_result.scalars().all())
        expected = sorted(
            (
                item["preset_type"],
                item["operation"],
                item["preset_id"],
                item["state"],
                item.get("error_code"),
            )
            for item in results
        )
        actual = []
        for history in history_entries:
            state, error_code = _decode_observation(history)
            actual.append(
                (
                    history.preset_type.value,
                    history.operation.value,
                    history.preset_id,
                    state,
                    error_code,
                )
            )
        return expected == sorted(actual)

    # ── Private helpers ───────────────────────────────────────────

    async def _get_all_active_presets(
        self, user_id: int, preset_type: str
    ) -> list[dict]:
        """Получить все активные пресеты пользователя для полной синхронизации."""
        if preset_type == "filament":
            return await self._get_filament_presets(user_id, since=None)
        elif preset_type == "printer":
            return await self._get_printer_profiles(user_id, since=None)
        elif preset_type == "print":
            return await self._get_print_profiles(user_id, since=None)
        return []

    async def _get_updated_presets(
        self, user_id: int, preset_type: str, since: datetime | None
    ) -> list[dict]:
        """Получить пресеты обновлённые после определённого времени."""
        if preset_type == "filament":
            return await self._get_filament_presets(user_id, since=since)
        elif preset_type == "printer":
            return await self._get_printer_profiles(user_id, since=since)
        elif preset_type == "print":
            return await self._get_print_profiles(user_id, since=since)
        return []

    async def _get_filament_presets(
        self, user_id: int, since: datetime | None
    ) -> list[dict]:
        """Получить точный desired set из пользовательской библиотеки."""
        query = (
            select(Preset)
            .join(UserSavedPreset, UserSavedPreset.preset_id == Preset.id)
            .where(
                and_(
                    UserSavedPreset.user_id == user_id,
                    UserSavedPreset.sync.is_(True),
                    Preset.active.is_(True),
                    Preset.filament_id.isnot(None),
                )
            )
        )
        if since:
            query = query.where((Preset.updated_at >= since) | (UserSavedPreset.saved_at >= since))

        result = await self.db.execute(query)
        presets = list(result.scalars().unique().all())

        return [
            {
                "id": p.id,
                "name": p.name,
                "user_id": p.user_id,
                "updated_at": p.updated_at.isoformat() if p.updated_at else None,
                "orcaslicer_settings": p.orcaslicer_settings,
            }
            for p in presets
        ]

    async def _get_printer_profiles(
        self, user_id: int, since: datetime | None
    ) -> list[dict]:
        """Получить printer profiles пользователя."""
        query = select(PrinterProfile).where(
            and_(
                PrinterProfile.owner_user_id == user_id,
                PrinterProfile.active == True,
            )
        )
        if since:
            query = query.where(PrinterProfile.updated_at >= since)

        result = await self.db.execute(query)
        profiles = result.scalars().all()

        return [
            {
                "id": p.id,
                "name": p.name,
                "owner_user_id": p.owner_user_id,
                "updated_at": p.updated_at.isoformat() if p.updated_at else None,
                "orcaslicer_settings": p.orcaslicer_settings,
            }
            for p in profiles
        ]

    async def _get_print_profiles(
        self, user_id: int, since: datetime | None
    ) -> list[dict]:
        """Получить print profiles пользователя."""
        query = select(PrintProfile).where(
            and_(
                PrintProfile.owner_user_id == user_id,
                PrintProfile.active == True,
            )
        )
        if since:
            query = query.where(PrintProfile.updated_at >= since)

        result = await self.db.execute(query)
        profiles = result.scalars().all()

        return [
            {
                "id": p.id,
                "name": p.name,
                "owner_user_id": p.owner_user_id,
                "updated_at": p.updated_at.isoformat() if p.updated_at else None,
                "orcaslicer_settings": p.orcaslicer_settings,
            }
            for p in profiles
        ]

    async def _detect_deleted_presets(
        self,
        user_id: int,
        device_id: int,
        preset_type: str,
        sync_version: int,
    ) -> list[dict]:
        """Определить пресеты удалённые на сервере с момента последней синхронизации."""
        if sync_version == 0:
            return []

        deleted_query = select(SyncPresetState.preset_id).where(
            and_(
                SyncPresetState.device_id == device_id,
                SyncPresetState.preset_type == SyncPresetType(preset_type),
                SyncPresetState.present.is_(True),
            )
        )
        if preset_type == "filament":
            current = (
                select(UserSavedPreset.preset_id)
                .join(Preset, Preset.id == UserSavedPreset.preset_id)
                .where(
                    and_(
                        UserSavedPreset.preset_id == SyncPresetState.preset_id,
                        UserSavedPreset.user_id == user_id,
                        UserSavedPreset.sync.is_(True),
                        Preset.active.is_(True),
                        Preset.filament_id.isnot(None),
                    )
                )
            )
            deleted_query = deleted_query.where(~current.exists())
        elif preset_type == "printer":
            current = (
                select(PrinterProfile.id).where(
                    and_(
                        PrinterProfile.id == SyncPresetState.preset_id,
                        PrinterProfile.owner_user_id == user_id,
                        PrinterProfile.active.is_(True),
                    )
                )
            )
            deleted_query = deleted_query.where(~current.exists())
        elif preset_type == "print":
            current = (
                select(PrintProfile.id).where(
                    and_(
                        PrintProfile.id == SyncPresetState.preset_id,
                        PrintProfile.owner_user_id == user_id,
                        PrintProfile.active.is_(True),
                    )
                )
            )
            deleted_query = deleted_query.where(~current.exists())

        deleted_result = await self.db.execute(
            deleted_query.order_by(SyncPresetState.preset_id)
        )
        deleted_ids = list(deleted_result.scalars().all())
        if not deleted_ids:
            return []

        metadata: dict[int, tuple[str, int | None]] = {}
        if preset_type == "filament":
            metadata_result = await self.db.execute(
                select(Preset.id, Preset.name, Preset.user_id).where(
                    Preset.id.in_(deleted_ids)
                )
            )
        elif preset_type == "printer":
            metadata_result = await self.db.execute(
                select(
                    PrinterProfile.id,
                    PrinterProfile.name,
                    PrinterProfile.owner_user_id,
                ).where(PrinterProfile.id.in_(deleted_ids))
            )
        else:
            metadata_result = await self.db.execute(
                select(
                    PrintProfile.id,
                    PrintProfile.name,
                    PrintProfile.owner_user_id,
                ).where(PrintProfile.id.in_(deleted_ids))
            )
        metadata = {
            preset_id: (name, owner_user_id)
            for preset_id, name, owner_user_id in metadata_result.all()
        }

        return [
            {
                "id": preset_id,
                "name": metadata.get(preset_id, (f"Preset #{preset_id}", None))[0],
                "user_id": metadata.get(preset_id, ("", None))[1],
            }
            for preset_id in deleted_ids
        ]
