# Финальный подход: Обработка удалённых пресетов через систему уведомлений

## ✅ Статус: Реализовано

Все компоненты системы обработки удалённых пресетов реализованы и готовы к использованию.

## Ключевые факторы

### 1. Типы пресетов в "Мои пресеты"

**Созданные пользователем** (`Preset.user_id == current_user.id`):
- Пользователь сам создал пресет в FilamentHub
- Пресет принадлежит пользователю
- **НЕ удалять автоматически** из FilamentHub при удалении уведомления

**Сохранённые пресеты** (`UserSavedPreset`):
- Пользователь сохранил пресет из каталога (добавил в избранное)
- Пресет создан другим пользователем или производителем
- **Можно удалить** из "Мои пресеты" (убрать из избранного) при удалении уведомления
- Сам пресет остается в каталоге

### 2. Правила пользователя

**Варианты правил**:
- `always_restore` - Всегда восстанавливать пресеты
- `always_delete` - Всегда удалять пресеты из "Мои пресеты"
- `always_ask` - Всегда спрашивать (по умолчанию)
- `restore_created_delete_saved` - Восстанавливать созданные, удалять сохранённые
- `restore_created_ask_saved` - Восстанавливать созданные, спрашивать для сохранённых

### 3. Группировка уведомлений

- Несколько удалённых пресетов объединяются в **одно уведомление**
- В модалке можно выбрать несколько пресетов галочками
- Можно применить действие ко всем выбранным пресетам

### 4. Обработка удалённых уведомлений

- Если пользователь **удалил уведомление** (не обработал):
  - Для **созданных пресетов**: НЕ удалять из FilamentHub (оставить как есть)
  - Для **сохранённых пресетов**: Удалить из "Мои пресеты" (убрать из избранного) через 7 дней или при следующей синхронизации

---

## Архитектура решения

### 1. OrcaSlicer (C++) → Бэкенд (API)

**Файл**: `docs/OrcaSlicer/src/slic3r/GUI/FilamentHubPanel.cpp`

**Что**: Обнаруживает удалённые пресеты и отправляет на бэкенд

**Как**:
```cpp
// В synchronize_presets(), после обнаружения удалённых пресетов
if (!deleted_presets.empty()) {
    // Собираем данные для отправки
    nlohmann::json deleted_presets_json = nlohmann::json::array();
    for (const auto& preset : deleted_presets) {
        nlohmann::json preset_json;
        preset_json["preset_id"] = preset.preset_id;
        preset_json["preset_name"] = preset.preset_name;
        preset_json["bundle_preset_name"] = preset.bundle_preset_name;
        deleted_presets_json.push_back(preset_json);
    }
    
    // Отправляем на бэкенд
    client.report_deleted_presets(
        access_token,
        deleted_presets_json.dump(),
        [](std::string json_body, unsigned http_status) {
            BOOST_LOG_TRIVIAL(info) << "FilamentHub: Deleted presets reported. Status: " << http_status;
        },
        [](std::string body, std::string error, unsigned http_status) {
            BOOST_LOG_TRIVIAL(error) << "FilamentHub: Failed to report deleted presets: " << error;
        }
    );
}
```

### 2. Бэкенд → Создание уведомления

**Файл**: `backend/app/api/v1/endpoints/orca_sync.py` (расширен)

**Что**: Создаёт уведомление через `notification_service.create_notification()`

