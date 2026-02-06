# Анализ цепочки синхронизации пресетов FilamentHub

## 🔄 Полная цепочка синхронизации

### 1. Открытие OrcaSlicer → Вкладка FilamentHub

**Текущая реализация:**
```cpp
void FilamentHubPanel::init() {
    // ... создание UI ...
    
    // Если пользователь уже залогинен, автоматически синхронизируем пресеты
    std::string access_token;
    int user_id = 0;
    if (load_auth_token(access_token, user_id)) {
        BOOST_LOG_TRIVIAL(info) << "FilamentHub: User already logged in (ID: " << user_id 
                                 << "), auto-syncing presets on panel load...";
        CallAfter([this]() {
            synchronize_presets(false); // Инкрементальная синхронизация
        });
    }
}
```

**Проблема:** Используется `CallAfter` излишне - коллбэки уже в UI потоке.

**Решение:** Убрать `CallAfter`, вызывать напрямую:
```cpp
if (load_auth_token(access_token, user_id)) {
    synchronize_presets(false); // Прямой вызов, коллбэк будет в UI потоке
}
```

### 2. Пользователь нажимает кнопку "Synchronize"

**Текущая реализация:**
```cpp
void FilamentHubPanel::on_sync_button_click(wxCommandEvent& evt) {
    if (m_is_syncing) {
        return; // Предотвращаем повторный клик
    }
    
    update_sync_button_state(true);
    synchronize_presets(false); // Инкрементальная синхронизация
}
```

**Статус:** ✅ Работает правильно (после упрощения).

### 3. Процесс синхронизации

#### 3.1. Загрузка токена
```cpp
std::string access_token;
int user_id = 0;
if (!load_auth_token(access_token, user_id)) {
    // Показываем ошибку, выходим
    return;
}
```

#### 3.2. Получение `last_sync_time`
```cpp
std::string updated_since;
if (!force_full_sync) {
    updated_since = load_last_sync_time(user_id); // ISO 8601 формат
}
```

#### 3.3. HTTP запрос к API
```cpp
client.get_my_presets(
    access_token,
    updated_since,  // Параметр запроса: ?updated_since=2025-01-15T10:30:00.000000
    on_complete,
    on_error
);
```

**Backend API:** `GET /api/v1/auth/my-presets?updated_since=...`

**Ответ:**
```json
{
    "items": [
        {
            "id": 1,
            "name": "PLA 210°C",
            "updated_at": "2025-01-15T10:30:00.000000",
            ...
        }
    ],
    "total": 1
}
```

#### 3.4. Обработка каждого пресета

**Текущая логика:**
```cpp
for (const auto& preset_json : presets) {
    int preset_id = preset_json["id"];
    std::string preset_name = preset_json["name"];
    
    // Проверяем маппинг (есть ли уже в OrcaSlicer)
    std::string bundle_preset_name = load_preset_mapping(preset_id);
    
    if (bundle_preset_name.empty()) {
        // Пресета нет в маппинге - новый пресет, импортируем
        import_preset_silent(preset_id, preset_name, access_token);
    } else {
        // Пресет уже в маппинге, но API вернул его (значит обновлен)
        // Переимпортируем его
        import_preset_silent(preset_id, preset_name, access_token);
    }
}
```

**❌ КРИТИЧЕСКАЯ ПРОБЛЕМА:** Не проверяется, существует ли пресет в `PresetBundle`!

**Сценарий проблемы:**
1. Пользователь импортирует пресет `preset_id=1` → `bundle_preset_name="PLA 210°C [FilamentHub]`
2. Маппинг сохраняется: `preset_mapping_1 = "PLA 210°C [FilamentHub]"`
3. Пользователь удаляет пресет в OrcaSlicer (в UI пользовательских пресетов)
4. Пресет удаляется из `PresetBundle`, но маппинг остается в `AppConfig`!
5. При следующей синхронизации:
   - Код проверяет маппинг → видит что он есть
   - Пытается переимпортировать пресет
   - Но `import_preset_silent` использует `overwrite=1`, поэтому должно работать
   - **НО:** Если имя пресета изменилось в FilamentHub, маппинг будет указывать на старое имя!

**Решение:**
```cpp
for (const auto& preset_json : presets) {
    int preset_id = preset_json["id"];
    std::string preset_name = preset_json["name"];
    
    // Проверяем маппинг
    std::string bundle_preset_name = load_preset_mapping(preset_id);
    
    // ВАЖНО: Проверяем, существует ли пресет в PresetBundle
    bool preset_exists = false;
    if (!bundle_preset_name.empty()) {
        // Пресет должен быть в пользовательских пресетах (type = Preset::TYPE_FILAMENT)
        PresetBundle* bundle = wxGetApp().preset_bundle;
        if (bundle != nullptr) {
            // Ищем пресет по имени в пользовательских пресетах
            const PresetCollection& filaments = bundle->filaments;
            // Ищем пресет с таким именем
            // TODO: Нужно проверить API PresetCollection для поиска пресета
            // Возможно: filaments.find_preset(bundle_preset_name) или похожее
        }
    }
    
    if (bundle_preset_name.empty() || !preset_exists) {
        // Пресета нет в маппинге ИЛИ пресет был удален → импортируем
        import_preset_silent(preset_id, preset_name, access_token);
    } else {
        // Пресет есть и существует → проверяем, нужно ли обновить
        // API вернул пресет (значит он обновлен после last_sync_time)
        // Переимпортируем для обновления
        import_preset_silent(preset_id, preset_name, access_token);
    }
}
```

