# Направление синхронизации OrcaSlicer ↔ FilamentHub

## 🔄 Направление синхронизации

### 1. **Из FilamentHub в OrcaSlicer (ИМПОРТ)** ✅ РЕАЛИЗОВАНО

**Что происходит:**
- Пользователь нажимает кнопку "Synchronize" в OrcaSlicer
- OrcaSlicer получает список профилей из FilamentHub через API
- OrcaSlicer скачивает каждый профиль из FilamentHub
- OrcaSlicer импортирует профили в локальную базу OrcaSlicer
- Профили добавляются с постфиксом `[FilamentHub]` к имени

**API запросы:**
- `GET /api/v1/auth/my-presets` - получить список filament presets
- `GET /api/v1/orcaslicer/printer-profiles` - получить список printer profiles
- `GET /api/v1/orcaslicer/print-profiles` - получить список print profiles
- `GET /api/v1/presets/{id}/export/orcaslicer.json` - скачать filament preset
- `GET /api/v1/printer-profiles/{id}/export/orcaslicer.json` - скачать printer profile
- `GET /api/v1/print-profiles/{id}/export/orcaslicer.json` - скачать print profile

**Реализация:**
- ✅ `synchronize_presets()` - синхронизация filament presets
- ✅ `synchronize_printer_profiles()` - синхронизация printer profiles
- ✅ `synchronize_print_profiles()` - синхронизация print profiles
- ✅ `import_preset_silent()` - импорт filament preset без UI диалогов
- ✅ `import_printer_profile_silent()` - импорт printer profile без UI диалогов
- ✅ `import_print_profile_silent()` - импорт print profile без UI диалогов

---

### 2. **Из OrcaSlicer в FilamentHub (ЭКСПОРТ)** ❌ НЕ РЕАЛИЗОВАНО

**Что должно происходить:**
- Пользователь выбирает профили в OrcaSlicer для экспорта
- OrcaSlicer экспортирует профили в формате OrcaSlicer (JSON)
- OrcaSlicer отправляет профили в FilamentHub через API
- FilamentHub импортирует профили в базу данных

**API эндпоинты (существуют, но не используются из OrcaSlicer):**
- `POST /api/v1/orcaslicer/printer-profiles/import` - импорт printer profiles в FilamentHub
- `POST /api/v1/orcaslicer/print-profiles/import` - импорт print profiles в FilamentHub
- `POST /api/v1/presets` - создание filament preset в FilamentHub (существует, но не используется для экспорта из OrcaSlicer)

**Что отсутствует:**
- ❌ UI для выбора профилей для экспорта из OrcaSlicer
- ❌ Логика экспорта профилей из OrcaSlicer в FilamentHub
- ❌ Автоматический экспорт при изменении профилей в OrcaSlicer
- ❌ Обработка конфликтов при экспорте (профиль уже существует)

---

## 📦 Что синхронизируется

### 1. **Filament Presets** (Пресеты материалов) ✅ РЕАЛИЗОВАНО

**Что синхронизируется:**
- Filament presets пользователя из FilamentHub
- Включает:
  - Созданные пользователем пресеты
  - Сохраненные пользователем пресеты (из каталога)
  - Официальные пресеты (если разрешено)

**Направление:**
- ✅ **Из FilamentHub в OrcaSlicer** (импорт) - реализовано
- ❌ **Из OrcaSlicer в FilamentHub** (экспорт) - не реализовано

**Как работает:**
1. Пользователь нажимает "Synchronize" в OrcaSlicer
2. OrcaSlicer получает список пресетов через `GET /api/v1/auth/my-presets`
3. Для каждого пресета:
   - Проверяется маппинг (есть ли уже в OrcaSlicer)
   - Если нет → скачивается через `GET /api/v1/presets/{id}/export/orcaslicer.json`
   - Импортируется в OrcaSlicer через `PresetBundle::import_json_presets()`
   - Сохраняется маппинг `preset_id → bundle_preset_name` в AppConfig

**Разрешения:**
- Нет отдельных разрешений для filament presets (всегда синхронизируются)
- Но можно добавить `allow_filament_presets_export` в будущем

---

### 2. **Printer Profiles** (Профили принтеров) ✅ РЕАЛИЗОВАНО

**Что синхронизируется:**
- Printer profiles пользователя из FilamentHub
- Включает:
  - Созданные пользователем printer profiles
  - Официальные printer profiles (если `include_official=true`)

**Направление:**
- ✅ **Из FilamentHub в OrcaSlicer** (импорт) - реализовано
- ❌ **Из OrcaSlicer в FilamentHub** (экспорт) - не реализовано (но есть API эндпоинт)

