# Схема сопоставления профилей в FilamentHub

## 🎯 Цель

Создать систему взаимосвязей между профилями, которая:
1. Соответствует структуре OrcaSlicer
2. Позволяет автоматически выводить совместимость
3. Использует существующие данные в БД
4. Масштабируется на большие объемы

---

## 📊 Текущее состояние в БД

### Существующие связи:

1. **PrinterProfile → PrintProfile:**
   - Поле: `PrinterProfile.default_print_profile_slug`
   - Статус: ✅ **Есть данные** (817 профилей, многие имеют default_print_profile_slug)

2. **PrintProfile → Printers:**
   - Поле: `PrintProfile.compatible_printers` (JSON массив)
   - Таблица: `print_profile_printers` (1539 записей!)
   - Статус: ✅ **Есть данные** (много связей)

3. **PrintProfile → Filaments:**
   - Поле: `PrintProfile.compatible_filaments` (JSON массив, пока NULL)
   - Таблица: `print_profile_filaments` (0 записей)
   - Статус: ⚠️ **Нет данных**

4. **Preset → Printers:**
   - Таблица: `preset_printers` (2 записи)
   - Статус: ⚠️ **Мало данных**

5. **Preset → Filament:**
   - Прямая связь: `Preset.filament_id` (один к одному)
   - Статус: ✅ **Есть данные**

---

## 🔗 Предлагаемая схема связей

### 1. Прямые связи (уже есть в БД)

```
PrinterProfile
  ├── printer_id → Printer (FK)
  └── default_print_profile_slug → PrintProfile.slug

PrintProfile
  ├── print_profile_printers → Printer (через printer_slug)
  └── print_profile_filaments → Filament (через filament_slug)

Preset
  ├── filament_id → Filament (FK)
  └── preset_printers → Printer (через printer_id)
```

### 2. Выведенные связи (автоматический вывод)

#### A. Filament → Printer (через Preset)

**Логика:**
```
Если Preset.filament_id = X И Preset.printer_links содержит Printer Y
  → Filament X совместим с Printer Y
```

**Реализация:**
- Использовать таблицу `preset_printers`
- Создать view или функцию для вывода совместимости

**Пример SQL:**
```sql
SELECT DISTINCT 
  f.id as filament_id,
  f.slug as filament_slug,
  p.id as printer_id,
  p.slug as printer_slug,
  'via_preset' as relation_source
FROM filaments f
JOIN presets pr ON pr.filament_id = f.id
JOIN preset_printers pp ON pp.preset_id = pr.id
JOIN printers p ON p.id = pp.printer_id
WHERE pr.active = true;
```

#### B. Filament → Printer (через PrintProfile)

**Логика:**
```
Если PrintProfile.compatible_filaments содержит Filament.slug X
  И PrintProfile.compatible_printers содержит Printer.slug Y
  → Filament X совместим с Printer Y
```

**Реализация:**
- Использовать `PrintProfile.compatible_filaments` (JSON)
- Использовать `print_profile_printers` (таблица)

**Пример SQL:**
```sql
SELECT DISTINCT
  f.id as filament_id,
  f.slug as filament_slug,
  p.id as printer_id,
  p.slug as printer_slug,
  'via_print_profile' as relation_source
FROM print_profiles pp
CROSS JOIN LATERAL jsonb_array_elements_text(pp.compatible_filaments::jsonb) as filament_slug
JOIN filaments f ON f.slug = filament_slug
JOIN print_profile_printers ppp ON ppp.print_profile_id = pp.id
JOIN printers p ON p.slug = ppp.printer_slug
WHERE pp.active = true;
```

#### C. Printer → Filament (через PrinterProfile → PrintProfile)

**Логика:**
```
Если PrinterProfile.printer_id = Printer X
  И PrinterProfile.default_print_profile_slug = PrintProfile.slug Y
  И PrintProfile.compatible_filaments содержит Filament.slug Z
  → Printer X может использовать Filament Z с профилем печати Y
```

**Реализация:**
- Использовать цепочку: PrinterProfile → PrintProfile → Filament

---

## 🗄️ Предлагаемая структура БД

### Вариант 1: Таблица выведенных связей (рекомендуется)

Создать таблицу для кеширования выведенных связей:

```sql
CREATE TABLE filament_printer_compatibility (
    id SERIAL PRIMARY KEY,
    filament_id INTEGER NOT NULL REFERENCES filaments(id) ON DELETE CASCADE,
    printer_id INTEGER NOT NULL REFERENCES printers(id) ON DELETE CASCADE,
    relation_source VARCHAR(50) NOT NULL, -- 'explicit', 'via_preset', 'via_print_profile', 'via_printer_profile'
    confidence_score FLOAT DEFAULT 1.0, -- 0.0-1.0
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(filament_id, printer_id, relation_source)
);

CREATE INDEX idx_fpc_filament ON filament_printer_compatibility(filament_id);
CREATE INDEX idx_fpc_printer ON filament_printer_compatibility(printer_id);
CREATE INDEX idx_fpc_source ON filament_printer_compatibility(relation_source);
```

