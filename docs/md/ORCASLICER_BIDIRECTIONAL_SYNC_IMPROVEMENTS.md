# Идеи для улучшения двусторонней синхронизации

> **Статус:** Идеи для обсуждения и реализации  
> **Дата создания:** 2025-11-12  
> **Версия:** 1.1 (обновлено с учетом комментариев пользователя)

## 📋 Резюме решений

### ✅ Что реализуем в MVP:
1. **Конфликты при синхронизации** (timestamp-based) - сравниваем `updated_at`, выигрывает более новая версия
2. **Лимиты на количество профилей** (50 профилей за запрос) - достаточно для большинства случаев
3. **Обработка ошибок и частичный импорт** - продолжаем импорт даже если некоторые профили провалились
4. **Система уведомлений (доработка)** - добавить типы для админа, объявлений, верификации
5. **Уведомления об импорте** - сообщать пользователю о результатах импорта

### ⏳ Что откладываем на потом:
- Валидация данных (температуры, скорости) - достаточно базовой валидации текста
- Батчинг - не нужен для MVP, обрабатываем последовательно
- Прогресс-бар - синхронизация быстрая, не критично
- Кэширование - отложено на потом
- Обработка edge cases - отложено на потом

---

## 🎯 Критичные улучшения (нужно реализовать в MVP)

### 1. Конфликты при синхронизации

**Что это такое (простыми словами):**

Представь ситуацию:
1. У тебя есть пресет "PLA Red" в FilamentHub
2. Ты синхронизировал его в OrcaSlicer (теперь он есть и там, и там)
3. Ты изменил температуру в FilamentHub (210°C → 215°C)
4. Одновременно изменил температуру в OrcaSlicer (210°C → 220°C)
5. Теперь у тебя **КОНФЛИКТ** - какая версия правильная?

**Текущая стратегия:**
- Приоритет у FilamentHub (версия с сайта всегда выигрывает)
- Это просто, но не всегда правильно (можешь потерять изменения из OrcaSlicer)

**Решения:**

**Вариант A (по времени изменения) - РЕКОМЕНДУЕТСЯ:**
- Сравниваем время изменения (`updated_at`)
- Если FilamentHub новее → используем версию с сайта
- Если OrcaSlicer новее → используем версию из OrcaSlicer
- Если равны → используем версию из OrcaSlicer (последнее изменение)

**Вариант B (по версии):**
- Добавляем поле `version` (число, увеличивается при каждом изменении)
- Более надежно, чем время (нет проблем с часовыми поясами)
- Но сложнее в реализации

**Вариант C (спросить пользователя):**
- Всегда спрашивать: "Какая версия правильная?"
- Надежно, но неудобно (особенно при массовом импорте)

**Решение для MVP:**
- Использовать вариант A (по времени изменения)
- Это просто и работает в 99% случаев
- Если нужно, позже добавим вариант B или C

**Пример:**
```
Пресет "PLA Red":
- FilamentHub: updated_at = 2025-11-12 10:00:00, temp = 215°C
- OrcaSlicer: updated_at = 2025-11-12 11:00:00, temp = 220°C

OrcaSlicer новее (11:00 > 10:00) → используем 220°C из OrcaSlicer
```

**Реализация:**
```python
# В _upsert_filament_preset()
if preset:
    # Проверяем конфликты
    if payload.updated_at and preset.updated_at:
        if payload.updated_at > preset.updated_at:
            # OrcaSlicer версия новее - обновляем
            preset.name = payload.name
            # ...
        elif preset.updated_at > payload.updated_at:
            # FilamentHub версия новее - возвращаем ошибку конфликта
            return OrcaSyncResult(
                external_id=payload.external_id,
                fhub_id=preset.id,
                status="conflict",
                message=f"Conflict: FilamentHub version is newer (updated_at: {preset.updated_at})",
            )
        else:
            # Равны - обновляем без конфликта
            preset.name = payload.name
            # ...
```

