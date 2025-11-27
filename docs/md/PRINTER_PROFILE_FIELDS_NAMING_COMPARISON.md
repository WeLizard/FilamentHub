# Сравнение названий полей: OrcaSlicer vs FilamentHub

## Проблема: Несоответствие названий полей

### ❌ Поля с разными названиями

| OrcaSlicer поле | FilamentHub поле (модель) | FilamentHub поле (экспорт) | Статус |
|-----------------|---------------------------|----------------------------|--------|
| `machine_start_gcode` | `start_gcode` | `machine_start_gcode` ✅ | ⚠️ **Несоответствие** - в модели другое название |
| `machine_end_gcode` | `end_gcode` | `machine_end_gcode` ✅ | ⚠️ **Несоответствие** - в модели другое название |
| `nozzle_diameter` | `nozzle_diameters` | `nozzle_diameter` ✅ | ⚠️ **Несоответствие** - в модели множественное число |
| `printable_height` | `printable_height_mm` | `printable_height` ✅ | ⚠️ **Несоответствие** - в модели суффикс `_mm` |
| `printer_notes` | `notes` | `printer_notes` ❌ | ⚠️ **Несоответствие** - в экспорте не используется |
| `default_print_profile` | `default_print_profile_slug` | `default_print_profile` ✅ | ⚠️ **Несоответствие** - в модели `_slug` |

### ✅ Поля с одинаковыми названиями

| OrcaSlicer поле | FilamentHub поле (модель) | Статус |
|-----------------|---------------------------|--------|
| `printable_area` | `printable_area` | ✅ **Совпадает** |
| `printer_model` | (в `extra_metadata` или из `printer.name`) | ✅ **Совпадает** (через экспортер) |
| `setting_id` | `setting_id` | ✅ **Совпадает** |
| `name` | `name` | ✅ **Совпадает** |
| `from` | `source` | ⚠️ **Несоответствие** - в модели `source`, в экспорте `from` |

---

## Детальный анализ

### 1. G-code поля

**OrcaSlicer:**
- `machine_start_gcode`
- `machine_end_gcode`

**FilamentHub модель:**
- `start_gcode` (строка 49)
- `end_gcode` (строка 50)

**Экспортер:**
```python
# backend/app/services/orcaslicer_machine_exporter.py, строки 273-276
if profile.start_gcode:
    settings["machine_start_gcode"] = profile.start_gcode  # ✅ Правильно маппится
if profile.end_gcode:
    settings["machine_end_gcode"] = profile.end_gcode  # ✅ Правильно маппится
```

**Вывод:** ✅ В экспорте правильно, но в модели названия другие.

---

### 2. Nozzle diameter

**OrcaSlicer:**
- `nozzle_diameter` (массив строк: `["0.4"]` или `["0.4", "0.6"]`)

**FilamentHub модель:**
- `nozzle_diameters` (массив float: `[0.4]` или `[0.4, 0.6]`)

**Экспортер:**
```python
# backend/app/services/orcaslicer_machine_exporter.py, строки 235-239
if profile.nozzle_diameters:
    settings["nozzle_diameter"] = [str(v) for v in profile.nozzle_diameters]  # ✅ Правильно маппится
```

**Вывод:** ✅ В экспорте правильно, но в модели множественное число.

---

### 3. Printable height

**OrcaSlicer:**
- `printable_height` (строка: `"250"`)

**FilamentHub модель:**
- `printable_height_mm` (float: `250.0`)

**Экспортер:**
```python
# backend/app/services/orcaslicer_machine_exporter.py, строка 263-264
if profile.printable_height_mm:
    settings["printable_height"] = str(profile.printable_height_mm)  # ✅ Правильно маппится
```

**Вывод:** ✅ В экспорте правильно, но в модели суффикс `_mm`.

---

### 4. Printer notes

**OrcaSlicer:**
- `printer_notes`

**FilamentHub модель:**
- `notes`

**Экспортер:**
```python
# ❌ НЕ используется в экспорте!
# В orcaslicer_settings должно быть поле printer_notes, но мы его не экспортируем
```

**Вывод:** ❌ **ПРОБЛЕМА** - поле `notes` не экспортируется в `printer_notes`.

---

### 5. Default print profile

**OrcaSlicer:**
- `default_print_profile` (имя профиля: `"0.20mm Standard @Voron"`)

**FilamentHub модель:**
- `default_print_profile_slug` (slug: `"0-20mm-standard-voron"`)

