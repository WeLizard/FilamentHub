# Анализ синхронизации OrcaSlicer ↔ FilamentHub

## Текущая реализация

### 1. Синхронизация Filament Presets (реализовано)

**OrcaSlicer сторона:**
- Пользователь нажимает "Synchronize" → `synchronize_presets(false)`
- Вызывается `FilamentHubClient::get_my_presets()` → `GET /api/v1/auth/my-presets`
- Для каждого пресета вызывается `import_preset_silent()` → `GET /api/v1/presets/{id}/export/orcaslicer.json`
- Пресеты импортируются в OrcaSlicer с постфиксом `[FilamentHub]`

**Backend сторона:**
- `GET /api/v1/auth/my-presets` возвращает список пресетов пользователя (созданные + сохраненные)
- `GET /api/v1/presets/{id}/export/orcaslicer.json` экспортирует пресет в формате OrcaSlicer

**Проблемы:**
- ✅ Работает корректно
- ⚠️ Нет проверки разрешений `allow_print_profiles_export` (но это для print profiles, не filament presets)

---

## Реализованный функционал

### 2. Синхронизация Printer Profiles (✅ РЕАЛИЗОВАНО)

**Что реализовано:**
- ✅ OrcaSlicer импортирует printer profiles из FilamentHub
- ✅ Проверка разрешений `allow_printer_profiles_export` перед синхронизацией
- ✅ Обработка ошибок 403 с понятными сообщениями
- ✅ Маппинг printer profiles (profile_id → bundle_profile_name) в AppConfig
- ✅ Добавление постфикса `[FilamentHub]` к именам профилей

**Backend эндпоинты:**
- ✅ `GET /api/v1/orcaslicer/printer-profiles` (экспорт, JWT токен)
- ✅ `GET /api/v1/printer-profiles/{id}/export/orcaslicer.json` (экспорт отдельного профиля, JWT токен)
- ✅ `POST /api/v1/orcaslicer/printer-profiles/import` (импорт, JWT токен)
- ✅ Проверка разрешений реализована в backend

**OrcaSlicer реализация:**
- ✅ Метод `synchronize_printer_profiles()` в `FilamentHubPanel`
- ✅ Методы в `FilamentHubClient`:
  - `get_my_printer_profiles()` → `GET /api/v1/orcaslicer/printer-profiles`
  - `download_printer_profile()` → `GET /api/v1/printer-profiles/{id}/export/orcaslicer.json`
  - `import_printer_profiles()` → `POST /api/v1/orcaslicer/printer-profiles/import`
- ✅ Метод `import_printer_profile_silent()` для импорта без UI диалогов
- ✅ Методы `save_printer_profile_mapping()` и `load_printer_profile_mapping()` для маппинга

**Осталось:**
- ⚠️ Экспорт printer profiles из OrcaSlicer в FilamentHub (импорт в FilamentHub реализован через API)
- ⚠️ UI для отображения статуса синхронизации printer profiles (логирование есть)

---

### 3. Синхронизация Print Profiles (✅ РЕАЛИЗОВАНО)

**Что реализовано:**
- ✅ OrcaSlicer импортирует print profiles из FilamentHub
- ✅ Проверка разрешений `allow_print_profiles_export` перед синхронизацией
- ✅ Обработка ошибок 403 с понятными сообщениями
- ✅ Маппинг print profiles (profile_id → bundle_profile_name) в AppConfig
- ✅ Добавление постфикса `[FilamentHub]` к именам профилей

**Backend эндпоинты:**
- ✅ `GET /api/v1/orcaslicer/print-profiles` (экспорт, JWT токен)
- ✅ `GET /api/v1/print-profiles/{id}/export/orcaslicer.json` (экспорт отдельного профиля, JWT токен)
- ✅ `POST /api/v1/orcaslicer/print-profiles/import` (импорт, JWT токен)
- ✅ Проверка разрешений реализована в backend

**OrcaSlicer реализация:**
- ✅ Метод `synchronize_print_profiles()` в `FilamentHubPanel`
- ✅ Методы в `FilamentHubClient`:
  - `get_my_print_profiles()` → `GET /api/v1/orcaslicer/print-profiles`
  - `download_print_profile()` → `GET /api/v1/print-profiles/{id}/export/orcaslicer.json`
  - `import_print_profiles()` → `POST /api/v1/orcaslicer/print-profiles/import`
