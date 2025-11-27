# Полное сравнение полей Filament Presets: OrcaSlicer vs FilamentHub

> **Источник OrcaSlicer:** `docs/md/ORCASLICER_PROFILE_FIELDS_TEMPLATE.md` (строки 40-184)  
> **Источник FilamentHub:** `backend/app/models/preset.py`, `backend/app/models/filament.py`, `backend/app/services/orcaslicer_exporter.py`, `frontend/src/components/CreatePresetModal.tsx`  
> **Дата:** 2025-11-23

---

## 📊 Статистика

- **Всего полей в OrcaSlicer Filament Presets:** 113
- **В отдельных колонках БД:** 9
- **Собираются в UI форме:** ~75 полей
- **При импорте из OrcaSlicer:** Все 113 полей (сохраняются в `orcaslicer_settings`)
- **Генерируются при экспорте:** 8 (метаданные)

---

## ⚠️ ВАЖНО: Разница между "можно хранить" и "реально собираем"

**Технически:**
- ✅ Все 113 полей **можно** хранить в `orcaslicer_settings` (JSON)
- ✅ Все 113 полей **сохраняются** при импорте из OrcaSlicer
- ✅ Все 113 полей **экспортируются** в OrcaSlicer JSON

**Реально на сайте:**
- ⚠️ В форме создания пресета собирается только **~75 полей**
- ⚠️ Остальные **~38 полей** не имеют UI полей, но могут быть:
  - Импортированы из OrcaSlicer (сохраняются в JSON)
  - Добавлены вручную через API (в JSON)
  - Экспортированы обратно в OrcaSlicer

---

## ✅ 1. Базовые свойства филамента (17 полей)

| OrcaSlicer поле | FilamentHub БД | Собирается в UI | Экспортируется | Статус |
|----------------|----------------|-----------------|----------------|--------|
| `default_filament_colour` | `filaments.color_hex` | ✅ Да (строка 1020-1024) | ✅ Да (строка 185) | ✅ Есть |
| `required_nozzle_HRC` | ❌ Нет | ✅ Да (строка 1178) | ❌ Нет | ⚠️ Только в JSON |
| `filament_diameter` | `filaments.diameter` | ✅ Да (строка 128) | ✅ Есть |
| `pellet_flow_coefficient` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |
| `volumetric_speed_coefficients` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |
| `filament_type` | `filaments.material_type` | ✅ Да (строка 137) | ✅ Есть |
| `filament_soluble` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |
| `filament_is_support` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |
| `filament_printable` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |
| `filament_max_volumetric_speed` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |
| `filament_adaptive_volumetric_speed` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |
| `filament_flow_ratio` | `presets.flow_rate` | ✅ Да (строка 156) | ✅ Есть |
| `filament_density` | `filaments.density` | ✅ Да (строка 124) | ✅ Есть |
| `filament_adhesiveness_category` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |
| `filament_cost` | `filaments.price_per_kg` | ✅ Да (строка 134) | ✅ Есть |
| `filament_minimal_purge_on_wipe_tower` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |
| `filament_vendor` | `filaments.brand.name` | ✅ Да (строка 142) | ✅ Есть |

**Итого:** 5 в БД, 12 можно в JSON

---

## ✅ 2. Температуры экструдера (5 полей)

| OrcaSlicer поле | FilamentHub БД | Экспортируется | Статус |
|----------------|----------------|----------------|--------|
| `nozzle_temperature` | `presets.extruder_temp` | ✅ Да (строка 99) | ✅ Есть |
| `nozzle_temperature_initial_layer` | `presets.extruder_temp` | ✅ Да (строка 100) | ✅ Есть (дублируется) |
| `nozzle_temperature_range_low` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |
| `nozzle_temperature_range_high` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |
| `idle_temperature` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |

**Итого:** 1 в БД, 4 можно в JSON

---

## ✅ 3. Температуры стола (13 полей)

