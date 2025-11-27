# Логика синхронизации профилей из OrcaSlicer

## Архитектура: Сущности vs Профили

**Важно:** В системе используется разделение на базовые сущности и профили:

- **`Filament`** (базовая сущность) + **`Preset`** (профиль настроек)
- **`Printer`** (базовая сущность) + **`PrinterProfile`** (профиль настроек)
- **`PrintProfile`** (независимый профиль печати)

Подробнее: [ARCHITECTURE_ENTITIES_PROFILES.md](./ARCHITECTURE_ENTITIES_PROFILES.md)

## Текущее состояние

### Что уже работает:

1. **Профили филаментов:**
   - ✅ Сопоставление с существующими филаментами во всех брендах
   - ✅ Создание черновиков в "User Materials" для новых материалов
   - ✅ Не перезаписывает существующие бренды и их филаменты

2. **Профили принтеров:**
   - ✅ Сопоставление принтера (`Printer`) с базой (`_ensure_printer_id`)
   - ✅ Создание нового профиля принтера (`PrinterProfile`) каждый раз (даже если меняется только сопло)

3. **Профили печати:**
   - ✅ Импорт из OrcaSlicer
   - ✅ Связь с принтерами через `compatible_printers` (список slugs)

## Проблемы и улучшения

### 1. Профили принтеров: избыточное создание при изменении сопла

**Проблема:**
- Сейчас для каждого сопла создаётся отдельный профиль: "Ворон 2.4 350 0.4", "Ворон 2.4 350 0.6"
- Это избыточно, так как основные характеристики одинаковые, меняется только сопло

**Решение:**
- В `PrinterProfile` уже есть поле `nozzle_diameters: list[float]` - список сопел
- При синхронизации:
  1. Ищем существующий профиль принтера для этого пользователя
  2. Критерии поиска: `printer_id` + `owner_user_id` + основные характеристики (без сопла)
  3. Если найден - добавляем новое сопло в `nozzle_diameters` (если его там нет)
  4. Если не найден - создаём новый профиль

**Алгоритм сопоставления профилей принтера:**
```
1. По fhub_id (если указан явно) - используем его
2. По slug + owner_user_id (если указан slug)
3. По printer_id + owner_user_id + основные характеристики:
   - printable_area (размер стола)
   - printable_height_mm (высота)
   - vendor (если есть)
   - model_id из extra_metadata
4. Если найден - обновляем (добавляем сопло, обновляем settings)
5. Если не найден - создаём новый
```

### 2. Системные профили печати

**Задача:**
- Подтянуть системные профили печати из OrcaSlicer (0.12, 0.2, 0.28 и т.д.)
- Создать их как типовые (`is_official=True`, `source="system"`)
- От них пользователи смогут отталкиваться

**Решение:**
- Создать эндпоинт `/orcaslicer/system-print-profiles/import` для админов
- Или автоматически импортировать при первом подключении пользователя
- Профили помечать как `is_official=True`, `source="orca_system"`

**Структура системных профилей:**
```json
{
  "name": "0.12mm Fine",
  "category": "quality",
  "quality_tier": "fine",
  "layer_height_mm": 0.12,
  "default_nozzle": "0.4",
  "is_official": true,
  "source": "orca_system",
  "compatible_printers": ["voron-2.4", "prusa-mk3", ...],  // Все принтеры по умолчанию
  "orcaslicer_settings": { ... }
}
```

### 3. Сопоставление профилей печати

**Задача:**
- Пользовательские профили печати (качество, скорость, вазочки) должны сопоставляться
- Системные профили - использовать существующие или создавать типовые

**Решение:**
- При импорте профилей печати:
  1. Проверяем `source`:
     - Если `source="orca_system"` - ищем системный профиль по `layer_height_mm` + `quality_tier`
     - Если `source="user"` - ищем пользовательский профиль по `slug` + `owner_user_id`
  2. Если найден - обновляем
  3. Если не найден - создаём новый

**Алгоритм сопоставления профилей печати:**
```
1. По fhub_id (если указан явно)
2. По slug + owner_user_id (для пользовательских)
3. По layer_height_mm + quality_tier + source (для системных)
4. По name + owner_user_id (резервный вариант)
```

### 4. Связи между профилями

**Текущая структура:**
- `Filament` ↔ `Preset` (через `filament_id`)
- `Printer` ↔ `PrinterProfile` (через `printer_id`)
- `PrintProfile` ↔ `Printer` (через `compatible_printers` - список slugs)
- `PrintProfile` ↔ `Filament` (через `compatible_filaments` - список slugs)

**Логика использования:**
1. Пользователь выбирает принтер → показываем `PrinterProfile` для этого принтера
2. Пользователь выбирает `PrintProfile` → показываем совместимые `Filament` + `Preset`
3. Пользователь выбирает `Filament` → показываем рекомендуемые `PrintProfile` для этого принтера