**Как**:
```python
@router.post("/deleted-presets")
async def report_deleted_presets(
    request: DeletedPresetsRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Сообщить бэкенду об удалённых пресетах в OrcaSlicer."""
    if not request.deleted_presets:
        return {"message": "No deleted presets to report"}
    
    # Разделяем пресеты на созданные и сохранённые
    created_preset_ids = []
    saved_preset_ids = []
    
    for preset_data in request.deleted_presets:
        preset_id = preset_data.preset_id
        
        # Проверяем, создан ли пресет пользователем
        preset_result = await db.execute(
            select(Preset).where(
                Preset.id == preset_id,
                Preset.user_id == current_user.id,
            )
        )
        preset = preset_result.scalar_one_or_none()
        
        if preset:
            # Пресет создан пользователем
            created_preset_ids.append(preset_id)
        else:
            # Пресет сохранён пользователем (из каталога)
            saved_preset_ids.append(preset_id)
    
    # Создаём уведомление
    preset_count = len(request.deleted_presets)
    title = f"Обнаружено {preset_count} удалённых пресетов"
    message = f"В OrcaSlicer обнаружено {preset_count} пресетов, которые были удалены локально, но остаются в FilamentHub."
    
    # Сохраняем список пресетов в extra_data с указанием типа
    extra_data = {
        "deleted_presets": [
            {
                "preset_id": preset.preset_id,
                "preset_name": preset.preset_name,
                "bundle_preset_name": preset.bundle_preset_name,
                "is_created": preset.preset_id in created_preset_ids,  # Создан пользователем
                "is_saved": preset.preset_id in saved_preset_ids,  # Сохранён пользователем
            }
            for preset in request.deleted_presets
        ],
        "created_count": len(created_preset_ids),
        "saved_count": len(saved_preset_ids),
    }
    
    # Проверяем правила пользователя
    user_rule = get_user_deleted_preset_rule(current_user.id, db)
    
    # Если правило "always_restore" или "always_delete", применяем автоматически
    if user_rule == "always_restore":
        # Восстанавливаем все пресеты (удаляем маппинг, OrcaSlicer переимпортирует)
        # Уведомление не создаём, просто удаляем маппинг
        return {"message": "All presets will be restored automatically", "rule": user_rule}
    
    elif user_rule == "always_delete":
        # Удаляем сохранённые пресеты из "Мои пресеты"
        # Созданные пресеты не трогаем
        for preset_id in saved_preset_ids:
            await remove_saved_preset(current_user.id, preset_id, db)
        
        # Уведомление не создаём
        return {"message": "Saved presets removed automatically", "rule": user_rule}
    
    # Если правило "always_ask" или другое, создаём уведомление
    notification = await create_notification(
        user_id=current_user.id,
        notification_type=NotificationType.PRESET_LOCALLY_DELETED,
        title=title,
        message=message,
        db=db,
        link=None,  # Не переходим по ссылке, открываем модалку
        extra_data=extra_data,
    )
    
    return {
        "message": "Notification created",
        "notification_id": notification.id,
        "preset_count": preset_count,
        "created_count": len(created_preset_ids),
        "saved_count": len(saved_preset_ids),
    }
```

### 3. Бэкенд → Обработка действия

**Файл**: `backend/app/api/v1/endpoints/orca_sync.py` (реализовано)

**Что**: Обрабатывает действие пользователя

**Как**:
```python
@router.post("/deleted-presets/{notification_id}/action")
async def handle_deleted_preset_action(
    notification_id: int,
    action: DeletedPresetAction,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Обработать действие пользователя для удалённого пресета."""
    # Получаем уведомление
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == current_user.id,
            Notification.type == NotificationType.PRESET_LOCALLY_DELETED,
        )
    )
    notification = result.scalar_one_or_none()
    
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    
    # Получаем список удалённых пресетов из extra_data
    deleted_presets = notification.extra_data.get("deleted_presets", [])
    
    # Фильтруем пресеты по выбранным preset_ids (если apply_to_all=False)
    if action.preset_ids:
        deleted_presets = [p for p in deleted_presets if p["preset_id"] in action.preset_ids]
    elif action.apply_to_all:
        # Применяем ко всем пресетам
        pass
    else:
        # Если не указаны preset_ids и не apply_to_all, возвращаем ошибку
        raise HTTPException(status_code=400, detail="preset_ids or apply_to_all required")
    
    processed_count = 0
    
    if action.action == "restore":
        # Восстанавливаем пресеты (удаляем маппинг, OrcaSlicer переимпортирует при следующей синхронизации)
        # Маппинг удаляется на стороне OrcaSlicer (C++), бэкенд просто подтверждает действие
        processed_count = len(deleted_presets)
    
    elif action.action == "delete":
        # Удаляем пресеты из "Мои пресеты"
        for preset_data in deleted_presets:
            preset_id = preset_data["preset_id"]
            is_created = preset_data.get("is_created", False)
            is_saved = preset_data.get("is_saved", False)
            
            if is_created:
                # Пресет создан пользователем - НЕ удаляем из FilamentHub
                # Просто пропускаем
                continue
            elif is_saved:
                # Пресет сохранён пользователем - удаляем из "Мои пресеты" (убираем из избранного)
                await remove_saved_preset(current_user.id, preset_id, db)
                processed_count += 1
    
    elif action.action == "skip":
        # Пропускаем (просто удаляем маппинг)
        # Маппинг удаляется на стороне OrcaSlicer (C++), бэкенд просто подтверждает действие
        processed_count = len(deleted_presets)
    
    # Сохраняем правило пользователя, если задано
    if action.save_rule:
        await save_user_deleted_preset_rule(current_user.id, action.action, db)
    
    # Отмечаем уведомление как прочитанное
    from datetime import datetime, timezone
    notification.read = True
    notification.read_at = datetime.now(timezone.utc)
    await db.commit()
    
    return {
        "message": "Action processed",
        "action": action.action,
        "processed_count": processed_count,
        "total_count": len(deleted_presets),
    }
```

