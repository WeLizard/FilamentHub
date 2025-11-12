# Ожидаемое поведение синхронизации OrcaSlicer ↔ FilamentHub

## 📋 Что должно происходить при нажатии кнопки "Synchronize"

### 1. Обработчик нажатия кнопки (`on_sync_button_click`)

**Логи, которые ДОЛЖНЫ появиться:**
```
[info] FilamentHub: ========== SYNC BUTTON CLICKED ==========
[info] FilamentHub: m_is_syncing=false
[info] FilamentHub: m_active_syncs=0
[info] FilamentHub: Reset m_active_syncs to 0
[info] FilamentHub: Set sync button state to 'Synchronizing...'
[info] FilamentHub: Loading auth token - token length: <N>, user_id_str: '<ID>'
[info] FilamentHub: Loaded auth token for user_id=<ID>, token length: <N>, token preview: <...>
[info] FilamentHub: Auth token loaded. User ID: <ID>, token length: <N>
[info] FilamentHub: Starting sync. m_active_syncs=1
[info] FilamentHub: Calling synchronize_presets(false)...
[info] FilamentHub: Attempting to sync printer and print profiles...
[info] FilamentHub: All sync operations started. m_active_syncs=1
[info] FilamentHub: Note: m_active_syncs may increase when printer/print profiles API responds
```

**Что происходит:**
1. ✅ Проверка, не идет ли уже синхронизация (`m_is_syncing`)
2. ✅ Сброс счетчика активных синхронизаций (`m_active_syncs = 0`)
3. ✅ Обновление состояния кнопки на "Synchronizing..." (`update_sync_button_state(true)`)
4. ✅ Загрузка токена и `user_id` из `AppConfig` (`load_auth_token`)
5. ✅ Если токен отсутствует → показ уведомления "Please login to FilamentHub first." и выход
6. ✅ Установка `m_active_syncs = 1` (для filament presets)
7. ✅ Вызов `synchronize_presets(false)` (инкрементальная синхронизация)
8. ✅ Вызов `synchronize_printer_profiles(false)` (может увеличить `m_active_syncs`)
9. ✅ Вызов `synchronize_print_profiles(false)` (может увеличить `m_active_syncs`)

---

### 2. Синхронизация Filament Presets (`synchronize_presets`)

**Логи, которые ДОЛЖНЫ появиться:**
```
[info] FilamentHub: ========== synchronize_presets() CALLED ==========
[info] FilamentHub: force_full_sync=false
[info] FilamentHub: m_is_syncing=true
[info] FilamentHub: m_active_syncs=1
[info] FilamentHub: Auth token loaded. User ID: <ID>, token length: <N>
[info] FilamentHub: Incremental sync. updated_since: <timestamp> или (none)
[info] FilamentHub: Calling get_my_presets. API: http://localhost:8000, updated_since: <timestamp> или (empty)
[info] FilamentHub: Received presets list. HTTP status: 200, JSON size: <N> bytes
[info] FilamentHub: Parsing presets list...
[info] FilamentHub: Found <N> presets to sync
[info] FilamentHub: Processing preset <ID> (<name>)...
[info] FilamentHub: Preset <ID> not in mapping, importing...
[info] FilamentHub: Importing preset <ID> (<name>)
[info] FilamentHub: Downloading preset <ID> from API: http://localhost:8000, token length: <N>
[info] FilamentHub: Preset <ID> downloaded successfully. HTTP status: 200, JSON size: <N> bytes
[info] FilamentHub: Saved profile to: <temp_file_path>
[info] FilamentHub: Profile imported successfully (name: <name> [FilamentHub])
[info] FilamentHub: Saved mapping preset_id=<ID> -> bundle_preset_name=<name> [FilamentHub]
[info] FilamentHub: Synchronization completed. Synced: <N>, Updated: <M>, Errors: <K>
[info] FilamentHub: Filament presets sync completed. Active syncs: <N>
[info] FilamentHub: Saved last_sync_time for user_id=<ID>: <timestamp>
```

