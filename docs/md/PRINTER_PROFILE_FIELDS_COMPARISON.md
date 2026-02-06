# Сравнение полей Printer Profile: OrcaSlicer vs FilamentHub

> **Цель:** Убедиться, что мы правильно храним все поля из OrcaSlicer в нашей системе

## Структура хранения в FilamentHub

В FilamentHub поля Printer Profile хранятся в двух местах:

1. **Отдельные колонки в БД** (`printer_profiles` таблица) - для часто используемых полей
2. **JSON поле `orcaslicer_settings`** - для всех остальных полей из OrcaSlicer

---

## Сравнение полей

### ✅ Поля, которые у нас есть в отдельных колонках

| FilamentHub поле | OrcaSlicer поле | Примечание |
|------------------|----------------|------------|
| `name` | `name` | ✅ Имя профиля |
| `slug` | - | ✅ Уникальный идентификатор (наш) |
| `description` | - | ✅ Описание (наше) |
| `printer_id` | - | ✅ Связь с Printer (наше) |
| `owner_user_id` | - | ✅ Владелец (наше) |
| `is_official` | - | ✅ Официальный профиль (наше) |
| `active` | - | ✅ Активность (наше) |
| `source` | `from` | ✅ Источник (system/user) |
| `vendor` | - | ✅ Производитель (наше) |
| `external_id` | `setting_id` | ✅ ID из OrcaSlicer |
| `setting_id` | `setting_id` | ✅ ID настройки |
| `nozzle_diameters` | `nozzle_diameter` (из settings) | ✅ Диаметры сопла (извлекаем из JSON) |
| `printable_area` | `printable_area` | ✅ Область печати |
| `printable_height_mm` | `printable_height` | ✅ Высота печати |
| `default_print_profile_slug` | `default_print_profile` | ✅ Профиль печати по умолчанию |
| `start_gcode` | `machine_start_gcode` | ✅ Начальный G-code |
| `end_gcode` | `machine_end_gcode` | ✅ Конечный G-code |
| `notes` | `printer_notes` | ✅ Заметки |
| `orcaslicer_settings` | **ВСЕ остальные поля** | ✅ Полный JSON из OrcaSlicer |

---

## ❌ Поля из OrcaSlicer, которые НЕ хранятся в отдельных колонках

Все эти поля должны храниться в `orcaslicer_settings` JSON:

### Базовые настройки принтера
- `printer_technology` - Технология принтера (FFF|SLA)
- `printer_model` - Модель принтера (ссылка на базовую модель)
- `printer_variant` - Вариант принтера (например "0.4")
- `printer_extruder_id` - ID экструдера принтера
- `printer_extruder_variant` - Вариант экструдера принтера
- `extruder_variant_list` - Список вариантов экструдеров
- `default_nozzle_volume_type` - Тип объема сопла по умолчанию
- `inherits` - Базовый профиль для наследования

### Область печати (расширенные)
- `extruder_printable_area` - Область печати экструдера (группы точек)
- `bed_exclude_area` - Исключаемая область стола (полигон точек)
- `extruder_printable_height` - Высота печати экструдера (мм)
- `extruder_clearance_radius` - Радиус очистки экструдера
- `extruder_clearance_height_to_lid` - Высота очистки до крышки
- `extruder_clearance_height_to_rod` - Высота очистки до стержня
- `nozzle_height` - Высота сопла
- `master_extruder_id` - ID главного экструдера

### Стол (bed)
- `bed_custom_texture` - Пользовательская текстура стола
- `bed_custom_model` - Пользовательская модель стола
- `support_multi_bed_types` - Поддержка нескольких типов столов (0|1)
- `default_bed_type` - Тип стола по умолчанию
- `bed_temperature_formula` - Формула температуры стола
- `bed_mesh_min` - Минимальная точка сетки стола
- `bed_mesh_max` - Максимальная точка сетки стола
- `bed_mesh_probe_distance` - Расстояние зондирования сетки стола
- `adaptive_bed_mesh_margin` - Отступ адаптивной сетки стола