### 4. Бэкенд → Обработка удалённых уведомлений

**Файл**: `backend/app/api/v1/endpoints/orca_sync.py` (реализовано)

**Что**: Обрабатывает автоматически удалённые уведомления

**Как**:
```python
@router.post("/deleted-presets/auto-process")
async def auto_process_deleted_presets(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Автоматически обработать удалённые пресеты для уведомлений, которые были удалены пользователем."""
    # Находим все непрочитанные уведомления об удалённых пресетах старше 7 дней
    from datetime import datetime, timezone, timedelta
    
    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
    
    result = await db.execute(
        select(Notification).where(
            Notification.user_id == current_user.id,
            Notification.type == NotificationType.PRESET_LOCALLY_DELETED,
            Notification.read == False,
            Notification.created_at < seven_days_ago,
        )
    )
    old_notifications = result.scalars().all()
    
    processed_count = 0
    
    for notification in old_notifications:
        deleted_presets = notification.extra_data.get("deleted_presets", [])
        
        # Удаляем только сохранённые пресеты из "Мои пресеты"
        # Созданные пресеты не трогаем
        for preset_data in deleted_presets:
            preset_id = preset_data["preset_id"]
            is_saved = preset_data.get("is_saved", False)
            
            if is_saved:
                # Удаляем сохранённый пресет из "Мои пресеты"
                await remove_saved_preset(current_user.id, preset_id, db)
                processed_count += 1
        
        # Отмечаем уведомление как прочитанное
        notification.read = True
        notification.read_at = datetime.now(timezone.utc)
    
    await db.commit()
    
    return {
        "message": "Auto-processed deleted presets",
        "processed_count": processed_count,
        "notifications_processed": len(old_notifications),
    }
```

### 5. Frontend → Модалка для обработки

**Файл**: `frontend/src/components/DeletedPresetsModal.tsx` (новый файл)

**Что**: Модалка для обработки удалённых пресетов

