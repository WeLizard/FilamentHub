# Обработка удалённых пресетов через систему уведомлений

## Правильный подход

OrcaSlicer общается с **бэкендом** через API, бэкенд создаёт уведомление, которое отображается на сайте в системе уведомлений (колокольчик в хедере/панели).

---

## Архитектура

### 1. OrcaSlicer (C++) → Бэкенд (API)

**Где**: `FilamentHubPanel::synchronize_presets()`

**Что**: Обнаруживает удалённые пресеты и отправляет на бэкенд

**Как**:
- C++ проверяет, существует ли пресет в `PresetBundle` (через `preset_exists_in_bundle()`)
- Если пресет не найден, но есть маппинг в `AppConfig` → пресет удалён локально
- Собираем список удалённых пресетов и отправляем на бэкенд через API

### 2. Бэкенд → Создание уведомления

**Где**: `backend/app/api/v1/endpoints/orcaslicer.py` (новый endpoint)

**Что**: Создаёт уведомление через `notification_service.create_notification()`

**Как**:
- Принимает список удалённых пресетов от OrcaSlicer
- Создаёт уведомление типа `PRESET_LOCALLY_DELETED`
- Сохраняет список пресетов в `extra_data`

### 3. Frontend (React) → Отображение уведомления

**Где**: `frontend/src/components/Notifications.tsx`

**Что**: Отображает уведомление в колокольчике

**Как**:
- Компонент `Notifications` получает уведомления через API
- Показывает уведомление в списке уведомлений
- При клике на уведомление типа `preset_locally_deleted` открывает модалку (вместо перехода по ссылке)

### 4. Frontend (React) → Модалка для обработки

**Где**: `frontend/src/components/DeletedPresetsModal.tsx` (новый компонент)

**Что**: Модалка для обработки удалённых пресетов

**Как**:
- Показывает список удалённых пресетов из `extra_data`
- Пользователь может выбрать действие для каждого пресета:
  - **Восстановить** - импортировать пресет обратно в OrcaSlicer
  - **Удалить из FilamentHub** - удалить пресет из FilamentHub
  - **Пропустить** - просто удалить маппинг
  - **Задать правила** - применить действие ко всем пресетам или сохранить правило на будущее

### 5. Frontend (React) → Бэкенд (API) → OrcaSlicer (C++)

**Где**: `backend/app/api/v1/endpoints/orcaslicer.py` (новый endpoint)

**Что**: Обрабатывает действие пользователя

**Как**:
- Принимает действие от фронтенда (восстановить, удалить, пропустить)
- Выполняет действие (удаляет пресет из FilamentHub, если нужно)
- Сохраняет правило пользователя (если задано)
- Возвращает результат

---

## Реализация

### Шаг 1: Добавить новый тип уведомления

**Файл**: `backend/app/models/notification.py`

```python
class NotificationType(str, Enum):
    """Типы уведомлений."""

    PRESET_UPDATED = "preset_updated"  # Пресет изменен
    PRESET_DELETED = "preset_deleted"  # Пресет удален
    PRESET_LOCALLY_DELETED = "preset_locally_deleted"  # Пресет удалён локально в OrcaSlicer
    BRAND_VERIFIED = "brand_verified"  # Бренд верифицирован
    BRAND_REQUEST_APPROVED = "brand_request_approved"  # Заявка на бренд одобрена
    BRAND_REQUEST_REJECTED = "brand_request_rejected"  # Заявка на бренд отклонена
```

**Файл**: `frontend/src/types/api.ts`

```typescript
export type NotificationType = 
  | 'preset_updated' 
  | 'preset_deleted' 
  | 'preset_locally_deleted'  // Новый тип
  | 'brand_verified' 
  | 'brand_request_approved' 
  | 'brand_request_rejected';
```

**Файл**: `frontend/src/components/Notifications.tsx`

```typescript
const getNotificationIcon = (type: NotificationType) => {
  switch (type) {
    case 'preset_updated':
      return <Settings className="w-5 h-5 text-blue-400" />;
    case 'preset_deleted':
      return <XCircle className="w-5 h-5 text-red-400" />;
    case 'preset_locally_deleted':  // Новый тип
      return <AlertCircle className="w-5 h-5 text-yellow-400" />;
    // ... остальные типы
  }
};
```