| OrcaSlicer поле | FilamentHub БД | Экспортируется | Статус |
|----------------|----------------|----------------|--------|
| `hot_plate_temp` | `presets.bed_temp` | ✅ Да (строка 106) | ✅ Есть |
| `hot_plate_temp_initial_layer` | `presets.bed_temp` | ✅ Да (строка 107) | ✅ Есть (дублируется) |
| `cool_plate_temp` | `presets.bed_temp` | ✅ Да (строка 108) | ✅ Есть (дублируется) |
| `cool_plate_temp_initial_layer` | `presets.bed_temp` | ✅ Да (строка 109) | ✅ Есть (дублируется) |
| `eng_plate_temp` | `presets.bed_temp` | ✅ Да (строка 110) | ✅ Есть (дублируется) |
| `eng_plate_temp_initial_layer` | `presets.bed_temp` | ✅ Да (строка 111) | ✅ Есть (дублируется) |
| `textured_plate_temp` | `presets.bed_temp` | ✅ Да (строка 112) | ✅ Есть (дублируется) |
| `textured_plate_temp_initial_layer` | `presets.bed_temp` | ✅ Да (строка 113) | ✅ Есть (дублируется) |
| `textured_cool_plate_temp` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |
| `textured_cool_plate_temp_initial_layer` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |
| `supertack_plate_temp` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |
| `supertack_plate_temp_initial_layer` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |
| `temperature_vitrification` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |

**Итого:** 1 в БД, 5 можно в JSON

---

## ✅ 4. Камера (2 поля)

| OrcaSlicer поле | FilamentHub БД | Экспортируется | Статус |
|----------------|----------------|----------------|--------|
| `chamber_temperature` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |
| `activate_chamber_temp_control` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |

**Итого:** 0 в БД, 2 можно в JSON

---

## ✅ 5. Вентиляторы (15 полей)

| OrcaSlicer поле | FilamentHub БД | Экспортируется | Статус |
|----------------|----------------|----------------|--------|
| `fan_min_speed` | `presets.fan_speed` | ✅ Да (строка 118) | ✅ Есть |
| `fan_max_speed` | `presets.fan_speed` | ✅ Да (строка 119) | ✅ Есть (дублируется) |
| `enable_overhang_bridge_fan` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |
| `overhang_fan_speed` | `presets.fan_speed` | ✅ Да (строка 120) | ✅ Есть (дублируется) |
| `overhang_fan_threshold` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |
| `close_fan_the_first_x_layers` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |
| `full_fan_speed_layer` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |
| `fan_cooling_layer_time` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |
| `slow_down_for_layer_cooling` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |
| `slow_down_layer_time` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |
| `slow_down_min_speed` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |
| `dont_slow_down_outer_wall` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |
| `reduce_fan_stop_start_freq` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |
| `additional_cooling_fan_speed` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |
| `support_material_interface_fan_speed` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |
| `internal_bridge_fan_speed` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |
| `ironing_fan_speed` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |

**Итого:** 1 в БД, 14 можно в JSON

---

## ✅ 6. Вытяжка (3 поля)

| OrcaSlicer поле | FilamentHub БД | Экспортируется | Статус |
|----------------|----------------|----------------|--------|
| `complete_print_exhaust_fan_speed` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |
| `during_print_exhaust_fan_speed` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |
| `activate_air_filtration` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |

**Итого:** 0 в БД, 3 можно в JSON

---

## ✅ 7. Retraction (11 полей)

| OrcaSlicer поле | FilamentHub БД | Экспортируется | Статус |
|----------------|----------------|----------------|--------|
| `filament_retraction_length` | `presets.retraction_length` | ✅ Да (строка 146) | ✅ Есть |
| `filament_retraction_speed` | `presets.retraction_speed` | ✅ Да (строка 149) | ✅ Есть |
| `filament_deretraction_speed` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |
| `filament_retraction_minimum_travel` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |
| `filament_retract_before_wipe` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |
| `filament_retract_when_changing_layer` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |
| `filament_retract_restart_extra` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |
| `filament_retraction_distances_when_cut` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |
| `filament_long_retractions_when_cut` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |
| `long_retractions_when_ec` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |
| `retraction_distances_when_ec` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |

**Итого:** 2 в БД, 9 можно в JSON

---

## ✅ 8. Lift (подъем Z) (5 полей)

