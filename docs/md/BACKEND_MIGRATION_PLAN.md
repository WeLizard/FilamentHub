# План переноса логики из C++ на бэкенд

## 🎯 Цель
Перенести бизнес-логику из C++ (OrcaSlicer) на бэкенд (Python/FastAPI), чтобы:
- ✅ Упростить C++ код (с 6241 до ~3000-4000 строк)
- ✅ Централизовать логику на сервере
- ✅ Легче обновлять и тестировать
- ✅ Синхронизация между устройствами пользователя

---

## 📋 Что можно перенести на бэкенд

### 1. ✅ Управление маппингами пресетов (preset_mapping)

**Текущее состояние (C++):**
- Хранится в `AppConfig` локально
- Ключ: `preset_mapping_{preset_id} = "{preset_name} [FilamentHub]"`
- Методы: `save_preset_mapping()`, `load_preset_mapping()`, `remove_preset_mapping()`

**Что сделать на бэкенде:**
```python
# Новая таблица в БД
class OrcaPresetMapping(Base):
    __tablename__ = "orca_preset_mappings"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    preset_id: Mapped[int] = mapped_column(ForeignKey("presets.id"))
    orca_preset_name: Mapped[str]  # Имя пресета в OrcaSlicer
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
```

**API эндпоинты:**
- `GET /api/v1/orcaslicer/mappings` - получить все маппинги пользователя
- `POST /api/v1/orcaslicer/mappings` - создать маппинг
- `PUT /api/v1/orcaslicer/mappings/{preset_id}` - обновить маппинг
- `DELETE /api/v1/orcaslicer/mappings/{preset_id}` - удалить маппинг

**Преимущества:**
- ✅ Синхронизация между устройствами
- ✅ История изменений
- ✅ Легче отлаживать

**C++ код после:**
- Просто вызывает API вместо работы с AppConfig
- ~200 строк → ~50 строк

---

### 2. ✅ Управление last_sync_time

**Текущее состояние (C++):**
- Хранится в `AppConfig` локально
- Ключ: `last_sync_time_{user_id} = "2025-01-15T10:30:00.000000"`
- Методы: `save_last_sync_time()`, `load_last_sync_time()`

**Что сделать на бэкенде:**
```python
# ✅ УЖЕ ЕСТЬ в User модели!
# last_sync_at: Mapped[datetime | None] - время последней синхронизации

# НО: Нужно разделить на 3 типа:
# - last_sync_filament_at
# - last_sync_printer_at  
# - last_sync_print_at

# Или использовать JSON поле для хранения всех типов:
# last_sync_times: Mapped[dict | None] = mapped_column(JSON, nullable=True)
# {"filament": "2025-01-15T10:30:00", "printer": "2025-01-15T10:25:00", ...}
```

**API эндпоинты:**
- `GET /api/v1/auth/my-settings` - получить настройки (включая last_sync_time)
- `PUT /api/v1/auth/my-settings` - обновить last_sync_time
- ✅ Или использовать существующий `GET /api/v1/auth/my-presets?updated_since=...`

**Преимущества:**
- ✅ Синхронизация между устройствами
- ✅ Можно использовать для аналитики
- ✅ Автоматическое обновление на сервере

**C++ код после:**
- Просто читает из API вместо AppConfig
- ~100 строк → ~30 строк

---

### 3. ✅ Управление deleted_preset_action

**Текущее состояние (C++):**
- Хранится в `AppConfig` локально
- Ключ: `deleted_preset_action = "ask" | "import" | "delete" | "skip"`
- Методы: `get_deleted_preset_action()`, `set_deleted_preset_action()`, `ask_deleted_preset_action()`

**Что сделать на бэкенде:**
```python
# ✅ УЖЕ ЕСТЬ в User модели!
# deleted_preset_rule: Mapped[str | None]
# Значения: "always_restore", "always_delete", "always_ask", 
#          "restore_created_delete_saved", "restore_created_ask_saved"

# ✅ УЖЕ ЕСТЬ в orcaslicer_service.py!
# get_user_deleted_preset_rule(), save_user_deleted_preset_rule()
```

**API эндпоинты:**
- `GET /api/v1/auth/my-settings` - получить deleted_preset_action
- `PUT /api/v1/auth/my-settings` - обновить deleted_preset_action

**Преимущества:**
- ✅ Уже частично реализовано!
- ✅ Единые настройки для всех устройств

**C++ код после:**
- Просто читает из API
- ~150 строк → ~30 строк

---

### 4. ✅ Валидация и обработка пресетов

**Текущее состояние (C++):**
- `ensure_parent_preset_exists()` - проверка родительского пресета
- `ensure_filamenthub_postfix()` - добавление [FilamentHub] к имени
- Логика обработки `inherits` в JSON

**Что сделать на бэкенде:**
- ✅ Уже реализовано в `orca_sync.py`!
- Валидация происходит на бэкенде при импорте/экспорте
- C++ просто отправляет JSON и получает результат

**Можно улучшить:**
- Добавить эндпоинт для валидации пресета перед импортом:
  - `POST /api/v1/orcaslicer/validate-preset` - проверить валидность JSON

**C++ код после:**
- Убрать дублирующую валидацию
- ~300 строк → ~100 строк

---

### 5. ✅ Проверка разрешений

