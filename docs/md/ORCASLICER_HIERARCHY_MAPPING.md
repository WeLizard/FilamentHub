# Иерархия профилей OrcaSlicer и сопоставление с FilamentHub

## 🎯 Цель документа

Проанализировать иерархическую структуру профилей в OrcaSlicer и обеспечить корректное сопоставление с моделью данных FilamentHub для валидной синхронизации (импорт/экспорт).

---

## 📋 Структура профилей в OrcaSlicer

### 1. Machine Model (`type = "machine_model"`)
**Назначение:** Базовая информация о модели принтера (без параметров сопла)

**Расположение в bundle:**
```json
{
  "machine_model_list": [
    {
      "name": "Orca Arena X1 Carbon",
      "sub_path": "machine/Orca Arena X1 Carbon.json"
    }
  ]
}
```

**Ключевые поля:**
- `model_id` — системный идентификатор Orca (например, `"Orca-Arena-X1-Carbon"`)
- `name` — название модели (например, `"Orca Arena X1 Carbon"`)
- `nozzle_diameter` — дефолтный диаметр сопла
- `default_materials` — список материалов через `;` (например, `"PLA;PETG;TPU"`)
- `build_volume_x/y/z` — размеры области печати
- `max_temperature_nozzle/bed` — максимальные температуры

**Соответствие FilamentHub:** `Printer` (модель принтера)
- `Printer.model_id` → `model_id`
- `Printer.name` → `name`
- `Printer.slug` → нормализованный `model_id`

**Slug:** ✅ **ОБЯЗАТЕЛЕН** — используется в связях с профилями печати

---

### 2. Machine Preset (`type = "machine"`)
**Назначение:** Конкретный профиль принтера с соплом (например, "Orca Arena X1 Carbon 0.4mm")

**Расположение в bundle:**
```json
{
  "machine_list": [
    {
      "name": "Orca Arena X1 Carbon 0.4 nozzle",
      "sub_path": "machine/Orca Arena X1 Carbon 0.4 nozzle.json"
    }
  ]
}
```

**Пример JSON:**
```json
{
  "type": "machine",
  "name": "Orca Arena X1 Carbon 0.4 nozzle",
  "inherits": "fdm_bbl_3dp_001_common",
  "from": "system",
  "setting_id": "GM001",
  "printer_model": "Orca Arena X1 Carbon",  // ← ссылка на Machine Model
  "default_print_profile": "0.20mm Standard @Arena X1C",  // ← SLUG PrintProfile
  "nozzle_diameter": ["0.4"],
  "printable_area": ["0x0", "256x0", "256x256", "0x256"],
  "printable_height": "256"
}
```

**Ключевые поля:**
- `name` — название профиля (например, "Orca Arena X1 Carbon 0.4 nozzle")
- `printer_model` — **ссылка на Machine Model** (строка, название модели)
- `default_print_profile` — **slug Process Preset** (например, `"0.20mm Standard @Arena X1C"`)
- `nozzle_diameter` — массив диаметров сопел `["0.4"]`
- `printable_area` / `printable_height` — размеры области печати
- `machine_start_gcode` / `machine_end_gcode` — G-code вставки

**Соответствие FilamentHub:** `PrinterProfile` (профиль принтера)
- `PrinterProfile.name` → `name`
- `PrinterProfile.slug` → нормализованный `name`
- `PrinterProfile.printer_id` → FK на `Printer` (сопоставление по `printer_model`)
- `PrinterProfile.default_print_profile_slug` → `default_print_profile`
- `PrinterProfile.nozzle_diameters` → массив `nozzle_diameter`
- `PrinterProfile.printable_area` → `printable_area`
- `PrinterProfile.printable_height_mm` → `printable_height`
- `PrinterProfile.start_gcode` / `end_gcode` → `machine_start_gcode` / `machine_end_gcode`

**Связи:**
- `printer_model` → `Printer.model_id` или `Printer.name` (FK через `PrinterProfile.printer_id`)
- `default_print_profile` → `PrintProfile.slug` (через `PrinterProfile.default_print_profile_slug`)

**Slug:** ⚠️ **ИСПОЛЬЗУЕТСЯ В ORCA** — `default_print_profile` содержит slug PrintProfile

---

### 3. Process Preset (`type = "process"`)
**Назначение:** Настройки печати (слои, скорость, заполнение и т.д.)

**Расположение в bundle:**
```json
{
  "process_list": [
    {
      "name": "0.20mm Standard @Arena X1C",
      "sub_path": "process/0.20mm Standard @Arena X1C.json"
    }
  ]
}
```