### Сопло (nozzle)
- `nozzle_type` - Тип сопла
- `nozzle_hrc` - Твердость сопла HRC
- `nozzle_volume` - Объем сопла
- `nozzle_flush_dataset` - Набор данных промывки сопла

### G-code (расширенные)
- `before_layer_change_gcode` - G-code перед сменой слоя
- `printing_by_object_gcode` - G-code при печати по объектам
- `layer_change_gcode` - G-code при смене слоя
- `time_lapse_gcode` - G-code для таймлапса
- `wrapping_detection_gcode` - G-code для обнаружения обертывания
- `change_filament_gcode` - G-code при смене филамента
- `change_extrusion_role_gcode` - G-code при смене роли экструзии
- `machine_pause_gcode` - G-code при паузе принтера
- `template_custom_gcode` - Пользовательский шаблон G-code

### Вентиляторы
- `fan_kickstart` - Запуск вентилятора
- `fan_speedup_time` - Время ускорения вентилятора
- `fan_speedup_overhangs` - Ускорение вентилятора для свесов
- `auxiliary_fan` - Вспомогательный вентилятор

### Экструдер
- `single_extruder_multi_material` - Один экструдер, несколько материалов (0|1)
- `manual_filament_change` - Ручная смена филамента (0|1)
- `extruder_type` - Тип экструдера
- `use_firmware_retraction` - Использовать ретракцию прошивки (0|1)
- `use_relative_e_distances` - Использовать относительные расстояния E (0|1)
- `physical_extruder_map` - Карта физических экструдеров

### Ретракция и перемещения
- `z_hop_types` - Типы подъема Z
- `travel_slope` - Наклон перемещения
- `retract_lift_enforce` - Принудительный подъем при ретракции
- `z_offset` - Смещение Z
- `enable_long_retraction_when_cut` - Включить длинную ретракцию при обрезке (0|1)
- `long_retractions_when_cut` - Длинные ретракции при обрезке
- `retraction_distances_when_cut` - Расстояния ретракции при обрезке

### Охлаждение и загрузка
- `cooling_tube_retraction` - Ретракция охлаждающей трубки
- `cooling_tube_length` - Длина охлаждающей трубки
- `high_current_on_filament_swap` - Высокий ток при смене филамента (0|1)
- `parking_pos_retraction` - Ретракция в позиции парковки
- `extra_loading_move` - Дополнительное движение загрузки
- `purge_in_prime_tower` - Очистка в башне прайминга (0|1)
- `enable_filament_ramming` - Включить ramming филамента (0|1)
- `grab_length` - Длина захвата

### Специальные функции
- `silent_mode` - Тихий режим (0|1)
- `scan_first_layer` - Сканирование первого слоя (0|1)
- `wrapping_detection_layers` - Слои обнаружения обертывания
- `wrapping_exclude_area` - Исключаемая область обертывания
- `upward_compatible_machine` - Совместимая машина вверх
- `printer_structure` - Структура принтера
- `best_object_pos` - Лучшая позиция объекта
- `head_wrap_detect_zone` - Зона обнаружения обертывания головы
- `preferred_orientation` - Предпочтительная ориентация
- `emit_machine_limits_to_gcode` - Выдавать ограничения машины в G-code (0|1)
- `pellet_modded_printer` - Принтер с модификацией для пеллет (0|1)
- `disable_m73` - Отключить M73 (0|1)

### Температура камеры
- `support_chamber_temp_control` - Поддержка контроля температуры камеры (0|1)
- `support_air_filtration` - Поддержка воздушной фильтрации (0|1)

### Время и стоимость
- `machine_load_filament_time` - Время загрузки филамента
- `machine_unload_filament_time` - Время выгрузки филамента
- `machine_tool_change_time` - Время смены инструмента
- `time_cost` - Стоимость времени

### Сетевые настройки (Print Host)
- `host_type` - Тип хоста
- `print_host` - Хост печати
- `printhost_apikey` - API ключ хоста печати
- `bbl_use_printhost` - Использовать хост печати BBL (0|1)
- `print_host_webui` - WebUI хоста печати
- `printhost_cafile` - CA файл хоста печати
- `printhost_port` - Порт хоста печати
- `printhost_authorization_type` - Тип авторизации хоста печати
- `printhost_user` - Пользователь хоста печати
- `printhost_password` - Пароль хоста печати
- `printhost_ssl_ignore_revoke` - Игнорировать отзыв SSL (0|1)