**Как**:
```typescript
export const DeletedPresetsModal: React.FC<DeletedPresetsModalProps> = ({
  open,
  onOpenChange,
  notification,
}) => {
  const [selectedPresetIds, setSelectedPresetIds] = useState<number[]>([]);
  const [selectedAction, setSelectedAction] = useState<'restore' | 'delete' | 'skip' | null>(null);
  const [applyToAll, setApplyToAll] = useState(false);
  const [saveRule, setSaveRule] = useState(false);
  const [processing, setProcessing] = useState(false);
  
  if (!notification || !notification.extra_data?.deleted_presets) {
    return null;
  }
  
  const deletedPresets = notification.extra_data.deleted_presets as Array<{
    preset_id: number;
    preset_name: string;
    bundle_preset_name: string;
    is_created: boolean;
    is_saved: boolean;
  }>;
  
  const createdPresets = deletedPresets.filter(p => p.is_created);
  const savedPresets = deletedPresets.filter(p => p.is_saved);
  
  const handleTogglePreset = (presetId: number) => {
    if (selectedPresetIds.includes(presetId)) {
      setSelectedPresetIds(selectedPresetIds.filter(id => id !== presetId));
    } else {
      setSelectedPresetIds([...selectedPresetIds, presetId]);
    }
  };
  
  const handleSelectAll = () => {
    if (selectedPresetIds.length === deletedPresets.length) {
      setSelectedPresetIds([]);
    } else {
      setSelectedPresetIds(deletedPresets.map(p => p.preset_id));
    }
  };
  
  const handleAction = async (action: 'restore' | 'delete' | 'skip') => {
    setProcessing(true);
    try {
      await orcaslicerAPI.handleDeletedPresetAction(notification.id, {
        action,
        preset_ids: applyToAll ? undefined : selectedPresetIds,
        apply_to_all: applyToAll,
        save_rule: saveRule,
      });
      
      // Закрываем модалку после успешной обработки
      onOpenChange(false);
      
      // Обновляем список уведомлений
      queryClient.invalidateQueries({ queryKey: ['notifications', user?.id] });
    } catch (error) {
      console.error('Failed to handle deleted preset action:', error);
    } finally {
      setProcessing(false);
    }
  };
  
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Удалённые пресеты</DialogTitle>
          <DialogDescription>
            Обнаружено {deletedPresets.length} пресетов, которые были удалены из OrcaSlicer, 
            но остаются в FilamentHub.
          </DialogDescription>
        </DialogHeader>
        
        <div className="space-y-4">
          {/* Информация о типах пресетов */}
          <div className="flex gap-4 text-sm text-gray-400">
            <span>Созданные: {createdPresets.length}</span>
            <span>Сохранённые: {savedPresets.length}</span>
          </div>
          
          {/* Предупреждение для созданных пресетов */}
          {createdPresets.length > 0 && (
            <div className="p-3 bg-yellow-500/10 border border-yellow-500/20 rounded">
              <p className="text-sm text-yellow-400">
                ⚠️ {createdPresets.length} пресетов были созданы вами. Они не будут удалены из FilamentHub автоматически.
              </p>
            </div>
          )}
          
          {/* Список пресетов */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="flex items-center space-x-2">
                <Checkbox
                  checked={selectedPresetIds.length === deletedPresets.length}
                  onCheckedChange={handleSelectAll}
                />
                <span>Выбрать все</span>
              </label>
            </div>
            
            <div className="space-y-2 max-h-64 overflow-y-auto">
              {deletedPresets.map((preset) => (
                <div
                  key={preset.preset_id}
                  className={`flex items-center justify-between p-3 border rounded ${
                    selectedPresetIds.includes(preset.preset_id) ? 'bg-blue-500/10' : ''
                  }`}
                >
                  <div className="flex items-center space-x-3">
                    <Checkbox
                      checked={selectedPresetIds.includes(preset.preset_id)}
                      onCheckedChange={() => handleTogglePreset(preset.preset_id)}
                    />
                    <div>
                      <p className="font-semibold">{preset.preset_name}</p>
                      <p className="text-sm text-gray-500">{preset.bundle_preset_name}</p>
                      {preset.is_created && (
                        <span className="text-xs text-yellow-400">Создан вами</span>
                      )}
                      {preset.is_saved && (
                        <span className="text-xs text-blue-400">Сохранён из каталога</span>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
          
          {/* Опции */}
          <div className="space-y-2">
            <label className="flex items-center space-x-2">
              <Checkbox
                checked={applyToAll}
                onCheckedChange={(checked) => setApplyToAll(checked as boolean)}
              />
              <span>Применить действие ко всем выбранным пресетам</span>
            </label>
            <label className="flex items-center space-x-2">
              <Checkbox
                checked={saveRule}
                onCheckedChange={(checked) => setSaveRule(checked as boolean)}
              />
              <span>Запомнить выбор и применять автоматически в будущем</span>
            </label>
          </div>
        </div>
        
        <DialogFooter>
          <Button
            onClick={() => handleAction('restore')}
            disabled={processing || selectedPresetIds.length === 0}
          >
            Восстановить ({selectedPresetIds.length || deletedPresets.length})
          </Button>
          <Button
            onClick={() => handleAction('delete')}
            disabled={processing || selectedPresetIds.length === 0}
            variant="destructive"
          >
            Удалить из "Мои пресеты" ({selectedPresetIds.length || deletedPresets.length})
          </Button>
          <Button
            onClick={() => handleAction('skip')}
            disabled={processing || selectedPresetIds.length === 0}
            variant="outline"
          >
            Пропустить ({selectedPresetIds.length || deletedPresets.length})
          </Button>
          <Button onClick={() => onOpenChange(false)} variant="outline">
            Закрыть
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
```