### 2. Валидация данных перед импортом ⏳ **ОТЛОЖЕНО**

**Проблема:** Сейчас валидируется только текст, но не температуры, скорости и т.д.

**Статус:** Отложено на потом, будем дорабатывать отдельно.

**Идеи (для будущего):**
- Валидация температур (0-500°C для экструдера, 0-200°C для стола)
- Валидация скоростей (1-1000 mm/s)
- Валидация других параметров (layer_height, retraction_length, fan_speed)
- Валидация размера JSON (максимум 1MB)

**Примечание:** На MVP достаточно базовой валидации текста (уже реализовано).

### 3. Обработка ошибок и частичный импорт

**Проблема:** Если один профиль не удалось импортировать, весь батч может провалиться.

**Идеи:**
- **Частичный импорт:** Продолжать импорт даже если некоторые профили не удались
  - Уже частично реализовано (каждый профиль обрабатывается отдельно)
  - Нужно улучшить отчетность (сколько успешно, сколько провалилось)
- **Транзакции:** Использовать транзакции для каждого профиля отдельно
  - Если один профиль провалился, остальные все равно импортируются
- **Откат изменений:** Если все профили провалились, откатить все изменения
  - Сложно, требует сохранения состояния до импорта

**Реализация:**
```python
# В import_filament_presets()
results: list[OrcaSyncResult] = []
success_count = 0
error_count = 0

for item in payload.profiles:
    try:
        # Начинаем транзакцию для каждого профиля
        async with db.begin():
            result = await _upsert_filament_preset(
                payload=item,
                current_user=current_user,
                db=db,
            )
            if result.status in ("created", "updated"):
                success_count += 1
            else:
                error_count += 1
    except Exception as exc:
        error_count += 1
        result = OrcaSyncResult(
            external_id=getattr(item, "external_id", None),
            fhub_id=getattr(item, "fhub_id", None),
            status="error",
            message=f"Unexpected error: {exc}",
        )
    results.append(result)

# Возвращаем статистику
return FilamentPresetSyncResponse(
    results=results,
    total=len(results),
    success_count=success_count,
    error_count=error_count,
)
```

### 4. Лимиты на количество импортируемых профилей

**Проблема:** Пользователь может импортировать тысячи профилей за раз, что может перегрузить сервер.

**Решение:**
- **Лимит на батч:** Максимум **50 профилей** за один запрос
  - Большинство пользователей используют одни и те же бренды
  - Редко покупают новые катушки филаментов
  - 50 профилей достаточно для большинства случаев
- **Гибкость:** Лимит можно изменить в будущем:
  - Вывести в админку (настройка лимита)
  - Увеличить при переходе на более мощные сервера
  - Сделать лимит зависящим от роли пользователя (админ = больше)

**Реализация:**
```python
MAX_PROFILES_PER_REQUEST = 50  # Для MVP достаточно

if len(payload.profiles) > MAX_PROFILES_PER_REQUEST:
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Too many profiles: {len(payload.profiles)} (max {MAX_PROFILES_PER_REQUEST})",
    )
```

**Будущие улучшения:**
- Настройка лимита в админке (вывести в админ-панель)
- Разные лимиты для разных ролей (user=50, brand=100, admin=500)
- Проверка размера payload (максимум 10MB)
- Увеличение лимита при переходе на более мощные сервера

### 5. Обработка дубликатов

**Проблема:** Пользователь может случайно импортировать один и тот же профиль несколько раз.

**Идеи:**
- **Проверка на дубликаты:** Перед импортом проверять, не существует ли уже профиль с таким `external_id`
- **Объединение дубликатов:** Если профиль уже существует, обновить его вместо создания нового
- **Уведомление пользователя:** Сообщить пользователю о дубликатах

