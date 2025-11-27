# Анализ структуры профилей и связей в OrcaSlicer

## 📋 Типы профилей в OrcaSlicer

### 1. Machine Model (`type = "machine_model"`)
**Назначение:** Базовая информация о модели принтера (без параметров сопла)

**Ключевые поля:**
- `model_id` — системный идентификатор Orca (например, `Anycubic-Kobra-2`)
- `name` — название модели
- `nozzle_diameter` — дефолтный диаметр сопла
- `default_materials` — список материалов через `;` (например, `"PLA;PETG;TPU"`)

**Соответствие FilamentHub:** `Printer` (модель принтера)

**Slug:** ✅ **НУЖЕН** — используется для URL и идентификации

---

### 2. Machine Preset (`type = "machine"`)
**Назначение:** Конкретный профиль принтера + сопло (например, "Ender 3 Pro 0.4mm")

**Ключевые поля:**
- `name` — название профиля (например, "Ender 3 Pro 0.4mm")
- `printer_model` — ссылка на `machine_model` (например, `"Ender-3-Pro"`)
- `default_print_profile` — **slug** предустановленного процесса печати
- `nozzle_diameter` — диаметр сопла
- `printable_area`, `printable_height` — размеры области печати

**Соответствие FilamentHub:** `PrinterProfile`

**Slug:** ⚠️ **ИСПОЛЬЗУЕТСЯ В ORCA** — поле `default_print_profile` содержит slug PrintProfile

**Связи:**
- `printer_model` → `Printer.model_id` (через `PrinterProfile.printer_id`)
- `default_print_profile` → `PrintProfile.slug` (через `PrinterProfile.default_print_profile_slug`)

---

### 3. Process Preset (`type = "process"`)
**Назначение:** Настройки печати (слои, скорость, заполнение и т.д.)

**Ключевые поля:**
- `name` — название профиля (например, "0.20mm Standard")
- `compatible_printers` — массив **slug'ов** принтеров или строка с условием
- `compatible_printers_condition` — логическое выражение для совместимости
- `layer_height` — высота слоя
- `print_settings_id` — внутренний ID

**Соответствие FilamentHub:** `PrintProfile`

**Slug:** ⚠️ **ИСПОЛЬЗУЕТСЯ В ORCA** — на него ссылается `PrinterProfile.default_print_profile`

**Связи:**
- `compatible_printers` → массив `Printer.slug` или `PrinterProfile.slug`
- Связь через таблицу `print_profile_printers` (хранит `printer_slug`)

---

### 4. Filament Preset (`type = "filament"`)
**Назначение:** Настройки материала (температуры, охлаждение, ретракция)

**Ключевые поля:**
- `name` — название материала (например, "PLA")
- `compatible_printers` — массив **slug'ов** принтеров или `"*"` (все)
- `compatible_printers_condition` — условие совместимости
- `filament_settings_id` — внутренний ID

**Соответствие FilamentHub:** `Preset` (настройки для `Filament`)

**Slug:** ❓ **НЕ ИСПОЛЬЗУЕТСЯ ПРЯМО** — но `Filament` имеет slug, который используется в связях

**Связи:**
- `compatible_printers` → массив `Printer.slug`
- Связь через `PresetPrinter` (many-to-many)

---

## 🔗 Структура связей в OrcaSlicer

### Иерархия связей:

```
Vendor Bundle (производитель)
  ├── Machine Model (Printer)
  │   └── Machine Preset (PrinterProfile)
  │       └── default_print_profile → Process Preset (PrintProfile)
  │
  ├── Process Preset (PrintProfile)
  │   ├── compatible_printers → [Printer.slug, ...]
  │   └── compatible_filaments → [Filament.slug, ...] (опционально)
  │
  └── Filament Preset (Preset)
      └── compatible_printers → [Printer.slug, ...] или "*"
```

### Ключевые моменты:

1. **Machine Preset → Print Profile:**
   - Связь через `default_print_profile` (slug PrintProfile)
   - Это **обязательная связь** в OrcaSlicer
   - ✅ **Slug PrintProfile НУЖЕН** для этой связи