**Что происходит:**
1. ✅ Логирование начала синхронизации
2. ✅ Загрузка токена и `user_id` из `AppConfig`
3. ✅ Если токен отсутствует → уменьшение `m_active_syncs`, обновление UI, показ уведомления, выход
4. ✅ Получение `last_sync_time` из `AppConfig` (для инкрементальной синхронизации)
5. ✅ Создание `FilamentHubClient` с API base URL
6. ✅ Вызов `client.get_my_presets(access_token, updated_since)` → `GET /api/v1/auth/my-presets?updated_since=...`
7. ✅ **Backend:** Проверка JWT токена через `get_current_active_user`
8. ✅ **Backend:** Возврат списка пресетов пользователя (JSON)
9. ✅ Парсинг ответа и получение списка пресетов
10. ✅ Для каждого пресета:
    - Проверка маппинга через `load_preset_mapping(preset_id)`
    - Если нет в маппинге:
      - Вызов `import_preset_silent(preset_id, preset_name, access_token)`
      - Скачивание профиля через `client.download_profile()` → `GET /api/v1/presets/{id}/export/orcaslicer.json`
      - Парсинг JSON профиля
      - Добавление постфикса `[FilamentHub]` к имени пресета
      - Проверка и исправление родительского пресета (`inherits`)
      - Создание временного файла с JSON профилем
      - Импорт профиля через `PresetBundle::import_json_presets()`
      - Сохранение маппинга через `save_preset_mapping(preset_id, bundle_preset_name)`
      - Обновление UI через `wxGetApp().load_current_presets()`
    - Если уже в маппинге:
      - Пропуск (уже синхронизирован)
      - Логирование "Preset <ID> already mapped to <name>, skipping (already synced)"
11. ✅ Обновление `last_sync_time` в `AppConfig`
12. ✅ Уменьшение `m_active_syncs--` в `CallAfter`
13. ✅ Если `m_active_syncs <= 0`:
    - Обновление кнопки синхронизации (`update_sync_button_state(false)`)
    - Обновление информации о пользователе (`update_user_info()`)

**Обработка ошибок:**
- ✅ **401 (Unauthorized):** Очистка токена через `logout()`, показ уведомления "Your session has expired. Please login again.", уменьшение `m_active_syncs`
- ✅ **403 (Forbidden):** Парсинг деталей ошибки из `body`, показ уведомления с объяснением, уменьшение `m_active_syncs`
- ✅ **500+ (Server Error):** Показ уведомления "Server error. Please try again later.", уменьшение `m_active_syncs`
- ✅ **Другие ошибки:** Показ общего сообщения об ошибке, уменьшение `m_active_syncs`
- ✅ **Ошибка парсинга JSON:** Логирование ошибки, показ уведомления, уменьшение `m_active_syncs`

---

### 3. Синхронизация Printer Profiles (`synchronize_printer_profiles`)

**Логи, которые ДОЛЖНЫ появиться:**
```
[info] FilamentHub: ========== synchronize_printer_profiles() CALLED ==========
[info] FilamentHub: force_full_sync=false
[info] FilamentHub: Loading auth token - token length: <N>, user_id_str: '<ID>'
[info] FilamentHub: Loaded auth token for user_id=<ID>, token length: <N>
[info] FilamentHub: Calling get_my_printer_profiles. API: http://localhost:8000, updated_since: <timestamp> или (empty)
[info] FilamentHub: Received printer profiles list. HTTP status: 200, JSON size: <N> bytes
[info] FilamentHub: Incremented m_active_syncs for printer profiles. Active syncs: <N>
[info] FilamentHub: Parsing printer profiles list...
[info] FilamentHub: Found <N> printer profiles to sync
[info] FilamentHub: Processing printer profile <ID> (<name>)...
[info] FilamentHub: Printer profile <ID> not in mapping, importing...
[info] FilamentHub: Downloading printer profile <ID> from API: http://localhost:8000, token length: <N>
[info] FilamentHub: Printer profile <ID> downloaded successfully. HTTP status: 200, JSON size: <N> bytes
[info] FilamentHub: Saved printer profile to: <temp_file_path>
[info] FilamentHub: Printer profile imported successfully (name: <name> [FilamentHub])
[info] FilamentHub: Saved mapping printer_profile_id=<ID> -> bundle_profile_name=<name> [FilamentHub]
[info] FilamentHub: Printer profiles sync completed. Active syncs: <N>
```

