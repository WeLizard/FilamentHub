# OrcaSlicer - Все типы филамента

## 📋 Полный список типов материалов (из MaterialType.cpp)

OrcaSlicer поддерживает **92 типа материалов**:

### Базовые материалы:

1. **PLA** - Polylactic Acid (180-240°C)
2. **ABS** - Acrylonitrile Butadiene Styrene (190-300°C)
3. **PETG** - Polyethylene Terephthalate Glycol (190-260°C)
4. **TPU** - Thermoplastic Polyurethane (175-260°C)
5. **ASA** - Acrylonitrile Styrene Acrylate (220-300°C)
6. **PC** - Polycarbonate (240-300°C)
7. **PA** - Polyamide / Nylon (235-280°C)
8. **PVA** - Polyvinyl Alcohol (185-250°C)
9. **HIPS** - High Impact Polystyrene (220-270°C)
10. **PET** - Polyethylene Terephthalate (200-290°C)
11. **PP** - Polypropylene (200-240°C)
12. **POM** - Polyoxymethylene / Delrin (210-250°C)

### Материалы с добавками:

#### Углеродное волокно (CF):
- **ABS-CF** (220-300°C)
- **ASA-CF** (230-300°C)
- **PA-CF** (240-315°C)
- **PC-CF** (270-295°C)
- **PET-CF** (240-320°C)
- **PLA-CF** (190-250°C)
- **PE-CF** (175-260°C)
- **PEI-1010-CF** (380-430°C)
- **PEI-9085-CF** (365-390°C)
- **PEEK-CF** (380-410°C)
- **PEKK-CF** (360-400°C)
- **PP-CF** (210-250°C)
- **PA6-CF** (230-300°C)
- **PA11-CF** (275-295°C)
- **PA12-CF** (250-300°C)
- **PAHT-CF** (270-310°C)

#### Стекловолокно (GF):
- **ABS-GF** (240-280°C)
- **ASA-GF** (240-300°C)
- **PA-GF** (240-290°C)
- **PC-PBT** (260-300°C)
- **PET-GF** (280-320°C)
- **PETG-GF** (210-270°C)
- **PE-GF** (230-270°C)
- **PP-GF** (220-260°C)
- **PEI-1010-GF** (380-430°C)
- **PEI-9085-GF** (370-390°C)
- **PEEK-GF** (375-410°C)
- **PA6-GF** (260-300°C)
- **PA11-GF** (275-295°C)
- **PA12-GF** (255-270°C)
- **PAHT-GF** (270-310°C)
- **PPA-GF** (260-290°C)

### Специальные материалы:

#### Полиамиды (PA вариации):
- **PA6** (260-300°C)
- **PA11** (275-295°C)
- **PA12** (250-270°C)
- **PAHT** - High Temperature (260-310°C)

#### Полиэфиримиды (PEI):
- **PEI-1010** (370-430°C)
- **PEI-9085** (350-390°C)

#### Высокотемпературные материалы:
- **PEEK** - Polyether Ether Ketone (350-460°C)
- **PEKK** - Polyether Ketone Ketone (325-400°C)
- **PES** - Polyethersulfone (340-390°C)
- **PPS** - Polyphenylene Sulfide (300-345°C)
- **PPSU** - Polyphenylene Sulfone (360-420°C)
- **PSU** - Polysulfone (350-380°C)
- **TPI** - Thermoplastic Polyimide (420-445°C)
- **PI** - Polyimide (390-410°C)

#### Гибкие материалы:
- **FLEX** (210-230°C)
- **PCL** - Polycaprolactone (130-170°C)

#### Растворимые материалы для поддержек:
- **BVOH** - Butenediol Vinyl Alcohol (190-240°C)
- **PVB** - Polyvinyl Butyral (190-250°C)

#### Специальные материалы:
- **ASA-AERO** (240-280°C)
- **PLA-AERO** (220-270°C)
- **PC-ABS** (230-270°C)
- **PCTG** - Polyethylene Terephthalate Glycol Modified (220-300°C)
- **PHA** - Polyhydroxyalkanoates (190-250°C)
- **PE** - Polyethylene (175-260°C)
- **PVDF** - Polyvinylidene Fluoride (245-265°C)
- **SBS** - Styrene-Butadiene-Styrene (195-250°C)
- **PPA-CF** (260-300°C)
- **PPA-GF** (260-290°C)
- **EVA** - Ethylene-Vinyl Acetate (175-220°C)

---

## 🎯 Системные пресеты (из build/OrcaSlicer/resources/profiles/Blocks/filament)

В OrcaSlicer есть следующие **системные пресеты** (для использования в поле `inherits`):

### Базовые системные пресеты:

1. **Generic PLA @System** (fdm_filament_pla)
   - Базовый пресет для PLA
   - Наследуется от: `fdm_filament_common`

2. **Generic ABS @System** (fdm_filament_abs)
   - Базовый пресет для ABS
   - Наследуется от: `fdm_filament_common`

3. **Generic PETG @System** (fdm_filament_petg)
   - Базовый пресет для PETG
   - Наследуется от: `fdm_filament_common`

4. **Generic TPU @System** (fdm_filament_tpu)
   - Базовый пресет для TPU
   - Наследуется от: `fdm_filament_common`

5. **Generic ASA @System** (fdm_filament_asa)
   - Базовый пресет для ASA
   - Наследуется от: `fdm_filament_common`