**Экспортер:**
```python
# backend/app/services/orcaslicer_machine_exporter.py, строки 278-300
# Преобразует slug в name через поиск в БД
if default_print_profile_name:
    settings["default_print_profile"] = default_print_profile_name  # ✅ Правильно маппится
```

**Вывод:** ✅ В экспорте правильно преобразуется slug → name.

---

### 6. Source field

**OrcaSlicer:**
- `from` (значения: `"system"`, `"user"`)

**FilamentHub модель:**
- `source` (значения: `"system"`, `"user"`)

**Экспортер:**
```python
# backend/app/services/orcaslicer_machine_exporter.py, строка 224
settings["from"] = "system" if profile.is_official else profile.source or "user"  # ✅ Правильно маппится
```

**Вывод:** ✅ В экспорте правильно маппится `source` → `from`.

---

## Поля, которые хранятся только в `orcaslicer_settings`

Все остальные поля из OrcaSlicer (например, `printer_technology`, `gcode_flavor`, `machine_max_speed_x`, etc.) хранятся в `orcaslicer_settings` JSON с **оригинальными названиями** из OrcaSlicer.

**Вывод:** ✅ Эти поля имеют правильные названия, так как хранятся как есть в JSON.

---

## Проблемы и рекомендации

### ❌ Проблема 1: `notes` не экспортируется в `printer_notes`

**Текущее состояние:**
- В модели: `notes`
- В экспорте: ❌ не используется

**Исправление:**
```python
# backend/app/services/orcaslicer_machine_exporter.py
# Добавить после строки 276:
if profile.notes:
    settings["printer_notes"] = profile.notes
```

---

### ⚠️ Проблема 2: Несоответствие названий в модели

**Текущее состояние:**
- Модель использует упрощенные названия (`start_gcode` вместо `machine_start_gcode`)
- Экспортер правильно маппит их в OrcaSlicer формат

**Рекомендация:**
- ✅ **Оставить как есть** - это нормально, так как:
  1. В модели удобнее использовать короткие названия
  2. Экспортер правильно преобразует их в OrcaSlicer формат
  3. Все поля из OrcaSlicer хранятся в `orcaslicer_settings` с оригинальными названиями

---

## Итоговая таблица соответствия

| Категория | OrcaSlicer | FilamentHub модель | Экспортер | Статус |
|-----------|------------|-------------------|-----------|--------|
| **G-code** | `machine_start_gcode` | `start_gcode` | ✅ `machine_start_gcode` | ✅ OK |
| **G-code** | `machine_end_gcode` | `end_gcode` | ✅ `machine_end_gcode` | ✅ OK |
| **Nozzle** | `nozzle_diameter` | `nozzle_diameters` | ✅ `nozzle_diameter` | ✅ OK |
| **Area** | `printable_area` | `printable_area` | ✅ `printable_area` | ✅ OK |
| **Height** | `printable_height` | `printable_height_mm` | ✅ `printable_height` | ✅ OK |
| **Notes** | `printer_notes` | `notes` | ❌ **НЕ используется** | ❌ **ПРОБЛЕМА** |
| **Default** | `default_print_profile` | `default_print_profile_slug` | ✅ `default_print_profile` | ✅ OK |
| **Source** | `from` | `source` | ✅ `from` | ✅ OK |
| **Остальные** | Все остальные поля | `orcaslicer_settings` | ✅ Оригинальные названия | ✅ OK |

---

## Вывод

### ✅ Что работает правильно:
1. ✅ Все поля правильно маппятся в экспорте
2. ✅ Все поля из OrcaSlicer хранятся в `orcaslicer_settings` с оригинальными названиями
3. ✅ Упрощенные названия в модели удобны для использования
4. ✅ При экспорте используется правильный приоритет: `orcaslicer_settings` > отдельные колонки
5. ✅ При импорте извлекаются поля из `orcaslicer_settings` в отдельные колонки

### ✅ Исправлено:
1. ✅ **Добавлен экспорт `notes` → `printer_notes`** в экспортер
2. ✅ **Исправлен приоритет полей** - теперь `orcaslicer_settings` имеет приоритет над отдельными колонками
3. ✅ **Добавлено извлечение `printer_notes`** из `orcaslicer_settings` в `notes` при импорте

### 📝 Итоговое состояние:
- ✅ Все поля правильно маппятся между OrcaSlicer и FilamentHub
- ✅ Приоритет полей правильный: `orcaslicer_settings` > отдельные колонки
- ✅ Импорт и экспорт работают корректно

