# Полный путь синхронизации OrcaSlicer ↔ FilamentHub

## Описание процесса

Когда пользователь нажимает кнопку "Synchronize" в OrcaSlicer, происходит следующее:

### 1. Проверка авторизации

**OrcaSlicer (`FilamentHubPanel::on_sync_button_click`):**
1. Загружает токен и `user_id` из `AppConfig`
2. Если токен отсутствует → показывает сообщение "Please login to FilamentHub first." и завершает

### 2. Проверка разрешений

**OrcaSlicer (`FilamentHubPanel::check_user_permissions`):**
1. Вызывает `FilamentHubClient::get_current_user(access_token)` → `GET /api/v1/auth/me`
2. **Backend (`/api/v1/auth/me`):**
   - Использует `get_current_active_user` (JWT токен)
   - Возвращает информацию о пользователе, включая разрешения:
     - `allow_printer_profiles_import`
     - `allow_printer_profiles_export`
     - `allow_print_profiles_import`
     - `allow_print_profiles_export`
3. **OrcaSlicer:**
   - Извлекает разрешения из ответа
   - Если ошибка 401 → очищает токен, показывает сообщение "Your session has expired. Please login again."
   - Если ошибка 403 → показывает сообщение "Access denied. Please check your permissions in FilamentHub settings."
   - Если ошибка 500+ → показывает сообщение "Server error. Please try again later."
   - Если успешно → продолжает синхронизацию

### 3. Синхронизация Filament Presets (всегда)

**OrcaSlicer (`FilamentHubPanel::synchronize_presets`):**
1. Увеличивает счетчик активных синхронизаций (`m_active_syncs++`)
2. Получает `last_sync_time` из `AppConfig` (для инкрементальной синхронизации)
3. Вызывает `FilamentHubClient::get_my_presets(access_token, updated_since)` → `GET /api/v1/auth/my-presets?updated_since=...`
4. **Backend (`/api/v1/auth/my-presets`):**
   - Использует `get_current_active_user` (JWT токен)
   - Возвращает список пресетов пользователя (созданные + сохраненные)
   - Поддерживает фильтрацию по `updated_since` (инкрементальная синхронизация)
5. **OrcaSlicer:**
   - Парсит ответ и получает список пресетов
   - Для каждого пресета:
     - Проверяет маппинг (есть ли уже в OrcaSlicer) через `load_preset_mapping(preset_id)`
     - Если нет в маппинге:
       - Вызывает `import_preset_silent(preset_id, preset_name, access_token)`
       - Который вызывает `FilamentHubClient::download_profile(preset_id, access_token)` → `GET /api/v1/presets/{id}/export/orcaslicer.json`
       - **Backend (`/api/v1/presets/{id}/export/orcaslicer.json`):**
         - Экспортирует пресет в формате OrcaSlicer (JSON)
         - Возвращает JSON файл с профилем
       - **OrcaSlicer:**
         - Парсит JSON профиль
         - Добавляет постфикс `[FilamentHub]` к имени пресета
         - Проверяет и исправляет родительский пресет (inherits)
         - Создает временный файл с JSON профилем
         - Импортирует профиль через `PresetBundle::import_json_presets()`
         - Сохраняет маппинг через `save_preset_mapping(preset_id, bundle_preset_name)`
         - Обновляет UI через `wxGetApp().load_current_presets()`
     - Если уже в маппинге:
       - Пропускает (уже синхронизирован)
       - TODO: Сравнить `updated_at` с временем последнего импорта для обновления
   - Обновляет `last_sync_time` в `AppConfig`
   - Уменьшает счетчик активных синхронизаций (`m_active_syncs--`)
   - Если все синхронизации завершены (`m_active_syncs <= 0`):
     - Обновляет кнопку синхронизации (`update_sync_button_state(false)`)
     - Обновляет информацию о пользователе (`update_user_info()`)

### 4. Синхронизация Printer Profiles (если разрешено)

**OrcaSlicer (`FilamentHubPanel::synchronize_printer_profiles`):**
1. Проверяет разрешение `allow_printer_profiles_export` (получено на шаге 2)
2. Если разрешено:
   - Увеличивает счетчик активных синхронизаций (`m_active_syncs++`)
   - Получает `last_sync_time` из `AppConfig`
   - Вызывает `FilamentHubClient::get_my_printer_profiles(access_token, updated_since)` → `GET /api/v1/orcaslicer/printer-profiles?updated_since=...&include_official=true`
