# Анализ проблем синхронизации FilamentHub ↔ OrcaSlicer

**Дата:** 2025-11-23  
**Статус:** 🔥 КРИТИЧЕСКИЕ ПРОБЛЕМЫ ОБНАРУЖЕНЫ

---

## 🚨 КРИТИЧЕСКАЯ ПРОБЛЕМА #1: Разошедшиеся миграции БД

### Симптомы:
```bash
alembic heads
# Результат: 5 головных ревизий вместо 1!
feedback_table_enum (head)
add_last_sync_at_to_users (head)
a1b2c3d4e5f9 (head)
c3d4e5f6a7b0 (head)
e01bc3b29297 (head)
```

### Что это значит:
- Alembic миграции разошлись на 5 независимых веток
- БД в несогласованном состоянии
- Невозможно корректно применять новые миграции
- При попытке `alembic upgrade head` будет ошибка: "Multiple heads detected"

### Причина:
Множественные миграции создавались параллельно без согласования `down_revision`.

### Решение:
Необходимо создать **объединяющую миграцию** (merge migration):

```bash
cd backend
alembic merge -m "merge_multiple_heads" feedback_table_enum add_last_sync_at_to_users a1b2c3d4e5f9 c3d4e5f6a7b0 e01bc3b29297
alembic upgrade head
```

---

## 🚨 КРИТИЧЕСКАЯ ПРОБЛЕМА #2: Отсутствие постоянных меток в JSON/INFO файлах

### Симптомы:
- Профили FilamentHub и пользовательские профили OrcaSlicer не различаются надежно
- Постфикс `[FilamentHub]` может быть удален пользователем
- Метки `fhub_id`, `fhub_source` добавляются в JSON, но могут затираться при экспорте/импорте OrcaSlicer

### Что происходит сейчас:

#### В `.json` файле:
```json
{
  "name": "My Preset [FilamentHub]",
  "fhub_id": 123,  // ← НЕ сохраняется OrcaSlicer при редактировании!
  "fhub_source": "filamenthub",  // ← НЕ сохраняется OrcaSlicer при редактировании!
  "nozzle_temperature": [245],
  ...
}
```

#### В `.info` файле:
```ini
sync_info =   # ← Пустое поле (можем использовать!)
user_id = 2136879404
setting_id =   # ← Пустое поле (можем использовать!)
base_id = OGFSA04
updated_time = 1760287771
```

### Решение:
Использовать `.info` файл как **постоянное хранилище меток**:

```ini
sync_info = fhub:123:filamenthub  # format: fhub:<preset_id>:<source>
setting_id = FHUB000123  # FilamentHub preset ID в формате FHUB + zero-padded ID
user_id = 2136879404
base_id = OGFSA04
updated_time = 1760287771
```

**Почему `.info`:**
- OrcaSlicer не перезаписывает `.info` файл при редактировании пресета
- `.info` файл сохраняется даже после экспорта/импорта
- Поля `sync_info` и `setting_id` пустые и доступны для нас

---

## ⚠️ ПРОБЛЕМА #3: Нет защиты от дубликатов при многократной синхронизации

### Симптомы:
- При многократной синхронизации (OrcaSlicer → FilamentHub → OrcaSlicer) могут создаваться дубликаты
- Не ясно: это новый пресет или обновление существующего?

### Текущая логика идентификации:
```python
# backend/app/api/v1/endpoints/orca_sync.py, строка 1589-1598

# Приоритет 1: fhub_id из payload (явное указание)
if payload.fhub_id:
    preset = await db.get(Preset, payload.fhub_id)

# Приоритет 2: fhub_id из JSON metadata
fhub_id_from_metadata = orcaslicer_settings.get("fhub_id")
if fhub_id_from_metadata:
    preset = await db.get(Preset, fhub_id_from_metadata)

# Приоритет 3: external_id + user_id
# ... НО! external_id может меняться при редактировании в OrcaSlicer!
```

### Проблема:
1. **external_id НЕ постоянный** - OrcaSlicer может его изменить при создании копии пресета
2. **fhub_id в JSON НЕ сохраняется** - OrcaSlicer при редактировании перезаписывает JSON и теряет кастомные поля
3. **Постфикс [FilamentHub] НЕ надежен** - пользователь может удалить его

### Решение:
1. Хранить `fhub_id` в `.info` файле (`sync_info` и `setting_id`)
2. При импорте из OrcaSlicer читать `.info` файл и извлекать `fhub_id`
3. При экспорте в OrcaSlicer записывать `fhub_id` в `.info` файл
4. При проверке дубликатов приоритетно использовать `fhub_id` из `.info`