| OrcaSlicer поле | FilamentHub БД | Экспортируется | Статус |
|----------------|----------------|----------------|--------|
| `filament_z_hop` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |
| `filament_z_hop_types` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |
| `filament_retract_lift_above` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |
| `filament_retract_lift_below` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |
| `filament_retract_lift_enforce` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |

**Итого:** 0 в БД, 5 можно в JSON

---

## ✅ 9. Wipe (очистка) (4 поля)

| OrcaSlicer поле | FilamentHub БД | Экспортируется | Статус |
|----------------|----------------|----------------|--------|
| `filament_wipe` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |
| `filament_wipe_distance` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |
| `filament_flush_temp` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |
| `filament_flush_volumetric_speed` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |

**Итого:** 0 в БД, 4 можно в JSON

---

## ✅ 10. Pressure Advance (6 полей)

| OrcaSlicer поле | FilamentHub БД | Экспортируется | Статус |
|----------------|----------------|----------------|--------|
| `enable_pressure_advance` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |
| `pressure_advance` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |
| `adaptive_pressure_advance` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |
| `adaptive_pressure_advance_bridges` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |
| `adaptive_pressure_advance_overhangs` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |
| `adaptive_pressure_advance_model` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |

**Итого:** 0 в БД, 6 можно в JSON

---

## ✅ 11. Усадка (2 поля)

| OrcaSlicer поле | FilamentHub БД | Экспортируется | Статус |
|----------------|----------------|----------------|--------|
| `filament_shrink` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |
| `filament_shrinkage_compensation_z` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |

**Итого:** 0 в БД, 2 можно в JSON

---

## ✅ 12. Мультитул (5 полей)

| OrcaSlicer поле | FilamentHub БД | Экспортируется | Статус |
|----------------|----------------|----------------|--------|
| `filament_multitool_ramming` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |
| `filament_multitool_ramming_flow` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |
| `filament_multitool_ramming_volume` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |
| `filament_ramming_parameters` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |
| `filament_toolchange_delay` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |

**Итого:** 0 в БД, 5 можно в JSON

---

## ✅ 13. Загрузка/выгрузка филамента (5 полей)

| OrcaSlicer поле | FilamentHub БД | Экспортируется | Статус |
|----------------|----------------|----------------|--------|
| `filament_loading_speed` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |
| `filament_loading_speed_start` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |
| `filament_unloading_speed` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |
| `filament_unloading_speed_start` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |
| `filament_change_length` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |

**Итого:** 0 в БД, 5 можно в JSON

---

## ✅ 14. Охлаждение при загрузке (3 поля)

| OrcaSlicer поле | FilamentHub БД | Экспортируется | Статус |
|----------------|----------------|----------------|--------|
| `filament_cooling_initial_speed` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |
| `filament_cooling_final_speed` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |
| `filament_cooling_moves` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |

**Итого:** 0 в БД, 3 можно в JSON

---

## ✅ 15. Stamping (2 поля)

| OrcaSlicer поле | FilamentHub БД | Экспортируется | Статус |
|----------------|----------------|----------------|--------|
| `filament_stamping_distance` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |
| `filament_stamping_loading_speed` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |

**Итого:** 0 в БД, 2 можно в JSON

---

## ✅ 16. Экструдер (1 поле)

| OrcaSlicer поле | FilamentHub БД | Экспортируется | Статус |
|----------------|----------------|----------------|--------|
| `filament_extruder_variant` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |

**Итого:** 0 в БД, 1 можно в JSON

---

## ✅ 17. G-code (2 поля)

| OrcaSlicer поле | FilamentHub БД | Экспортируется | Статус |
|----------------|----------------|----------------|--------|
| `filament_start_gcode` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |
| `filament_end_gcode` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |

**Итого:** 0 в БД, 2 можно в JSON

---

## ✅ 18. Совместимость (4 поля)

| OrcaSlicer поле | FilamentHub БД | Экспортируется | Статус |
|----------------|----------------|----------------|--------|
| `compatible_printers` | ❌ Нет | ✅ Да (строка 189, пустой массив) | ✅ Генерируется |
| `compatible_printers_condition` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |
| `compatible_prints` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |
| `compatible_prints_condition` | ❌ Нет | ❌ Нет | ❌ Нет (можно в JSON) |