3. **Backend (`/api/v1/orcaslicer/printer-profiles`):**
   - Использует `get_current_active_user` (JWT токен)
   - Проверяет разрешение `allow_printer_profiles_export`:
     - Если `False` → возвращает 403 с сообщением "Экспорт профилей принтера отключен в настройках пользователя"
   - Возвращает список printer profiles пользователя (созданные + официальные)
   - Поддерживает фильтрацию по `updated_since` и `include_official`
4. **OrcaSlicer:**
   - Если ошибка 403:
     - Показывает предупреждение "Printer profiles export is disabled in your FilamentHub settings. Please enable it in your profile settings."
     - Уменьшает счетчик активных синхронизаций
     - Завершает синхронизацию printer profiles
   - Если успешно:
     - Парсит ответ и получает список printer profiles
     - Для каждого printer profile:
       - Проверяет маппинг через `load_printer_profile_mapping(profile_id)`
       - Если нет в маппинге:
         - Вызывает `import_printer_profile_silent(profile_id, profile_name, access_token)`
         - Который вызывает `FilamentHubClient::download_printer_profile(profile_id, access_token)` → `GET /api/v1/printer-profiles/{id}/export/orcaslicer.json`
         - **Backend (`/api/v1/printer-profiles/{id}/export/orcaslicer.json`):**
           - Экспортирует printer profile в формате OrcaSlicer (JSON)
           - Возвращает JSON файл с профилем принтера
         - **OrcaSlicer:**
           - Парсит JSON профиль
           - Добавляет постфикс `[FilamentHub]` к имени профиля
           - Создает временный файл с JSON профилем
           - Импортирует профиль через `PresetBundle::import_json_presets()`
           - Сохраняет маппинг через `save_printer_profile_mapping(profile_id, bundle_profile_name)`
           - Обновляет UI через `wxGetApp().load_current_presets()`
       - Если уже в маппинге:
         - Пропускает (уже синхронизирован)
     - Уменьшает счетчик активных синхронизаций (`m_active_syncs--`)
     - Если все синхронизации завершены (`m_active_syncs <= 0`):
       - Обновляет кнопку синхронизации (`update_sync_button_state(false)`)
3. Если не разрешено:
   - Пропускает синхронизацию printer profiles
   - Логирует "Printer profiles export disabled, skipping"

### 5. Синхронизация Print Profiles (если разрешено)

**OrcaSlicer (`FilamentHubPanel::synchronize_print_profiles`):**
1. Проверяет разрешение `allow_print_profiles_export` (получено на шаге 2)
2. Если разрешено:
   - Увеличивает счетчик активных синхронизаций (`m_active_syncs++`)
   - Получает `last_sync_time` из `AppConfig`
   - Вызывает `FilamentHubClient::get_my_print_profiles(access_token, updated_since)` → `GET /api/v1/orcaslicer/print-profiles?updated_since=...&include_official=true`
3. **Backend (`/api/v1/orcaslicer/print-profiles`):**
   - Использует `get_current_active_user` (JWT токен)
   - Проверяет разрешение `allow_print_profiles_export`:
     - Если `False` → возвращает 403 с сообщением "Экспорт профилей печати отключен в настройках пользователя"
   - Возвращает список print profiles пользователя (созданные + официальные)
   - Поддерживает фильтрацию по `updated_since` и `include_official`
4. **OrcaSlicer:**
   - Если ошибка 403:
     - Показывает предупреждение "Print profiles export is disabled in your FilamentHub settings. Please enable it in your profile settings."
     - Уменьшает счетчик активных синхронизаций
     - Завершает синхронизацию print profiles
   - Если успешно:
     - Парсит ответ и получает список print profiles
     - Для каждого print profile:
       - Проверяет маппинг через `load_print_profile_mapping(profile_id)`
       - Если нет в маппинге:
         - Вызывает `import_print_profile_silent(profile_id, profile_name, access_token)`
         - Который вызывает `FilamentHubClient::download_print_profile(profile_id, access_token)` → `GET /api/v1/print-profiles/{id}/export/orcaslicer.json`
         - **Backend (`/api/v1/print-profiles/{id}/export/orcaslicer.json`):**
           - Экспортирует print profile в формате OrcaSlicer (JSON)
           - Возвращает JSON файл с профилем печати
         - **OrcaSlicer:**
           - Парсит JSON профиль
           - Добавляет постфикс `[FilamentHub]` к имени профиля
           - Создает временный файл с JSON профилем
           - Импортирует профиль через `PresetBundle::import_json_presets()`
           - Сохраняет маппинг через `save_print_profile_mapping(profile_id, bundle_profile_name)`
           - Обновляет UI через `wxGetApp().load_current_presets()`
       - Если уже в маппинге:
         - Пропускает (уже синхронизирован)
     - Уменьшает счетчик активных синхронизаций (`m_active_syncs--`)
     - Если все синхронизации завершены (`m_active_syncs <= 0`):
       - Обновляет кнопку синхронизации (`update_sync_button_state(false)`)