**Как работает:**
1. Пользователь нажимает "Synchronize" в OrcaSlicer
2. OrcaSlicer проверяет разрешение `allow_printer_profiles_export` (получено через `GET /api/v1/auth/me`)
3. Если разрешено:
   - OrcaSlicer получает список printer profiles через `GET /api/v1/orcaslicer/printer-profiles`
   - Для каждого printer profile:
     - Проверяется маппинг (есть ли уже в OrcaSlicer)
     - Если нет → скачивается через `GET /api/v1/printer-profiles/{id}/export/orcaslicer.json`
     - Импортируется в OrcaSlicer через `PresetBundle::import_json_presets()`
     - Сохраняется маппинг `printer_profile_id → bundle_profile_name` в AppConfig
4. Если не разрешено (403):
   - Показывается предупреждение "Printer profiles export is disabled in your FilamentHub settings"
   - Синхронизация printer profiles пропускается

**Разрешения:**
- `allow_printer_profiles_export` - разрешение на экспорт printer profiles из FilamentHub
- `allow_printer_profiles_import` - разрешение на импорт printer profiles в FilamentHub (используется для экспорта из OrcaSlicer)

---

### 3. **Print Profiles** (Профили печати) ✅ РЕАЛИЗОВАНО

**Что синхронизируется:**
- Print profiles пользователя из FilamentHub
- Включает:
  - Созданные пользователем print profiles
  - Официальные print profiles (если `include_official=true`)

**Направление:**
- ✅ **Из FilamentHub в OrcaSlicer** (импорт) - реализовано
- ❌ **Из OrcaSlicer в FilamentHub** (экспорт) - не реализовано (но есть API эндпоинт)

**Как работает:**
1. Пользователь нажимает "Synchronize" в OrcaSlicer
2. OrcaSlicer проверяет разрешение `allow_print_profiles_export` (получено через `GET /api/v1/auth/me`)
3. Если разрешено:
   - OrcaSlicer получает список print profiles через `GET /api/v1/orcaslicer/print-profiles`
   - Для каждого print profile:
     - Проверяется маппинг (есть ли уже в OrcaSlicer)
     - Если нет → скачивается через `GET /api/v1/print-profiles/{id}/export/orcaslicer.json`
     - Импортируется в OrcaSlicer через `PresetBundle::import_json_presets()`
     - Сохраняется маппинг `print_profile_id → bundle_profile_name` в AppConfig
4. Если не разрешено (403):
   - Показывается предупреждение "Print profiles export is disabled in your FilamentHub settings"
   - Синхронизация print profiles пропускается

**Разрешения:**
- `allow_print_profiles_export` - разрешение на экспорт print profiles из FilamentHub
- `allow_print_profiles_import` - разрешение на импорт print profiles в FilamentHub (используется для экспорта из OrcaSlicer)

---

## 🔐 Разрешения пользователя

### Текущие разрешения (в User модели):

1. **`allow_printer_profiles_import`** (bool, default=True)
   - Разрешение на импорт printer profiles в FilamentHub (из OrcaSlicer)
   - Используется при экспорте printer profiles из OrcaSlicer в FilamentHub
   - Проверяется в `POST /api/v1/orcaslicer/printer-profiles/import`

2. **`allow_printer_profiles_export`** (bool, default=True)
   - Разрешение на экспорт printer profiles из FilamentHub (в OrcaSlicer)
   - Используется при импорте printer profiles из FilamentHub в OrcaSlicer
   - Проверяется в `GET /api/v1/orcaslicer/printer-profiles`

3. **`allow_print_profiles_import`** (bool, default=True)
   - Разрешение на импорт print profiles в FilamentHub (из OrcaSlicer)
   - Используется при экспорте print profiles из OrcaSlicer в FilamentHub
   - Проверяется в `POST /api/v1/orcaslicer/print-profiles/import`

4. **`allow_print_profiles_export`** (bool, default=True)
   - Разрешение на экспорт print profiles из FilamentHub (в OrcaSlicer)
   - Используется при импорте print profiles из FilamentHub в OrcaSlicer
   - Проверяется в `GET /api/v1/orcaslicer/print-profiles`

### Логика разрешений:

- **`allow_*_export`** = разрешение на экспорт **из FilamentHub** (используется при импорте в OrcaSlicer)
- **`allow_*_import`** = разрешение на импорт **в FilamentHub** (используется при экспорте из OrcaSlicer)

**Пример:**
- Если `allow_printer_profiles_export = true` → пользователь может синхронизировать printer profiles из FilamentHub в OrcaSlicer
- Если `allow_printer_profiles_export = false` → пользователь **НЕ может** синхронизировать printer profiles из FilamentHub в OrcaSlicer (получит 403)
- Если `allow_printer_profiles_import = true` → пользователь может экспортировать printer profiles из OrcaSlicer в FilamentHub (когда это будет реализовано)
- Если `allow_printer_profiles_import = false` → пользователь **НЕ может** экспортировать printer profiles из OrcaSlicer в FilamentHub (получит 403)