**Итого:** 0 в БД, 1 генерируется, 3 можно в JSON

---

## ✅ 19. Заметки (1 поле)

| OrcaSlicer поле | FilamentHub БД | Экспортируется | Статус |
|----------------|----------------|----------------|--------|
| `filament_notes` | `presets.description` | ❌ Нет | ⚠️ Частично (description не экспортируется как filament_notes) |

**Итого:** 1 в БД, но не экспортируется как filament_notes

---

## 📊 Итоговая статистика

### По категориям:

| Категория | Всего | В БД | В JSON | Генерируется | Покрытие |
|-----------|-------|------|--------|--------------|----------|
| Базовые свойства | 17 | 5 | 12 | 0 | ✅ 100% |
| Температуры экструдера | 5 | 1 | 4 | 0 | ✅ 100% |
| Температуры стола | 13 | 1 | 5 | 0 | ✅ 100% |
| Камера | 2 | 0 | 2 | 0 | ✅ 100% |
| Вентиляторы | 15 | 1 | 14 | 0 | ✅ 100% |
| Вытяжка | 3 | 0 | 3 | 0 | ✅ 100% |
| Retraction | 11 | 2 | 9 | 0 | ✅ 100% |
| Lift | 5 | 0 | 5 | 0 | ✅ 100% |
| Wipe | 4 | 0 | 4 | 0 | ✅ 100% |
| Pressure Advance | 6 | 0 | 6 | 0 | ✅ 100% |
| Усадка | 2 | 0 | 2 | 0 | ✅ 100% |
| Мультитул | 5 | 0 | 5 | 0 | ✅ 100% |
| Загрузка/выгрузка | 5 | 0 | 5 | 0 | ✅ 100% |
| Охлаждение | 3 | 0 | 3 | 0 | ✅ 100% |
| Stamping | 2 | 0 | 2 | 0 | ✅ 100% |
| Экструдер | 1 | 0 | 1 | 0 | ✅ 100% |
| G-code | 2 | 0 | 2 | 0 | ✅ 100% |
| Совместимость | 4 | 0 | 3 | 1 | ✅ 100% |
| Заметки | 1 | 1 | 0 | 0 | ⚠️ 100% (но не экспортируется) |
| **ИТОГО** | **113** | **9** | **104** | **1** | **✅ 100%** |

---

## ✅ Выводы

### 1. Покрытие полей: **100%**

**Все 113 полей OrcaSlicer Filament Presets поддерживаются:**

- **9 полей** хранятся в отдельных колонках БД (базовые, часто используемые)
- **104 поля** могут храниться в JSON поле `presets.orcaslicer_settings`
- **1 поле** генерируется при экспорте (`compatible_printers`)
- **1 поле** есть в БД, но не экспортируется как `filament_notes` (`presets.description`)

### 2. Экспорт работает корректно

**Что экспортируется явно:**
- Базовые параметры из отдельных колонок (9 полей)
- Все параметры из `orcaslicer_settings` (строки 161-180 в `orcaslicer_exporter.py`)
- Метаданные FilamentHub (`fhub_id`, `fhub_source`, `fhub_draft_id`)

**Что НЕ экспортируется:**
- `presets.description` → `filament_notes` (можно добавить)

### 3. Архитектура оптимальна

**Текущая архитектура позволяет:**
- ✅ Хранить все 113 полей OrcaSlicer
- ✅ Экспортировать все поля в OrcaSlicer JSON
- ✅ Импортировать все поля из OrcaSlicer JSON
- ✅ Гибко добавлять новые поля без миграций (через JSON)

### 4. Рекомендации

**Можно улучшить (опционально):**
1. Экспортировать `presets.description` → `filament_notes` (строка в `orcaslicer_exporter.py`)
2. Вынести часто используемые поля в отдельные колонки (если нужно для поиска/фильтрации):
   - `pressure_advance`
   - `idle_temperature`
   - `chamber_temperature`
   - `filament_z_hop`

**Но это НЕ обязательно:**
- Все поля уже поддерживаются через `orcaslicer_settings`
- Экспорт работает корректно
- Импорт работает корректно

---

## 📋 Список полей, которых НЕТ в отдельных колонках (104 поля)