### Шаг 2: Создать API endpoint для отправки удалённых пресетов

**Файл**: `backend/app/api/v1/endpoints/orcaslicer.py` (новый файл или расширить существующий)

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import List

from app.core.dependencies import get_current_active_user
from app.db.session import get_db
from app.models.user import User
from app.models.notification import NotificationType
from app.services.notification_service import create_notification

router = APIRouter(prefix="/orcaslicer", tags=["orcaslicer"])


class DeletedPreset(BaseModel):
    """Удалённый пресет."""
    preset_id: int
    preset_name: str
    bundle_preset_name: str  # Имя пресета в OrcaSlicer


class DeletedPresetsRequest(BaseModel):
    """Запрос на создание уведомления об удалённых пресетах."""
    deleted_presets: List[DeletedPreset]


@router.post("/deleted-presets")
async def report_deleted_presets(
    request: DeletedPresetsRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Сообщить бэкенду об удалённых пресетах в OrcaSlicer."""
    if not request.deleted_presets:
        return {"message": "No deleted presets to report"}
    
    # Создаём уведомление
    preset_count = len(request.deleted_presets)
    title = f"Обнаружено {preset_count} удалённых пресетов"
    message = f"В OrcaSlicer обнаружено {preset_count} пресетов, которые были удалены локально, но остаются в FilamentHub."
    
    # Сохраняем список пресетов в extra_data
    extra_data = {
        "deleted_presets": [
            {
                "preset_id": preset.preset_id,
                "preset_name": preset.preset_name,
                "bundle_preset_name": preset.bundle_preset_name,
            }
            for preset in request.deleted_presets
        ]
    }
    
    # Создаём уведомление
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
    }
```

### Шаг 3: Создать API endpoint для обработки действия

**Файл**: `backend/app/api/v1/endpoints/orcaslicer.py` (расширить)

```python
class DeletedPresetAction(BaseModel):
    """Действие для удалённого пресета."""
    action: str  # "restore", "delete", "skip"
    apply_to_all: bool = False  # Применить ко всем пресетам в уведомлении
    save_rule: bool = False  # Сохранить правило на будущее


@router.post("/deleted-presets/{notification_id}/action")
async def handle_deleted_preset_action(
    notification_id: int,
    action: DeletedPresetAction,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Обработать действие пользователя для удалённого пресета."""
    # Получаем уведомление
    from sqlalchemy import select
    from app.models.notification import Notification
    
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
    
    if action.action == "delete":
        # Удаляем пресеты из FilamentHub
        from app.models.preset import Preset
        from app.services.preset_service import delete_preset
        
        for preset_data in deleted_presets:
            preset_id = preset_data["preset_id"]
            # Проверяем, что пресет принадлежит пользователю
            preset_result = await db.execute(
                select(Preset).where(
                    Preset.id == preset_id,
                    Preset.user_id == current_user.id,
                )
            )
            preset = preset_result.scalar_one_or_none()
            
            if preset:
                await delete_preset(preset_id, current_user.id, db)
    
    elif action.action == "restore":
        # Восстанавливаем пресеты в OrcaSlicer (OrcaSlicer сам импортирует при следующей синхронизации)
        # Просто удаляем маппинг из AppConfig (через специальный endpoint или флаг)
        # Или оставляем маппинг, чтобы OrcaSlicer переимпортировал пресет
        pass
    
    elif action.action == "skip":
        # Пропускаем (просто удаляем маппинг)
        pass
    
    # Сохраняем правило пользователя, если задано
    if action.save_rule:
        # Сохраняем правило в UserSettings или AppConfig
        # Например, в таблице user_settings или в extra_data пользователя
        pass
    
    # Отмечаем уведомление как прочитанное
    from datetime import datetime, timezone
    notification.read = True
    notification.read_at = datetime.now(timezone.utc)
    await db.commit()
    
    return {
        "message": "Action processed",
        "action": action.action,
        "preset_count": len(deleted_presets),
    }
```

### Шаг 4: Расширить компонент Notifications для обработки клика

**Файл**: `frontend/src/components/Notifications.tsx`

```typescript
const [deletedPresetsModalOpen, setDeletedPresetsModalOpen] = useState(false);
const [selectedNotification, setSelectedNotification] = useState<Notification | null>(null);

const handleNotificationClick = (notification: Notification) => {
  // Отмечаем как прочитанное при клике
  if (!notification.read) {
    markAsReadMutation.mutate(notification.id);
  }
  
  // Если это уведомление об удалённых пресетах, открываем модалку
  if (notification.type === 'preset_locally_deleted') {
    setSelectedNotification(notification);
    setDeletedPresetsModalOpen(true);
    setIsOpen(false);  // Закрываем dropdown уведомлений
    return;
  }
  
  // Для других типов уведомлений переходим по ссылке
  if (notification.link) {
    navigate(notification.link);
    setIsOpen(false);
  }
};

// В JSX добавляем модалку
<DeletedPresetsModal
  open={deletedPresetsModalOpen}
  onOpenChange={setDeletedPresetsModalOpen}
  notification={selectedNotification}
/>
```

### Шаг 5: Создать модалку для обработки удалённых пресетов

**Файл**: `frontend/src/components/DeletedPresetsModal.tsx` (новый файл)

```typescript
import { useState } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from './ui/dialog';
import { Button } from './ui/button';
import { Checkbox } from './ui/checkbox';
import type { Notification } from '../types/api';
import { orcaslicerAPI } from '../api/client';

interface DeletedPresetsModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  notification: Notification | null;
}