6. **Generic PC @System** (fdm_filament_pc)
   - Базовый пресет для PC
   - Наследуется от: `fdm_filament_common`

7. **Generic PA @System** (fdm_filament_pa)
   - Базовый пресет для PA/Nylon
   - Наследуется от: `fdm_filament_common`

8. **Generic PVA @System** (fdm_filament_pva)
   - Базовый пресет для PVA (растворимые поддержки)
   - Наследуется от: `fdm_filament_common`

9. **fdm_filament_common**
   - Базовый универсальный пресет (используется как fallback)

### Blocks пресеты (специализированные):

1. **Blocks Generic PLA @System**
   - Специализированный PLA пресет для принтеров Bambu Lab
   - Наследуется от: `fdm_filament_pla`

2. **Blocks Generic PLA-CF @System**
   - PLA с углеродным волокном для Bambu Lab
   - Наследуется от: `fdm_filament_pla`

3. **Blocks Generic ABS @System**
   - Специализированный ABS пресет для Bambu Lab
   - Наследуется от: `fdm_filament_abs`

4. **Blocks Generic ASA @System**
   - Специализированный ASA пресет для Bambu Lab
   - Наследуется от: `fdm_filament_asa`

5. **Blocks Generic ASA-CF @System**
   - ASA с углеродным волокном для Bambu Lab
   - Наследуется от: `fdm_filament_asa`

6. **Blocks Generic PA @System**
   - Специализированный PA пресет для Bambu Lab
   - Наследуется от: `fdm_filament_pa`

7. **Blocks Generic PA-CF @System**
   - PA с углеродным волокном для Bambu Lab
   - Наследуется от: `fdm_filament_pa`

8. **Blocks Generic PC @System**
   - Специализированный PC пресет для Bambu Lab
   - Наследуется от: `fdm_filament_pc`

9. **Blocks Generic PETG @System**
   - Специализированный PETG пресет для Bambu Lab
   - Наследуется от: `fdm_filament_petg`

10. **Blocks Generic PVA @System**
    - Специализированный PVA пресет для Bambu Lab
    - Наследуется от: `fdm_filament_pva`

11. **Blocks Generic TPU @System**
    - Специализированный TPU пресет для Bambu Lab
    - Наследуется от: `fdm_filament_tpu`

---

## 🔄 Маппинг Material Type → System Preset (для FilamentHub)

Текущий маппинг в `orcaslicer_exporter.py`:

```python
material_type_base_map = {
    "PLA": "Generic PLA @System",
    "ABS": "Generic ABS @System",
    "PETG": "Generic PETG @System",
    "PET": "Generic PETG @System",  # PET наследуется от PETG
    "TPU": "Generic TPU @System",
    "ASA": "Generic ASA @System",
    "PC": "Generic PC @System",
    "PA": "Generic PA @System",
    "PA-CF": "Generic PA @System",  # Используем базовый PA
    "PVA": "Generic PVA @System",
    "HIPS": "Generic ABS @System",  # HIPS наследуется от ABS
    # Альтернативные названия
    "PLA+": "Generic PLA @System",
    "PLA PRO": "Generic PLA @System",
    "PLA PRO+": "Generic PLA @System",
}
```

### Рекомендации для расширения маппинга:

Для материалов, которых нет в системных пресетах, используем ближайший по свойствам:

- **PET-CF**, **PETG-CF** → `"Generic PETG @System"`
- **PLA-CF** → `"Generic PLA @System"`
- **ABS-CF**, **ABS-GF** → `"Generic ABS @System"`
- **ASA-CF**, **ASA-GF** → `"Generic ASA @System"`
- **PC-CF**, **PC-ABS** → `"Generic PC @System"`
- **PA-CF**, **PA-GF**, **PA6**, **PA11**, **PA12** → `"Generic PA @System"`
- **PEI**, **PEEK**, **PEKK**, **PES**, **PPS**, **PPSU**, **PSU** → `"Generic PC @System"` (высокотемпературные)
- **FLEX**, **TPI** → `"Generic TPU @System"` (гибкие)
- **BVOH**, **PVB** → `"Generic PVA @System"` (растворимые)
- **PP**, **POM** → `"Generic PLA @System"` (по умолчанию)
- Все остальные → `"Generic PLA @System"` (fallback)

---

## 📝 Примечания

1. **Формат имен**: Системные пресеты в OrcaSlicer называются в формате `"Generic {Material} @System"`, но внутренние файлы используют формат `fdm_filament_{material}`.

2. **Автопреобразование**: OrcaSlicer умеет автоматически преобразовывать `fdm_filament_pla` → `Generic PLA @System` через `find_preset2()`.

3. **Наследование**: Все системные пресеты наследуются от `fdm_filament_common`, который является базовым универсальным пресетом.

4. **Blocks пресеты**: Префикс "Blocks" указывает на специализированные пресеты для принтеров Bambu Lab (Blocks = Bambu Lab).

5. **Расширение**: Если нужно добавить новый материал, который не существует в системных пресетах, используем ближайший по свойствам базовый пресет.

---

**Обновлено**: 2025-11-03
**Источники**: 
- `docs/OrcaSlicer/src/libslic3r/MaterialType.cpp` (92 типа материалов)
- `docs/OrcaSlicer/build/OrcaSlicer/resources/profiles/Blocks/filament/*.json` (системные пресеты)
- `docs/OrcaSlicer/src/libslic3r/Preset.cpp` (логика преобразования имен)

