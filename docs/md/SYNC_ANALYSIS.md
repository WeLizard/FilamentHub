# Анализ логики синхронизации: первый раз vs последующие разы

## 🔄 Сценарий 1: Первая синхронизация (force_full_sync=true)

### Что происходит:
1. **OrcaSlicer:** `synchronize_presets(true)` вызывается после логина
2. **Проверка:** `force_full_sync=true` → `updated_since=""` (пустая строка)
3. **API запрос:** `GET /api/v1/auth/my-presets?updated_since=` (без параметра)
4. **Бэкенд:** Возвращает ВСЕ пресеты пользователя с `sync_enabled=True`
5. **OrcaSlicer:** Импортирует все пресеты, создает маппинги в AppConfig
6. **Обновление:** `last_sync_time` сохраняется в AppConfig (текущее время)

### Ожидаемое поведение:
- ✅ Все пресеты с `sync_enabled=True` импортируются
- ✅ Создаются маппинги `preset_mapping_{preset_id} = "{preset_name} [FilamentHub]"`
- ✅ `last_sync_time` устанавливается в текущее время
- ✅ Пресеты сохраняются в `user/{user_id}/filament/` с метками `fhub_id`, `fhub_source`

---

## 🔄 Сценарий 2: Последующие синхронизации (force_full_sync=false)

### Что происходит:
1. **OrcaSlicer:** `synchronize_presets(false)` вызывается пользователем или автоматически
2. **Проверка:** `force_full_sync=false` → загружается `last_sync_time` из AppConfig
3. **API запрос:** `GET /api/v1/auth/my-presets?updated_since={last_sync_time}`
4. **Бэкенд:** Возвращает только пресеты, обновленные после `last_sync_time` с `sync_enabled=True`
5. **OrcaSlicer:** Импортирует только измененные/новые пресеты
6. **Обновление:** `last_sync_time` обновляется в AppConfig

### Ожидаемое поведение:
- ✅ Только измененные/новые пресеты импортируются
- ✅ Существующие пресеты обновляются (если изменились)
- ✅ `last_sync_time` обновляется после успешной синхронизации

---

## ⚠️ ПРОБЛЕМА 1: Зацикливание при пустом списке

### Где происходит:
**Файл:** `FilamentHubPanel.cpp`, строки 1190-1212

```cpp
if (presets.empty() && !force_full_sync && !updated_since.empty()) {
    // Очищаем last_sync_time и делаем полную синхронизацию
    save_last_sync_time(user_id, ""); // Очищаем last_sync_time
    m_active_syncs--;
    // Перезапускаем синхронизацию с force_full_sync=true
    CallAfter([this]() {
        m_is_syncing = false;
        synchronize_presets(true); // ⚠️ РЕКУРСИВНЫЙ ВЫЗОВ!
    });
    return;
}
```

### Проблема:
1. Если API возвращает пустой список при инкрементальной синхронизации
2. Код очищает `last_sync_time` и вызывает `synchronize_presets(true)`
3. Если при полной синхронизации список снова пуст → **ЗАЦИКЛИВАНИЕ!**

### Когда это может произойти:
- Пользователь отключил синхронизацию для всех пресетов (`sync_enabled=False`)
- Все пресеты были удалены из FilamentHub
- Проблемы с API (возвращает пустой список)

### Решение:
Добавить защиту от повторного вызова:
```cpp
if (presets.empty() && !force_full_sync && !updated_since.empty()) {
    // Проверяем, не делали ли мы уже полную синхронизацию
    static bool full_sync_attempted = false;
    if (full_sync_attempted) {
        // Уже пытались - не зацикливаемся
        BOOST_LOG_TRIVIAL(warning) << "Full sync already attempted, skipping to prevent loop";
        return;
    }
    full_sync_attempted = true;
    // ... остальной код
}
```

**ЛУЧШЕ:** Использовать флаг в классе вместо static переменной.

---

## ⚠️ ПРОБЛЕМА 2: Обновление last_sync_time ДО завершения импорта

### Где происходит:
**Файл:** `FilamentHubPanel.cpp`, строки 1413-1420

```cpp
// 9. Обновляем last_sync_time (ISO 8601 format)
save_last_sync_time(user_id, current_time);
```

### Проблема:
`last_sync_time` обновляется **ДО** того, как все пресеты импортированы через очередь!

### Последствия:
1. Если синхронизация прервется (ошибка, закрытие приложения)
2. `last_sync_time` уже обновлен
3. При следующей синхронизации пропустятся пресеты, которые не успели импортироваться

### Решение:
Обновлять `last_sync_time` **ПОСЛЕ** завершения импорта всех пресетов из очереди (в `process_preset_import_queue()`).

---

## ✅ ПРОБЛЕМА 3: Проверка sync_enabled при импорте из OrcaSlicer (ИСПРАВЛЕНО)

### Где происходило:
**Файл:** `orca_sync.py`, строки 1632-1720

### Проблема (была):
При импорте из OrcaSlicer проверялся `sync_enabled`, что неправильно:
- `sync_enabled` контролирует только **экспорт из FilamentHub в OrcaSlicer**
- При импорте из OrcaSlicer пользователь явно экспортировал пресет, значит хочет его синхронизировать

### Решение (применено):
✅ Убрана проверка `sync_enabled` при импорте из OrcaSlicer
- При импорте из OrcaSlicer пресет всегда обрабатывается
- `sync_enabled` проверяется только при экспорте из FilamentHub (в `/api/v1/auth/my-presets`)

---

## ✅ ПРОБЛЕМА 4: Экспорт пресетов с sync_enabled=False (ИСПРАВЛЕНО)

### Где происходило:
**Файл:** `FilamentHubPanel.cpp`, `export_filament_presets_to_filamenthub_internal()`

### Проблема (была):
Экспорт проверял только наличие `fhub_id`, но не проверял `sync_enabled`.

### Решение (применено):
✅ Проверка `sync_enabled` выполняется на бэкенде:
- При экспорте из FilamentHub в OrcaSlicer используется `/api/v1/auth/my-presets`
- Этот эндпоинт возвращает только пресеты с `sync_enabled=True` (строки 407, 442, 450 в `auth.py`)
- Пресеты с `sync_enabled=False` не попадают в список для синхронизации

---

## 📋 Статус исправлений

### 1. Защита от зацикливания ✅ ИСПРАВЛЕНО
- ✅ Добавлен флаг `m_full_sync_attempted` в класс
- ✅ Проверка флага перед рекурсивным вызовом
- ✅ Сброс флага после успешной синхронизации и при новом запуске

### 2. Обновление last_sync_time ✅ ИСПРАВЛЕНО
- ✅ Перемещено обновление `last_sync_time` в `process_preset_import_queue()`
- ✅ Обновляется только после успешного импорта всех пресетов из очереди
- ✅ Добавлен `user_id` в структуру `PresetImportTask` для обновления

### 3. Проверка sync_enabled ✅ ИСПРАВЛЕНО
- ✅ Убрана проверка `sync_enabled` при импорте из OrcaSlicer
- ✅ Проверка остается только при экспорте из FilamentHub (в `/api/v1/auth/my-presets`)

### 4. Логирование
- ✅ Добавлены логи для отслеживания зацикливаний
- ✅ Логируются все рекурсивные вызовы `synchronize_presets()`

---

## ✅ Все проблемы исправлены!