**Что происходит:**
1. ✅ Логирование начала синхронизации
2. ✅ Загрузка токена и `user_id` из `AppConfig`
3. ✅ Если токен отсутствует → выход (не увеличивает `m_active_syncs`)
4. ✅ Получение `last_sync_time` из `AppConfig` (для инкрементальной синхронизации)
5. ✅ Создание `FilamentHubClient` с API base URL
6. ✅ Вызов `client.get_my_printer_profiles(access_token, updated_since)` → `GET /api/v1/orcaslicer/printer-profiles?updated_since=...&include_official=true`
7. ✅ **Backend:** Проверка JWT токена через `get_current_active_user`
8. ✅ **Backend:** Проверка разрешения `allow_printer_profiles_export`
9. ✅ **Backend:** Если разрешение отключено → возврат 403 с сообщением "Экспорт профилей принтера отключен в настройках пользователя"
10. ✅ **Backend:** Возврат списка printer profiles пользователя (JSON)
11. ✅ **OrcaSlicer:** Если HTTP status == 200:
    - Увеличение `m_active_syncs++` (после успешного ответа от API)
    - Парсинг ответа и получение списка printer profiles
    - Для каждого printer profile:
      - Проверка маппинга через `load_printer_profile_mapping(profile_id)`
      - Если нет в маппинге:
        - Вызов `import_printer_profile_silent(profile_id, profile_name, access_token)`
        - Скачивание профиля через `client.download_printer_profile()` → `GET /api/v1/printer-profiles/{id}/export/orcaslicer.json`
        - Парсинг JSON профиля
        - Добавление постфикса `[FilamentHub]` к имени профиля
        - Создание временного файла с JSON профилем
        - Импорт профиля через `PresetBundle::import_json_presets()`
        - Сохранение маппинга через `save_printer_profile_mapping(profile_id, bundle_profile_name)`
        - Обновление UI через `wxGetApp().load_current_presets()`
      - Если уже в маппинге:
        - Пропуск (уже синхронизирован)
    - Уменьшение `m_active_syncs--` в `CallAfter`
    - Если `m_active_syncs <= 0`:
      - Обновление кнопки синхронизации (`update_sync_button_state(false)`)
12. ✅ **OrcaSlicer:** Если HTTP status == 403:
    - Парсинг деталей ошибки из `body`
    - Показ уведомления "Printer profiles export is disabled in your FilamentHub settings. Please enable it in your profile settings."
    - Уменьшение `m_active_syncs--` (если был увеличен)
    - Завершение синхронизации printer profiles

**Обработка ошибок:**
- ✅ **401 (Unauthorized):** Очистка токена через `logout()`, показ уведомления, уменьшение `m_active_syncs` (если был увеличен)
- ✅ **403 (Forbidden):** Парсинг деталей ошибки, показ уведомления, уменьшение `m_active_syncs` (если был увеличен)
- ✅ **500+ (Server Error):** Показ уведомления, уменьшение `m_active_syncs` (если был увеличен)
- ✅ **Другие ошибки:** Показ общего сообщения об ошибке, уменьшение `m_active_syncs` (если был увеличен)
- ✅ **Ошибка парсинга JSON:** Логирование ошибки, показ уведомления, уменьшение `m_active_syncs` (если был увеличен)

---

### 4. Синхронизация Print Profiles (`synchronize_print_profiles`)

**Логи, которые ДОЛЖНЫ появиться:**
```
[info] FilamentHub: ========== synchronize_print_profiles() CALLED ==========
[info] FilamentHub: force_full_sync=false
[info] FilamentHub: Loading auth token - token length: <N>, user_id_str: '<ID>'
[info] FilamentHub: Loaded auth token for user_id=<ID>, token length: <N>
[info] FilamentHub: Calling get_my_print_profiles. API: http://localhost:8000, updated_since: <timestamp> или (empty)
[info] FilamentHub: Received print profiles list. HTTP status: 200, JSON size: <N> bytes
[info] FilamentHub: Incremented m_active_syncs for print profiles. Active syncs: <N>
[info] FilamentHub: Parsing print profiles list...
[info] FilamentHub: Found <N> print profiles to sync
[info] FilamentHub: Processing print profile <ID> (<name>)...
[info] FilamentHub: Print profile <ID> not in mapping, importing...
[info] FilamentHub: Downloading print profile <ID> from API: http://localhost:8000, token length: <N>
[info] FilamentHub: Print profile <ID> downloaded successfully. HTTP status: 200, JSON size: <N> bytes
[info] FilamentHub: Saved print profile to: <temp_file_path>
[info] FilamentHub: Print profile imported successfully (name: <name> [FilamentHub])
[info] FilamentHub: Saved mapping print_profile_id=<ID> -> bundle_profile_name=<name> [FilamentHub]
[info] FilamentHub: Print profiles sync completed. Active syncs: <N>
```