**Пример JSON:**
```json
{
  "type": "process",
  "name": "0.20mm Standard @Arena X1C",
  "from": "system",
  "setting_id": "PP001",
  "compatible_printers": ["Orca Arena X1 Carbon", "Orca Arena P1P"],  // ← массив SLUG Printer
  "compatible_filaments": ["PLA", "PETG"],  // ← массив SLUG Filament (опционально)
  "layer_height": "0.2",
  "print_settings_id": "0.20mm Standard @Arena X1C",
  "quality_tier": "standard"
}
```

**Ключевые поля:**
- `name` — название профиля (например, "0.20mm Standard @Arena X1C")
- `compatible_printers` — **массив slug'ов Printer** (например, `["Orca Arena X1 Carbon"]`)
- `compatible_printers_condition` — логическое выражение для совместимости (опционально)
- `compatible_filaments` — массив slug'ов Filament (опционально)
- `layer_height` — высота слоя
- `print_settings_id` — внутренний ID

**Соответствие FilamentHub:** `PrintProfile` (профиль печати)
- `PrintProfile.name` → `name`
- `PrintProfile.slug` → нормализованный `name`
- `PrintProfile.compatible_printers` → JSON-массив `compatible_printers`
- `PrintProfile.compatible_filaments` → JSON-массив `compatible_filaments`
- `PrintProfile.layer_height_mm` → `layer_height`
- `PrintProfile.quality_tier` → `quality_tier`

**Связи:**
- `compatible_printers` → массив `Printer.slug` (хранится в `print_profile_printers` через `printer_slug`)
- `compatible_filaments` → массив `Filament.slug` (хранится в `print_profile_filaments` через `filament_slug`)

**Slug:** ⚠️ **ИСПОЛЬЗУЕТСЯ В ORCA** — на него ссылается `PrinterProfile.default_print_profile`

---

### 4. Filament Preset (`type = "filament"`)
**Назначение:** Настройки материала (температуры, охлаждение, ретракция)

**Расположение в bundle:**
```json
{
  "filament_list": [
    {
      "name": "Arena PLA Basic @Arena X1C",
      "sub_path": "filament/Arena PLA Basic @Arena X1C.json"
    }
  ]
}
```

**Ключевые поля:**
- `name` — название материала (например, "Arena PLA Basic @Arena X1C")
- `compatible_printers` — массив **slug'ов Printer** или `"*"` (все)
- `compatible_printers_condition` — условие совместимости
- `filament_settings_id` — внутренний ID

**Соответствие FilamentHub:** `Preset` (настройки для `Filament`)

**Связи:**
- `compatible_printers` → массив `Printer.slug` (хранится в `preset_printers`)

**Slug:** ❓ **НЕ ИСПОЛЬЗУЕТСЯ ПРЯМО** — но `Filament` имеет slug, который используется в связях

---

## 🔗 Иерархия связей в OrcaSlicer

### Визуализация иерархии:
```
Vendor Bundle (производитель)
  │
  ├── Machine Model (Printer)
  │   └── Machine Preset (PrinterProfile)
  │       ├── printer_model → ссылка на Machine Model
  │       └── default_print_profile → SLUG Process Preset (PrintProfile)
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
   - ✅ **Slug PrintProfile ОБЯЗАТЕЛЕН** для этой связи

2. **Print Profile → Printers:**
   - Связь через `compatible_printers` (массив slug'ов)
   - Хранится в `print_profile_printers` (через `printer_slug`)
   - ✅ **Slug Printer ОБЯЗАТЕЛЕН** для этой связи

3. **Print Profile → Filaments:**
   - Связь через `compatible_filaments` (массив slug'ов)
   - Хранится в `print_profile_filaments` (через `filament_slug`)
   - ✅ **Slug Filament ОБЯЗАТЕЛЕН** для этой связи

4. **Machine Preset → Machine Model:**
   - Связь через `printer_model` (строка, название модели)
   - В FilamentHub: FK через `PrinterProfile.printer_id` → `Printer.id`
   - Сопоставление происходит по `Printer.model_id` или `Printer.name`

---

## 📊 Сопоставление иерархии FilamentHub с OrcaSlicer

### В FilamentHub:
```
Printer (модель принтера)
  └── PrinterProfile (профиль принтера с соплом)
      ├── printer_id → FK на Printer
      ├── default_print_profile_slug → ссылка на PrintProfile.slug
      └── nozzle_diameters → [0.4, 0.6, 0.8]
          │
          └── PrintProfile (профиль печати)
              ├── compatible_printers → массив Printer.slug
              └── compatible_filaments → массив Filament.slug (опционально)
```

### При экспорте в OrcaSlicer:
```
Machine Model (из Printer)
  └── Machine Preset (из PrinterProfile)
      ├── printer_model → Printer.model_id или Printer.name
      └── default_print_profile → PrintProfile.slug
          │
          └── Process Preset (из PrintProfile)
              ├── compatible_printers → [Printer.slug, ...]
              └── compatible_filaments → [Filament.slug, ...]