**Реализация:**
```python
# В _upsert_filament_preset()
# Уже реализовано через external_id и fhub_id
# Но можно улучшить:
if payload.external_id:
    # Проверяем дубликаты по external_id
    existing = await db.execute(
        select(Preset).where(
            Preset.external_id == payload.external_id,
            Preset.user_id == current_user.id,
        )
    )
    duplicate = existing.scalar_one_or_none()
    if duplicate and duplicate.id != preset.id if preset else None:
        return OrcaSyncResult(
            external_id=payload.external_id,
            fhub_id=duplicate.id,
            status="duplicate",
            message=f"Duplicate preset found (id={duplicate.id})",
        )
```

---

## 🔧 Улучшения производительности

### 6. Массовый импорт и батчинг

**Что это такое (простыми словами):**

**Батчинг** = обработка данных группами (батчами), а не по одному.

**Пример без батчинга:**
```
Импортируем 50 профилей:
1. Импортируем профиль #1 → ждём → сохраняем в БД
2. Импортируем профиль #2 → ждём → сохраняем в БД
3. Импортируем профиль #3 → ждём → сохраняем в БД
...
50. Импортируем профиль #50 → ждём → сохраняем в БД

Время: 50 × 0.1 сек = 5 секунд
```

**Пример с батчингом:**
```
Импортируем 50 профилей батчами по 10:
Батч 1 (профили #1-10):
  - Обрабатываем все 10 профилей параллельно
  - Сохраняем все 10 в БД одной транзакцией
Батч 2 (профили #11-20):
  - Обрабатываем все 10 профилей параллельно
  - Сохраняем все 10 в БД одной транзакцией
...

Время: 5 батчей × 0.2 сек = 1 секунда (в 5 раз быстрее!)
```

**Преимущества:**
- ⚡ Быстрее (обрабатываем несколько профилей одновременно)
- 💾 Эффективнее (меньше запросов к БД)
- 🎯 Надежнее (если один профиль провалился, остальные в батче всё равно обрабатываются)

**Недостатки:**
- 🧠 Сложнее (нужно управлять параллельной обработкой)
- 🐛 Больше багов (проблемы с транзакциями, race conditions)

**Решение для MVP:**
- **НЕ использовать батчинг** на MVP
- Обрабатывать профили последовательно (один за другим)
- Это проще и надежнее
- Для 50 профилей разница не критична (5 секунд vs 1 секунда)

**Когда нужен батчинг:**
- Когда импортируем 1000+ профилей
- Когда производительность становится проблемой
- После переезда на более мощные сервера

**Реализация (для будущего):**
```python
# Обработка батчами (если понадобится)
BATCH_SIZE = 10
for i in range(0, len(payload.profiles), BATCH_SIZE):
    batch = payload.profiles[i:i + BATCH_SIZE]
    # Обрабатываем батч параллельно
    batch_results = await asyncio.gather(*[
        _upsert_filament_preset(
            payload=item,
            current_user=current_user,
            db=db,
        ) for item in batch
    ])
    results.extend(batch_results)
```

### 7. Кэширование

**Проблема:** Повторяющиеся запросы к БД для одного и того же материала/бренда.

**Идеи:**
- **Кэш материалов:** Кэшировать часто используемые материалы в памяти
- **Кэш брендов:** Кэшировать служебный бренд "User Materials"
- **Кэш маппингов:** Кэшировать маппинги `external_id → fhub_id`

**Реализация:**
```python
# Кэш для служебного бренда
USER_MATERIALS_BRAND_ID = 1
_user_materials_brand_cache: Brand | None = None

async def get_user_materials_brand(db: AsyncSession) -> Brand:
    """Получить служебный бренд 'User Materials' с кэшированием."""
    global _user_materials_brand_cache
    if _user_materials_brand_cache is None:
        _user_materials_brand_cache = await db.get(Brand, USER_MATERIALS_BRAND_ID)
        if _user_materials_brand_cache is None:
            raise ValueError("User Materials brand not found")
    return _user_materials_brand_cache
```

