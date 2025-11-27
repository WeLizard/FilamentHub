# Анализ полей профилей OrcaSlicer vs FilamentHub

## 📚 Полный список полей, которые OrcaSlicer читает из JSON профилей

**Источник:** `docs/md/ORCASLICER_PARAMETERS_FULL.md`

**Всего параметров:** ~113+ (в зависимости от версии OrcaSlicer)

### Категории параметров:

1. **Базовые поля профиля** (8 полей)
2. **Температуры** (15+ полей)
3. **Вентиляторы** (15+ полей)
4. **Свойства филамента** (15+ полей)
5. **Retraction** (15+ полей)
6. **Wipe** (4 поля)
7. **Скорости и замедления** (4 поля)
8. **Pressure Advance** (6 полей)
9. **Мультитул** (5 полей)
10. **Загрузка/выгрузка** (5 полей)
11. **Охлаждение при загрузке** (3 поля)
12. **Stamping** (2 поля)
13. **Экструдер** (2 поля)
14. **Дополнительные** (4 поля)
15. **G-code** (2 поля)
16. **Совместимость** (4 поля)
17. **Заметки** (1 поле)

**Полный список см. в:** `docs/md/ORCASLICER_PARAMETERS_FULL.md`

---

## 📋 Поля в .info файлах OrcaSlicer

### Текущие поля, которые мы сохраняем:

1. **sync_info** - строка синхронизации (обычно пустая)
2. **user_id** - ID пользователя в OrcaSlicer (или FilamentHub user_id)
3. **setting_id** - уникальный ID профиля (например, `FHUB000123`)
4. **base_id** - ID базового профиля (обычно "null" для пользовательских)
5. **updated_time** - timestamp последнего обновления (Unix timestamp)

### Где генерируется:

**Backend:** `backend/app/services/orcaslicer_exporter.py` → функция `generate_profile_info()`

```python
def generate_profile_info(preset: Preset, filament: Filament) -> str:
    """
    Генерировать .info файл в формате INI для OrcaSlicer.
    
    Формат .info файла OrcaSlicer (INI):
    sync_info = значение (или пустая строка)
    user_id = значение (или пустая строка)
    setting_id = значение
    base_id = значение (или "null")
    updated_time = timestamp (число)
    """
```

---

## 🔍 Поиск тегов в OrcaSlicer

### Результаты поиска:

1. **В JSON профилях** - не найдено поля `tag` или `tags`
2. **В .info файлах** - не найдено поля `tag` или `tags`
3. **В исходниках OrcaSlicer** - найдены упоминания `tag`, но они относятся к:
   - UI элементам (кнопки, подсказки)
   - G-code тегам (для маркировки слоёв)
   - НЕ к профилям материалов

### Примеры найденных упоминаний:

- `docs/OrcaSlicer/src/slic3r/GUI/HintNotification.cpp` - теги для уведомлений
- `docs/OrcaSlicer/src/slic3r/GUI/FilamentGroupPopup.cpp` - теги для UI кнопок
- `docs/OrcaSlicer/src/libslic3r/GCode.cpp` - теги для G-code маркировки

**Вывод:** В OrcaSlicer НЕТ стандартного поля `tag` или `tags` для профилей материалов.

---

## 💾 Хранение в базе данных FilamentHub

### Таблица `presets`:

**Поля, связанные с метаданными:**
- `id` - Primary key
- `user_id` - ID пользователя, создавшего пресет
- `external_id` - ID профиля в OrcaSlicer (для маппинга)
- `setting_id` - генерируется как `FHUB{id:06d}`
- `source` - источник пресета ("orcaslicer", "user", "system")
- `sync_enabled` - включена ли синхронизация
- `orcaslicer_settings` - JSON с расширенными параметрами

**Поля, НЕ связанные с тегами:**
- Нет поля `tags` в таблице `presets`
- Нет поля `tag` в таблице `presets`
- Нет отдельной таблицы для тегов

### Таблица `filaments`:

**Поля, связанные с категоризацией:**
- `material_type` - тип материала (PLA, PETG, ABS и т.д.)
- `color_name` - название цвета
- `color_hex` - HEX код цвета
- `visual_settings` - JSON с визуальными настройками (финиш, наполнитель и т.д.)

**Поля, НЕ связанные с тегами:**
- Нет поля `tags` в таблице `filaments`
- Нет поля `tag` в таблице `filaments`

---

## 📊 Сравнительная таблица