export const DeletedPresetsModal: React.FC<DeletedPresetsModalProps> = ({
  open,
  onOpenChange,
  notification,
}) => {
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
  }>;
  
  const handleAction = async (action: 'restore' | 'delete' | 'skip') => {
    setProcessing(true);
    try {
      await orcaslicerAPI.handleDeletedPresetAction(notification.id, {
        action,
        apply_to_all: applyToAll,
        save_rule: saveRule,
      });
      
      // Закрываем модалку после успешной обработки
      onOpenChange(false);
      
      // Обновляем список уведомлений
      // (queryClient.invalidateQueries уже вызывается в Notifications компоненте)
    } catch (error) {
      console.error('Failed to handle deleted preset action:', error);
      // Показываем ошибку пользователю
    } finally {
      setProcessing(false);
    }
  };
  
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Удалённые пресеты</DialogTitle>
          <DialogDescription>
            Обнаружено {deletedPresets.length} пресетов, которые были удалены из OrcaSlicer, 
            но остаются в FilamentHub.
          </DialogDescription>
        </DialogHeader>
        
        <div className="space-y-4">
          {/* Список пресетов */}
          <div className="space-y-2 max-h-64 overflow-y-auto">
            {deletedPresets.map((preset) => (
              <div key={preset.preset_id} className="flex items-center justify-between p-3 border rounded">
                <div>
                  <p className="font-semibold">{preset.preset_name}</p>
                  <p className="text-sm text-gray-500">{preset.bundle_preset_name}</p>
                </div>
                {!applyToAll && (
                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => handleAction('restore')}
                      disabled={processing}
                    >
                      Восстановить
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => handleAction('delete')}
                      disabled={processing}
                    >
                      Удалить
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => handleAction('skip')}
                      disabled={processing}
                    >
                      Пропустить
                    </Button>
                  </div>
                )}
              </div>
            ))}
          </div>
          
          {/* Опции */}
          <div className="space-y-2">
            <label className="flex items-center space-x-2">
              <Checkbox
                checked={applyToAll}
                onCheckedChange={(checked) => setApplyToAll(checked as boolean)}
              />
              <span>Применить действие ко всем пресетам</span>
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
          {applyToAll && (
            <>
              <Button
                onClick={() => handleAction('restore')}
                disabled={processing}
              >
                Восстановить все
              </Button>
              <Button
                onClick={() => handleAction('delete')}
                disabled={processing}
                variant="destructive"
              >
                Удалить все из FilamentHub
              </Button>
              <Button
                onClick={() => handleAction('skip')}
                disabled={processing}
                variant="outline"
              >
                Пропустить все
              </Button>
            </>
          )}
          <Button onClick={() => onOpenChange(false)} variant="outline">
            Закрыть
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
```

### Шаг 6: Обновить C++ код для отправки удалённых пресетов

**Файл**: `docs/OrcaSlicer/src/slic3r/GUI/FilamentHubPanel.cpp`

```cpp
// В synchronize_presets(), после обнаружения удалённых пресетов
if (!deleted_presets.empty()) {
    // Отправляем на бэкенд через API
    FilamentHubClient client;
    client.set_api_base_url(m_api_base_url.empty() ? FilamentHubClient::DEFAULT_API_BASE_URL : m_api_base_url);
    
    std::string access_token = load_access_token();
    if (!access_token.empty()) {
        // Собираем данные для отправки
        nlohmann::json deleted_presets_json = nlohmann::json::array();
        for (const auto& preset : deleted_presets) {
            nlohmann::json preset_json;
            preset_json["preset_id"] = preset.preset_id;
            preset_json["preset_name"] = preset.preset_name;
            preset_json["bundle_preset_name"] = preset.bundle_preset_name;
            deleted_presets_json.push_back(preset_json);
        }
        
        nlohmann::json request_json;
        request_json["deleted_presets"] = deleted_presets_json;
        
        // Отправляем на бэкенд
        client.report_deleted_presets(
            access_token,
            request_json.dump(),
            [this](std::string json_body, unsigned http_status) {
                BOOST_LOG_TRIVIAL(info) << "FilamentHub: Deleted presets reported. Status: " << http_status;
            },
            [](std::string body, std::string error, unsigned http_status) {
                BOOST_LOG_TRIVIAL(error) << "FilamentHub: Failed to report deleted presets: " << error;
            }
        );
    }
}
```

### Шаг 7: Добавить метод в FilamentHubClient

**Файл**: `docs/OrcaSlicer/src/slic3r/Utils/FilamentHubClient.cpp`

```cpp
void FilamentHubClient::report_deleted_presets(
    const std::string& access_token,
    const std::string& request_body,
    std::function<void(std::string, unsigned)> on_complete,
    std::function<void(std::string, std::string, unsigned)> on_error
) {
    std::string url = m_api_base_url + "/api/v1/orcaslicer/deleted-presets";
    
    Http::get().perform_sync(
        Http::post(url)
            .header("Authorization", "Bearer " + access_token)
            .header("Content-Type", "application/json")
            .body(request_body),
        on_complete,
        on_error
    );
}
```

---

## Преимущества подхода

### ✅ Единообразие
- Используем существующую систему уведомлений
- Пользователь видит уведомление в привычном месте (колокольчик)
- Не нужно создавать новую систему уведомлений

### ✅ Централизация
- Вся логика на бэкенде
- OrcaSlicer просто сообщает бэкенду об удалённых пресетах
- Бэкенд управляет уведомлениями и правилами пользователя

### ✅ Гибкость
- Можно добавить правила пользователя (например, "всегда восстанавливать")
- Можно сохранить историю действий
- Можно добавить аналитику

### ✅ Простота
- Не нужно синхронизировать состояние между OrcaSlicer и сайтом
- Уведомление появляется автоматически при следующем обновлении списка уведомлений
- Пользователь видит уведомление в привычном месте

---

## Вопросы для обсуждения

1. **Нужно ли сохранять правила пользователя?**
   - Да, сохранять в `user_settings` или `extra_data` пользователя
   - Нет, просто применять действие без сохранения

2. **Что делать, если пользователь не обработал уведомление?**
   - Оставить уведомление висеть до обработки
   - Автоматически обработать через некоторое время (например, через 7 дней)

3. **Нужно ли группировать уведомления?**
   - Да, если есть несколько уведомлений об удалённых пресетах, объединить их в одно
   - Нет, показывать каждое уведомление отдельно

4. **Как обрабатывать восстановление пресетов?**
   - OrcaSlicer сам импортирует пресеты при следующей синхронизации (если маппинг удалён)
   - Нужен специальный endpoint для принудительного импорта пресетов