**Преимущества:**
- Быстрый поиск совместимости
- Можно хранить несколько источников связи
- Можно обновлять периодически (cron job)

**Недостатки:**
- Дополнительная таблица
- Нужно поддерживать синхронизацию

### Вариант 2: View (для чтения)

Создать view для динамического вывода:

```sql
CREATE VIEW filament_printer_compatibility_view AS
-- Через Preset
SELECT DISTINCT 
  f.id as filament_id,
  f.slug as filament_slug,
  p.id as printer_id,
  p.slug as printer_slug,
  'via_preset' as relation_source,
  0.8 as confidence_score
FROM filaments f
JOIN presets pr ON pr.filament_id = f.id
JOIN preset_printers pp ON pp.preset_id = pr.id
JOIN printers p ON p.id = pp.printer_id
WHERE pr.active = true

UNION ALL

-- Через PrintProfile
SELECT DISTINCT
  f.id,
  f.slug,
  p.id,
  p.slug,
  'via_print_profile',
  0.9
FROM print_profiles pp
CROSS JOIN LATERAL jsonb_array_elements_text(pp.compatible_filaments::jsonb) as filament_slug
JOIN filaments f ON f.slug = filament_slug
JOIN print_profile_printers ppp ON ppp.print_profile_id = pp.id
JOIN printers p ON p.slug = ppp.printer_slug
WHERE pp.active = true AND pp.compatible_filaments IS NOT NULL;
```

**Преимущества:**
- Всегда актуальные данные
- Не нужно синхронизировать
- Простое использование

**Недостатки:**
- Медленнее на больших объемах
- Сложнее для сложных запросов

---

## 🔄 Алгоритм вывода совместимости

### Шаг 1: Сбор данных из существующих связей

```python
# 1. Preset → Printer (через preset_printers)
preset_links = db.query(PresetPrinter).all()
# Результат: {filament_id: [printer_id, ...]}

# 2. PrintProfile → Printer + Filament
print_profile_links = db.query(PrintProfile).filter(
    PrintProfile.compatible_filaments.isnot(None)
).all()
# Результат: {filament_slug: [printer_slug, ...]}

# 3. PrinterProfile → PrintProfile → Filament
printer_profile_links = db.query(PrinterProfile).filter(
    PrinterProfile.default_print_profile_slug.isnot(None)
).all()
# Результат: {printer_id: [filament_slug, ...]}
```

### Шаг 2: Объединение и дедупликация

```python
compatibility_map = {}

# Из preset_printers
for link in preset_links:
    filament_id = link.preset.filament_id
    printer_id = link.printer_id
    key = (filament_id, printer_id)
    if key not in compatibility_map:
        compatibility_map[key] = {
            'sources': [],
            'confidence': 0.0
        }
    compatibility_map[key]['sources'].append('via_preset')
    compatibility_map[key]['confidence'] = max(
        compatibility_map[key]['confidence'], 
        0.8  # Preset = средняя уверенность
    )

# Из print_profile
for profile in print_profile_links:
    for filament_slug in profile.compatible_filaments:
        for printer_link in profile.printer_links:
            filament = get_filament_by_slug(filament_slug)
            printer = get_printer_by_slug(printer_link.printer_slug)
            if filament and printer:
                key = (filament.id, printer.id)
                # ... аналогично
                compatibility_map[key]['confidence'] = max(
                    compatibility_map[key]['confidence'],
                    0.9  # PrintProfile = высокая уверенность
                )
```

### Шаг 3: Сохранение в БД

```python
for (filament_id, printer_id), data in compatibility_map.items():
    db.merge(FilamentPrinterCompatibility(
        filament_id=filament_id,
        printer_id=printer_id,
        relation_source=','.join(data['sources']),
        confidence_score=data['confidence']
    ))
```

---

## 📈 Использование в API

### Эндпоинт: Получить совместимые принтеры для филамента

```python
@router.get("/filaments/{filament_id}/compatible-printers")
async def get_compatible_printers(
    filament_id: int,
    min_confidence: float = 0.5,
    db: AsyncSession = Depends(get_db)
):
    """Получить список принтеров, совместимых с филаментом."""
    
    # Вариант 1: Из таблицы (быстро)
    links = await db.execute(
        select(FilamentPrinterCompatibility)
        .where(
            FilamentPrinterCompatibility.filament_id == filament_id,
            FilamentPrinterCompatibility.confidence_score >= min_confidence
        )
    )
    
    # Вариант 2: Из view (динамически)
    # links = await db.execute(
    #     select(FilamentPrinterCompatibilityView)
    #     .where(...)
    # )
    
    return [link.printer for link in links.scalars().all()]
```