| Поле | OrcaSlicer .info | OrcaSlicer JSON | FilamentHub DB | Комментарий |
|------|------------------|-----------------|----------------|-------------|
| `sync_info` | ✅ | ❌ | ❌ | Только в .info файле |
| `user_id` | ✅ | ❌ | ✅ (`presets.user_id`) | Есть в обоих |
| `setting_id` | ✅ | ✅ | ✅ (`presets.setting_id`) | Есть в обоих |
| `base_id` | ✅ | ❌ | ❌ | Только в .info файле |
| `updated_time` | ✅ | ❌ | ✅ (`presets.updated_at`) | Есть в обоих (разные форматы) |
| `tag` / `tags` | ❌ | ❌ | ❌ | **НЕ НАЙДЕНО** |
| `fhub_id` | ❌ | ✅ | ✅ (`presets.id`) | В JSON профиле для синхронизации |
| `fhub_source` | ❌ | ✅ | ❌ | В JSON профиле для идентификации |

---

## 🤔 Возможные интерпретации "тегов"

Если пользователь имел в виду что-то другое под "тегами":

### 1. **Категории материалов** (`material_type`)
- **OrcaSlicer:** Хранится в JSON как `filament_type`
- **FilamentHub:** Хранится в `filaments.material_type`
- ✅ **Синхронизируется**

### 2. **Визуальные характеристики** (`visual_settings`)
- **OrcaSlicer:** Нет стандартного поля
- **FilamentHub:** Хранится в `filaments.visual_settings` (JSON)
- ❌ **НЕ синхронизируется** (только для сайта)

### 3. **Метаданные синхронизации** (`fhub_id`, `fhub_source`)
- **OrcaSlicer:** Хранится в JSON профиля
- **FilamentHub:** Хранится в `presets.id` и генерируется при экспорте
- ✅ **Синхронизируется**

### 4. **Производитель** (`filament_vendor`)
- **OrcaSlicer:** Хранится в JSON как `filament_vendor`
- **FilamentHub:** Хранится через связь `filaments.brand.name`
- ✅ **Синхронизируется**

---

## ✅ Выводы

1. **В OrcaSlicer НЕТ стандартного поля `tag` или `tags` для профилей материалов**
2. **В FilamentHub НЕТ поля `tag` или `tags` в базе данных**
3. **Все существующие поля метаданных синхронизируются корректно:**
   - `user_id` ✅
   - `setting_id` ✅
   - `updated_time` ✅
   - `fhub_id` ✅ (в JSON)
   - `fhub_source` ✅ (в JSON)

---

## 💡 Рекомендации

Если нужно добавить поддержку тегов:

1. **В базе данных FilamentHub:**
   - Добавить поле `tags` в таблицу `presets` (JSON массив строк)
   - Или создать отдельную таблицу `preset_tags` (many-to-many)

2. **В OrcaSlicer:**
   - Добавить поле `tags` в JSON профиль (массив строк)
   - Добавить поле `tags` в .info файл (через запятую или JSON)

3. **В синхронизации:**
   - Экспортировать теги из FilamentHub в OrcaSlicer JSON
   - Импортировать теги из OrcaSlicer JSON в FilamentHub
   - Сохранять теги в .info файле (если нужно)

---

## 📊 Сравнение: Что мы экспортируем vs Что OrcaSlicer может читать

### ✅ Поля, которые мы экспортируем (из `orcaslicer_exporter.py`):

**Базовые:**
- `version`, `type`, `name`, `from`, `instantiation`, `filament_settings_id`
- `setting_id`, `filament_id`, `inherits`

**Температуры:**
- `nozzle_temperature`, `nozzle_temperature_initial_layer`
- `hot_plate_temp`, `hot_plate_temp_initial_layer`
- `cool_plate_temp`, `cool_plate_temp_initial_layer`
- `eng_plate_temp`, `eng_plate_temp_initial_layer`
- `textured_plate_temp`, `textured_plate_temp_initial_layer`

**Вентиляторы:**
- `fan_min_speed`, `fan_max_speed`, `overhang_fan_speed`

**Свойства филамента:**
- `filament_type`, `filament_vendor`, `filament_diameter`, `filament_density`
- `filament_cost`, `default_filament_colour`

**Retraction:**
- `filament_retraction_length`, `filament_retraction_speed`

**Flow:**
- `filament_flow_ratio`