---

## 🛡️ Безопасность и валидация

### 8. Защита от инъекций и XSS

**Проблема:** Пользователь может отправить вредоносный JSON.

**Идеи:**
- **Валидация JSON:** Убедиться, что JSON валидный и не содержит циклических ссылок
- **Санитизация текста:** Удалять опасные символы из текстовых полей
- **Проверка размера:** Ограничивать размер полей

**Реализация:**
```python
import json
import sys

def validate_json_size(data: dict, max_size: int = 1_000_000) -> bool:
    """Проверить размер JSON."""
    try:
        json_size = len(json.dumps(data))
        return json_size <= max_size
    except (TypeError, ValueError):
        return False

def check_circular_references(data: dict) -> bool:
    """Проверить на циклические ссылки."""
    visited = set()
    def check(obj, path=()):
        if id(obj) in visited:
            return False
        visited.add(id(obj))
        if isinstance(obj, dict):
            for key, value in obj.items():
                if not check(value, path + (key,)):
                    return False
        elif isinstance(obj, (list, tuple)):
            for i, item in enumerate(obj):
                if not check(item, path + (i,)):
                    return False
        visited.remove(id(obj))
        return True
    return check(data)
```

### 9. Проверка прав доступа

**Проблема:** Пользователь может попытаться импортировать профиль от другого пользователя.

**Идеи:**
- **Проверка владельца:** Убедиться, что пользователь может обновлять только свои профили
- **Проверка бренда:** Убедиться, что пользователь может привязывать материалы только к своим брендам
- **Проверка прав:** Убедиться, что пользователь имеет права на импорт

**Реализация:**
```python
# В _upsert_filament_preset()
if preset:
    # Проверяем права на обновление
    if preset.user_id != current_user.id and current_user.role != UserRole.ADMIN:
        return OrcaSyncResult(
            external_id=payload.external_id,
            fhub_id=preset.id,
            status="error",
            message="Недостаточно прав для обновления этого пресета",
        )
    
    # Проверяем права на изменение бренда (если указан)
    if payload.brand_id and payload.brand_id != USER_MATERIALS_BRAND_ID:
        brand = await db.get(Brand, payload.brand_id)
        if brand and current_user.brand_id != brand.id and current_user.role != UserRole.ADMIN:
            return OrcaSyncResult(
                external_id=payload.external_id,
                fhub_id=preset.id,
                status="error",
                message="Недостаточно прав для привязки к этому бренду",
            )
```

---

## 🎨 Улучшения UX

### 10. Уведомления пользователю

**Проблема:** Пользователь не знает, успешно ли прошел импорт.

**Идеи:**
- **Уведомления об успехе:** Сообщить пользователю о количестве успешно импортированных профилей
- **Уведомления об ошибках:** Сообщить пользователю об ошибках импорта
- **Уведомления о конфликтах:** Сообщить пользователю о конфликтах и запросить решение

**Реализация:**
```python
# В FilamentHubPanel (C++)
void FilamentHubPanel::handle_import_response(
    const std::string& profile_type,
    const std::string& response_body,
    unsigned http_status
)
{
    if (http_status != 200) {
        show_notification_in_webview(
            wxString::Format(_L("Failed to import %s profiles. Status: %d"), profile_type, http_status),
            "error"
        );
        return;
    }
    
    nlohmann::json response = nlohmann::json::parse(response_body);
    int success_count = 0;
    int error_count = 0;
    
    for (const auto& result : response["results"]) {
        std::string status = result["status"].get<std::string>();
        if (status == "created" || status == "updated") {
            success_count++;
        } else {
            error_count++;
        }
    }
    
    // Показываем уведомление
    if (error_count == 0) {
        show_notification_in_webview(
            wxString::Format(_L("Successfully imported %d %s profiles"), success_count, profile_type),
            "success"
        );
    } else {
        show_notification_in_webview(
            wxString::Format(_L("Imported %d %s profiles, %d errors"), success_count, profile_type, error_count),
            "warning"
        );
    }
}
```