## План реализации

### Этап 1: Улучшение сопоставления профилей принтера

1. **Создать функцию `_find_existing_printer_profile`:**
   ```python
   async def _find_existing_printer_profile(
       *,
       printer_id: int,
       owner_user_id: int,
       printable_area: dict | None,
       printable_height_mm: float | None,
       vendor: str | None,
       db: AsyncSession,
   ) -> PrinterProfile | None:
       """Найти существующий профиль принтера по основным характеристикам."""
   ```

2. **Обновить `_upsert_printer_profile`:**
   - Добавить поиск существующего профиля по основным характеристикам
   - Если найден - обновлять `nozzle_diameters`, добавляя новые сопла
   - Если не найден - создавать новый

### Этап 2: Системные профили печати

1. **Создать эндпоинт для импорта системных профилей:**
   - `/orcaslicer/system-print-profiles/import` (только для админов)
   - Или автоматически при первом подключении

2. **Структура системных профилей:**
   - Категории: `quality`, `speed`, `special` (вазочки и т.д.)
   - Типы: `fine` (0.12), `standard` (0.2), `draft` (0.28), `vase_mode`, и т.д.

### Этап 3: Улучшение сопоставления профилей печати

1. **Создать функцию `_find_existing_print_profile`:**
   ```python
   async def _find_existing_print_profile(
       *,
       owner_user_id: int,
       layer_height_mm: float | None,
       quality_tier: str | None,
       source: str,
       db: AsyncSession,
   ) -> PrintProfile | None:
       """Найти существующий профиль печати."""
   ```

2. **Обновить `_upsert_print_profile`:**
   - Разделить логику для системных и пользовательских профилей
   - Системные - искать по `layer_height_mm` + `quality_tier`
   - Пользовательские - по `slug` + `owner_user_id`

### Этап 4: Документация

1. Описать логику сопоставления в коде
2. Добавить примеры использования
3. Обновить API документацию

## Примеры использования

### Пример 1: Синхронизация профиля принтера с разными соплами

```
1. Пользователь импортирует "Ворон 2.4 350 0.4" → создаётся профиль с nozzle_diameters=[0.4]
2. Пользователь импортирует "Ворон 2.4 350 0.6" → находится существующий профиль, обновляется nozzle_diameters=[0.4, 0.6]
3. В базе один профиль с двумя соплами
```

### Пример 2: Системные профили печати

```
1. Админ импортирует системные профили из OrcaSlicer
2. Создаются типовые профили:
   - "0.12mm Fine" (layer_height=0.12, quality_tier="fine")
   - "0.2mm Standard" (layer_height=0.2, quality_tier="standard")
   - "0.28mm Draft" (layer_height=0.28, quality_tier="draft")
   - "Vase Mode" (category="special", quality_tier="vase")
3. Пользователи могут использовать эти профили как базовые
```

### Пример 3: Сопоставление профилей печати

```
1. Пользователь создаёт профиль "Моя качественная печать" (0.12mm)
2. При синхронизации из OrcaSlicer система находит этот профиль по slug
3. Обновляет настройки, но не создаёт дубликат
```

## Персонализация на основе принтеров пользователя

### Концепция

Благодаря синхронизации профилей принтеров из OrcaSlicer мы можем:
1. **Определять принтеры пользователя** - понимать какими принтерами он пользуется
2. **Персонализировать контент** - показывать только релевантные материалы и профили
3. **Улучшать UX** - не засорять каталог нерелевантными предложениями

### Источники данных

1. **Профили принтеров пользователя** (`PrinterProfile.owner_user_id == user.id`)
   - Активные профили принтеров, синхронизированные из OrcaSlicer
   - Показывают реальное использование

2. **Привязка к принтерам** (`PrinterProfile.printer_id`)
   - Позволяет определить модели принтеров пользователя
   - Через `Printer.slug` и `Printer.model_id` можем сопоставить с базой

### Применение персонализации

#### 1. Каталог филаментов

**Фильтрация по совместимости:**
- По умолчанию показывать только филаменты, совместимые с принтерами пользователя
- Через `filament_printer_compatibility_view` находим совместимость
- Опция "Показать все" для просмотра всего каталога

**Рекомендации:**
- Приоритетно показывать филаменты с высоким `confidence_score`
- Отмечать "Рекомендуется для вашего принтера"
- Уведомления о новых совместимых материалах

#### 2. Профили печати

**Релевантные профили:**
- Показывать только профили, совместимые с принтерами пользователя
- `PrintProfile.compatible_printers` содержит список slugs принтеров
- Сравниваем с `Printer.slug` из профилей пользователя

**Персонализация:**
- Предлагать системные профили для его принтеров
- Показывать популярные профили от других пользователей с такими же принтерами
- Рекомендации на основе истории использования

#### 3. Создание пресетов