**Упрощенное решение (если нет API для проверки существования):**
```cpp
// Всегда импортируем пресеты, которые вернул API
// import_preset_silent использует overwrite=1, поэтому существующие пресеты будут обновлены
// Если пресет был удален, он будет создан заново
import_preset_silent(preset_id, preset_name, access_token);
```

**Но тогда нужно обновлять маппинг после каждого импорта!**

### 4. Импорт пресета (`import_preset_silent`)

#### 4.1. Скачивание JSON из API
```cpp
client.download_profile(preset_id, access_token, on_complete, on_error);
```

**Backend API:** `GET /api/v1/presets/{preset_id}/export/orcaslicer.json`

**Ответ:** JSON профиль OrcaSlicer (см. раздел "Формат JSON")

#### 4.2. Обработка JSON
```cpp
nlohmann::json profile_json = nlohmann::json::parse(json_content);

// Добавляем постфикс [FilamentHub] к имени
std::string original_name = profile_json.value("name", preset_name);
std::string new_name = ensure_filamenthub_postfix(original_name);
profile_json["name"] = new_name;

// Проверяем и исправляем родительский пресет (inherits)
ensure_parent_preset_exists(profile_json);
```

#### 4.3. Импорт в PresetBundle
```cpp
bool success = bundle->import_json_presets(
    substitutions,
    file_path,  // Временный файл с JSON
    override_confirm,  // Автоматически подтверждаем перезапись
    ForwardCompatibilitySubstitutionRule::Enable,
    overwrite,  // 1 = перезаписывать если существует
    import_result
);
```

#### 4.4. Сохранение маппинга
```cpp
if (success || !import_result.empty()) {
    // Сохраняем маппинг preset_id → bundle_preset_name
    save_preset_mapping(preset_id, new_name);  // new_name = "PLA 210°C [FilamentHub]"
}
```

**Проблема:** Если пресет был удален в OrcaSlicer, маппинг не обновляется, остается старое имя.

**Решение:** Всегда обновлять маппинг после успешного импорта (уже реализовано).

### 5. Обновление `last_sync_time`

```cpp
std::time_t now = std::time(nullptr);
std::stringstream ss;
ss << std::put_time(std::gmtime(&now), "%Y-%m-%dT%H:%M:%S.000000");
std::string current_time = ss.str();
save_last_sync_time(user_id, current_time);
```

**Формат:** ISO 8601 (`2025-01-15T10:30:00.000000`)

**Использование:** При следующей синхронизации передается в API как `updated_since`.

## 📋 Формат JSON профиля OrcaSlicer

### Генерация JSON в FilamentHub (backend)

**Файл:** `backend/app/services/orcaslicer_exporter.py`

**Функция:** `preset_to_orcaslicer_json(preset, filament, db)`

**Структура JSON:**
```json
{
    "version": "2.3.0.0",
    "type": "filament",
    "name": "PLA 210°C",
    "from": "user",
    "instantiation": "true",
    "filament_settings_id": ["PLA 210°C"],
    "setting_id": "FHUB000001",
    "filament_id": "FHUB000002",
    "inherits": "Generic PLA @System",
    "nozzle_temperature": ["210"],
    "nozzle_temperature_initial_layer": ["210"],
    "hot_plate_temp": ["60"],
    "hot_plate_temp_initial_layer": ["60"],
    "fan_min_speed": ["50"],
    "fan_max_speed": ["100"],
    "filament_density": ["1.24"],
    "filament_diameter": ["1.75"],
    "filament_cost": ["5"],
    "filament_type": ["PLA"],
    "filament_vendor": ["Polymaker"],
    "filament_retraction_length": ["0.8"],
    "filament_retraction_speed": ["40"],
    "filament_flow_ratio": ["1.0"],
    "default_filament_colour": ["#FF0000"],
    "compatible_printers": []
}
```

**Обязательные поля:**
- `version` - версия профиля OrcaSlicer
- `type` - тип профиля (`"filament"`)
- `name` - имя пресета (будет добавлен постфикс `[FilamentHub]` в C++)
- `from` - источник (`"system"` или `"user"`)
- `instantiation` - флаг инстанцирования (`"true"`)
- `filament_settings_id` - **ОБЯЗАТЕЛЬНО:** OrcaSlicer определяет тип профиля по наличию этого поля
- `inherits` - родительский пресет (например `"Generic PLA @System"`)

**Важные особенности:**
1. Все параметры хранятся как массивы строк (для поддержки мультиэкструдеров)
2. `inherits` должен указывать на существующий системный пресет OrcaSlicer
3. `setting_id` и `filament_id` - уникальные идентификаторы FilamentHub
4. `filament_vendor` - название бренда из FilamentHub