- ✅ Метод `import_print_profile_silent()` для импорта без UI диалогов
- ✅ Методы `save_print_profile_mapping()` и `load_print_profile_mapping()` для маппинга

**Осталось:**
- ⚠️ Экспорт print profiles из OrcaSlicer в FilamentHub (импорт в FilamentHub реализован через API)
- ⚠️ UI для отображения статуса синхронизации print profiles (логирование есть)

---

### 4. Синхронизация "Полных бандлов" (НЕ реализовано)

**Что должно быть:**
- Пользователь может включить/выключить синхронизацию "полных бандлов" (Filament + Printer + Print)
- Если включено, при синхронизации должны подтягиваться все три типа профилей
- Если выключено, синхронизируются только отдельные типы профилей

**Текущее состояние:**
- ❌ Нет логики для синхронизации бандлов
- ✅ Поля разрешений существуют в User модели:
  - `allow_printer_profiles_import/export`
  - `allow_print_profiles_import/export`
- ⚠️ Но нет отдельного флага для "полных бандлов"

**Что нужно добавить:**
1. **Backend:**
   - Новое поле `allow_full_bundles_sync: bool` в User модели
   - Эндпоинт `GET /api/v1/orcaslicer/bundles` для получения полных бандлов
   - Эндпоинт `POST /api/v1/orcaslicer/bundles/import` для импорта полных бандлов

2. **OrcaSlicer:**
   - Метод `synchronize_full_bundles()` в `FilamentHubPanel`
   - UI для включения/выключения синхронизации бандлов
   - Логика объединения Filament + Printer + Print профилей

---

## Проблемные места

### 1. Авторизация через API Key vs JWT Token (✅ ИСПРАВЛЕНО)

**Было:**
- Backend эндпоинты `/orcaslicer/*` использовали `get_current_user_by_api_key` (ожидали заголовок `X-API-Key`)
- OrcaSlicer использовал JWT токен (Bearer token) для авторизации
- **Эндпоинты `/orcaslicer/*` НЕ РАБОТАЛИ с текущей реализацией OrcaSlicer!**

**Исправлено:**
- ✅ Все эндпоинты `/orcaslicer/*` теперь используют `get_current_active_user` (JWT токен)
- ✅ Единый механизм авторизации (JWT) для всех эндпоинтов
- ✅ `FilamentHubClient` отправляет `Authorization: Bearer {token}`, backend корректно обрабатывает

**Текущее состояние:**
- ✅ `GET /api/v1/auth/my-presets` использует JWT (через `get_current_active_user`)
- ✅ `GET /api/v1/orcaslicer/printer-profiles` использует JWT (через `get_current_active_user`)
- ✅ `GET /api/v1/orcaslicer/print-profiles` использует JWT (через `get_current_active_user`)
- ✅ `POST /api/v1/orcaslicer/printer-profiles/import` использует JWT (через `get_current_active_user`)
- ✅ `POST /api/v1/orcaslicer/print-profiles/import` использует JWT (через `get_current_active_user`)

---

### 2. Отсутствие проверки разрешений в OrcaSlicer (✅ ИСПРАВЛЕНО)

**Было:**
- OrcaSlicer не проверял разрешения пользователя перед синхронизацией
- Если у пользователя отключены разрешения, OrcaSlicer все равно пытался синхронизировать
- Backend возвращал 403, но пользователь не понимал почему

**Исправлено:**
- ✅ Метод `check_user_permissions()` в `FilamentHubPanel` проверяет разрешения перед синхронизацией
- ✅ Получает информацию о пользователе через `GET /api/v1/auth/me` (включая разрешения)
- ✅ Проверяет разрешения перед началом синхронизации каждого типа профилей
- ✅ Показывает понятные сообщения об ошибках (403) с объяснением причины
- ✅ Синхронизирует только те типы профилей, для которых разрешено экспортирование

---

### 3. Отсутствие UI для управления синхронизацией

**Проблема:**
- Пользователь не может выбрать, что синхронизировать (только filament presets, или все типы)
- Нет индикации прогресса синхронизации для каждого типа профилей
- Нет возможности включить/выключить синхронизацию бандлов