### 11. Прогресс импорта

**Проблема:** Пользователь не видит прогресс импорта большого количества профилей.

**Идеи:**
- **Прогресс-бар:** Показывать прогресс импорта в UI
- **Логи импорта:** Показывать логи импорта в реальном времени
- **Статистика:** Показывать статистику импорта (успешно, ошибки, конфликты)

**Реализация:**
```cpp
// В FilamentHubPanel
void FilamentHubPanel::export_profiles_to_filamenthub()
{
    // Показываем прогресс-бар
    m_export_progress->Show();
    m_export_progress->SetRange(100);
    m_export_progress->SetValue(0);
    
    // Экспортируем профили
    int total = printer_profiles.size() + print_profiles.size() + filament_presets.size();
    int completed = 0;
    
    // Отправка Printer Profiles
    for (const auto& profile : printer_profiles) {
        // ...
        completed++;
        m_export_progress->SetValue((completed * 100) / total);
    }
    
    // Аналогично для других типов профилей
}
```

---

## 🔍 Edge cases и особые ситуации

### 12. Обработка удаленных брендов

**Проблема:** Что если служебный бренд "User Materials" был удален?

**Идеи:**
- **Автоматическое создание:** Автоматически создавать служебный бренд, если его нет
- **Проверка при импорте:** Проверять существование служебного бренда перед импортом
- **Миграция:** Убедиться, что миграция создает служебный бренд

**Реализация:**
```python
async def ensure_user_materials_brand_exists(db: AsyncSession) -> Brand:
    """Убедиться, что служебный бренд 'User Materials' существует."""
    brand = await db.get(Brand, USER_MATERIALS_BRAND_ID)
    if brand is None:
        # Создаем служебный бренд
        brand = Brand(
            id=USER_MATERIALS_BRAND_ID,
            name="User Materials",
            slug="user-materials",
            verified=False,
            active=True,
            description="User-imported materials from OrcaSlicer (drafts)",
        )
        db.add(brand)
        await db.flush()
    return brand
```

### 13. Обработка несуществующих принтеров

**Проблема:** Что если профиль принтера ссылается на несуществующий принтер?

**Идеи:**
- **Создание принтера:** Автоматически создавать принтер, если его нет
- **Игнорирование:** Игнорировать несуществующие принтеры
- **Уведомление:** Уведомлять пользователя о несуществующих принтерах

**Реализация:**
```python
# В _upsert_printer_profile()
if payload.printer_id:
    printer = await db.get(Printer, payload.printer_id)
    if printer is None:
        # Создаем принтер автоматически (если возможно)
        # Или возвращаем ошибку
        return OrcaSyncResult(
            external_id=payload.external_id,
            fhub_id=payload.fhub_id,
            status="error",
            message=f"Printer with id={payload.printer_id} not found",
        )
```

### 14. Маппинг material_type из OrcaSlicer

**Проблема:** Маппинг `material_type` из OrcaSlicer в FilamentHub может быть неоднозначным.

**Идеи:**
- **Таблица маппингов:** Создать таблицу маппингов `OrcaSlicer material_type → FilamentHub material_type`
- **Умный поиск:** Использовать fuzzy matching для поиска похожих типов материалов
- **Fallback:** Использовать fallback (например, "PLA") если маппинг не найден

