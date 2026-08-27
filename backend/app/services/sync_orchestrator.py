"""Оркестратор синхронизации пресетов между OrcaSlicer и FilamentHub."""

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.preset import Preset
from app.models.print_profile import PrintProfile
from app.models.printer_profile import PrinterProfile
from app.models.sync_device import SyncDevice
from app.models.sync_history import SyncHistory, SyncOperation, SyncPresetType, SyncStatus
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


def _decode_observation(history: SyncHistory) -> tuple[str, str | None]:
    """Read new structured observations while keeping old history useful."""
    if history.error_message:
        try:
            payload = json.loads(history.error_message)
        except (TypeError, ValueError):
            payload = None
        if isinstance(payload, dict) and payload.get("state") in _OBSERVATION_STATUS:
            error_code = payload.get("error_code")
            return payload["state"], error_code if isinstance(error_code, str) else None

    if history.status == SyncStatus.ERROR:
        return "error", "legacy_sync_error"
    if history.status == SyncStatus.CONFLICT:
        return "pending_restart", None
    if history.operation == SyncOperation.DELETE:
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
        }

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
            )
            self.db.add(history)

        device.sync_version = sync_version
        device.last_sync_at = datetime.now(timezone.utc)
        await self.db.flush()
        return device, False

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

        results = []
        for item in deleted_ids:
            preset_id = item["id"]
            results.append({
                "preset_id": preset_id,
                "name": item.get("name", ""),
                "was_created_by_user": item.get("user_id") == user_id,
                "was_saved_by_user": await self._is_saved_by_user(user_id, preset_id),
            })
        return results

    async def get_sync_status(
        self,
        user_id: int,
        device_fingerprint: str | None = None,
    ) -> dict:
        """Получить desired state и последнее наблюдение выбранного устройства."""
        devices_result = await self.db.execute(
            select(SyncDevice).where(SyncDevice.user_id == user_id)
        )
        devices = list(devices_result.scalars().all())
        devices.sort(
            key=lambda item: (
                item.last_sync_at or item.updated_at or item.created_at,
                item.id,
            ),
            reverse=True,
        )

        device = None
        if device_fingerprint is not None:
            device = next(
                (item for item in devices if item.device_fingerprint == device_fingerprint),
                None,
            )
            if device is None:
                raise LookupError("sync device not found")
        elif devices:
            device = devices[0]

        saved_result = await self.db.execute(
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
        saved_presets = list(saved_result.scalars().all())

        history_entries: list[SyncHistory] = []
        latest_by_preset: dict[int, SyncHistory] = {}
        if device is not None:
            history_result = await self.db.execute(
                select(SyncHistory)
                .where(
                    and_(
                        SyncHistory.device_id == device.id,
                        SyncHistory.preset_type == SyncPresetType.FILAMENT,
                    )
                )
                .order_by(SyncHistory.created_at.desc(), SyncHistory.id.desc())
            )
            all_history = list(history_result.scalars().all())
            for history in all_history:
                latest_by_preset.setdefault(history.preset_id, history)
            history_entries = [
                history for history in all_history if history.sync_version == device.sync_version
            ]

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
                observed_at = latest.created_at.isoformat()
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

        success_count = sum(1 for h in history_entries if h.status == SyncStatus.SUCCESS)
        error_count = sum(1 for h in history_entries if h.status == SyncStatus.ERROR)
        conflict_count = sum(1 for h in history_entries if h.status == SyncStatus.CONFLICT)

        return {
            "device_fingerprint": device.device_fingerprint if device else None,
            "sync_version": device.sync_version if device else 0,
            "last_sync_at": (
                device.last_sync_at.isoformat()
                if device is not None and device.last_sync_at
                else None
            ),
            "last_sync_stats": {
                "total": len(history_entries),
                "success": success_count,
                "errors": error_count,
                "pending_restart": conflict_count,
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
            "presets": preset_statuses,
        }

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

        # Получить ID пресетов из истории последней синхронизации
        result = await self.db.execute(
            select(SyncHistory.preset_id).where(
                and_(
                    SyncHistory.device_id == device_id,
                    SyncHistory.preset_type == SyncPresetType(preset_type),
                    SyncHistory.status == SyncStatus.SUCCESS,
                    SyncHistory.operation == SyncOperation.DOWNLOAD,
                )
            )
        )
        synced_ids = {row[0] for row in result.all()}

        if not synced_ids:
            return []

        # Получить текущие активные ID
        current_ids = set()
        if preset_type == "filament":
            res = await self.db.execute(
                select(UserSavedPreset.preset_id)
                .join(Preset, Preset.id == UserSavedPreset.preset_id)
                .where(
                    and_(
                        UserSavedPreset.user_id == user_id,
                        UserSavedPreset.sync.is_(True),
                        Preset.active.is_(True),
                        Preset.filament_id.isnot(None),
                    )
                )
            )
            current_ids = {row[0] for row in res.all()}
        elif preset_type == "printer":
            res = await self.db.execute(
                select(PrinterProfile.id).where(
                    and_(PrinterProfile.owner_user_id == user_id, PrinterProfile.active == True)
                )
            )
            current_ids = {row[0] for row in res.all()}
        elif preset_type == "print":
            res = await self.db.execute(
                select(PrintProfile.id).where(
                    and_(PrintProfile.owner_user_id == user_id, PrintProfile.active == True)
                )
            )
            current_ids = {row[0] for row in res.all()}

        deleted_ids = synced_ids - current_ids

        # Собираем метаданные удалённых
        deleted_presets = []
        for pid in deleted_ids:
            # Попробуем найти неактивный пресет для получения имени
            name = f"Preset #{pid}"
            p_user_id = None
            if preset_type == "filament":
                res = await self.db.execute(select(Preset).where(Preset.id == pid))
                p = res.scalar_one_or_none()
                if p:
                    name = p.name
                    p_user_id = p.user_id
            elif preset_type == "printer":
                res = await self.db.execute(select(PrinterProfile).where(PrinterProfile.id == pid))
                p = res.scalar_one_or_none()
                if p:
                    name = p.name
                    p_user_id = p.owner_user_id
            elif preset_type == "print":
                res = await self.db.execute(select(PrintProfile).where(PrintProfile.id == pid))
                p = res.scalar_one_or_none()
                if p:
                    name = p.name
                    p_user_id = p.owner_user_id

            deleted_presets.append({
                "id": pid,
                "name": name,
                "user_id": p_user_id,
            })

        return deleted_presets

    async def _is_saved_by_user(self, user_id: int, preset_id: int) -> bool:
        """Проверить, сохранён ли пресет пользователем."""
        result = await self.db.execute(
            select(UserSavedPreset.id).where(
                and_(
                    UserSavedPreset.user_id == user_id,
                    UserSavedPreset.preset_id == preset_id,
                )
            )
        )
        return result.scalar_one_or_none() is not None