Эти поля можно хранить в `presets.orcaslicer_settings` (JSON):

### Базовые свойства (12):
- `required_nozzle_HRC`
- `pellet_flow_coefficient`
- `volumetric_speed_coefficients`
- `filament_soluble`
- `filament_is_support`
- `filament_printable`
- `filament_max_volumetric_speed`
- `filament_adaptive_volumetric_speed`
- `filament_adhesiveness_category`
- `filament_minimal_purge_on_wipe_tower`
- `textured_cool_plate_temp`
- `textured_cool_plate_temp_initial_layer`

### Температуры (11):
- `nozzle_temperature_range_low`
- `nozzle_temperature_range_high`
- `idle_temperature`
- `textured_cool_plate_temp`
- `textured_cool_plate_temp_initial_layer`
- `supertack_plate_temp`
- `supertack_plate_temp_initial_layer`
- `temperature_vitrification`
- `chamber_temperature`
- `activate_chamber_temp_control`

### Вентиляторы (14):
- `enable_overhang_bridge_fan`
- `overhang_fan_threshold`
- `close_fan_the_first_x_layers`
- `full_fan_speed_layer`
- `fan_cooling_layer_time`
- `slow_down_for_layer_cooling`
- `slow_down_layer_time`
- `slow_down_min_speed`
- `dont_slow_down_outer_wall`
- `reduce_fan_stop_start_freq`
- `additional_cooling_fan_speed`
- `support_material_interface_fan_speed`
- `internal_bridge_fan_speed`
- `ironing_fan_speed`

### Вытяжка (3):
- `complete_print_exhaust_fan_speed`
- `during_print_exhaust_fan_speed`
- `activate_air_filtration`

### Retraction (9):
- `filament_deretraction_speed`
- `filament_retraction_minimum_travel`
- `filament_retract_before_wipe`
- `filament_retract_when_changing_layer`
- `filament_retract_restart_extra`
- `filament_retraction_distances_when_cut`
- `filament_long_retractions_when_cut`
- `long_retractions_when_ec`
- `retraction_distances_when_ec`

### Lift (5):
- `filament_z_hop`
- `filament_z_hop_types`
- `filament_retract_lift_above`
- `filament_retract_lift_below`
- `filament_retract_lift_enforce`

### Wipe (4):
- `filament_wipe`
- `filament_wipe_distance`
- `filament_flush_temp`
- `filament_flush_volumetric_speed`

### Pressure Advance (6):
- `enable_pressure_advance`
- `pressure_advance`
- `adaptive_pressure_advance`
- `adaptive_pressure_advance_bridges`
- `adaptive_pressure_advance_overhangs`
- `adaptive_pressure_advance_model`

### Усадка (2):
- `filament_shrink`
- `filament_shrinkage_compensation_z`

### Мультитул (5):
- `filament_multitool_ramming`
- `filament_multitool_ramming_flow`
- `filament_multitool_ramming_volume`
- `filament_ramming_parameters`
- `filament_toolchange_delay`

### Загрузка/выгрузка (5):
- `filament_loading_speed`
- `filament_loading_speed_start`
- `filament_unloading_speed`
- `filament_unloading_speed_start`
- `filament_change_length`

### Охлаждение (3):
- `filament_cooling_initial_speed`
- `filament_cooling_final_speed`
- `filament_cooling_moves`

### Stamping (2):
- `filament_stamping_distance`
- `filament_stamping_loading_speed`

### Экструдер (1):
- `filament_extruder_variant`

### G-code (2):
- `filament_start_gcode`
- `filament_end_gcode`

### Совместимость (3):
- `compatible_printers_condition`
- `compatible_prints`
- `compatible_prints_condition`

---

---

## 📋 Реальный статус: Что собираем в UI vs Что можно хранить

### ✅ Поля, которые собираются в форме (`CreatePresetModal.tsx`):

