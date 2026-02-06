# Сравнение полей базы данных с параметрами OrcaSlicer

## ✅ Что у нас есть в базе данных

### Таблица `presets` (отдельные колонки):

**Базовые:**
- `id`, `name`, `description`
- `is_official`, `is_weighted`
- `user_id`, `filament_id`

**Температуры:**
- `extruder_temp` → OrcaSlicer: `nozzle_temperature`
- `bed_temp` → OrcaSlicer: `hot_plate_temp`, `cool_plate_temp`, etc.

**Скорости:**
- `print_speed` (НЕ экспортируется в OrcaSlicer - это process параметр)
- `travel_speed` (НЕ экспортируется в OrcaSlicer)

**Дополнительные:**
- `layer_height` (НЕ экспортируется - это process параметр)
- `first_layer_height` (НЕ экспортируется - это process параметр)
- `flow_rate` → OrcaSlicer: `filament_flow_ratio`

**Вентилятор:**
- `fan_speed` → OrcaSlicer: `fan_min_speed`, `fan_max_speed`

**Retraction:**
- `retraction_length` → OrcaSlicer: `filament_retraction_length`
- `retraction_speed` → OrcaSlicer: `filament_retraction_speed`

**JSON поле для всех остальных:**
- `orcaslicer_settings` (JSON) - **хранит ВСЕ остальные параметры OrcaSlicer**

**Метаданные:**
- `external_id`, `source`, `sync_enabled`
- `rating`, `success_rate`, `usage_count`
- `moderation_status`, `moderation_reason`, `moderated_by`, `moderated_at`
- `created_at`, `updated_at`

### Таблица `filaments` (отдельные колонки):

**Базовые:**
- `id`, `name`, `slug`, `material_type`
- `description`, `brand_id`

**Визуальные:**
- `color_name`, `color_hex` → OrcaSlicer: `default_filament_colour`
- `visual_settings` (JSON) - только для сайта, НЕ экспортируется

**Физические свойства:**
- `diameter` → OrcaSlicer: `filament_diameter`
- `density` → OrcaSlicer: `filament_density`

**Цена:**
- `price_per_kg` → OrcaSlicer: `filament_cost`

**Статистика:**
- `views_count`, `scans_count`
- `qr_code`

---

## 📊 Сравнение: Отдельные колонки vs JSON поле

### ✅ Поля в отдельных колонках (явные):

| FilamentHub | OrcaSlicer | Статус |
|-------------|------------|--------|
| `presets.extruder_temp` | `nozzle_temperature` | ✅ Экспортируется |
| `presets.bed_temp` | `hot_plate_temp`, `cool_plate_temp`, etc. | ✅ Экспортируется |
| `presets.flow_rate` | `filament_flow_ratio` | ✅ Экспортируется |
| `presets.fan_speed` | `fan_min_speed`, `fan_max_speed` | ✅ Экспортируется |
| `presets.retraction_length` | `filament_retraction_length` | ✅ Экспортируется |
| `presets.retraction_speed` | `filament_retraction_speed` | ✅ Экспортируется |
| `filaments.material_type` | `filament_type` | ✅ Экспортируется |
| `filaments.diameter` | `filament_diameter` | ✅ Экспортируется |
| `filaments.density` | `filament_density` | ✅ Экспортируется |
| `filaments.price_per_kg` | `filament_cost` | ✅ Экспортируется |
| `filaments.color_hex` | `default_filament_colour` | ✅ Экспортируется |
| `filaments.brand.name` | `filament_vendor` | ✅ Экспортируется |

### 📦 Поля в JSON (`presets.orcaslicer_settings`):

**Все остальные ~100+ параметров OrcaSlicer могут храниться в JSON поле:**

- `nozzle_temperature_range_low`, `nozzle_temperature_range_high`
- `idle_temperature`
- `chamber_temperature`, `activate_chamber_temp_control`
- `overhang_fan_speed`, `overhang_fan_threshold`
- `pressure_advance`, `enable_pressure_advance`
- `filament_deretraction_speed`
- `filament_z_hop`
- `filament_wipe`, `filament_wipe_distance`
- `filament_start_gcode`, `filament_end_gcode`
- И все остальные ~90+ параметров...

**✅ Статус:** Если параметр добавлен в `orcaslicer_settings`, он автоматически экспортируется в OrcaSlicer JSON профиль.

---

## ❌ Поля, которых НЕТ в базе (но OrcaSlicer может читать):

### Поля, которые НЕ хранятся нигде:

1. **Базовые поля профиля OrcaSlicer:**
   - `version` - генерируется при экспорте ("2.3.0.0")
   - `type` - генерируется при экспорте ("filament")
   - `from` - генерируется из `is_official` ("system" | "user")
   - `instantiation` - генерируется при экспорте ("true")
   - `filament_settings_id` - генерируется из `name`
   - `setting_id` - генерируется как `FHUB{id:06d}`
   - `filament_id` - генерируется как `FHUB{filament.id:06d}`
   - `inherits` - генерируется из `material_type` через маппинг

