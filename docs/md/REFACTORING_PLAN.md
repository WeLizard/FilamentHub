# План рефакторинга FilamentHubPanel

## Текущее состояние
- **Файл:** `FilamentHubPanel.cpp` - **6241 строка** ❌
- **Методов:** 71 метод
- **Ответственности:** UI, синхронизация, экспорт, импорт, конфигурация, уведомления

## Проблемы
1. ❌ Слишком большой файл (6241 строка)
2. ❌ Нарушение Single Responsibility Principle
3. ❌ Сложно поддерживать и тестировать
4. ❌ Медленная компиляция
5. ❌ Сложно найти нужный код

---

## Предлагаемая структура

### 1. FilamentHubPanel (основной UI класс)
**Размер:** ~800-1000 строк
**Ответственности:**
- Инициализация UI (WebView, кнопки, панели)
- Обработка событий WebView
- Навигация (catalog, profile)
- Координация между компонентами

**Методы:**
- `init()`, `load_url()`, `reload()`
- `OnError()`, `OnLoaded()`, `OnScriptMessage()`
- `navigate_to_catalog()`, `navigate_to_profile()`
- `show_login()`, `logout()`
- `update_user_info()`, `update_sync_button_state()`

---

### 2. FilamentHubSyncManager (синхронизация)
**Размер:** ~1500-2000 строк
**Ответственности:**
- Синхронизация filament presets
- Синхронизация printer profiles
- Синхронизация print profiles
- Очередь импорта пресетов
- Обновление last_sync_time

**Методы:**
- `synchronize_presets()`, `continue_sync_after_token_validation()`
- `synchronize_printer_profiles()`, `synchronize_print_profiles()`
- `process_preset_import_queue()`
- `import_preset_silent()`, `import_preset_silent_with_callback()`
- `update_preset_info_file()`

**Файлы:**
- `FilamentHubSyncManager.hpp`
- `FilamentHubSyncManager.cpp`

---

### 3. FilamentHubExportManager (экспорт)
**Размер:** ~1000-1500 строк
**Ответственности:**
- Экспорт filament presets в FilamentHub
- Экспорт printer profiles в FilamentHub
- Экспорт print profiles в FilamentHub
- Проверка разрешений перед экспортом

**Методы:**
- `export_filament_presets_to_filamenthub()`
- `export_filament_presets_to_filamenthub_internal()`
- `export_printer_profiles_to_filamenthub()`
- `export_printer_profiles_to_filamenthub_internal()`
- `export_print_profiles_to_filamenthub()`
- `export_print_profiles_to_filamenthub_internal()`

**Файлы:**
- `FilamentHubExportManager.hpp`
- `FilamentHubExportManager.cpp`

---

### 4. FilamentHubConfigManager (конфигурация)
**Размер:** ~300-500 строк
**Ответственности:**
- Управление токенами (save/load)
- Управление маппингами пресетов
- Управление last_sync_time
- Управление настройками (frontend_url, api_base_url)

**Методы:**
- `save_auth_token()`, `load_auth_token()`
- `save_preset_mapping()`, `load_preset_mapping()`, `remove_preset_mapping()`
- `save_last_sync_time()`, `load_last_sync_time()`
- `save_printer_profile_mapping()`, `load_printer_profile_mapping()`
- `save_print_profile_mapping()`, `load_print_profile_mapping()`
- `load_configuration()`, `apply_configuration()`
- `update_frontend_url()`, `update_api_base_url()`

**Файлы:**
- `FilamentHubConfigManager.hpp`
- `FilamentHubConfigManager.cpp`

---

### 5. FilamentHubPresetHelper (утилиты для пресетов)
**Размер:** ~200-300 строк
**Ответственности:**
- Вспомогательные функции для работы с пресетами
- Проверка существования пресетов
- Обработка имен пресетов

**Методы:**
- `preset_exists_in_bundle()`
- `ensure_filamenthub_postfix()`
- `ensure_parent_preset_exists()`
- `get_deleted_preset_action()`, `set_deleted_preset_action()`
- `ask_deleted_preset_action()`
- `delete_preset_from_filamenthub()`

**Файлы:**
- `FilamentHubPresetHelper.hpp`
- `FilamentHubPresetHelper.cpp`

---

### 6. FilamentHubNotificationsManager (уведомления)
**Размер:** ~200-300 строк
**Ответственности:**
- Управление уведомлениями
- Отображение счетчика непрочитанных
- Dropdown меню уведомлений

**Методы:**
- `update_unread_notifications_count()`
- `show_notifications_dropdown()`

**Файлы:**
- `FilamentHubNotificationsManager.hpp`
- `FilamentHubNotificationsManager.cpp`

---

## Структура после рефакторинга

```
docs/OrcaSlicer/src/slic3r/GUI/
├── FilamentHubPanel.hpp (~200 строк)
├── FilamentHubPanel.cpp (~800 строк)
├── FilamentHubSyncManager.hpp (~150 строк)
├── FilamentHubSyncManager.cpp (~1500 строк)
├── FilamentHubExportManager.hpp (~100 строк)
├── FilamentHubExportManager.cpp (~1000 строк)
├── FilamentHubConfigManager.hpp (~100 строк)
├── FilamentHubConfigManager.cpp (~400 строк)
├── FilamentHubPresetHelper.hpp (~80 строк)
├── FilamentHubPresetHelper.cpp (~250 строк)
├── FilamentHubNotificationsManager.hpp (~50 строк)
└── FilamentHubNotificationsManager.cpp (~200 строк)
```

**Итого:** ~5000 строк (было 6241) + заголовки

---

## Преимущества рефакторинга

1. ✅ **Читаемость:** Каждый класс отвечает за свою область
2. ✅ **Поддерживаемость:** Легче найти и исправить баги
3. ✅ **Тестируемость:** Можно тестировать компоненты отдельно
4. ✅ **Компиляция:** Быстрее компилируется (меньше зависимостей)
5. ✅ **Масштабируемость:** Легче добавлять новые фичи

---

## План выполнения

### Этап 1: ConfigManager (самый простой)
1. Создать `FilamentHubConfigManager`
2. Перенести методы работы с конфигурацией
3. Обновить `FilamentHubPanel` для использования ConfigManager

### Этап 2: PresetHelper
1. Создать `FilamentHubPresetHelper`
2. Перенести утилиты для пресетов
3. Обновить зависимости

### Этап 3: NotificationsManager
1. Создать `FilamentHubNotificationsManager`
2. Перенести логику уведомлений
3. Обновить UI

### Этап 4: ExportManager
1. Создать `FilamentHubExportManager`
2. Перенести логику экспорта
3. Обновить зависимости

### Этап 5: SyncManager (самый сложный)
1. Создать `FilamentHubSyncManager`
2. Перенести логику синхронизации
3. Обновить зависимости

---

## Риски

1. ⚠️ **Время:** Рефакторинг займет 2-3 часа
2. ⚠️ **Тестирование:** Нужно протестировать все сценарии
3. ⚠️ **Зависимости:** Нужно правильно передать зависимости между классами

---

## Рекомендация

**Сейчас:** Можно оставить как есть, если нет времени на рефакторинг.

**Потом:** Обязательно сделать рефакторинг перед добавлением новых фич.

**Приоритет:** Средний (не критично, но желательно)