### Дополнительные настройки
- `gcode_flavor` - Вкус G-code (Marlin, RepRap, etc.)
- `thumbnails` - Миниатюры
- `thumbnails_format` - Формат миниатюр

---

## Machine Limits (ограничения машины)

Эти поля также должны храниться в `orcaslicer_settings`:

### Acceleration limits
- `machine_max_acceleration_extruding`
- `machine_max_acceleration_retracting`
- `machine_max_acceleration_travel`
- `machine_max_acceleration_x`
- `machine_max_acceleration_y`
- `machine_max_acceleration_z`
- `machine_max_acceleration_e`

### Speed limits
- `machine_max_speed_x`
- `machine_max_speed_y`
- `machine_max_speed_z`
- `machine_max_speed_e`

### Minimum rates
- `machine_min_extruding_rate`
- `machine_min_travel_rate`

### Jerk limits
- `machine_max_jerk_x`
- `machine_max_jerk_y`
- `machine_max_jerk_z`
- `machine_max_jerk_e`
- `machine_max_junction_deviation`

### Resonance avoidance
- `resonance_avoidance`
- `min_resonance_avoidance_speed`
- `max_resonance_avoidance_speed`

---

## Текущая реализация

### Импорт (из OrcaSlicer в FilamentHub)

**Файл:** `backend/app/api/v1/endpoints/orca_sync.py` (функция `_upsert_printer_profile`)

**Логика:**
1. ✅ Полный `orcaslicer_settings` сохраняется в БД как есть (строки 680-694)
2. ✅ Отдельные поля извлекаются и сохраняются в отдельные колонки:
   - `nozzle_diameters` - извлекается из `orcaslicer_settings["nozzle_diameter"]` (строки 666-673)
   - `printable_area` - из `payload.printable_area` (строка 675)
   - `printable_height_mm` - из `payload.printable_height_mm` (строка 677)
   - `start_gcode` - из `payload.start_gcode` (строка 697)
   - `end_gcode` - из `payload.end_gcode` (строка 698)
   - `notes` - из `payload.notes` (строка 699)

**Проблем:** ❌ При обновлении существующего профиля, если `payload.orcaslicer_settings` пуст или не передан, старые `orcaslicer_settings` сохраняются (строка 696), но отдельные поля (`start_gcode`, `end_gcode`) могут перезаписать значения из `orcaslicer_settings`.

### Экспорт (из FilamentHub в OrcaSlicer)

**Файл:** `backend/app/services/orcaslicer_machine_exporter.py` (функция `printer_profile_to_orca_json`)

**Логика:**
1. ✅ Начинает с `orcaslicer_settings` (строка 184)
2. ✅ Если нет важных полей, берет из `printer.extra_metadata` (строки 198-209)
3. ⚠️ **ПЕРЕЗАПИСЫВАЕТ** поля из `orcaslicer_settings` значениями из отдельных колонок:
   - `nozzle_diameter` - из `profile.nozzle_diameters` (строки 235-239)
   - `printable_area` - из `profile.printable_area` (строки 242-249)
   - `printable_height` - из `profile.printable_height_mm` (строки 263-264)
   - `machine_start_gcode` - из `profile.start_gcode` (строки 273-274)
   - `machine_end_gcode` - из `profile.end_gcode` (строки 275-276)
   - `printer_model` - из `printer.name` (строки 267-270)
   - `default_print_profile` - из `profile.default_print_profile_slug` (строки 279-300)

**Проблем:** ❌ При экспорте значения из отдельных колонок **всегда перезаписывают** значения из `orcaslicer_settings`, даже если в `orcaslicer_settings` есть более актуальные данные.

---

## Выводы

### ✅ Что работает правильно:

1. **Импорт** - полный `orcaslicer_settings` сохраняется в БД
2. **Извлечение данных** - часто используемые поля извлекаются в отдельные колонки для удобства
3. **Экспорт** - базовые поля всегда присутствуют в экспортируемом JSON

### ⚠️ Проблемы:

1. **При импорте:**
   - Если `payload.orcaslicer_settings` не передан, старые настройки сохраняются, но отдельные поля могут быть обновлены
   - Это может привести к рассинхронизации: в `orcaslicer_settings` одно значение, в отдельной колонке - другое

2. **При экспорте:**
   - Значения из отдельных колонок **всегда перезаписывают** значения из `orcaslicer_settings`
   - Если пользователь изменил поле в OrcaSlicer (например, `machine_start_gcode`), оно сохранится в `orcaslicer_settings`, но при экспорте будет перезаписано значением из `profile.start_gcode`
   - Это может привести к потере изменений пользователя

3. **Приоритет полей:**
   - Сейчас: отдельные колонки > `orcaslicer_settings` (при экспорте)
   - Должно быть: `orcaslicer_settings` > отдельные колонки (при экспорте)

---

## Рекомендации

### 1. При импорте (исправить):

```python
# Текущая логика (строка 680-696):
if payload.orcaslicer_settings:
    profile.orcaslicer_settings = updated_settings
else:
    profile.orcaslicer_settings = profile.orcaslicer_settings or {}

# Проблема: если payload.orcaslicer_settings пуст, старые настройки сохраняются
# Но отдельные поля (start_gcode, end_gcode) обновляются из payload

# Рекомендация:
if payload.orcaslicer_settings:
    # Обновляем orcaslicer_settings
    profile.orcaslicer_settings = updated_settings
    # Синхронизируем отдельные колонки с orcaslicer_settings
    if "machine_start_gcode" in updated_settings:
        profile.start_gcode = updated_settings["machine_start_gcode"]
    if "machine_end_gcode" in updated_settings:
        profile.end_gcode = updated_settings["machine_end_gcode"]
else:
    # Если orcaslicer_settings не передан, обновляем только отдельные колонки
    # И обновляем orcaslicer_settings из отдельных колонок
    if profile.orcaslicer_settings:
        if profile.start_gcode:
            profile.orcaslicer_settings["machine_start_gcode"] = profile.start_gcode
        if profile.end_gcode:
            profile.orcaslicer_settings["machine_end_gcode"] = profile.end_gcode
```

### 2. При экспорте (исправить):

```python
# Текущая логика (строки 273-276):
if profile.start_gcode:
    settings["machine_start_gcode"] = profile.start_gcode
if profile.end_gcode:
    settings["machine_end_gcode"] = profile.end_gcode

# Проблема: всегда перезаписывает значения из orcaslicer_settings

# Рекомендация:
# Использовать значения из orcaslicer_settings (приоритет), если нет - из отдельных колонок
if "machine_start_gcode" not in settings and profile.start_gcode:
    settings["machine_start_gcode"] = profile.start_gcode
if "machine_end_gcode" not in settings and profile.end_gcode:
    settings["machine_end_gcode"] = profile.end_gcode

# Аналогично для других полей:
# - nozzle_diameter
# - printable_area
# - printable_height
# - printer_model
# - default_print_profile
```

### 3. Валидация:

1. ✅ Все поля из шаблона могут быть сохранены в `orcaslicer_settings` (JSON поле)
2. ✅ Нет конфликтов имен полей (отдельные колонки имеют другие имена)
3. ⚠️ Нужно исправить приоритет полей при экспорте

---

## План исправления

1. **Исправить экспорт** - использовать значения из `orcaslicer_settings` с приоритетом
2. **Исправить импорт** - синхронизировать отдельные колонки с `orcaslicer_settings`
3. **Добавить тесты** - проверить, что изменения пользователя в OrcaSlicer не теряются при экспорте

---

**Источник OrcaSlicer:** `docs/OrcaSlicer/src/libslic3r/Preset.cpp` (строки 998-1022, 987-996)  
**Источник FilamentHub:** `backend/app/models/printer_profile.py`, `backend/app/schemas/printer_profile.py`