**Реализация:**
```python
# Маппинг material_type из OrcaSlicer
MATERIAL_TYPE_MAPPING = {
    "fdm_filament_pla": "PLA",
    "fdm_filament_petg": "PETG",
    "fdm_filament_abs": "ABS",
    "fdm_filament_tpu": "TPU",
    # ...
}

def map_orcaslicer_material_type(orcaslicer_type: str) -> str:
    """Маппинг material_type из OrcaSlicer в FilamentHub."""
    # Пробуем найти точное совпадение
    if orcaslicer_type in MATERIAL_TYPE_MAPPING:
        return MATERIAL_TYPE_MAPPING[orcaslicer_type]
    
    # Пробуем найти частичное совпадение
    orcaslicer_type_lower = orcaslicer_type.lower()
    for key, value in MATERIAL_TYPE_MAPPING.items():
        if key.lower() in orcaslicer_type_lower or orcaslicer_type_lower in key.lower():
            return value
    
    # Fallback
    return "PLA"
```

### 15. Обработка специальных символов в именах

**Проблема:** Специальные символы в именах профилей могут вызвать проблемы.

**Идеи:**
- **Санитизация имен:** Удалять или заменять опасные символы
- **Валидация имен:** Проверять имена на валидность
- **Экранирование:** Экранировать специальные символы в JSON

**Реализация:**
```python
import re

def sanitize_preset_name(name: str) -> str:
    """Санитизация имени пресета."""
    # Удаляем опасные символы
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    # Удаляем ведущие/завершающие пробелы
    name = name.strip()
    # Ограничиваем длину
    if len(name) > 200:
        name = name[:200]
    return name
```

---

## 📊 Мониторинг и логирование

### 16. Расширенное логирование

**Проблема:** Сложно отлаживать проблемы импорта без подробных логов.

**Идеи:**
- **Логирование каждого шага:** Логировать каждый шаг импорта
- **Логирование ошибок:** Логировать подробные ошибки с stack trace
- **Логирование статистики:** Логировать статистику импорта (успешно, ошибки, конфликты)

**Реализация:**
```python
import logging

logger = logging.getLogger(__name__)

async def _upsert_filament_preset(
    *,
    payload: OrcaFilamentPresetPayload,
    current_user: User,
    db: AsyncSession,
) -> OrcaSyncResult:
    """Создать или обновить Filament Preset из OrcaSlicer."""
    logger.info(
        f"Importing filament preset: external_id={payload.external_id}, "
        f"name={payload.name}, user_id={current_user.id}"
    )
    
    try:
        # ... импорт ...
        logger.info(
            f"Successfully imported filament preset: external_id={payload.external_id}, "
            f"fhub_id={preset.id}, status={result.status}"
        )
        return result
    except Exception as exc:
        logger.error(
            f"Failed to import filament preset: external_id={payload.external_id}, "
            f"error={exc}",
            exc_info=True
        )
        raise
```

### 17. Метрики и аналитика

**Проблема:** Нет метрик для отслеживания использования импорта.

**Идеи:**
- **Метрики импорта:** Отслеживать количество импортированных профилей
- **Метрики ошибок:** Отслеживать количество ошибок импорта
- **Метрики производительности:** Отслеживать время импорта

**Реализация:**
```python
from prometheus_client import Counter, Histogram

import_requests_total = Counter(
    'filamenthub_import_requests_total',
    'Total number of import requests',
    ['profile_type', 'status']
)

import_duration_seconds = Histogram(
    'filamenthub_import_duration_seconds',
    'Time spent importing profiles',
    ['profile_type']
)

@router.post("/filaments/import")
async def import_filament_presets(...):
    with import_duration_seconds.labels(profile_type='filament').time():
        # ... импорт ...
        import_requests_total.labels(profile_type='filament', status='success').inc()
```

---

## 🧪 Тестирование

### 18. Unit тесты

**Идеи:**
- **Тесты валидации:** Тесты для валидации payload
- **Тесты импорта:** Тесты для импорта профилей
- **Тесты конфликтов:** Тесты для обработки конфликтов
- **Тесты edge cases:** Тесты для edge cases (удаленные бренды, несуществующие принтеры)

### 19. Integration тесты