```

---

## ✅ Рекомендации по реализации в FilamentHub

### 1. Группировка профилей по принтерам
**Текущая реализация:** ✅ Реализовано в `ProfilePage.tsx`
- Группируем `PrinterProfile` по `Printer` (через `printer_id` или `printer_slug`)
- Показываем иерархию: `Printer` → `PrinterProfile[]` → `PrintProfile[]`

**Логика группировки:**
```typescript
const printersWithProfiles = useMemo(() => {
  const printerMap = new Map<string | number, {
    id: number | null;
    slug: string | null;
    name: string | null;
    profiles: PrinterProfile[];
  }>();

  myPrinterProfiles.forEach((profile) => {
    const printerKey = profile.printer_id ?? profile.printer_slug ?? `unknown_${profile.id}`;
    // ...
  });
}, [myPrinterProfiles]);
```

### 2. Связи между профилями
**При импорте из OrcaSlicer:**
1. `Machine Model` → создаём/обновляем `Printer` (по `model_id` или `name`)
2. `Machine Preset` → создаём/обновляем `PrinterProfile`:
   - Связываем с `Printer` через `printer_model`
   - Сохраняем `default_print_profile` в `default_print_profile_slug`
3. `Process Preset` → создаём/обновляем `PrintProfile`:
   - Сохраняем `compatible_printers` (массив slug'ов) в `compatible_printers`
   - Создаём связи в `print_profile_printers` (через `printer_slug`)

**При экспорте в OrcaSlicer:**
1. Для каждого `PrinterProfile`:
   - Создаём `Machine Preset` JSON
   - `printer_model` → `Printer.model_id` или `Printer.name`
   - `default_print_profile` → `PrintProfile.slug` (из `default_print_profile_slug`)
2. Для каждого `PrintProfile`:
   - Создаём `Process Preset` JSON
   - `compatible_printers` → массив `Printer.slug` (из `print_profile_printers`)

### 3. Обеспечение валидности
**Обязательные поля для экспорта:**
- `Printer.slug` — для `compatible_printers` в PrintProfile
- `PrintProfile.slug` — для `default_print_profile` в PrinterProfile
- `Filament.slug` — для `compatible_filaments` в PrintProfile (если используется)

**Валидация при импорте:**
- Проверять, что `printer_model` существует в базе `Printer`
- Проверять, что `default_print_profile` существует в базе `PrintProfile`
- Проверять, что все `compatible_printers` существуют в базе `Printer`

---

## 📝 Примеры синхронизации

### Пример 1: Импорт Machine Preset
```json
{
  "type": "machine",
  "name": "Orca Arena X1 Carbon 0.4 nozzle",
  "printer_model": "Orca Arena X1 Carbon",
  "default_print_profile": "0.20mm Standard @Arena X1C"
}
```

**Действия в FilamentHub:**
1. Найти `Printer` по `printer_model` → "Orca Arena X1 Carbon"
2. Найти `PrintProfile` по `default_print_profile` → "0.20mm Standard @Arena X1C"
3. Создать/обновить `PrinterProfile`:
   - `printer_id` = ID найденного Printer
   - `default_print_profile_slug` = "0.20mm Standard @Arena X1C"

### Пример 2: Экспорт PrinterProfile
**Данные в FilamentHub:**
- `PrinterProfile.name` = "Voron 2.4 350 0.4"
- `PrinterProfile.printer.slug` = "voron-2.4-350"
- `PrinterProfile.default_print_profile_slug` = "0.20mm-standard-voron-2.4"

**Результирующий JSON для OrcaSlicer:**
```json
{
  "type": "machine",
  "name": "Voron 2.4 350 0.4",
  "printer_model": "Voron 2.4 350",
  "default_print_profile": "0.20mm-standard-voron-2.4"
}
```

---

## 🎯 Итоговый вывод

**Иерархия в OrcaSlicer:**
- `Machine Model` (Printer) → `Machine Preset` (PrinterProfile) → `default_print_profile` (PrintProfile slug)
- `Process Preset` (PrintProfile) имеет `compatible_printers` (массив Printer slug)

**Иерархия в FilamentHub (UI):**
- `Printer` → `PrinterProfile[]` → `PrintProfile[]` (вложенная структура)

**Критически важно:**
1. ✅ **Slug обязателен** для `Printer`, `PrintProfile`, `Filament`
2. ✅ **Группировка по принтерам** обеспечивает логичную иерархию
3. ✅ **Связи через slug** обеспечивают валидность экспорта в OrcaSlicer

---

**Документ создан:** 2025-01-XX  
**Последнее обновление:** 2025-01-XX