**Расширенные (из `orcaslicer_settings`):**
- Все параметры из JSON поля `presets.orcaslicer_settings` экспортируются автоматически

**Метаданные FilamentHub:**
- `fhub_id`, `fhub_source`, `fhub_draft_id` (для черновиков)

### ❌ Поля, которые OrcaSlicer может читать, но мы НЕ экспортируем явно:

**Температуры:**
- `nozzle_temperature_range_low`, `nozzle_temperature_range_high`
- `idle_temperature`
- `textured_cool_plate_temp`, `textured_cool_plate_temp_initial_layer`
- `supertack_plate_temp`, `supertack_plate_temp_initial_layer`
- `temperature_vitrification`
- `chamber_temperature`, `activate_chamber_temp_control`

**Вентиляторы:**
- `overhang_fan_threshold`, `fan_cooling_layer_time`
- `close_fan_the_first_x_layers`, `full_fan_speed_layer`
- `reduce_fan_stop_start_freq`, `additional_cooling_fan_speed`
- `enable_overhang_bridge_fan`, `internal_bridge_fan_speed`
- `ironing_fan_speed`, `support_material_interface_fan_speed`
- `complete_print_exhaust_fan_speed`, `during_print_exhaust_fan_speed`
- `activate_air_filtration`

**Свойства филамента:**
- `filament_is_support`, `filament_soluble`, `filament_printable`
- `filament_adhesiveness_category`
- `filament_max_volumetric_speed`, `filament_adaptive_volumetric_speed`
- `volumetric_speed_coefficients`
- `filament_shrink`, `filament_shrinkage_compensation_z`

**Retraction (расширенные):**
- `filament_deretraction_speed`
- `filament_retraction_minimum_travel`
- `filament_retract_before_wipe`, `filament_retract_when_changing_layer`
- `filament_retract_restart_extra`
- `filament_retraction_distances_when_cut`, `filament_long_retractions_when_cut`
- `filament_z_hop`, `filament_z_hop_types`
- `filament_retract_lift_above`, `filament_retract_lift_below`, `filament_retract_lift_enforce`

**Wipe:**
- `filament_wipe`, `filament_wipe_distance`
- `filament_flush_temp`, `filament_flush_volumetric_speed`

**Скорости:**
- `slow_down_for_layer_cooling`, `slow_down_layer_time`
- `slow_down_min_speed`, `dont_slow_down_outer_wall`

**Pressure Advance:**
- `pressure_advance`, `enable_pressure_advance`
- `adaptive_pressure_advance`, `adaptive_pressure_advance_bridges`
- `adaptive_pressure_advance_overhangs`, `adaptive_pressure_advance_model`

**Мультитул:**
- `filament_multitool_ramming`, `filament_multitool_ramming_flow`
- `filament_multitool_ramming_volume`, `filament_ramming_parameters`
- `filament_toolchange_delay`

**Загрузка/выгрузка:**
- `filament_loading_speed`, `filament_loading_speed_start`
- `filament_unloading_speed`, `filament_unloading_speed_start`
- `filament_change_length`

**Охлаждение:**
- `filament_cooling_initial_speed`, `filament_cooling_final_speed`
- `filament_cooling_moves`

**Stamping:**
- `filament_stamping_distance`, `filament_stamping_loading_speed`

**Экструдер:**
- `filament_extruder_variant`, `required_nozzle_HRC`

**Дополнительные:**
- `filament_minimal_purge_on_wipe_tower`
- `long_retractions_when_ec`, `retraction_distances_when_ec`
- `pellet_flow_coefficient`

**G-code:**
- `filament_start_gcode`, `filament_end_gcode`

**Совместимость:**
- `compatible_printers`, `compatible_printers_condition`
- `compatible_prints`, `compatible_prints_condition`

**Заметки:**
- `filament_notes`

### 💡 Важно:

**Все эти поля МОГУТ быть экспортированы через `orcaslicer_settings`!**

Если пользователь добавит любое из этих полей в JSON поле `presets.orcaslicer_settings`, оно автоматически будет экспортировано в OrcaSlicer JSON профиль (см. строки 161-180 в `orcaslicer_exporter.py`).

---

**Дата анализа:** 2025-11-23  
**Статус:** ✅ Все существующие поля синхронизируются корректно. Поле `tag`/`tags` не найдено ни в OrcaSlicer, ни в FilamentHub.  
**Полный список параметров OrcaSlicer:** `docs/md/ORCASLICER_PARAMETERS_FULL.md`

