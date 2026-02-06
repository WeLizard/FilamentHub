# OrcaSlicer System Preset JSON Schema

## 1. Vendor bundle (`*.json` в корне производителя)
- **Назначение:** реестр всех файлов производителя.
- **Основные поля:**
  - `name` — название бренда (отображается в UI Orca).
  - `version` — строка версии пакета (семвер, используется для обновлений).
  - `force_update` — `"1"`/`"0"`; при `1` Orca принудительно перезаписывает локальные пресеты.
  - `description` — текстовое описание пакета.
  - `machine_model_list[]` — список `{ name, sub_path }` (регистрационные файлы типа `machine_model`).
  - `process_list[]` — список `{ name, sub_path }` (пресеты печати).
  - Дополнительно встречаются `material_list` и другие секции (в текущих пакетах отсутствуют, но поле нужно предусмотреть).
- **Соответствие FilamentHub:** один `*.json` → сущность производителя + набор `Printer`/`PrinterProfile` и `PrintProfile`.

## 2. Machine model (`type = "machine_model"`)
- **Содержит:** базовую информацию о конкретной модели принтера (без параметров сопла).
- **Поля:**
  - `model_id` — системный идентификатор Orca (`Anycubic-Kobra-2`).
  - `nozzle_diameter` — дефолтный диаметр сопла (строка).
  - `machine_tech` — технология (`FFF`, `SLA` и т.д.).
  - `family` — бренд/семейство (совпадает с `name` родительского пакета).
  - `bed_model`, `bed_texture`, `hotend_model` — пути к моделям/иконкам (можно хранить в метаданных, в FilamentHub напрямую не нужны).
  - `default_materials` — список материалов через `;` (используем для автосвязывания с нашими Filament-профилями).
- **Формат:** ключи → строки. При импорте полезно нормализовать в типы (`float`, `list[str]` и т.д.).
- **Соответствие FilamentHub:** хорошая основа для сущности `Printer` (название, slug, совместимые материалы).

## 3. Machine preset (`type = "machine"`)
- **Назначение:** конкретный профиль принтера + сопло (0.4 и т.д.).
- **Мета-поля:**
  - `inherits` — имя базового файла (обычно `fdm_machine_common`). Нужно сохранять для реконструкции и диффов.
  - `from` — источник (`system`/`user`). Используем для метки официального профиля.
  - `setting_id` — ID профиля (может пригодиться для обновлений).
  - `instantiation` — `"true"/"false"` → bool (нужно для Orca).
  - `printer_model` — ссылка на `machine_model` (используем для связи с `Printer`).
  - `default_print_profile` — предустановленный процесс (сопоставляется с `PrintProfile`).
  - `nozzle_diameter`, `printable_area`, `printable_height` — основные размеры.
  - Остальные ключи (`machine_max_acceleration_*`, `machine_max_speed_*`, `gcode_*`, `max_layer_height` и т.д.) образуют параметры профиля.
- **Соответствие FilamentHub:**
  - `PrinterProfile.name/slug` → `name` (слуг генерируем из него).
  - `PrinterProfile.orcaslicer_settings` → полный JSON (после нормализации типов).
  - `PrinterProfile.is_official` → `from == "system"`.
  - `PrinterProfile.printer_id` → по `printer_model` / `model_id`.
  - `PrinterProfile.default_print_profile_slug` (доп. поле, если потребуется) → `default_print_profile`.

## 4. Process preset (`type = "process"`)
- **Назначение:** пресеты печати (print settings).
- **Мета-поля:**
  - `inherits`, `from`, `setting_id`, `instantiation` — аналогично machine.
  - `compatiable_printers_condition` / `compatible_printers` — правила совместимости (строки условных выражений). Нужно хранить, чтобы Orca могла фильтровать.
  - `print_settings_id` — внутренний ID (бывает пустым).
- **Параметры:** десятки ключей (`layer_height`, `wall_loops`, `bridge_flow`, `speed_*`, `acceleration_*`, `ironing_*`, `seam_position`, `draft_shield`). Все строки, многие содержат `%` или списки.
- **Соответствие FilamentHub:**
  - `PrintProfile.name/slug` ← `name`.
  - `PrintProfile.category` — можно извлечь из имени (`0.20mm Standard` → category `standard`) или из дополнительных ключей.
  - `PrintProfile.orcaslicer_settings` — сохраняем весь JSON с конвертированными типами.
  - `PrintProfile.compatible_printers` — разобрать `compatible_printers` и `compatible_printers_condition` (условие → список slug, где применимо).
  - `PrintProfile.is_official` → `from == "system"`.

## 5. Общие правила нормализации
- **Типы:** Orca хранит всё строками. Для удобства дальнейшего сравнения стоит конвертировать в Python-типы:
  - `"true"/"false"` → `bool`;
  - `"123"` или `"123.4"` → `int`/`float` (если нет суффиксов `%`, `mm` и т.д.);
  - значения с `%`, `mm`, `°C` желательно хранить строками, но добавить аналитические поля, если понадобится сравнение.
- **Списки:** многие поля содержат массивы строк, но фактически это либо списки точек (`printable_area`), либо диапазоны; для БД лучше хранить как `list[str]`.
- **Совместимости:** ключи `compatible_*_condition` — мини-DSL Orca (логические выражения). Мы можем до поры хранить как `str` и только для популярных случаев (по slug) вычислять список.
- **Slug:** систему Orca не требует slug, но для FilamentHub нужно генерировать уникальные (`generate_unique_slug`).

## 6. Mapping в сущности FilamentHub

| Orca JSON | FilamentHub | Комментарий |
|-----------|-------------|-------------|
| `Vendor bundle.name` | `Brand.name` / reference | Бренд производителя. |
| `machine_model` | `Printer` | model_id → slug, `default_materials` → связи с Filament. |
| `machine` | `PrinterProfile` | `orcaslicer_settings` полностью сохраняется. |
| `process` | `PrintProfile` | `orcaslicer_settings` + категории. |
| `default_print_profile` | связь `PrinterProfile` → `PrintProfile` | Можно сохранять отдельным полем/таблицей. |
| `setting_id` | тех. ключ | Используем для детекции обновлений в будущем. |
| `force_update` | политика обновлений | Если `1`, автоматически перезаписываем user overrides при новой версии. |

## 7. Импорт и обновления
1. Читаем vendor bundle, резолвим относительные пути `sub_path` относительно `docs/orca_bundles/system_presets/<Vendor>`.
2. Валидируем через Pydantic-схемы (см. `backend/app/schemas/orca_bundle.py`).
3. Нормализуем данные (конверсия типов, генерация slug, сопоставление с существующими `Printer`/`PrinterProfile`/`PrintProfile`).
4. Сохраняем новые или обновляем существующие записи (`setting_id` + `model_id` помогут найти соответствия).
5. Оставшиеся поля кладём в `orcaslicer_settings` без потерь — это гарантирует 100% совместимость при отдаче назад в OrcaSlicer.

## 8. Что ещё учесть
- Некоторые пакеты содержат `fdm_machine_common.json` / `fdm_process_common.json`: это базовые профили, которые в Orca используются как `inherits`. Стоит хранить их отдельно (например, в `PrinterProfile`/`PrintProfile` с признаком `is_common = True` или в служебной таблице).
- При экспорте в OrcaSlicer важно восстановить исходную структуру (`type`, `name`, `inherits`, `from`, и полностью `orcaslicer_settings`).
- В будущем можно добавить вычисление «ETAs» (скорости/акселерации) на сервере — после нормализации типов это проще.

Документ служит эталоном для импорта системных пресетов и формирования пользовательских профилей на сервере.

