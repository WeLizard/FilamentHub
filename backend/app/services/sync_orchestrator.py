"""Оркестратор синхронизации пресетов между OrcaSlicer и FilamentHub."""

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

        # Полная синхронизация или инкрементальная
        if force_full_sync or device.sync_version == 0:
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
    ) -> SyncDevice:
        """
        Завершить синхронизацию — инкрементировать sync_version ОДИН раз.

        Вызывается ПОСЛЕ того как клиент подтвердил что всё скачал.
        """
        device = await self.get_or_create_device(user_id, device_fingerprint)
        device.sync_version += 1
        device.last_sync_at = datetime.now(timezone.utc)
        await self.db.flush()
        return device

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
        device_fingerprint: str,
    ) -> dict:
        """Получить статус последней синхронизации."""
        device = await self.get_or_create_device(user_id, device_fingerprint)

        # Последняя история для этого устройства
        result = await self.db.execute(
            select(SyncHistory)
            .where(
                and_(
                    SyncHistory.device_id == device.id,
                    SyncHistory.sync_version == device.sync_version,
                )
            )
            .order_by(SyncHistory.created_at.desc())
        )
        history_entries = result.scalars().all()

        success_count = sum(1 for h in history_entries if h.status == SyncStatus.SUCCESS)
        error_count = sum(1 for h in history_entries if h.status == SyncStatus.ERROR)

        return {
            "device_fingerprint": device.device_fingerprint,
            "sync_version": device.sync_version,
            "last_sync_at": device.last_sync_at.isoformat() if device.last_sync_at else None,
            "last_sync_stats": {
                "total": len(history_entries),
                "success": success_count,
                "errors": error_count,
            },
        }

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
        """Получить filament presets пользователя."""
        # Собственные пресеты
        own_query = select(Preset).where(
            and_(
                Preset.user_id == user_id,
                Preset.active == True,
            )
        )
        if since:
            own_query = own_query.where(Preset.updated_at >= since)

        result = await self.db.execute(own_query)
        own_presets = {p.id: p for p in result.scalars().all()}

        # Сохранённые пресеты с sync=True
        saved_query = (
            select(Preset)
            .join(UserSavedPreset, UserSavedPreset.preset_id == Preset.id)
            .where(
                and_(
                    UserSavedPreset.user_id == user_id,
                    UserSavedPreset.sync == True,
                    Preset.active == True,
                )
            )
        )
        if since:
            saved_query = saved_query.where(Preset.updated_at >= since)

        result = await self.db.execute(saved_query)
        # Сохранённые НЕ перезаписывают собственные (собственные имеют приоритет)
        for p in result.scalars().all():
            if p.id not in own_presets:
                own_presets[p.id] = p

        return [
            {
                "id": p.id,
                "name": p.name,
                "user_id": p.user_id,
                "updated_at": p.updated_at.isoformat() if p.updated_at else None,
                "orcaslicer_settings": p.orcaslicer_settings,
            }
            for p in own_presets.values()
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
                select(Preset.id).where(
                    and_(Preset.user_id == user_id, Preset.active == True)
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