---

## ⚠️ ПРОБЛЕМА #4: Импорт чужих профилей как черновиков (не завершено)

### Требование:
- Профили из OrcaSlicer без `[FilamentHub]` постфикса → импортировать как черновики (active=false, filament_id=null)
- Пользователь потом может превратить черновик в полноценный пресет

### Текущая реализация:
```python
# backend/app/api/v1/endpoints/orca_sync.py, строка 1447-1554

is_our_preset = "@FilamentHub" in preset_name

if is_our_preset:
    # Ищем существующий filament или создаем новый
    filament = await _find_existing_filament(...)
else:
    # Для черновиков НЕ создаем Filament
    filament = None
    # Preset с filament_id=None и active=False
```

### Проблемы:
1. **Метка после первого импорта:** После импорта чужого профиля как черновика, мы должны пометить его в `.info` файле как "уже импортирован" (`fhub_draft_id`)
2. **Повторный импорт:** При повторной синхронизации не создавать дубликат черновика
3. **UI для активации:** Нужен UI на сайте для превращения черновика в полноценный пресет

### Решение:
1. При создании черновика записать в `.info` файл:
   ```ini
   sync_info = fhub_draft:<draft_id>:imported
   ```
2. При повторном импорте проверять `fhub_draft_id` и обновлять существующий черновик
3. На сайте добавить страницу "Черновики" где можно активировать черновик

---

## ⚠️ ПРОБЛЕМА #5: Бесконечные уведомления (не подтверждено, но подозрение)

### Симптомы (со слов пользователя):
- В OrcaSlicer сотнями сыплются уведомления
- Как будто бесконечно пытается что-то синхронизировать

### Возможные причины:

#### Теория 1: Цикл синхронизации
```
1. User clicks "Synchronize" in OrcaSlicer
2. Import presets from FilamentHub → OrcaSlicer
3. load_current_presets() called (line 2834)
4. [HYPOTHESIS] load_current_presets() triggers export back to FilamentHub?
5. Backend detects changes → notifies user
6. OrcaSlicer polls notifications → detects new notification
7. Shows notification → repeat from step 3?
```

**Нужно проверить:**
- Что делает `wxGetApp().load_current_presets()` в GUI_App.cpp?
- Есть ли автоматический экспорт после `load_current_presets()`?

#### Теория 2: Бесконечный polling уведомлений
```cpp
// FilamentHubPanel.cpp, строка 2873-2875
// После завершения синхронизации
update_unread_notifications_count();
```

Функция `update_unread_notifications_count()` делает HTTP запрос к `/api/v1/notifications/unread-count`. Если она вызывается слишком часто или в цикле - это может вызывать сотни уведомлений.

**Нужно проверить:**
- Сколько раз вызывается `update_unread_notifications_count()` за синхронизацию?
- Есть ли таймер/интервал для polling'а уведомлений?

#### Теория 3: Уведомления о deleted presets
При синхронизации проверяется список удаленных пресетов (не синхронизированных):
```python
# backend/app/api/v1/endpoints/orca_sync.py, строка 2205-2351
@router.post("/deleted-presets", ...)
async def report_deleted_presets(...)
```

Если логика определения "удаленных" пресетов неправильная - может создавать уведомления на каждом цикле.

### Решение:
1. Добавить **debounce** для `update_unread_notifications_count()` - не чаще чем раз в 10 секунд
2. Добавить **флаг** для предотвращения автоматического экспорта после синхронизации
3. Добавить **детальное логирование** для отладки:
   ```cpp
   BOOST_LOG_TRIVIAL(info) << "FilamentHub: [NOTIFICATION] update_unread_notifications_count() called from: " << __FUNCTION__;
   ```
4. Проверить логику `load_current_presets()` - не вызывает ли она экспорт

---

## 📊 План исправлений (приоритетный)

### 🔥 КРИТИЧНО (исправить немедленно):

1. **Исправить миграции БД:**
   ```bash
   cd backend
   alembic merge -m "merge_multiple_heads" <head1> <head2> <head3> <head4> <head5>
   alembic upgrade head
   ```

2. **Добавить постоянные метки в .info файл:**
   - Backend: При экспорте записывать `fhub_id` в `.info` (`sync_info`, `setting_id`)
   - OrcaSlicer: При импорте читать `fhub_id` из `.info`
   - OrcaSlicer: При экспорте обратно отправлять `fhub_id` из `.info`

### ⚠️ ВАЖНО (исправить в течение недели):

