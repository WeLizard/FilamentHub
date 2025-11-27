# Улучшение синхронизации принтеров и пресетов

## Цель

Исправить синхронизацию принтеров, printer profiles и print profiles:
1. Правильное сопоставление принтеров (не "Принтер 1021", а "Voron 2.4 350")
2. Добавить метки `fhub_id` и `fhub_source` для printer и print profiles
3. Извлечение меток из JSON при экспорте в OrcaSlicer
4. Правильная иерархия: Принтеры → Printer Profiles → Print Profiles

## Этап 1: Исправление создания принтера ✅

### Проблема
При создании нового принтера использовалось `name=profile_name` (например, "Voron 2.4 350 0.4 nozzle"), что приводило к неправильным названиям.

### Решение
Использовать очищенное имя профиля (без диаметра сопла) и формировать правильное имя из `manufacturer + model`.

**Файл:** `backend/app/api/v1/endpoints/orca_sync.py`  
**Функция:** `_ensure_printer_id()`  
**Строка:** ~361

**Изменения:**
- Использовать `clean_printer_name` (без диаметра сопла) для отображения
- Формировать имя из `manufacturer + model` если они определены правильно
- Fallback на очищенное имя профиля или исходное имя

## Этап 2: Добавление меток для Printer Profiles ✅

### Изменения в бэкенде

**Файл:** `backend/app/api/v1/endpoints/orca_sync.py`  
**Функция:** `_upsert_printer_profile()`

**Что сделано:**
1. ✅ Поиск по меткам из `orcaslicer_settings` (fhub_id, fhub_source)
2. ✅ Сохранение меток при обновлении printer profile
3. ✅ Добавление меток при создании printer profile

**Приоритеты поиска:**
1. По `fhub_id` из payload (явное указание)
2. По меткам из `orcaslicer_settings` (fhub_id + fhub_source)
3. По `external_id` (fallback)
4. По `slug` (fallback)

## Этап 3: Добавление меток для Print Profiles ✅

### Изменения в бэкенде

**Файл:** `backend/app/api/v1/endpoints/orca_sync.py`  
**Функция:** `_upsert_print_profile()`

**Что сделано:**
1. ✅ Поиск по меткам из `orcaslicer_settings` (fhub_id, fhub_source)
2. ✅ Сохранение меток при обновлении print profile
3. ✅ Добавление меток при создании print profile

## Этап 4: Экспорт меток из FilamentHub ✅

### Изменения в бэкенде

**Файл:** `backend/app/services/orcaslicer_exporter.py`  
**Функция:** `preset_to_orcaslicer_json()`

**Что сделано:**
- ✅ Добавлены метки `fhub_id` и `fhub_source` в JSON профиля для filament presets
- ✅ Убраны метки `fhub_draft_id` при активации черновика

**TODO:** Добавить аналогичные метки для printer и print profiles (если есть экспорт этих типов).

## Этап 5: Извлечение меток в OrcaSlicer (C++) ✅

### Изменения в C++ коде

**Файл:** `docs/OrcaSlicer/src/slic3r/GUI/FilamentHubPanel.cpp`

**Для filament presets:**
- ✅ Функция `export_filament_presets_to_filamenthub_internal()` - извлечение меток из JSON файла (уже реализовано)

**Для printer profiles:**
- ✅ Функция `export_printer_profiles_to_filamenthub_internal()` - добавлено извлечение меток из JSON файла
  - Строка: ~5190 (после `get_config_json(preset.config)`)
  - Читает оригинальный JSON файл и извлекает `fhub_id`, `fhub_source`
  - Приоритет: метки из JSON > маппинг из AppConfig
  - Логирование на каждом этапе

**Для print profiles:**
- ✅ Функция `export_print_profiles_to_filamenthub_internal()` - добавлено извлечение меток из JSON файла
  - Строка: ~5683 (после `get_config_json(preset.config)`)
  - Читает оригинальный JSON файл и извлекает `fhub_id`, `fhub_source`
  - Приоритет: метки из JSON > маппинг из AppConfig
  - Логирование на каждом этапе

**Изменение:**
После `get_config_json(preset.config)` читать JSON файл напрямую через `boost::filesystem::ifstream` и извлекать метки `fhub_id`, `fhub_source` из корня JSON. Если метки найдены в JSON, они имеют приоритет над маппингом из AppConfig.

**Логирование:**
- `debug`: Успешное чтение меток из JSON файла
- `info`: Найдены метки из JSON или маппинга
- `warning`: Ошибки при чтении файла или парсинге меток
- `debug`: Файл недоступен или пустой

## Иерархия профилей

### Структура в FilamentHub:
```
Printer (Принтер)
  └─ PrinterProfile (Профиль принтера)
       └─ PrintProfile (Профиль печати)
            └─ Preset (Пресет филамента)
```

### При синхронизации из OrcaSlicer:
1. Printer Profile → создает/находит Printer → создает PrinterProfile
2. Print Profile → привязывается к Printer Profile (через compatible_printers)
3. Filament Preset → привязывается к Filament

## Результат

После всех изменений:
- ✅ Принтеры создаются с правильными именами (не "Принтер 1021")
- ✅ Printer profiles имеют метки для предотвращения дубликатов
- ✅ Print profiles имеют метки для предотвращения дубликатов
- ✅ При экспорте метки сохраняются в JSON
- ✅ При импорте метки извлекаются из JSON для поиска существующих профилей

---

**Статус:** Этапы 1-4 выполнены, этап 5 требует изменений в C++ коде OrcaSlicer.