**Идеи:**
- **Тесты синхронизации:** Тесты для полного цикла синхронизации
- **Тесты производительности:** Тесты для массового импорта
- **Тесты безопасности:** Тесты для проверки прав доступа

---

## 📚 Документация

### 20. Документация для пользователей

**Идеи:**
- **Руководство пользователя:** Руководство по использованию импорта/экспорта
- **FAQ:** Часто задаваемые вопросы
- **Видео-туториалы:** Видео-туториалы по использованию

---

## 🚀 Будущие улучшения

### 21. Версионирование профилей

**Идеи:**
- **Версии профилей:** Хранить историю изменений профилей
- **Откат изменений:** Возможность откатить изменения к предыдущей версии
- **Сравнение версий:** Возможность сравнить разные версии профиля

### 22. Умный импорт

**Идеи:**
- **Автоматическое определение типа материала:** Автоматически определять тип материала из параметров
- **Автоматическое создание бренда:** Автоматически создавать бренд, если его нет
- **Автоматическое связывание профилей:** Автоматически связывать профили (printer + print + filament)

### 23. Пакетный импорт/экспорт

**Идеи:**
- **Экспорт в файл:** Экспорт профилей в файл (JSON, ZIP)
- **Импорт из файла:** Импорт профилей из файла
- **Пакетное редактирование:** Редактирование нескольких профилей одновременно

---

## 🎯 Приоритеты

### Высокий приоритет (нужно реализовать в MVP):
1. ✅ Конфликты при синхронизации (timestamp-based) - **РЕКОМЕНДУЕТСЯ**
2. ⏳ Обработка ошибок и частичный импорт - **РЕКОМЕНДУЕТСЯ**
3. ✅ Лимиты на количество импортируемых профилей (50 профилей) - **РЕКОМЕНДУЕТСЯ**
4. ✅ Система уведомлений (доработка для админа, объявлений, верификации) - **РЕКОМЕНДУЕТСЯ**
5. ✅ Уведомления об импорте профилей - **РЕКОМЕНДУЕТСЯ**

### Средний приоритет (можно реализовать после MVP):
6. ⏳ Валидация данных перед импортом - **ОТЛОЖЕНО**
7. ⏳ Массовый импорт и батчинг - **НЕ НУЖЕН для MVP** (обрабатываем последовательно)
8. ⏳ Кэширование - **ОТЛОЖЕНО**
9. ⏳ Защита от инъекций и XSS - **ЧАСТИЧНО РЕАЛИЗОВАНО** (валидация текста)
10. ⏳ Проверка прав доступа - **РЕАЛИЗОВАНО** (проверка владельца и бренда)
11. ⏳ Прогресс импорта - **ОТЛОЖЕНО** (синхронизация быстрая)

### Низкий приоритет (можно реализовать позже):
12. ⏳ Обработка удаленных брендов - **ОТЛОЖЕНО**
13. ⏳ Обработка несуществующих принтеров - **ОТЛОЖЕНО**
14. ⏳ Маппинг material_type из OrcaSlicer - **ОТЛОЖЕНО** (используем базовый маппинг)
15. ⏳ Обработка специальных символов в именах - **ОТЛОЖЕНО** (Pydantic валидация)
16. ⏳ Расширенное логирование - **ЧАСТИЧНО РЕАЛИЗОВАНО** (базовое логирование)
17. ⏳ Метрики и аналитика - **ОТЛОЖЕНО**
18. ⏳ Тестирование - **ОТЛОЖЕНО** (базовые тесты есть)
19. ⏳ Документация для пользователей - **ОТЛОЖЕНО**
20. ⏳ Версионирование профилей - **ОТЛОЖЕНО** (используем timestamp)
21. ⏳ Умный импорт - **ОТЛОЖЕНО**
22. ⏳ Пакетный импорт/экспорт - **ОТЛОЖЕНО**

---

**Дата создания:** 2025-11-12  
**Статус:** Идеи для обсуждения