3. Если не разрешено:
   - Пропускает синхронизацию print profiles
   - Логирует "Print profiles export disabled, skipping"

### 6. Завершение синхронизации

**OrcaSlicer:**
1. Все синхронизации выполняются параллельно (асинхронно)
2. Каждая синхронизация уменьшает счетчик активных синхронизаций при завершении
3. Когда все синхронизации завершены (`m_active_syncs <= 0`):
   - Обновляется кнопка синхронизации (`update_sync_button_state(false)`)
   - Обновляется информация о пользователе (`update_user_info()`)
   - Логируется итоговый статус синхронизации

## Обработка ошибок

### 401 Unauthorized (Токен истек или невалидный)
- **OrcaSlicer:** Очищает токен через `logout()`, показывает сообщение "Your session has expired. Please login again."
- **Backend:** Возвращает 401, если JWT токен невалидный или истек

### 403 Forbidden (Доступ запрещен)
- **OrcaSlicer:** Парсит ответ и извлекает сообщение об ошибке из `detail`, показывает предупреждение с объяснением причины
- **Backend:** Возвращает 403, если у пользователя отключены соответствующие разрешения:
  - "Экспорт профилей принтера отключен в настройках пользователя"
  - "Экспорт профилей печати отключен в настройках пользователя"
  - "Импорт профилей принтера отключен в настройках пользователя"
  - "Импорт профилей печати отключен в настройках пользователя"

### 500+ Server Error
- **OrcaSlicer:** Показывает сообщение "Server error. Please try again later."
- **Backend:** Возвращает 500+ при внутренних ошибках сервера

### Другие ошибки
- **OrcaSlicer:** Показывает общее сообщение об ошибке с деталями из ответа
- **Backend:** Возвращает соответствующий HTTP статус код с описанием ошибки

## Проверка разрешений

Разрешения проверяются на двух уровнях:

1. **OrcaSlicer (перед синхронизацией):**
   - Получает разрешения через `GET /api/v1/auth/me`
   - Проверяет разрешения перед началом синхронизации каждого типа профилей
   - Синхронизирует только те типы профилей, для которых разрешено экспортирование

2. **Backend (во время запроса):**
   - Проверяет разрешения в каждом эндпоинте синхронизации:
     - `GET /api/v1/orcaslicer/printer-profiles` → проверяет `allow_printer_profiles_export`
     - `GET /api/v1/orcaslicer/print-profiles` → проверяет `allow_print_profiles_export`
     - `POST /api/v1/orcaslicer/printer-profiles/import` → проверяет `allow_printer_profiles_import`
     - `POST /api/v1/orcaslicer/print-profiles/import` → проверяет `allow_print_profiles_import`
   - Если разрешение отключено → возвращает 403 с понятным сообщением

## Маппинг профилей

Для каждого типа профилей сохраняется маппинг между FilamentHub ID и OrcaSlicer именем профиля:

- **Filament Presets:** `preset_mapping_{preset_id} = bundle_preset_name`
- **Printer Profiles:** `printer_profile_mapping_{profile_id} = bundle_profile_name`
- **Print Profiles:** `print_profile_mapping_{profile_id} = bundle_profile_name`

Маппинг сохраняется в `AppConfig` и используется для:
- Проверки, импортирован ли профиль уже в OrcaSlicer
- Избежания повторного импорта уже синхронизированных профилей
- Отслеживания связи между FilamentHub и OrcaSlicer профилями

## Инкрементальная синхронизация

