# Анализ синхронизации - ПОСЛЕ

**Дата:** 2025-11-23  
**Пользователь:** admin (id=6)

## 🔍 Что произошло

### 1. Импорт из OrcaSlicer → База данных

**Создано 8 новых черновиков (пресетов):**

| ID | Название | Filament ID | External ID | Sync Enabled | Active |
|----|----------|-------------|-------------|--------------|--------|
| 3752 | FDPlast TPU SOFT @Lizard B2BEE 0.4 nozzle | 53 | PFUS3edc7dfa08ed41 | **True** | False |
| 3753 | Generic ABS template @Ivilol Ulti 1 0.4 nozzle | 54 | PFUSf3801f6d49aebc | **True** | False |
| 3754 | Generic PET template @Ivilol Ulti 1 0.4 nozzle | 55 | PFUSff5c7e17de0433 | **True** | False |
| 3755 | Generic TPU template @Lizard B2BEE 0.4 nozzle | 56 | PFUSbe4b21642de12 | **True** | False |
| 3756 | HTP ABS | 57 | PFUS81c04093a0f5ef | **True** | False |
| 3757 | HTP ABS @Lizard B2BEE 0.5 nozzle | 58 | PFUS4f15885bfa62b0 | **True** | False |
| 3758 | HTP PETG | 67 | PFUSf6e839bf949420 | **True** | False |
| 3759 | HTP PETG @Lizard B2BEE 0.5 nozzle | 62 | PFUScbc04048e9184c | **True** | False |

**Все черновики:**
- `source = 'orcaslicer'` ✅
- `active = False` ✅ (черновики)
- `sync_enabled = True` ✅ (будут синхронизироваться)
- `external_id` заполнен ✅ (ID из OrcaSlicer)

### 2. Экспорт из Базы данных → OrcaSlicer

**Экспортировано 8 пресетов:**
- Все 8 новых черновиков с `sync_enabled=True` были экспортированы обратно в OrcaSlicer
- **Проблема:** Ожидался экспорт только 1 пресета (PolyTerra Green Standard, id=14), но экспортировались все 9 пресетов с `sync_enabled=True` (1 оригинальный + 8 черновиков)

**Сообщения:**
```
Successfully exported 8 filament presets (created).
Successfully exported 8 filament presets (updated). (повторялось много раз)
```

## ⚠️ Обнаруженные проблемы

### Проблема 1: Экспорт всех пресетов с sync_enabled=True
**Ожидалось:** Экспортироваться должен только пресет PolyTerra Green Standard (id=14)  
**Фактически:** Экспортировались все 9 пресетов с `sync_enabled=True` (включая черновики)

**Причина:** Логика экспорта в `export_filament_presets_to_filamenthub_internal()` экспортирует все пресеты с `sync_enabled=True`, включая черновики (`active=False`).

**Решение:** Нужно добавить фильтр `active=True` в экспорт, чтобы не экспортировать черновики.

### Проблема 2: Пресеты с [FilamentHub] не найдены в файловой системе
**Ожидалось:** Пресеты должны появиться в `user/2136879404/filament/` с постфиксом [FilamentHub]  
**Фактически:** Пресеты с [FilamentHub] не найдены в этой директории

**Возможные причины:**
1. Пресеты созданы в другом месте (например, в default/)
2. Пресеты не были созданы (ошибка экспорта)
3. Пресеты были созданы, но без постфикса [FilamentHub]

## 📊 Сравнение ДО и ПОСЛЕ

### База данных

**ДО:**
- 5 пресетов пользователя admin
- 1 пресет с `sync_enabled=True` (PolyTerra Green Standard)
- 0 черновиков

**ПОСЛЕ:**
- 13 пресетов пользователя admin (5 оригинальных + 8 новых черновиков)
- 9 пресетов с `sync_enabled=True` (1 оригинальный + 8 черновиков)
- 8 черновиков (импортированы из OrcaSlicer)

### OrcaSlicer файлы

**ДО:**
- Локальные пресеты без [FilamentHub] в `user/2136879404/filament/`
- Пресеты с [FilamentHub] не найдены

**ПОСЛЕ:**
- Локальные пресеты без изменений
- Пресеты с [FilamentHub] **не найдены** (нужно проверить другие директории)

## 📝 Дополнительные находки

### Brand ID для "User Materials"
- **Ожидалось:** brand_id = 1
- **Фактически:** brand_id = 9
- **Причина:** Бренд был создан автоматически с другим ID (возможно, id=1 был занят)

### .info файлы
- **HTP ABS.info:** 
  - `user_id = 2136879404` ✅ (заполнен)
  - `setting_id = PFUS81c04093a0f5ef` ✅ (заполнен)
  - `sync_info = ` ❌ (пустой)
  - `base_id = ` ❌ (пустой)

### JSON файлы
- **Метки FilamentHub:** Нет меток `fhub_id`, `fhub_source`, `fhub_draft_id` в JSON файлах
- **Причина:** Пресеты были импортированы из OrcaSlicer, но не были экспортированы обратно с метками

## 🔧 Что нужно исправить

1. **Фильтр экспорта:** Добавить `active=True` в условие экспорта в `export_filament_presets_to_filamenthub_internal()`, чтобы не экспортировать черновики
   ```cpp
   // В FilamentHubPanel.cpp, функция export_filament_presets_to_filamenthub_internal()
   // Добавить проверку: if (preset.active == false) continue;
   ```

2. **Проверить создание пресетов:** Убедиться, что пресеты с [FilamentHub] создаются в правильной директории (`user/2136879404/filament/`)
   - Пресеты с [FilamentHub] не найдены в файловой системе
   - Возможно, они создаются в другом месте или не создаются вообще

3. **Проверить метки:** Убедиться, что в JSON файлах появляются метки `fhub_id`, `fhub_source` при экспорте
   - Сейчас метки отсутствуют в JSON файлах

4. **Проверить .info файлы:** Убедиться, что .info файлы обновляются с правильными метаданными
   - `sync_info` пустой (должен содержать информацию о синхронизации)
   - `base_id` пустой (может быть нормально для черновиков)

5. **Логика sync_enabled для черновиков:** Черновики автоматически получают `sync_enabled=True`, что приводит к их экспорту. Нужно решить:
   - Либо не устанавливать `sync_enabled=True` для черновиков по умолчанию
   - Либо фильтровать черновики при экспорте (`active=True`)

---

**Следующий шаг:** 
1. Исправить логику экспорта (добавить фильтр `active=True`)
2. Проверить, где создаются пресеты с [FilamentHub] (возможно, в default/ или другом месте)
3. Проверить логи OrcaSlicer для понимания процесса экспорта