**Умные подсказки:**
- При создании пресета автоматически предлагать принтеры пользователя
- Предзаполнение совместимых принтеров на основе выбранного филамента
- Валидация совместимости перед сохранением

#### 4. Dashboard пользователя

**Персонализированные секции:**
- "Рекомендуемые материалы для ваших принтеров"
- "Популярные профили для [принтер пользователя]"
- "Недавно добавленные совместимые материалы"

#### 5. Уведомления

**Умные уведомления:**
- "Новый материал [name] совместим с вашим [printer]"
- "Добавлены рекомендуемые настройки для [printer]"
- "Новый профиль печати для [printer] от производителя [brand]"

### Техническая реализация

#### Функция получения принтеров пользователя:

```python
async def get_user_printers(
    *,
    user_id: int,
    db: AsyncSession,
    active_only: bool = True,
) -> list[Printer]:
    """Получить список принтеров пользователя на основе его профилей."""
    # Получаем активные профили принтеров пользователя
    result = await db.execute(
        select(PrinterProfile)
        .where(
            PrinterProfile.owner_user_id == user_id,
            PrinterProfile.active == active_only,
            PrinterProfile.printer_id.isnot(None),
        )
        .distinct()
    )
    profiles = result.scalars().all()
    
    # Получаем уникальные принтеры
    printer_ids = [p.printer_id for p in profiles if p.printer_id]
    if not printer_ids:
        return []
    
    result = await db.execute(
        select(Printer).where(Printer.id.in_(printer_ids))
    )
    return list(result.scalars().all())
```

#### Функция фильтрации по совместимости:

```python
async def get_recommended_filaments_for_user(
    *,
    user_id: int,
    db: AsyncSession,
    limit: int = 20,
) -> list[Filament]:
    """Получить рекомендуемые филаменты для принтеров пользователя."""
    user_printers = await get_user_printers(user_id=user_id, db=db)
    if not user_printers:
        return []
    
    printer_slugs = [p.slug for p in user_printers]
    
    # Используем VIEW для получения совместимых филаментов
    query = text("""
        SELECT DISTINCT filament_id
        FROM filament_printer_compatibility_view
        WHERE printer_slug = ANY(:printer_slugs)
          AND confidence_score >= 0.7
        ORDER BY confidence_score DESC
        LIMIT :limit
    """)
    
    result = await db.execute(query, {
        "printer_slugs": printer_slugs,
        "limit": limit,
    })
    filament_ids = [row[0] for row in result.fetchall()]
    
    if not filament_ids:
        return []
    
    result = await db.execute(
        select(Filament).where(
            Filament.id.in_(filament_ids),
            Filament.active == True,
        )
    )
    return list(result.scalars().all())
```

#### Эндпоинты для персонализации:

```python
@router.get("/recommendations/filaments", response_model=FilamentListResponse)
async def get_recommended_filaments(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(20, ge=1, le=100),
) -> FilamentListResponse:
    """Получить рекомендуемые филаменты для принтеров пользователя."""
    filaments = await get_recommended_filaments_for_user(
        user_id=current_user.id,
        db=db,
        limit=limit,
    )
    return FilamentListResponse(items=filaments, total=len(filaments), page=1, size=limit, pages=1)


@router.get("/recommendations/print-profiles", response_model=PrintProfileListResponse)
async def get_recommended_print_profiles(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(20, ge=1, le=100),
) -> PrintProfileListResponse:
    """Получить рекомендуемые профили печати для принтеров пользователя."""
    user_printers = await get_user_printers(user_id=current_user.id, db=db)
    printer_slugs = [p.slug for p in user_printers]
    
    # Получаем профили, совместимые с принтерами пользователя
    # ...
```

### Преимущества

1. **Улучшенный UX** - пользователь видит только релевантный контент
2. **Меньше мусора** - не засоряем каталог несовместимыми материалами
3. **Персонализация** - каждый пользователь видит свой уникальный опыт
4. **Конверсия** - релевантные рекомендации повышают вероятность использования
5. **Аналитика** - можем отслеживать популярность материалов по принтерам

### Настройки приватности

**Важно:** Пользователь должен иметь возможность:
1. Отключить синхронизацию принтеров (если не хочет делиться)
2. Выбрать какие принтеры показывать (если несколько)
3. Просматривать все материалы, а не только совместимые (опция)

## Критерии успеха

1. ✅ Не создаются дубликаты профилей при изменении только сопла
2. ✅ Системные профили доступны всем пользователям
3. ✅ Пользовательские профили сопоставляются корректно
4. ✅ Связи между профилями работают правильно
5. ✅ Не перезаписываются существующие данные без явного указания
6. ✅ **Персонализация работает на основе принтеров пользователя**
7. ✅ **Рекомендации учитывают совместимость**
8. ✅ **Пользователь может управлять уровнем персонализации**