**Что происходит:**
1. ✅ Логирование начала синхронизации
2. ✅ Загрузка токена и `user_id` из `AppConfig`
3. ✅ Если токен отсутствует → выход (не увеличивает `m_active_syncs`)
4. ✅ Получение `last_sync_time` из `AppConfig` (для инкрементальной синхронизации)
5. ✅ Создание `FilamentHubClient` с API base URL
6. ✅ Вызов `client.get_my_print_profiles(access_token, updated_since)` → `GET /api/v1/orcaslicer/print-profiles?updated_since=...&include_official=true`
7. ✅ **Backend:** Проверка JWT токена через `get_current_active_user`
8. ✅ **Backend:** Проверка разрешения `allow_print_profiles_export`
9. ✅ **Backend:** Если разрешение отключено → возврат 403 с сообщением "Экспорт профилей печати отключен в настройках пользователя"
10. ✅ **Backend:** Возврат списка print profiles пользователя (JSON)
11. ✅ **OrcaSlicer:** Если HTTP status == 200:
    - Увеличение `m_active_syncs++` (после успешного ответа от API)
    - Парсинг ответа и получение списка print profiles
    - Для каждого print profile:
      - Проверка маппинга через `load_print_profile_mapping(profile_id)`
      - Если нет в маппинге:
        - Вызов `import_print_profile_silent(profile_id, profile_name, access_token)`
        - Скачивание профиля через `client.download_print_profile()` → `GET /api/v1/print-profiles/{id}/export/orcaslicer.json`
        - Парсинг JSON профиля
        - Добавление постфикса `[FilamentHub]` к имени профиля
        - Создание временного файла с JSON профилем
        - Импорт профиля через `PresetBundle::import_json_presets()`
        - Сохранение маппинга через `save_print_profile_mapping(profile_id, bundle_profile_name)`
        - Обновление UI через `wxGetApp().load_current_presets()`
      - Если уже в маппинге:
        - Пропуск (уже синхронизирован)
    - Уменьшение `m_active_syncs--` в `CallAfter`
    - Если `m_active_syncs <= 0`:
      - Обновление кнопки синхронизации (`update_sync_button_state(false)`)
12. ✅ **OrcaSlicer:** Если HTTP status == 403:
    - Парсинг деталей ошибки из `body`
    - Показ уведомления "Print profiles export is disabled in your FilamentHub settings. Please enable it in your profile settings."
    - Уменьшение `m_active_syncs--` (если был увеличен)
    - Завершение синхронизации print profiles

**Обработка ошибок:**
- ✅ **401 (Unauthorized):** Очистка токена через `logout()`, показ уведомления, уменьшение `m_active_syncs` (если был увеличен)
- ✅ **403 (Forbidden):** Парсинг деталей ошибки, показ уведомления, уменьшение `m_active_syncs` (если был увеличен)
- ✅ **500+ (Server Error):** Показ уведомления, уменьшение `m_active_syncs` (если был увеличен)
- ✅ **Другие ошибки:** Показ общего сообщения об ошибке, уменьшение `m_active_syncs` (если был увеличен)
- ✅ **Ошибка парсинга JSON:** Логирование ошибки, показ уведомления, уменьшение `m_active_syncs` (если был увеличен)

---

### 5. Завершение синхронизации

**Логи, которые ДОЛЖНЫ появиться:**
```
[info] FilamentHub: Filament presets sync completed. Active syncs: <N>
[info] FilamentHub: Printer profiles sync completed. Active syncs: <N>
[info] FilamentHub: Print profiles sync completed. Active syncs: <N>
[info] FilamentHub: All syncs completed. Active syncs: 0
[info] FilamentHub: Reset sync button state to 'Synchronize'
[info] FilamentHub: Updated user info
```

**Что происходит:**
1. ✅ Все синхронизации выполняются параллельно (асинхронно)
2. ✅ Каждая синхронизация уменьшает `m_active_syncs--` после завершения
3. ✅ Когда `m_active_syncs <= 0`:
    - Обновление кнопки синхронизации (`update_sync_button_state(false)`)
    - Обновление информации о пользователе (`update_user_info()`)
    - Логирование итогового статуса синхронизации

---

## 🔍 Проблемы, которые могут возникнуть

### 1. Нет логов о синхронизации

**Возможные причины:**
- ❌ Кнопка "Synchronize" не нажималась
- ❌ Логирование `BOOST_LOG_TRIVIAL` не настроено для уровня `info`
- ❌ Логи пишутся в другой файл (например, `debug_network_*.log.enc`)
- ❌ Синхронизация не запускается (ошибка при загрузке токена)

**Что проверить:**
- ✅ Нажималась ли кнопка "Synchronize"?
- ✅ Есть ли токен в `AppConfig`?
- ✅ Есть ли другие лог-файлы с записями о синхронизации?
- ✅ Настроено ли логирование `BOOST_LOG_TRIVIAL` для уровня `info`?