**Решение:**
- Добавить настройки синхронизации в UI OrcaSlicer
- Показывать отдельные прогресс-бары для каждого типа профилей
- Добавить чекбоксы для выбора типов синхронизации

---

### 4. Отсутствие экспорта из OrcaSlicer в FilamentHub

**Проблема:**
- Текущая синхронизация только импортирует из FilamentHub в OrcaSlicer
- Нет возможности экспортировать профили из OrcaSlicer в FilamentHub
- Пользователь не может синхронизировать свои локальные профили на сервер

**Решение:**
- Добавить логику экспорта профилей из OrcaSlicer
- Использовать существующие эндпоинты:
  - `POST /api/v1/orcaslicer/printer-profiles/import`
  - `POST /api/v1/orcaslicer/print-profiles/import`
- Добавить UI для выбора профилей для экспорта

---

### 5. Отсутствие обработки ошибок разрешений (✅ ИСПРАВЛЕНО)

**Было:**
- Если у пользователя отключены разрешения, backend возвращал 403
- OrcaSlicer показывал общую ошибку, но не объяснял причину
- Пользователь не понимал, что нужно включить разрешения в настройках профиля

**Исправлено:**
- ✅ Парсинг ответа 403 и извлечение сообщения об ошибке из `detail`
- ✅ Понятные сообщения: "Printer profiles export is disabled in your FilamentHub settings. Please enable it in your profile settings."
- ✅ Обработка ошибок 403 в методах синхронизации с показом предупреждений
- ✅ Использование `CallAfter()` для безопасного обновления UI из асинхронных коллбэков

---

## Рекомендации по реализации

### ✅ Выполнено:

**Приоритет 1: Исправить авторизацию**
1. ✅ Изменены backend эндпоинты `/orcaslicer/*` для поддержки JWT токенов
2. ✅ Все эндпоинты используют `get_current_active_user` вместо `get_current_user_by_api_key`

**Приоритет 2: Добавить синхронизацию Printer/Print Profiles**
1. ✅ Реализованы методы синхронизации в OrcaSlicer (`synchronize_printer_profiles()`, `synchronize_print_profiles()`)
2. ✅ Добавлены методы в `FilamentHubClient` для получения и скачивания профилей
3. ✅ Добавлены методы импорта без UI диалогов (`import_printer_profile_silent()`, `import_print_profile_silent()`)
4. ✅ Добавлены методы маппинга профилей (`save_printer_profile_mapping()`, `load_printer_profile_mapping()`, и т.д.)

**Приоритет 3: Проверка разрешений**
1. ✅ Добавлен метод `check_user_permissions()` для проверки разрешений перед синхронизацией
2. ✅ Получение информации о пользователе через `GET /api/v1/auth/me` (включая разрешения)
3. ✅ Синхронизация только тех типов профилей, для которых разрешено экспортирование

**Приоритет 4: Обработка ошибок**
1. ✅ Добавлена обработка ошибок 403 с парсингом сообщения об ошибке
2. ✅ Понятные сообщения об ошибках с объяснением причины
3. ✅ Использование `CallAfter()` для безопасного обновления UI из асинхронных коллбэков

**Приоритет 5: Управление состоянием синхронизации**
1. ✅ Добавлен счетчик активных синхронизаций (`m_active_syncs`)
2. ✅ Правильное обновление UI только после завершения всех синхронизаций
3. ✅ Логирование статуса синхронизации для каждого типа профилей

### 🟡 Осталось:

**Приоритет 1: Добавить синхронизацию полных бандлов**
1. Добавить поле `allow_full_bundles_sync` в User модель (или использовать существующие разрешения)
2. Реализовать логику синхронизации бандлов (Filament + Printer + Print в одной операции)
3. Добавить UI для управления синхронизацией бандлов

**Приоритет 2: Улучшить UX**
1. Добавить UI для отображения статуса синхронизации для каждого типа профилей отдельно
2. Добавить настройки синхронизации в UI OrcaSlicer (выбор типов профилей)
3. Добавить индикацию прогресса синхронизации (сколько профилей синхронизировано, сколько осталось)

**Приоритет 3: Экспорт из OrcaSlicer в FilamentHub**
1. Добавить UI для выбора профилей для экспорта
2. Реализовать экспорт printer и print profiles из OrcaSlicer в FilamentHub
3. Использовать существующие эндпоинты `POST /api/v1/orcaslicer/printer-profiles/import` и `POST /api/v1/orcaslicer/print-profiles/import`