3. **Исправить логику идентификации профилей:**
   - Приоритет 1: `fhub_id` из `.info` файла
   - Приоритет 2: `fhub_id` из JSON metadata
   - Приоритет 3: `external_id` + `user_id` (только для fallback)

4. **Завершить импорт чужих профилей как черновиков:**
   - Добавить `fhub_draft_id` в `.info` файл
   - Проверять при повторном импорте
   - UI для активации черновиков на сайте

5. **Найти причину бесконечных уведомлений:**
   - Добавить детальное логирование
   - Проверить `load_current_presets()` не вызывает ли экспорт
   - Добавить debounce для `update_unread_notifications_count()`

### 📝 ЖЕЛАТЕЛЬНО (можно отложить):

6. **Улучшить обработку ошибок:**
   - Более информативные сообщения об ошибках
   - Показывать пользователю что именно пошло не так

7. **Добавить тесты:**
   - Unit тесты для логики синхронизации
   - Integration тесты для полного цикла (импорт → экспорт → импорт)

---

## 🔧 Реализация: Исправление меток в .info файле

### Backend изменения:

#### 1. Экспорт пресета → OrcaSlicer (добавить .info файл)

**Файл:** `backend/app/services/orcaslicer_exporter.py`

**Новая функция:** `preset_to_orcaslicer_info(preset: Preset) -> str`

```python
def preset_to_orcaslicer_info(preset: Preset) -> str:
    """
    Генерировать .info файл для пресета FilamentHub.
    
    Формат .info файла:
    sync_info = fhub:<preset_id>:<source>
    user_id = <orcaslicer_user_id>
    setting_id = FHUB<preset_id_zero_padded>
    base_id = <base_preset_id>
    updated_time = <unix_timestamp>
    """
    # sync_info: Метка FilamentHub (приоритетный источник истины)
    sync_info = f"fhub:{preset.id}:filamenthub"
    
    # setting_id: FilamentHub preset ID в формате FHUB + zero-padded
    setting_id = f"FHUB{preset.id:06d}"
    
    # base_id: Базовый профиль (из inherits)
    # Извлекаем из orcaslicer_settings если есть, иначе из material_type
    orcaslicer_settings = preset.orcaslicer_settings or {}
    inherits = orcaslicer_settings.get("inherits", "fdm_filament_common")
    base_id = inherits
    
    # updated_time: Unix timestamp обновления
    import time
    updated_time = int(preset.updated_at.timestamp())
    
    # user_id: Оставляем пустым (OrcaSlicer заполнит сам)
    
    return f"""sync_info = {sync_info}
user_id = 
setting_id = {setting_id}
base_id = {base_id}
updated_time = {updated_time}
"""
```

#### 2. Импорт пресета ← OrcaSlicer (читать .info файл)

**Файл:** `backend/app/api/v1/endpoints/orca_sync.py`

**Изменение функции:** `_upsert_filament_preset()`

```python
async def _upsert_filament_preset(...) -> OrcaSyncResult:
    # ... существующий код ...
    
    # НОВОЕ: Читаем .info файл (если есть в payload)
    info_content = payload.info_content  # Добавить в schema OrcaFilamentPresetPayload
    fhub_id_from_info = None
    
    if info_content:
        # Парсим .info файл
        for line in info_content.split('\n'):
            if line.startswith('sync_info = '):
                sync_info = line.split(' = ')[1].strip()
                # Формат: fhub:<preset_id>:<source>
                if sync_info.startswith('fhub:'):
                    parts = sync_info.split(':')
                    if len(parts) >= 2:
                        try:
                            fhub_id_from_info = int(parts[1])
                        except ValueError:
                            pass
    
    # Приоритет идентификации:
    # 1. fhub_id из .info файла (самый надежный)
    # 2. fhub_id из payload (явное указание)
    # 3. fhub_id из JSON metadata
    # 4. external_id + user_id (fallback)
    
    if fhub_id_from_info:
        preset = await db.get(Preset, fhub_id_from_info)
        if preset:
            logger.info(f"Found preset by fhub_id from .info file: {fhub_id_from_info}")
    elif payload.fhub_id:
        preset = await db.get(Preset, payload.fhub_id)
        # ... остальная логика ...
```

### OrcaSlicer изменения:

#### 1. Экспорт пресета → FilamentHub (отправлять .info содержимое)

**Файл:** `docs/OrcaSlicer/src/slic3r/GUI/FilamentHubPanel.cpp`

**Функция:** `export_filament_presets_to_filamenthub_internal()`, строка ~4800