2. **Print Profile → Printers:**
   - Связь через `compatible_printers` (массив slug'ов)
   - Хранится в `print_profile_printers` (через `printer_slug`)
   - ✅ **Slug Printer НУЖЕН** для этой связи

3. **Print Profile → Filaments:**
   - Связь через `compatible_filaments` (массив slug'ов)
   - Хранится в `print_profile_filaments` (через `filament_slug`)
   - ✅ **Slug Filament НУЖЕН** для этой связи

4. **Filament Preset → Printers:**
   - Связь через `compatible_printers` (массив slug'ов или "*")
   - Хранится в `preset_printers` (через `printer_id`, но можно и через slug)
   - ✅ **Slug Printer НУЖЕН** для этой связи

---

## 📊 Выводы по использованию slug

### ✅ Slug НУЖЕН для:
1. **Printer** — используется в `compatible_printers` и `compatible_filaments`
2. **Filament** — используется в `compatible_filaments` и связях с профилями
3. **PrintProfile** — используется в `PrinterProfile.default_print_profile_slug`
4. **PrinterProfile** — используется для идентификации в синхронизации (можно заменить на `external_id`)

### ⚠️ Slug используется в OrcaSlicer для:
- `PrinterProfile.default_print_profile` → ссылается на `PrintProfile.slug`
- `PrintProfile.compatible_printers` → массив `Printer.slug`
- `PrintProfile.compatible_filaments` → массив `Filament.slug`
- `Preset.compatible_printers` → массив `Printer.slug`

---

## 🎯 Рекомендации

### Оставить slug для:
- ✅ **Printer** — обязательно (используется в связях)
- ✅ **Filament** — обязательно (используется в связях)
- ✅ **PrintProfile** — **обязательно** (используется в `default_print_profile`)
- ⚠️ **PrinterProfile** — можно оставить (используется в синхронизации, но можно заменить на `external_id`)

### Альтернатива для PrinterProfile:
Если убрать slug из `PrinterProfile`, можно использовать:
- `external_id` — ID из OrcaSlicer
- `name + owner_user_id` — комбинация для уникальности
- Но это усложнит синхронизацию и поиск

---

## 📝 Структура бандлов в OrcaSlicer

### Vendor Bundle (JSON файл производителя):
```json
{
  "name": "BambuLab",
  "version": "1.0.0",
  "machine_model_list": [
    { "name": "X1 Carbon", "sub_path": "X1_Carbon.json" }
  ],
  "process_list": [
    { "name": "0.20mm Standard", "sub_path": "0.20mm_Standard.json" }
  ]
}
```

### Machine Preset (PrinterProfile):
```json
{
  "type": "machine",
  "name": "X1 Carbon 0.4mm",
  "printer_model": "BambuLab-X1-Carbon",
  "default_print_profile": "0.20mm Standard @BambuLab",  // ← SLUG PrintProfile
  "nozzle_diameter": "0.4",
  "printable_area": "...",
  ...
}
```

### Process Preset (PrintProfile):
```json
{
  "type": "process",
  "name": "0.20mm Standard",
  "compatible_printers": ["BambuLab-X1-Carbon", "BambuLab-P1P"],  // ← SLUG Printer
  "compatible_filaments": ["PLA", "PETG"],  // ← SLUG Filament (опционально)
  "layer_height": "0.2",
  ...
}
```

### Filament Preset (Preset):
```json
{
  "type": "filament",
  "name": "PLA",
  "compatible_printers": ["*"],  // ← все принтеры или массив SLUG Printer
  "filament_temperature": [215, 220],
  ...
}
```

---

## ✅ Итоговый вывод

**Slug необходим для всех профилей**, так как:
1. OrcaSlicer использует slug'и для связей между профилями
2. `default_print_profile` в PrinterProfile ссылается на slug PrintProfile
3. `compatible_printers` и `compatible_filaments` содержат массивы slug'ов
4. Синхронизация с OrcaSlicer требует сохранения структуры связей

**Рекомендация:** Оставить slug для всех типов профилей, но можно скрыть его в UI (не показывать пользователю, использовать только для внутренней логики).


