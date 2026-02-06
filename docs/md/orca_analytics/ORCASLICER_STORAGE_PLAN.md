# OrcaSlicer Preset Storage Plan

Цель: поддержать десятки тысяч системных и пользовательских пресетов (принтеры, сопла, принты) без потери совместимости с OrcaSlicer и с возможностью быстрого поиска/фильтрации.

## 1. Базовые сущности

### `printers`
- Отражает `machine_model` Orca.
- Ключевые поля: `slug`, `manufacturer`, `model_id`, габариты, список материалов (`default_materials` → отдельная связь `printer_materials`).
- Источник данных: импорт из `machine_model_list`.

### `printer_profiles`
- Хранит конкретный пресет принтера (машина + сопло).
- Новые колонки:
  - `printer_id` (FK → `printers`) – уже есть, заполняем при импорте.
  - `nozzle_diameters` (`JSONB`/`ARRAY(float)`) – нормализованный список.
  - `printable_area_mm` (`JSONB` с `x_min`, `x_max`, `y_min`, `y_max`).
  - `printable_height_mm` (`float`).
  - `default_print_profile_slug` (`String`, индекс для быстрого резолва).
  - `metadata` (`JSONB`) – «чистый» подмножество ключевых числовых/булевых параметров (ускорения, скорости) в нормализованном виде.
- `orcaslicer_settings` (JSONB) остаётся для полного тела пресета.

### `print_profiles`
- Соответствует `process` Orca.
- Новые колонки:
  - `layer_height_mm` (`numeric`) – из `layer_height`.
  - `quality_tier` (`enum`/`varchar`) – derived из имени (`HighDetail`, `Draft`, `Standard` и т.п.).
  - `default_nozzle` (`float`/`varchar`) – из имени или `parameters`.
  - `metadata` (`JSONB`) – сокращённый набор параметров (скорости, плотности).
- `compatible_printers` и `compatible_filaments` переносим в отдельные связующие таблицы:
  - `print_profile_printers(profile_id, printer_slug, relation_type)` с индексом по `(profile_id)` и `(printer_slug)`.
  - `print_profile_filaments(profile_id, filament_slug)`.

### `profile_versions` (опционально)
- Журнал обновлений (vendor, setting_id, version, payload_hash, created_at).
- Используется для сравнения с новым бандлом и для rollback.

## 2. JSONB и индексы
- `orcaslicer_settings` и `metadata` хранятся как `JSONB`.
- Индексы:
  - `printer_profiles`: `idx_printer_profiles_slug`, `idx_printer_profiles_printer_id`, `idx_printer_profiles_is_official`, `idx_printer_profiles_default_print_profile`.
  - `print_profiles`: `idx_print_profiles_slug`, `idx_print_profiles_category`, `idx_print_profiles_layer_height`, `idx_print_profiles_is_official`.
  - GIN индексы поверх `metadata` только для популярных ключей (`machine_max_speed_x`, `sparse_infill_density` и т.п.).
  - Для `print_profile_printers`/`print_profile_filaments` — BTree на `printer_slug`/`filament_slug`.

## 3. Импортный пайплайн
1. Считываем `vendor bundle` → `OrcaVendorBundle`.
2. Для каждого `machine_model`:
   - создаём/обновляем запись в `printers` (по `model_id`/`slug`).
   - сохраняем `default_materials` в `printer_materials`.
3. Для каждого `machine`:
   - парсим через `OrcaMachinePreset`.
   - извлекаем нормализованные поля → заполняем новые колонки.
   - полный JSON кладём в `orcaslicer_settings`.
   - связь `printer_id` по `printer_model`.
4. Для каждого `process`:
   - парсим `OrcaProcessPreset`.
   - вычисляем `layer_height`, `quality_tier`, `default_nozzle`.
   - разбираем `compatible_printers_condition` в `print_profile_printers` (простые выражения типа `printer_model==...`; сложные условия сохраняем строкой в `metadata.condition_raw`).
5. Регистрируем версию в `profile_versions`.

## 4. Пользовательские пресеты
- Создаём записи в тех же таблицах (`is_official=False`, `owner_user_id` заполнен).
- Храним «полный» JSON в `orcaslicer_settings`, но `metadata` заполняем автоматом из ключевых параметров (набор парсеров общий с системными профилями).
- Для отслеживания отклонений от официальных профилей можно:
  - хранить `base_profile_id` (FK на официальный профиль);
  - сохранять дифф в `profile_overrides (profile_id, base_profile_id, diff_json)`.

## 5. Масштабирование
- При >50к записей включаем партиционирование по `is_official`/`brand` (PostgreSQL declarative partitioning).
- Redis/KeyDB держит горячий кеш (мэп `printer_slug+nozzle → profile_id`).
- Сырые бандлы лежат в `docs/orca_bundles/system_presets` и дублируются на S3; в БД хранится только хеш/версия.

## 6. Следующие шаги
1. Миграции:
   - Добавить новые колонки (`nozzle_diameters`, `printable_area`, `metadata`, и т.п.) + индексы.
   - Создать `print_profile_printers` и `print_profile_filaments`.
2. Импортёр:
   - пользуясь `Orca*` схемами, реализовать `manage_orca_import` (скрипт/команда).
3. Нормализация текущих данных:
   - прогнать скрипт поверх `docs/orca_bundles/system_presets`, заполнить таблицы.
4. Кэш и API:
   - обновить эндпоинты, чтобы выдавать нормализованные поля (nozzle, layer_height), использовать их в фильтрах.
5. Версионирование (по необходимости):
   - добавить `profile_versions`, `profile_overrides`.

Этот план покрывает и системные, и пользовательские пресеты, обеспечивает масштабируемость и при этом сохраняет совместимость с форматом OrcaSlicer.