---

## 📊 Итоговая таблица синхронизации

| Тип профиля | Из FilamentHub в OrcaSlicer | Из OrcaSlicer в FilamentHub | Разрешение для импорта в OrcaSlicer | Разрешение для экспорта в FilamentHub |
|-------------|----------------------------|----------------------------|-----------------------------------|-------------------------------------|
| **Filament Presets** | ✅ Реализовано | ❌ Не реализовано | ❌ Нет (всегда разрешено) | ❌ Нет |
| **Printer Profiles** | ✅ Реализовано | ❌ Не реализовано (есть API) | ✅ `allow_printer_profiles_export` | ✅ `allow_printer_profiles_import` |
| **Print Profiles** | ✅ Реализовано | ❌ Не реализовано (есть API) | ✅ `allow_print_profiles_export` | ✅ `allow_print_profiles_import` |

---

## 🎯 Выводы

### Что реализовано:
1. ✅ **Импорт Filament Presets** из FilamentHub в OrcaSlicer
2. ✅ **Импорт Printer Profiles** из FilamentHub в OrcaSlicer (с проверкой разрешений)
3. ✅ **Импорт Print Profiles** из FilamentHub в OrcaSlicer (с проверкой разрешений)
4. ✅ **API эндпоинты** для экспорта из OrcaSlicer в FilamentHub (но не используются)

### Что не реализовано:
1. ❌ **Экспорт Filament Presets** из OrcaSlicer в FilamentHub
2. ❌ **Экспорт Printer Profiles** из OrcaSlicer в FilamentHub (есть API, но нет UI и логики)
3. ❌ **Экспорт Print Profiles** из OrcaSlicer в FilamentHub (есть API, но нет UI и логики)
4. ❌ **UI для выбора профилей** для экспорта из OrcaSlicer
5. ❌ **Автоматический экспорт** при изменении профилей в OrcaSlicer

### Текущее поведение:
- При нажатии "Synchronize" в OrcaSlicer происходит **только импорт** из FilamentHub в OrcaSlicer
- **Нет экспорта** из OrcaSlicer в FilamentHub (даже если есть API эндпоинты)
- Синхронизация работает **односторонне**: FilamentHub → OrcaSlicer

---

## 🔮 Будущее развитие

### Планируемые улучшения:
1. **Двусторонняя синхронизация:**
   - Импорт из FilamentHub в OrcaSlicer (реализовано)
   - Экспорт из OrcaSlicer в FilamentHub (планируется)

2. **Автоматическая синхронизация:**
   - Автоматический экспорт при изменении профилей в OrcaSlicer
   - Автоматический импорт при изменении профилей в FilamentHub

3. **UI для управления синхронизацией:**
   - Выбор профилей для экспорта
   - Настройки синхронизации (автоматическая, ручная)
   - Индикация прогресса синхронизации

4. **Синхронизация полных бандлов:**
   - Синхронизация Filament + Printer + Print в одной операции
   - Сохранение связей между профилями

---

## 📝 Резюме

**Направление синхронизации:**
- ✅ **Из FilamentHub в OrcaSlicer** (импорт) - **РЕАЛИЗОВАНО**
- ❌ **Из OrcaSlicer в FilamentHub** (экспорт) - **НЕ РЕАЛИЗОВАНО**

**Что синхронизируется:**
- ✅ **Filament Presets** (пресеты материалов) - импорт реализован
- ✅ **Printer Profiles** (профили принтеров) - импорт реализован
- ✅ **Print Profiles** (профили печати) - импорт реализован

**Разрешения:**
- ✅ `allow_printer_profiles_export` - разрешение на импорт printer profiles из FilamentHub в OrcaSlicer
- ✅ `allow_print_profiles_export` - разрешение на импорт print profiles из FilamentHub в OrcaSlicer
- ✅ `allow_printer_profiles_import` - разрешение на экспорт printer profiles из OrcaSlicer в FilamentHub (не используется, так как экспорт не реализован)
- ✅ `allow_print_profiles_import` - разрешение на экспорт print profiles из OrcaSlicer в FilamentHub (не используется, так как экспорт не реализован)

**Текущее поведение:**
- При нажатии "Synchronize" в OrcaSlicer происходит **односторонняя синхронизация** (импорт из FilamentHub в OrcaSlicer)
- Синхронизируются все типы профилей (Filament, Printer, Print), для которых разрешен экспорт из FilamentHub
- Разрешения проверяются на уровне backend и OrcaSlicer