---

## Схема полной синхронизации (целевое состояние)

```
Пользователь нажимает "Synchronize"
    ↓
1. Проверка разрешений (из AppConfig или API)
    ↓
2. Если allow_full_bundles_sync == true:
   - Синхронизация полных бандлов (Filament + Printer + Print)
    ↓
3. Если allow_full_bundles_sync == false:
   - Если allow_printer_profiles_import == true:
     → Синхронизация Printer Profiles
   - Если allow_print_profiles_import == true:
     → Синхронизация Print Profiles
   - Всегда:
     → Синхронизация Filament Presets
    ↓
4. Отображение результатов синхронизации
```

---

## API Endpoints Summary

### Существующие (работают):
- ✅ `GET /api/v1/auth/my-presets` - список filament presets пользователя (JWT)
- ✅ `GET /api/v1/presets/{id}/export/orcaslicer.json` - экспорт filament preset (JWT)
- ✅ `GET /api/v1/auth/me` - информация о пользователе, включая разрешения (JWT)
- ✅ `GET /api/v1/orcaslicer/printer-profiles` - список printer profiles (JWT)
- ✅ `GET /api/v1/orcaslicer/print-profiles` - список print profiles (JWT)
- ✅ `GET /api/v1/printer-profiles/{id}/export/orcaslicer.json` - экспорт printer profile (JWT)
- ✅ `GET /api/v1/print-profiles/{id}/export/orcaslicer.json` - экспорт print profile (JWT)
- ✅ `POST /api/v1/orcaslicer/printer-profiles/import` - импорт printer profiles (JWT)
- ✅ `POST /api/v1/orcaslicer/print-profiles/import` - импорт print profiles (JWT)

### Отсутствующие:
- ❌ `GET /api/v1/orcaslicer/bundles` - список полных бандлов (Filament + Printer + Print)
- ❌ `POST /api/v1/orcaslicer/bundles/import` - импорт полных бандлов

---

## Заключение

**Текущее состояние:** 
- ✅ Работает синхронизация Filament Presets (импорт из FilamentHub в OrcaSlicer)
- ✅ Работает синхронизация Printer Profiles (импорт из FilamentHub в OrcaSlicer)
- ✅ Работает синхронизация Print Profiles (импорт из FilamentHub в OrcaSlicer)
- ✅ Единая авторизация (JWT токен) для всех эндпоинтов
- ✅ Проверка разрешений перед синхронизацией
- ✅ Обработка ошибок разрешений (403) с понятными сообщениями
- ✅ Счетчик активных синхронизаций для правильного обновления UI

**Реализовано:**
1. ✅ Синхронизация Printer Profiles (импорт из FilamentHub)
2. ✅ Синхронизация Print Profiles (импорт из FilamentHub)
3. ✅ Единая авторизация (JWT токен)
4. ✅ Проверка разрешений в OrcaSlicer
5. ✅ Обработка ошибок разрешений (403)
6. ✅ Эндпоинты экспорта отдельных профилей (`/printer-profiles/{id}/export/orcaslicer.json`, `/print-profiles/{id}/export/orcaslicer.json`)

**Осталось:**
1. ⚠️ Синхронизация полных бандлов (Filament + Printer + Print в одной операции)
2. ⚠️ Экспорт из OrcaSlicer в FilamentHub (импорт в FilamentHub реализован через API, но нет UI для экспорта из OrcaSlicer)
3. ⚠️ UI для управления синхронизацией (выбор типов профилей, настройки синхронизации)
4. ⚠️ Индикация прогресса синхронизации для каждого типа профилей отдельно

**Критичность:**
- ✅ Критично: Исправить авторизацию (JWT vs API Key) - **ВЫПОЛНЕНО**
- ✅ Важно: Добавить синхронизацию Printer/Print Profiles - **ВЫПОЛНЕНО**
- ✅ Важно: Проверка разрешений перед синхронизацией - **ВЫПОЛНЕНО**
- ✅ Важно: Обработка ошибок разрешений (403) - **ВЫПОЛНЕНО**
- 🟡 Желательно: Добавить синхронизацию полных бандлов
- 🟢 Желательно: Улучшить UX (UI для управления синхронизацией, индикация прогресса)