**Текущее состояние (C++):**
- `check_user_permissions()` - проверяет разрешения через API
- Вызывается перед синхронизацией/экспортом

**Что сделать на бэкенде:**
- ✅ Уже реализовано! Проверка происходит на бэкенде через JWT токен
- C++ просто получает ошибку 403 если нет прав

**Можно улучшить:**
- Добавить эндпоинт для проверки разрешений:
  - `GET /api/v1/auth/permissions` - получить список разрешений пользователя

**C++ код после:**
- Упростить проверку разрешений
- ~100 строк → ~50 строк

---

### 6. ✅ Обработка удаленных пресетов

**Текущее состояние (C++):**
- Обнаружение удаленных пресетов (есть в FilamentHub, но нет локально)
- Отправка списка удаленных пресетов на бэкенд
- Обработка ответа от бэкенда

**Что сделать на бэкенде:**
- ✅ Уже реализовано в `orca_sync.py`!
- Эндпоинт: `POST /api/v1/orcaslicer/deleted-presets`
- Обрабатывает удаленные пресеты согласно `deleted_preset_action`

**C++ код после:**
- Упростить логику отправки
- ~200 строк → ~100 строк

---

### 7. ❌ НЕ переносить: UI и работа с PresetBundle

**Должно остаться в C++:**
- ✅ UI (WebView, кнопки, панели) - ~800 строк
- ✅ Работа с PresetBundle (импорт/экспорт) - ~1000 строк
- ✅ Очередь импорта (локальная) - ~300 строк
- ✅ Обработка событий WebView - ~200 строк
- ✅ Локальное кеширование для офлайн работы

**Итого в C++:** ~2300-2500 строк (было 6241)

---

## 📊 Итоговая оценка

### Что переносится на бэкенд:

| Компонент | Строк в C++ | Строк после | Экономия |
|-----------|-------------|-------------|----------|
| preset_mapping | ~200 | ~50 | -150 |
| last_sync_time | ~100 | ~30 | -70 |
| deleted_preset_action | ~150 | ~30 | -120 |
| Валидация пресетов | ~300 | ~100 | -200 |
| Проверка разрешений | ~100 | ~50 | -50 |
| Обработка удаленных | ~200 | ~100 | -100 |
| **ИТОГО** | **~1050** | **~360** | **-690** |

### Новые таблицы в БД:

1. `orca_preset_mappings` - маппинги пресетов (НОВОЕ)
2. ~~`user_settings`~~ - НЕ НУЖНО! Уже есть в `users`:
   - ✅ `last_sync_at` - время последней синхронизации
   - ✅ `deleted_preset_rule` - правило обработки удаленных пресетов
   - ⚠️ Нужно только разделить `last_sync_at` на 3 типа (filament/printer/print)

### Новые API эндпоинты:

1. `GET /api/v1/orcaslicer/mappings` - получить маппинги
2. `POST /api/v1/orcaslicer/mappings` - создать маппинг
3. `PUT /api/v1/orcaslicer/mappings/{preset_id}` - обновить маппинг
4. `DELETE /api/v1/orcaslicer/mappings/{preset_id}` - удалить маппинг
5. `GET /api/v1/auth/my-settings` - получить настройки
6. `PUT /api/v1/auth/my-settings` - обновить настройки
7. `GET /api/v1/auth/permissions` - получить разрешения (опционально)
8. `POST /api/v1/orcaslicer/validate-preset` - валидация пресета (опционально)

---

## 🚀 План реализации

### Этап 1: Расширение User модели (30 мин - 1 час)
1. Создать миграцию для разделения `last_sync_at` на 3 типа:
   - `last_sync_filament_at`
   - `last_sync_printer_at`
   - `last_sync_print_at`
2. Или использовать JSON поле `last_sync_times` (проще)
3. Создать эндпоинт `GET /api/v1/auth/my-settings` (опционально)
4. Обновить C++ код для использования API вместо AppConfig

### Этап 2: OrcaPresetMapping (2-3 часа)
1. Создать миграцию для `orca_preset_mappings`
2. Создать модель `OrcaPresetMapping`
3. Создать эндпоинты для маппингов
4. Обновить C++ код для использования API

### Этап 3: Упрощение C++ кода (1-2 часа)
1. Убрать работу с AppConfig для маппингов
2. Убрать работу с AppConfig для last_sync_time
3. Упростить валидацию (полагаться на бэкенд)

**Итого:** 4-7 часов работы

---

## ✅ Преимущества

1. **Упрощение C++ кода:** 6241 → ~3500-4000 строк (-40%)
2. **Централизация логики:** Вся бизнес-логика на бэкенде
3. **Синхронизация:** Настройки синхронизируются между устройствами
4. **Тестируемость:** Легче тестировать на бэкенде
5. **Обновляемость:** Можно обновлять логику без пересборки OrcaSlicer

---

## ⚠️ Риски

1. **Офлайн работа:** Нужно кешировать маппинги локально
2. **Производительность:** Дополнительные API запросы
3. **Совместимость:** Нужно поддерживать старые версии OrcaSlicer

---

## 🎯 Рекомендация

**Приоритет:** Высокий (значительно упростит код)

**Когда делать:** После завершения текущих фич синхронизации

**Порядок:** Сначала UserSettings, потом OrcaPresetMapping