```cpp
// Читаем .info файл
boost::filesystem::path info_file = preset.file;
info_file.replace_extension(".info");

std::string info_content;
if (boost::filesystem::exists(info_file)) {
    try {
        std::ifstream ifs(info_file.string());
        if (ifs.is_open()) {
            std::stringstream buffer;
            buffer << ifs.rdbuf();
            info_content = buffer.str();
            ifs.close();
            
            BOOST_LOG_TRIVIAL(debug) << "FilamentHub: Read .info file for preset: " 
                                     << preset.name << " (file: " << info_file.string() << ")";
        }
    } catch (const std::exception& e) {
        BOOST_LOG_TRIVIAL(warning) << "FilamentHub: Failed to read .info file: " << e.what();
    }
}

// Добавляем info_content в preset_data
if (!info_content.empty()) {
    preset_data["info_content"] = info_content;
}
```

#### 2. Импорт пресета ← FilamentHub (записывать .info файл)

**Файл:** `docs/OrcaSlicer/src/slic3r/GUI/FilamentHubPanel.cpp`

**Функция:** `update_preset_info_file()`, строка ~6200

```cpp
void FilamentHubPanel::update_preset_info_file(int preset_id, const std::string& preset_name, const std::string& access_token)
{
    // ... существующий код для скачивания .info файла через API ...
    
    // НОВОЕ: API endpoint для получения .info файла
    std::string endpoint = "/api/v1/orcaslicer/presets/" + std::to_string(preset_id) + "/info";
    
    client.get(
        endpoint,
        access_token,
        // on_complete: успешно скачан .info файл
        [this, preset_name](std::string body, unsigned http_status) {
            if (http_status == 200) {
                // Записываем .info файл
                PresetBundle* bundle = wxGetApp().preset_bundle;
                if (bundle == nullptr) return;
                
                // Ищем пресет по имени
                Preset* preset = bundle->filaments.find_preset(preset_name, false);
                if (preset && !preset->file.empty()) {
                    boost::filesystem::path info_file = preset->file;
                    info_file.replace_extension(".info");
                    
                    try {
                        std::ofstream ofs(info_file.string());
                        if (ofs.is_open()) {
                            ofs << body;  // body содержит содержимое .info файла
                            ofs.close();
                            
                            BOOST_LOG_TRIVIAL(info) << "FilamentHub: Updated .info file for preset: " 
                                                   << preset_name << " (file: " << info_file.string() << ")";
                        }
                    } catch (const std::exception& e) {
                        BOOST_LOG_TRIVIAL(error) << "FilamentHub: Failed to write .info file: " << e.what();
                    }
                }
            }
        },
        // on_error
        [](std::string body, std::string error, unsigned http_status) {
            BOOST_LOG_TRIVIAL(warning) << "FilamentHub: Failed to get .info file: " << error;
        }
    );
}
```

#### 3. Новый API endpoint: GET /api/v1/orcaslicer/presets/{id}/info

**Файл:** `backend/app/api/v1/endpoints/orca_sync.py`

```python
@router.get(
    "/presets/{preset_id}/info",
    response_class=PlainTextResponse,
    status_code=status.HTTP_200_OK,
)
async def get_preset_info_file(
    preset_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> str:
    """
    Получить .info файл для пресета FilamentHub.
    
    Используется OrcaSlicer для записи меток после импорта пресета.
    """
    preset = await db.get(Preset, preset_id)
    if not preset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Preset not found",
        )
    
    # Проверяем права доступа (публичный пресет или свой пресет)
    if not preset.active and preset.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    
    # Генерируем .info файл
    from app.services.orcaslicer_exporter import preset_to_orcaslicer_info
    info_content = preset_to_orcaslicer_info(preset)
    
    return info_content
```

---

## 🎯 Итого

**Обнаружено 5 проблем:**
1. 🔥 КРИТИЧНО: 5 головных ревизий в alembic (миграции разошлись)
2. 🔥 КРИТИЧНО: Отсутствие постоянных меток в `.info` файле
3. ⚠️ ВАЖНО: Нет защиты от дубликатов при многократной синхронизации
4. ⚠️ ВАЖНО: Импорт чужих профилей как черновиков не завершен
5. ⚠️ ВАЖНО: Возможный цикл синхронизации вызывает бесконечные уведомления

**Следующие шаги:**
1. Объединить миграции БД (merge)
2. Реализовать метки в `.info` файле (backend + OrcaSlicer)
3. Протестировать полный цикл синхронизации
4. Найти и исправить причину бесконечных уведомлений

**Оценка времени:**
- Исправление миграций: 30 минут
- Метки в `.info`: 2-3 часа
- Тестирование: 1-2 часа
- Поиск уведомлений: 1-2 часа

**Итого:** ~6-8 часов работы