### 2. Синхронизация не запускается

**Возможные причины:**
- ❌ Токен отсутствует или невалидный
- ❌ `load_auth_token` возвращает `false`
- ❌ Ошибка при загрузке токена из `AppConfig`

**Что проверить:**
- ✅ Есть ли токен в `AppConfig`?
- ✅ Валидный ли токен?
- ✅ Есть ли логи "FilamentHub: Loading auth token - token length: <N>, user_id_str: '<ID>'"?

### 3. Синхронизация запускается, но ничего не происходит

**Возможные причины:**
- ❌ API запросы не отправляются (ошибка в `FilamentHubClient`)
- ❌ API запросы отправляются, но не получают ответ (ошибка сети)
- ❌ API запросы получают ошибку (401, 403, 500+)
- ❌ Ошибка парсинга JSON ответа

**Что проверить:**
- ✅ Есть ли логи "FilamentHub: Calling get_my_presets. API: ..."?
- ✅ Есть ли логи "FilamentHub: Received presets list. HTTP status: ..."?
- ✅ Есть ли ошибки в логах?
- ✅ Работает ли backend API?
- ✅ Доступен ли backend API по адресу `http://localhost:8000`?

### 4. Синхронизация запускается, но не завершается

**Возможные причины:**
- ❌ `m_active_syncs` не уменьшается после завершения синхронизации
- ❌ Ошибка в обработке ответа от API
- ❌ Ошибка при импорте профилей

**Что проверить:**
- ✅ Есть ли логи "FilamentHub: Filament presets sync completed. Active syncs: <N>"?
- ✅ Есть ли ошибки в логах?
- ✅ Правильно ли уменьшается `m_active_syncs`?

---

## 📝 Итоговый чеклист

**Что ДОЛЖНО быть в логах при успешной синхронизации:**
- ✅ `[info] FilamentHub: ========== SYNC BUTTON CLICKED ==========`
- ✅ `[info] FilamentHub: Auth token loaded. User ID: <ID>, token length: <N>`
- ✅ `[info] FilamentHub: Starting sync. m_active_syncs=1`
- ✅ `[info] FilamentHub: ========== synchronize_presets() CALLED ==========`
- ✅ `[info] FilamentHub: Calling get_my_presets. API: http://localhost:8000, updated_since: ...`
- ✅ `[info] FilamentHub: Received presets list. HTTP status: 200, JSON size: <N> bytes`
- ✅ `[info] FilamentHub: Preset <ID> downloaded successfully. HTTP status: 200, JSON size: <N> bytes`
- ✅ `[info] FilamentHub: Profile imported successfully (name: <name> [FilamentHub])`
- ✅ `[info] FilamentHub: Synchronization completed. Synced: <N>, Updated: <M>, Errors: <K>`
- ✅ `[info] FilamentHub: Filament presets sync completed. Active syncs: 0`
- ✅ `[info] FilamentHub: Reset sync button state to 'Synchronize'`

**Что НЕ должно быть в логах:**
- ❌ Ошибки "FilamentHub: No auth token found, cannot synchronize presets"
- ❌ Ошибки "FilamentHub: Failed to get presets list. Error: ..., Status: 401"
- ❌ Ошибки "FilamentHub: Failed to get presets list. Error: ..., Status: 403"
- ❌ Ошибки "FilamentHub: Failed to get presets list. Error: ..., Status: 500+"
- ❌ Ошибки "FilamentHub: Error parsing presets list: ..."

---

## 🎯 Выводы

**Ожидаемое поведение:**
1. ✅ При нажатии кнопки "Synchronize" должны появиться логи о начале синхронизации
2. ✅ Должны быть отправлены API запросы к backend
3. ✅ Должны быть получены ответы от backend (200, 401, 403, 500+)
4. ✅ Должны быть импортированы профили в OrcaSlicer
5. ✅ Должны быть сохранены маппинги в `AppConfig`
6. ✅ Должно быть обновлено состояние UI (кнопка, информация о пользователе)

**Если синхронизация не работает:**
1. ❌ Проверить, нажималась ли кнопка "Synchronize"
2. ❌ Проверить, есть ли токен в `AppConfig`
3. ❌ Проверить, работают ли API запросы (есть ли логи о запросах)
4. ❌ Проверить, есть ли ответы от API (есть ли логи о ответах)
5. ❌ Проверить, есть ли ошибки в логах