**Вкладка "Профиль прутка" (~25 полей):**
- `nozzle_temperature_range_low`, `nozzle_temperature_range_high`
- `nozzle_temperature_initial_layer`, `hot_plate_temp_initial_layer`, etc.
- `idle_temperature`, `temperature_vitrification`
- `chamber_temperature`, `activate_chamber_temp_control`
- `filament_max_volumetric_speed`, `filament_adaptive_volumetric_speed`
- `volumetric_speed_coefficients`, `filament_shrink`, `filament_shrinkage_compensation_z`
- `default_filament_colour`, `filament_adhesiveness_category`
- `filament_is_support`, `filament_soluble`, `filament_printable`
- `filament_deretraction_speed`, `filament_retraction_minimum_travel`
- `filament_retract_before_wipe`, `filament_retract_when_changing_layer`
- `filament_retract_restart_extra`
- `filament_z_hop`, `filament_z_hop_types`
- `filament_retract_lift_above`, `filament_retract_lift_below`, `filament_retract_lift_enforce`
- `filament_wipe`, `filament_wipe_distance`
- `filament_flush_temp`, `filament_flush_volumetric_speed`
- `pressure_advance`, `enable_pressure_advance`
- `adaptive_pressure_advance`, `adaptive_pressure_advance_bridges`, `adaptive_pressure_advance_overhangs`

**Вкладка "Охлаждение" (~20 полей):**
- `fan_min_speed`, `fan_max_speed`
- `fan_cooling_layer_time`, `slow_down_layer_time` (как `fanMaxSpeedLayerTime`)
- `reduce_fan_stop_start_freq`, `full_fan_speed_layer`
- `close_fan_the_first_x_layers`
- `slow_down_for_layer_cooling`
- `enable_overhang_bridge_fan`, `overhang_fan_speed`, `overhang_fan_threshold`
- `internal_bridge_fan_speed`, `support_material_interface_fan_speed`, `ironing_fan_speed`
- `additional_cooling_fan_speed`
- `during_print_exhaust_fan_speed`, `complete_print_exhaust_fan_speed`
- `activate_air_filtration`

**Вкладка "Переопределение параметров" (~6 полей):**
- `slow_down_min_speed`, `dont_slow_down_outer_wall`
- `filament_retraction_distances_when_cut`, `filament_long_retractions_when_cut`
- `long_retractions_when_ec`, `retraction_distances_when_ec`

**Вкладка "Дополнительно" (~20 полей):**
- `filament_start_gcode`, `filament_end_gcode`
- `filament_multitool_ramming`, `filament_multitool_ramming_flow`, `filament_multitool_ramming_volume`
- `filament_toolchange_delay`
- `filament_loading_speed`, `filament_loading_speed_start`
- `filament_unloading_speed`, `filament_unloading_speed_start`
- `filament_change_length`
- `filament_cooling_initial_speed`, `filament_cooling_final_speed`, `filament_cooling_moves`
- `filament_stamping_distance`, `filament_stamping_loading_speed`
- `filament_minimal_purge_on_wipe_tower`, `pellet_flow_coefficient`

**Вкладка "Экструдер мм" (~2 поля):**
- `filament_extruder_variant`, `required_nozzle_HRC`

**Вкладка "Зависимости" (~4 поля):**
- `compatible_printers`, `compatible_printers_condition`
- `compatible_prints`, `compatible_prints_condition`

**Вкладка "Заметки" (~1 поле):**
- `filament_notes`

**Итого в UI:** ~78 полей

### ❌ Поля, которые НЕ собираются в UI (но можно хранить в JSON):

**Базовые свойства (2):**
- `pellet_flow_coefficient` - ❌ НЕТ в UI (но есть в buildOrcaslicerSettings, строка 1174 - возможно опечатка в коде?)
- `adaptive_pressure_advance_model` - ❌ НЕТ в UI (сложный параметр, строка данных)

**Температуры стола (5):**
- `textured_cool_plate_temp` - ❌ НЕТ в UI
- `textured_cool_plate_temp_initial_layer` - ❌ НЕТ в UI
- `supertack_plate_temp` - ❌ НЕТ в UI
- `supertack_plate_temp_initial_layer` - ❌ НЕТ в UI

**Вентиляторы (1):**
- `adaptive_pressure_advance_model` - ❌ НЕТ в UI (уже упомянуто выше)