### Валидация JSON в OrcaSlicer

**Импорт:** `PresetBundle::import_json_presets()`

**Проверки:**
1. Наличие обязательных полей (`version`, `type`, `name`, `filament_settings_id`)
2. Существование родительского пресета (`inherits`)
3. Валидность параметров (температуры, скорости и т.д.)

**Если родительский пресет не найден:**
- В `ensure_parent_preset_exists()` происходит поиск альтернативного пресета
- Если не найден - используется fallback `"fdm_filament_common"`

## 🔍 Проблема с удалением пресета

### Сценарий проблемы

1. **Импорт пресета:**
   - Пресет `preset_id=1` импортируется как `"PLA 210°C [FilamentHub]"`
   - Маппинг сохраняется: `preset_mapping_1 = "PLA 210°C [FilamentHub]"`

2. **Удаление пресета в OrcaSlicer:**
   - Пользователь удаляет пресет в UI OrcaSlicer (вкладка пользовательских пресетов)
   - Пресет удаляется из `PresetBundle`
   - **НО:** Маппинг остается в `AppConfig`!

3. **Следующая синхронизация:**
   - API возвращает пресет `preset_id=1` (обновлен)
   - Код проверяет маппинг → видит `"PLA 210°C [FilamentHub]"`
   - Пытается переимпортировать пресет
   - `import_preset_silent` использует `overwrite=1`, поэтому пресет будет создан заново
   - **НО:** Если имя пресета изменилось в FilamentHub (например, `"PLA 215°C"`), маппинг будет указывать на старое имя!

### Решение

**Вариант 1: Проверять существование пресета в PresetBundle**
```cpp
// Проверяем, существует ли пресет в PresetBundle
bool preset_exists = false;
if (!bundle_preset_name.empty()) {
    PresetBundle* bundle = wxGetApp().preset_bundle;
    if (bundle != nullptr) {
        // Ищем пресет по имени в пользовательских пресетах
        // TODO: Нужно найти API для проверки существования пресета
        // Возможно: bundle->filaments.find_preset(bundle_preset_name)
    }
}

if (bundle_preset_name.empty() || !preset_exists) {
    // Пресета нет → импортируем
    import_preset_silent(preset_id, preset_name, access_token);
} else {
    // Пресет существует → проверяем, нужно ли обновить
    // (API вернул пресет, значит он обновлен)
    import_preset_silent(preset_id, preset_name, access_token);
}
```

**Вариант 2: Всегда импортировать пресеты, которые вернул API**
```cpp
// API уже отфильтровал пресеты по updated_since
// Если пресет пришел от API, значит он новый или обновлен
// Всегда импортируем (overwrite=1 обновит существующие, создаст новые)
import_preset_silent(preset_id, preset_name, access_token);
```

**Вариант 3: Удалять маппинг при ошибке импорта**
```cpp
if (!import_preset_silent(preset_id, preset_name, access_token)) {
    // Если импорт не удался, возможно пресет был удален
    // Удаляем маппинг, чтобы при следующей синхронизации пресет был импортирован заново
    remove_preset_mapping(preset_id);
}
```

**Рекомендация:** Использовать **Вариант 2** (всегда импортировать) + обновлять маппинг после успешного импорта (уже реализовано).

## ✅ Чеклист исправлений

- [ ] Убрать `CallAfter` из `init()` (излишне)
- [ ] Упростить `synchronize_presets()` (убрать `CallAfter`, `m_active_syncs`)
- [ ] Исправить обработку пустого списка пресетов (обновлять состояние кнопки)
- [ ] Проверить валидность JSON при экспорте из FilamentHub
- [ ] Убедиться, что маппинг обновляется после каждого импорта
- [ ] Добавить логирование для отладки проблем с маппингом
- [ ] Протестировать сценарий: импорт → удаление → синхронизация

## 🔧 Валидация JSON

### Обязательные поля
- ✅ `version` - версия профиля
- ✅ `type` - тип профиля (`"filament"`)
- ✅ `name` - имя пресета
- ✅ `from` - источник (`"system"` или `"user"`)
- ✅ `instantiation` - флаг инстанцирования
- ✅ `filament_settings_id` - **КРИТИЧНО:** определяет тип профиля
- ✅ `inherits` - родительский пресет

### Валидность параметров
- ✅ Температуры: числа в разумных пределах (0-400°C)
- ✅ Скорости: положительные числа
- ✅ Проценты: 0-100
- ✅ Родительский пресет: должен существовать в OrcaSlicer

### Тестирование
1. Создать пресет в FilamentHub
2. Экспортировать JSON через API
3. Проверить валидность JSON (парсинг, обязательные поля)
4. Импортировать в OrcaSlicer
5. Проверить, что пресет появился в пользовательских пресетах
6. Проверить маппинг в AppConfig
7. Удалить пресет в OrcaSlicer
8. Синхронизировать снова
9. Проверить, что пресет импортирован заново