### 6. Бэкенд → Сохранение правил пользователя

**Файл**: `backend/app/models/user.py` (расширить)

**Что**: Добавить поле для правила обработки удалённых пресетов

**Как**:
```python
class User(Base):
    # ... существующие поля ...
    
    # Правило обработки удалённых пресетов
    deleted_preset_rule: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # deleted_preset_rule: "always_restore", "always_delete", "always_ask", "restore_created_delete_saved", "restore_created_ask_saved"
```

**Файл**: `backend/app/services/orcaslicer_service.py` (новый файл)

**Что**: Сервис для работы с правилами пользователя

**Как**:
```python
async def get_user_deleted_preset_rule(
    user_id: int,
    db: AsyncSession,
) -> str:
    """Получить правило обработки удалённых пресетов для пользователя."""
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        return "always_ask"  # По умолчанию
    
    return user.deleted_preset_rule or "always_ask"


async def save_user_deleted_preset_rule(
    user_id: int,
    rule: str,
    db: AsyncSession,
) -> None:
    """Сохранить правило обработки удалённых пресетов для пользователя."""
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise ValueError(f"User {user_id} not found")
    
    user.deleted_preset_rule = rule
    await db.commit()
    await db.refresh(user)


async def remove_saved_preset(
    user_id: int,
    preset_id: int,
    db: AsyncSession,
) -> None:
    """Удалить сохранённый пресет из "Мои пресеты"."""
    result = await db.execute(
        select(UserSavedPreset).where(
            UserSavedPreset.user_id == user_id,
            UserSavedPreset.preset_id == preset_id,
        )
    )
    saved_preset = result.scalar_one_or_none()
    
    if saved_preset:
        await db.delete(saved_preset)
        await db.commit()
```

---

## Резюме

### ✅ Реализованные функции:

1. **Различение типов пресетов**: Созданные vs Сохранённые
2. **Правила пользователя**: Всегда восстанавливать/удалять/спрашивать
3. **Группировка уведомлений**: Несколько пресетов в одном уведомлении
4. **Выбор нескольких пресетов**: Галочки для выбора отдельных пресетов
5. **Автоматическая обработка**: При удалении уведомления (только для сохранённых пресетов)
6. **Восстановление пресетов**: OrcaSlicer сам импортирует при следующей синхронизации

### ✅ Реализованные компоненты:

1. ✅ Добавлен тип уведомления `preset_locally_deleted` в `backend/app/models/notification.py`
2. ✅ Созданы API endpoints в `backend/app/api/v1/endpoints/orca_sync.py`:
   - `POST /orcaslicer/deleted-presets` - сообщение об удалённых пресетах
   - `POST /orcaslicer/deleted-presets/{notification_id}/action` - обработка действия
   - `POST /orcaslicer/deleted-presets/auto-process` - автоматическая обработка
3. ✅ Добавлено поле `deleted_preset_rule` в модель User (`backend/app/models/user.py`)
4. ✅ Создана Alembic миграция для добавления `deleted_preset_rule` в users
5. ✅ Создан сервис `backend/app/services/orcaslicer_service.py` для работы с правилами пользователя
6. ✅ Расширен компонент Notifications для открытия модалки при клике на уведомление
7. ✅ Создана модалка `frontend/src/components/DeletedPresetsModal.tsx` для обработки удалённых пресетов
8. ✅ Добавлены API методы в `frontend/src/api/client.ts` для работы с удалёнными пресетами
9. ✅ Обновлён C++ код:
   - Добавлен метод `report_deleted_presets` в `FilamentHubClient`
   - Обновлена логика `synchronize_presets()` для отправки удалённых пресетов на бэкенд
10. ✅ Реализована автоматическая обработка старых уведомлений (через 7 дней)

### 📋 Что нужно протестировать:

1. Синхронизация пресетов с удалёнными локально
2. Создание уведомлений на бэкенде
3. Открытие модалки при клике на уведомление
4. Обработка действий (restore, delete, skip)
5. Сохранение правил пользователя
6. Автоматическая обработка старых уведомлений