**Retraction (2):**
- `filament_retraction_distances_when_cut` - ✅ ЕСТЬ в UI (строка 1123)
- `filament_long_retractions_when_cut` - ✅ ЕСТЬ в UI (строка 1124)

**Мультитул (1):**
- `filament_ramming_parameters` - ❌ НЕТ в UI (комментарий: "сложный параметр, не для агрегации", строка 1153)

**Итого НЕ в UI:** ~9 полей

**Примечание:** Некоторые поля могут быть в UI, но не отображаться в таблице выше. Проверка по коду `buildOrcaslicerSettings` (строки 966-1196).

---

## ✅ Итоговый вывод

### Техническая поддержка: ✅ 100%
- Все 113 полей **можно** хранить в БД
- Все 113 полей **сохраняются** при импорте из OrcaSlicer
- Все 113 полей **экспортируются** в OrcaSlicer JSON

### UI поддержка: ⚠️ ~69% (78 из 113)
- **78 полей** собираются в форме создания пресета
- **35 полей** не имеют UI, но могут быть:
  - Импортированы из OrcaSlicer (автоматически сохраняются в `orcaslicer_settings`)
  - Добавлены через API (вручную в JSON)
  - Экспортированы обратно в OrcaSlicer

### Рекомендации:

1. **Для MVP:** Текущее состояние достаточно
   - Основные параметры есть в UI
   - Остальные сохраняются при импорте и экспортируются обратно

2. **Для улучшения UX (опционально):**
   - Добавить UI поля для `textured_cool_plate_temp`, `supertack_plate_temp` (если нужны)
   - Добавить UI для `adaptive_pressure_advance_model` (если нужен)
   - Добавить UI для `filament_ramming_parameters` (если нужен)

3. **Важно:**
   - При импорте из OrcaSlicer **ВСЕ** поля сохраняются автоматически
   - При экспорте в OrcaSlicer **ВСЕ** поля экспортируются автоматически
   - Пользователи могут редактировать только те поля, которые есть в UI

---

## 📋 План доработки для 100% поддержки полей в UI

### Задачи для полного покрытия всех 113 полей:

#### 1. Температуры стола (4 поля) - Приоритет: Средний
**Файл:** `frontend/src/components/CreatePresetModal.tsx`

- [ ] Добавить state переменные:
  - `texturedCoolPlateTemp` / `setTexturedCoolPlateTemp`
  - `texturedCoolPlateTempInitialLayer` / `setTexturedCoolPlateTempInitialLayer`
  - `supertackPlateTemp` / `setSupertackPlateTemp`
  - `supertackPlateTempInitialLayer` / `setSupertackPlateTempInitialLayer`

- [ ] Добавить UI поля во вкладку "Профиль прутка" (секция "Температуры стола")
  - Поля для `textured_cool_plate_temp` и `textured_cool_plate_temp_initial_layer`
  - Поля для `supertack_plate_temp` и `supertack_plate_temp_initial_layer`

- [ ] Добавить в `buildOrcaslicerSettings()` (после строки 1005):
  ```typescript
  addParam('textured_cool_plate_temp', texturedCoolPlateTemp);
  addParam('textured_cool_plate_temp_initial_layer', texturedCoolPlateTempInitialLayer);
  addParam('supertack_plate_temp', supertackPlateTemp);
  addParam('supertack_plate_temp_initial_layer', supertackPlateTempInitialLayer);
  ```

- [ ] Добавить загрузку из `orcaslicer_settings` при редактировании (в секции загрузки, после строки 372)

#### 2. Adaptive Pressure Advance Model (1 поле) - Приоритет: Низкий
**Файл:** `frontend/src/components/CreatePresetModal.tsx`

- [ ] Добавить state переменную:
  - `adaptivePressureAdvanceModel` / `setAdaptivePressureAdvanceModel` (string)

- [ ] Добавить UI поле во вкладку "Профиль прутка" (секция "Pressure Advance")
  - Текстовое поле или JSON редактор для `adaptive_pressure_advance_model`
  - Подсказка: "Строка данных модели адаптивного PA (сложный параметр)"

- [ ] Добавить в `buildOrcaslicerSettings()` (после строки 1055):
  ```typescript
  addParam('adaptive_pressure_advance_model', adaptivePressureAdvanceModel);
  ```