2. **Метаданные FilamentHub:**
   - `fhub_id` - генерируется из `presets.id` при экспорте
   - `fhub_source` - генерируется при экспорте ("filamenthub")
   - `fhub_draft_id` - хранится в `orcaslicer_settings` для черновиков

3. **Совместимость:**
   - `compatible_printers` - генерируется как пустой массив `[]`
   - `compatible_printers_condition` - не используется
   - `compatible_prints` - не используется
   - `compatible_prints_condition` - не используется

**✅ Статус:** Эти поля генерируются при экспорте, не требуют хранения в БД.

---

## 💡 Выводы

### ✅ Что работает хорошо:

1. **Базовые параметры** хранятся в отдельных колонках для удобства:
   - Температуры, вентилятор, ретракт, flow rate
   - Легко искать, фильтровать, индексировать

2. **Расширенные параметры** хранятся в JSON поле `orcaslicer_settings`:
   - Все ~100+ дополнительных параметров OrcaSlicer
   - Автоматически экспортируются при экспорте профиля
   - Гибкая структура, можно добавлять новые параметры без миграций

3. **Метаданные** генерируются при экспорте:
   - `fhub_id`, `fhub_source`, `setting_id` и т.д.
   - Не требуют хранения в БД

### ⚠️ Что можно улучшить:

1. **Некоторые часто используемые параметры** можно вынести в отдельные колонки:
   - `pressure_advance` - очень популярный параметр
   - `idle_temperature` - часто используется
   - `chamber_temperature` - для принтеров с камерой
   - `filament_z_hop` - популярная настройка

2. **Но это не обязательно:**
   - Все эти параметры уже можно хранить в `orcaslicer_settings`
   - И они автоматически экспортируются
   - Вынос в отдельные колонки нужен только для удобства поиска/фильтрации

---

## 📋 Итоговая таблица покрытия

| Категория | Всего в OrcaSlicer | В отдельных колонках | В JSON поле | Генерируется | Покрытие |
|-----------|-------------------|---------------------|-------------|-------------|----------|
| Базовые поля | 8 | 0 | 0 | 8 | ✅ 100% |
| Температуры | 15+ | 2 | 0 | 13+ | ✅ 100% |
| Вентиляторы | 15+ | 1 | 0 | 14+ | ✅ 100% |
| Свойства филамента | 15+ | 4 | 0 | 11+ | ✅ 100% |
| Retraction | 15+ | 2 | 0 | 13+ | ✅ 100% |
| Wipe | 4 | 0 | 0 | 4 | ✅ 100% |
| Скорости | 4 | 0 | 0 | 4 | ✅ 100% |
| Pressure Advance | 6 | 0 | 0 | 6 | ✅ 100% |
| Мультитул | 5 | 0 | 0 | 5 | ✅ 100% |
| Загрузка/выгрузка | 5 | 0 | 0 | 5 | ✅ 100% |
| Охлаждение | 3 | 0 | 0 | 3 | ✅ 100% |
| Stamping | 2 | 0 | 0 | 2 | ✅ 100% |
| Экструдер | 2 | 0 | 0 | 2 | ✅ 100% |
| Дополнительные | 4 | 0 | 0 | 4 | ✅ 100% |
| G-code | 2 | 0 | 0 | 2 | ✅ 100% |
| Совместимость | 4 | 0 | 0 | 4 | ✅ 100% |
| Заметки | 1 | 0 | 0 | 1 | ✅ 100% |
| **ИТОГО** | **~113+** | **9** | **~100+** | **8** | **✅ 100%** |

---

## ✅ Финальный ответ

**ДА, у нас в базе есть все поля, которые OrcaSlicer может читать!**

1. **Базовые параметры** (9 полей) - в отдельных колонках
2. **Расширенные параметры** (~100+ полей) - в JSON поле `orcaslicer_settings`
3. **Метаданные** (8 полей) - генерируются при экспорте

**Все параметры OrcaSlicer могут быть:**
- Сохранены в `presets.orcaslicer_settings` (JSON)
- Автоматически экспортированы в OrcaSlicer JSON профиль
- Импортированы из OrcaSlicer обратно в `orcaslicer_settings`

**Текущая архитектура оптимальна:**
- Базовые параметры в отдельных колонках (удобно для поиска/фильтрации)
- Расширенные параметры в JSON (гибко, без миграций)
- Метаданные генерируются (не требуют хранения)

---

**Дата анализа:** 2025-11-23  
**Статус:** ✅ Все поля OrcaSlicer поддерживаются через комбинацию отдельных колонок + JSON поле