Для каждого типа профилей поддерживается инкрементальная синхронизация:

1. **OrcaSlicer:**
   - Сохраняет `last_sync_time` в `AppConfig` для каждого пользователя
   - Отправляет `updated_since` в запросах к API
   - Получает только профили, обновленные после `last_sync_time`

2. **Backend:**
   - Поддерживает параметр `updated_since` в эндпоинтах:
     - `GET /api/v1/auth/my-presets?updated_since=...`
     - `GET /api/v1/orcaslicer/printer-profiles?updated_since=...`
     - `GET /api/v1/orcaslicer/print-profiles?updated_since=...`
   - Фильтрует профили по `updated_at >= updated_since`

3. **Принудительная полная синхронизация:**
   - Если `force_full_sync == true`, не отправляется `updated_since`
   - Синхронизируются все профили независимо от `last_sync_time`

## Параллельная синхронизация

Все типы профилей синхронизируются параллельно (асинхронно):

1. **Счетчик активных синхронизаций:**
   - Инициализируется в `on_sync_button_click()` с учетом разрешений
   - Увеличивается перед началом каждой синхронизации
   - Уменьшается после завершения каждой синхронизации

2. **Обновление UI:**
   - Кнопка синхронизации обновляется только после завершения всех синхронизаций
   - Используется `CallAfter()` для безопасного обновления UI из асинхронных коллбэков
   - Логируется статус синхронизации для каждого типа профилей

3. **Обработка ошибок:**
   - Каждая синхронизация обрабатывает ошибки независимо
   - Ошибки в одной синхронизации не влияют на другие
   - Счетчик активных синхронизаций уменьшается даже при ошибках

## Что НЕ реализовано

1. **Экспорт из OrcaSlicer в FilamentHub:**
   - Импорт в FilamentHub реализован через API (`POST /api/v1/orcaslicer/printer-profiles/import`, `POST /api/v1/orcaslicer/print-profiles/import`)
   - Но нет UI для выбора профилей для экспорта из OrcaSlicer
   - Нет автоматического экспорта при изменении профилей в OrcaSlicer

2. **Синхронизация полных бандлов:**
   - Нет эндпоинта для получения полных бандлов (Filament + Printer + Print в одной операции)
   - Нет логики синхронизации бандлов в OrcaSlicer
   - Нет UI для управления синхронизацией бандлов

3. **UI для управления синхронизацией:**
   - Нет UI для выбора типов профилей для синхронизации
   - Нет индикации прогресса синхронизации для каждого типа профилей отдельно
   - Нет настроек синхронизации в UI OrcaSlicer

4. **Обновление уже синхронизированных профилей:**
   - TODO: Сравнить `updated_at` с временем последнего импорта
   - TODO: Обновлять профили, если они изменились в FilamentHub

5. **Синхронизация при запуске OrcaSlicer:**
   - Нет автоматической синхронизации при запуске OrcaSlicer
   - Нет настройки для включения/выключения автоматической синхронизации

## Рекомендации по улучшению

1. **Добавить экспорт из OrcaSlicer в FilamentHub:**
   - UI для выбора профилей для экспорта
   - Автоматический экспорт при изменении профилей в OrcaSlicer
   - Обработка конфликтов при экспорте (профиль уже существует)

2. **Добавить синхронизацию полных бандлов:**
   - Эндпоинт `GET /api/v1/orcaslicer/bundles` для получения полных бандлов
   - Эндпоинт `POST /api/v1/orcaslicer/bundles/import` для импорта полных бандлов
   - Логика синхронизации бандлов в OrcaSlicer
   - UI для управления синхронизацией бандлов

3. **Улучшить UX:**
   - UI для отображения статуса синхронизации для каждого типа профилей отдельно
   - Индикация прогресса синхронизации (сколько профилей синхронизировано, сколько осталось)
   - Настройки синхронизации в UI OrcaSlicer (выбор типов профилей)

4. **Добавить обновление уже синхронизированных профилей:**
   - Сравнение `updated_at` с временем последнего импорта
   - Обновление профилей, если они изменились в FilamentHub
   - Обработка конфликтов при обновлении

5. **Добавить автоматическую синхронизацию:**
   - Синхронизация при запуске OrcaSlicer (опционально)
   - Периодическая синхронизация в фоновом режиме
   - Настройки для включения/выключения автоматической синхронизации