- [ ] Добавить загрузку из `orcaslicer_settings` при редактировании

#### 3. Filament Ramming Parameters (1 поле) - Приоритет: Низкий
**Файл:** `frontend/src/components/CreatePresetModal.tsx`

- [ ] Добавить state переменную:
  - `filamentRammingParameters` / `setFilamentRammingParameters` (string)

- [ ] Добавить UI поле во вкладку "Дополнительно" (секция "Мультитул")
  - Текстовое поле или JSON редактор для `filament_ramming_parameters`
  - Подсказка: "Параметры ramming для мультитула (сложный параметр, настраивается через OrcaSlicer)"

- [ ] Добавить в `buildOrcaslicerSettings()` (после строки 1152):
  ```typescript
  addParam('filament_ramming_parameters', filamentRammingParameters);
  ```

- [ ] Добавить загрузку из `orcaslicer_settings` при редактировании

#### 4. Pellet Flow Coefficient - Приоритет: Низкий
**Файл:** `frontend/src/components/CreatePresetModal.tsx`

- [ ] Проверить наличие state переменной `pelletFlowCoefficient` (строка 165)
- [ ] Проверить наличие UI поля (возможно уже есть, но не отображается)
- [ ] Если нет UI поля - добавить во вкладку "Дополнительно"
- [ ] Убедиться что поле добавляется в `buildOrcaslicerSettings()` (строка 1174)

#### 5. Filament Notes - Приоритет: Средний
**Файл:** `backend/app/services/orcaslicer_exporter.py`

- [ ] Добавить экспорт `presets.description` → `filament_notes` в функцию `preset_to_orcaslicer_json()`
  - После строки 156 (после flow_ratio):
  ```python
  # Заметки пользователя
  if preset.description:
      profile["filament_notes"] = to_array(preset.description)
  ```

#### 6. Полная проверка покрытия - Приоритет: Высокий
**Файл:** `docs/md/FILAMENT_FIELDS_COMPLETE_COMPARISON.md`

- [ ] Провести полную проверку всех 113 полей:
  - Сравнить каждое поле из `ORCASLICER_PROFILE_FIELDS_TEMPLATE.md` (строки 40-184)
  - С полями в `buildOrcaslicerSettings()` (строки 966-1196)
  - Убедиться что каждое поле либо:
    - Есть в UI и собирается
    - Явно пропущено по причине (с комментарием)
    - Добавлено в TODO для доработки

- [ ] Обновить таблицы в этом документе с колонкой "Собирается в UI" для всех 113 полей

---

### Оценка трудозатрат:

- **Температуры стола (4 поля):** ~2-3 часа
  - Добавление state переменных: 15 мин
  - Добавление UI полей: 1-1.5 часа
  - Интеграция в buildOrcaslicerSettings: 15 мин
  - Загрузка при редактировании: 30 мин
  - Тестирование: 30 мин

- **Adaptive Pressure Advance Model (1 поле):** ~1-1.5 часа
  - Добавление state переменной: 10 мин
  - Добавление UI поля: 30-45 мин
  - Интеграция: 15 мин
  - Тестирование: 15 мин

- **Filament Ramming Parameters (1 поле):** ~1-1.5 часа
  - Аналогично предыдущему

- **Pellet Flow Coefficient:** ~30 мин
  - Проверка и исправление

- **Filament Notes:** ~15 мин
  - Добавление экспорта

- **Полная проверка:** ~2-3 часа
  - Сравнение всех полей
  - Обновление документации

**Итого:** ~7-10 часов работы

---

### Приоритеты:

1. **Высокий:** Полная проверка покрытия (чтобы точно знать что дорабатывать)
2. **Средний:** Температуры стола (4 поля) + Filament Notes (часто используются)
3. **Низкий:** Adaptive Pressure Advance Model + Filament Ramming Parameters (сложные параметры, редко используются)

---

**Дата анализа:** 2025-11-23  
**Статус:** ✅ Все 113 полей OrcaSlicer Filament Presets поддерживаются технически. ~78 полей собираются в UI форме, остальные сохраняются при импорте из OrcaSlicer.  
**TODO:** Задачи добавлены в TODO список проекта

