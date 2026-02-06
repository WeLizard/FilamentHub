# Отчет сравнения синхронизации ДО и ПОСЛЕ

**Дата:** 2025-11-23  
**Пользователь:** admin (id=6, email=admin@filamenthub.ru)

---

## 📊 Сводка изменений

### База данных

| Параметр | ДО | ПОСЛЕ | Изменение |
|----------|-----|-------|-----------|
| Всего пресетов пользователя | 5 | 13 | +8 (новые черновики) |
| Пресетов с sync_enabled=True | 1 | 9 | +8 (все черновики получили sync_enabled=True) |
| Черновиков (active=False) | 0 | 8 | +8 (импортированы из OrcaSlicer) |
| Филаментов в "User Materials" | 0 | 8 | +8 (созданы автоматически) |

### OrcaSlicer файлы

| Параметр | ДО | ПОСЛЕ | Изменение |
|----------|-----|-------|-----------|
| Пресетов с [FilamentHub] в user/2136879404/filament/ | 0 | 0 | Без изменений |
| Локальных пресетов | ~14 | ~14 | Без изменений |

---

## 🔍 Детальный анализ

### 1. Импорт из OrcaSlicer → База данных ✅

**Успешно импортировано 8 пресетов:**

Все пресеты из `user/2136879404/filament/base/` были импортированы как черновики:
1. FDPlast TPU SOFT @Lizard B2BEE 0.4 nozzle
2. Generic ABS template @Ivilol Ulti 1 0.4 nozzle
3. Generic PET template @Ivilol Ulti 1 0.4 nozzle
4. Generic TPU template @Lizard B2BEE 0.4 nozzle
5. HTP ABS
6. HTP ABS @Lizard B2BEE 0.5 nozzle
7. HTP PETG
8. HTP PETG @Lizard B2BEE 0.5 nozzle

**Характеристики импортированных пресетов:**
- ✅ `source = 'orcaslicer'`
- ✅ `active = False` (черновики)
- ✅ `external_id` заполнен (ID из OrcaSlicer)
- ⚠️ `sync_enabled = True` (автоматически установлено, что приводит к экспорту)

**Созданные филаменты:**
- Все 8 филаментов созданы в бренде "User Materials" (brand_id=9, не 1)
- Все филаменты `active = False` (черновики)

### 2. Экспорт из Базы данных → OrcaSlicer ⚠️

**Проблема:** Экспортировались все 9 пресетов с `sync_enabled=True`, включая 8 черновиков.

**Ожидалось:**
- Экспортироваться должен только 1 пресет: PolyTerra Green Standard (id=14, sync_enabled=True, active=True)

**Фактически:**
- Экспортировались все 9 пресетов с `sync_enabled=True`:
  - 1 оригинальный (PolyTerra Green Standard, active=True) ✅
  - 8 черновиков (active=False) ❌ (не должны экспортироваться)

**Сообщения в OrcaSlicer:**
```
Successfully exported 8 filament presets (created).
Successfully exported 8 filament presets (updated). (повторялось много раз)
```

**Проблема:** Логика экспорта не фильтрует черновики (`active=False`).

### 3. Пресеты с [FilamentHub] в файловой системе ❌

**Ожидалось:**
- Пресеты должны появиться в `user/2136879404/filament/` с постфиксом [FilamentHub]
- JSON файлы должны содержать метки `fhub_id`, `fhub_source`
- .info файлы должны содержать `sync_info`, `user_id`, `setting_id`

**Фактически:**
- Пресеты с [FilamentHub] **не найдены** в `user/2136879404/filament/`
- JSON файлы не содержат меток `fhub_id`, `fhub_source`
- .info файлы частично заполнены:
  - `user_id = 2136879404` ✅
  - `setting_id = PFUS...` ✅
  - `sync_info = ` ❌ (пустой)
  - `base_id = ` ❌ (пустой)