### Эндпоинт: Получить совместимые филаменты для принтера

```python
@router.get("/printers/{printer_id}/compatible-filaments")
async def get_compatible_filaments(
    printer_id: int,
    min_confidence: float = 0.5,
    db: AsyncSession = Depends(get_db)
):
    """Получить список филаментов, совместимых с принтером."""
    # Аналогично
```

### Эндпоинт: Получить рекомендуемые профили печати

```python
@router.get("/filaments/{filament_id}/printers/{printer_id}/recommended-profiles")
async def get_recommended_profiles(
    filament_id: int,
    printer_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Получить рекомендуемые PrintProfile для комбинации Filament + Printer."""
    
    # 1. Найти PrintProfile, которые совместимы с обоими
    profiles = await db.execute(
        select(PrintProfile)
        .join(PrintProfileFilament).where(
            PrintProfileFilament.filament_id == filament_id
        )
        .join(PrintProfilePrinter).where(
            PrintProfilePrinter.printer_id == printer_id
        )
    )
    
    # 2. Найти через PrinterProfile → PrintProfile
    printer_profiles = await db.execute(
        select(PrinterProfile)
        .where(PrinterProfile.printer_id == printer_id)
        .join(PrintProfile).where(
            PrintProfile.slug == PrinterProfile.default_print_profile_slug
        )
        .join(PrintProfileFilament).where(
            PrintProfileFilament.filament_id == filament_id
        )
    )
    
    return {
        'print_profiles': profiles.scalars().all(),
        'via_printer_profiles': printer_profiles.scalars().all()
    }
```

---

## 🎯 Рекомендуемый подход

### Фаза 1: Использовать существующие данные

1. **Использовать `print_profile_printers`** (1539 записей!)
   - Это уже готовые связи PrintProfile → Printer
   - Можно использовать для вывода совместимости

2. **Заполнить `print_profile_filaments`**
   - При импорте из OrcaSlicer парсить `compatible_filaments`
   - При создании PrintProfile вручную — добавлять связи

3. **Использовать `preset_printers`** (2 записи — мало, но есть)
   - При создании Preset — предлагать выбрать принтер
   - При импорте из OrcaSlicer — парсить `compatible_printers`

### Фаза 2: Автоматический вывод

1. **Создать view** для динамического вывода совместимости
2. **Добавить эндпоинты** для получения совместимых профилей
3. **Показывать в UI** рекомендуемые комбинации

### Фаза 3: Оптимизация (если нужно)

1. **Создать таблицу** `filament_printer_compatibility` для кеширования
2. **Cron job** для периодического обновления
3. **Индексы** для быстрого поиска

---

## 📝 Примеры использования

### Пример 1: "Какие принтеры подходят для PLA?"

```sql
-- Через Preset
SELECT DISTINCT p.*
FROM printers p
JOIN preset_printers pp ON pp.printer_id = p.id
JOIN presets pr ON pr.id = pp.preset_id
JOIN filaments f ON f.id = pr.filament_id
WHERE f.material_type = 'PLA';

-- Через PrintProfile
SELECT DISTINCT p.*
FROM printers p
JOIN print_profile_printers ppp ON ppp.printer_slug = p.slug
JOIN print_profiles pf ON pf.id = ppp.print_profile_id
WHERE pf.compatible_filaments::jsonb ? 'pla';  -- если slug = 'pla'
```

### Пример 2: "Какие филаменты можно печатать на Ender 3?"

```sql
SELECT DISTINCT f.*
FROM filaments f
JOIN preset_printers pp ON pp.preset_id IN (
    SELECT id FROM presets WHERE filament_id = f.id
)
JOIN printers p ON p.id = pp.printer_id
WHERE p.slug = 'creality-ender-3';
```

### Пример 3: "Какой PrintProfile использовать для PLA на Ender 3?"

```sql
SELECT pf.*
FROM print_profiles pf
JOIN print_profile_printers ppp ON ppp.print_profile_id = pf.id
JOIN print_profile_filaments pff ON pff.print_profile_id = pf.id
JOIN printers p ON p.slug = ppp.printer_slug
JOIN filaments f ON f.slug = pff.filament_slug
WHERE p.slug = 'creality-ender-3' 
  AND f.material_type = 'PLA'
ORDER BY pf.is_official DESC, pf.rating DESC;
```

---

## ✅ Итоговые рекомендации

1. **Оставить slug** для всех профилей (нужен для OrcaSlicer)
2. **Использовать существующие таблицы** связей (`print_profile_printers`, `print_profile_filaments`, `preset_printers`)
3. **Создать view** для динамического вывода совместимости
4. **Добавить API эндпоинты** для получения совместимых профилей
5. **Показывать в UI** рекомендуемые комбинации на основе выведенных связей

**Не создавать костыли** — использовать то, что уже есть, и дополнять по мере необходимости.