**Возможные причины:**
1. Пресеты создаются в другом месте (например, в default/)
2. Пресеты не создаются из-за ошибки в логике экспорта
3. Пресеты создаются без постфикса [FilamentHub]

---

## ⚠️ Обнаруженные проблемы

### Проблема 1: Экспорт черновиков
**Описание:** Все черновики с `sync_enabled=True` экспортируются обратно в OrcaSlicer, хотя они должны быть только импортированы.

**Причина:** В функции `export_filament_presets_to_filamenthub_internal()` нет фильтра по `active=True`.

**Решение:** Добавить проверку `if (preset.active == false) continue;` перед экспортом.

**Файл:** `docs/OrcaSlicer/src/slic3r/GUI/FilamentHubPanel.cpp`  
**Функция:** `export_filament_presets_to_filamenthub_internal()`  
**Строка:** ~4715-4720 (в цикле for по пресетам)

### Проблема 2: Пресеты с [FilamentHub] не создаются
**Описание:** После экспорта пресеты с постфиксом [FilamentHub] не появляются в файловой системе OrcaSlicer.

**Возможные причины:**
1. Экспорт происходит, но пресеты создаются в другом месте
2. Ошибка в логике создания пресетов в OrcaSlicer
3. Пресеты создаются, но без постфикса [FilamentHub]

**Решение:** Проверить логи OrcaSlicer и код создания пресетов при экспорте.

### Проблема 3: sync_enabled для черновиков
**Описание:** Черновики автоматически получают `sync_enabled=True`, что приводит к их экспорту.

**Решение:** 
- Либо не устанавливать `sync_enabled=True` для черновиков по умолчанию
- Либо фильтровать черновики при экспорте (`active=True`)

### Проблема 4: Метки FilamentHub в JSON
**Описание:** В JSON файлах отсутствуют метки `fhub_id`, `fhub_source`, `fhub_draft_id`.

**Причина:** Пресеты импортированы из OrcaSlicer, но при экспорте обратно метки не добавляются.

**Решение:** Убедиться, что при экспорте в `preset_to_orcaslicer_json()` добавляются метки `fhub_id` и `fhub_source`.

---

## ✅ Что работает правильно

1. **Импорт из OrcaSlicer:** ✅ Работает корректно
   - Пресеты импортируются как черновики
   - Создаются филаменты в бренде "User Materials"
   - Заполняются `external_id`, `source`

2. **Создание черновиков:** ✅ Работает корректно
   - Черновики создаются с `active=False`
   - Филаменты создаются автоматически

3. **.info файлы:** ✅ Частично работает
   - `user_id` и `setting_id` заполняются
   - `sync_info` и `base_id` остаются пустыми

---

## 🔧 Рекомендации по исправлению

### Приоритет 1: Исправить экспорт черновиков
```cpp
// В FilamentHubPanel.cpp, функция export_filament_presets_to_filamenthub_internal()
// После строки 4719 (проверка is_system):
if (preset.is_system) {
    continue;
}

// ДОБАВИТЬ:
// Пропускаем черновики (active=false) - они не должны экспортироваться
if (!preset.active) {
    BOOST_LOG_TRIVIAL(debug) << "FilamentHub: Skipping inactive preset (draft): " << preset.name;
    continue;
}
```

### Приоритет 2: Проверить создание пресетов с [FilamentHub]
- Проверить логи OrcaSlicer при экспорте
- Убедиться, что пресеты создаются в правильной директории
- Проверить, что постфикс [FilamentHub] добавляется к именам

### Приоритет 3: Добавить метки в JSON при экспорте
- Убедиться, что `preset_to_orcaslicer_json()` добавляет `fhub_id` и `fhub_source`
- Проверить, что метки сохраняются в JSON файлах

---

**Следующий шаг:** Исправить логику экспорта (добавить фильтр `active=True`) и проверить создание пресетов с [FilamentHub].


