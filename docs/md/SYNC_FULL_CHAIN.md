# Полная цепочка синхронизации пресетов FilamentHub

## 🎯 Цель

Синхронизировать пресеты филаментов из FilamentHub в OrcaSlicer:
1. При открытии вкладки FilamentHub (если пользователь авторизован)
2. При нажатии кнопки "Synchronize"
3. После успешной авторизации

## 📋 Полная цепочка от начала до конца

### 1. Открытие OrcaSlicer → Переход на вкладку FilamentHub

**Шаг 1.1: Инициализация панели**
```cpp
void FilamentHubPanel::init() {
    // ... создание UI элементов ...
    
    // Загружаем токен из AppConfig
    std::string access_token;
    int user_id = 0;
    if (load_auth_token(access_token, user_id)) {
        // Пользователь уже авторизован
        // Автоматически запускаем синхронизацию
        CallAfter([this]() {
            synchronize_presets(false); // Инкрементальная синхронизация
        });
    }
}
```

**Что происходит:**
- Загружается токен из `AppConfig` (секция `filamenthub`, ключ `access_token`)
- Если токен найден → автоматически запускается синхронизация
- Если токен не найден → показывается форма входа

### 2. Авторизация пользователя

**Шаг 2.1: Пользователь вводит логин/пароль в WebView**
- WebView загружает фронтенд FilamentHub (`http://localhost:3000`)
- Пользователь вводит логин/пароль
- Фронтенд отправляет запрос к API: `POST /api/v1/auth/login`

**Шаг 2.2: Backend возвращает токен**
```json
{
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "refresh_token": "...",
    "token_type": "bearer",
    "user_id": 1
}
```

**Шаг 2.3: Фронтенд отправляет сообщение в OrcaSlicer**
```javascript
window.postMessage({
    command: "login_success",
    data: {
        access_token: "...",
        user_id: 1
    }
}, "*");
```

**Шаг 2.4: OrcaSlicer получает сообщение и сохраняет токен**
```cpp
void FilamentHubPanel::OnScriptMessage(wxWebViewEvent& evt) {
    if (command == "login_success") {
        std::string access_token = j["data"]["access_token"].get<std::string>();
        int user_id = j["data"]["user_id"].get<int>();
        
        // Сохраняем токен в AppConfig
        save_auth_token(access_token, user_id);
        
        // Обновляем UI
        update_user_info();
        
        // Автоматически синхронизируем пресеты после логина
        synchronize_presets(true); // force_full_sync = true для первого раза
    }
}
```

**Что происходит:**
- Токен сохраняется в `AppConfig` (секция `filamenthub`, ключ `access_token`)
- `user_id` сохраняется в `AppConfig` (секция `filamenthub`, ключ `user_id`)
- UI обновляется (показывается кнопка "Synchronize", информация о пользователе)
- Автоматически запускается синхронизация с `force_full_sync=true` (первая синхронизация)

### 3. Процесс синхронизации

#### 3.1. Загрузка токена и user_id

```cpp
std::string access_token;
int user_id = 0;
if (!load_auth_token(access_token, user_id)) {
    // Токен не найден → показываем ошибку
    update_sync_button_state(false);
    wxMessageBox(_L("Please login to FilamentHub first."), ...);
    return;
}
```

**Что происходит:**
- Загружается токен из `AppConfig`
- Загружается `user_id` из `AppConfig`
- Если токен не найден → показывается ошибка, синхронизация прекращается

#### 3.2. Получение `last_sync_time`

```cpp
std::string updated_since;
if (!force_full_sync) {
    updated_since = load_last_sync_time(user_id); // ISO 8601 формат: "2025-01-15T10:30:00.000000"
}
```

**Что происходит:**
- Если `force_full_sync=false` → загружается `last_sync_time` из `AppConfig`
- Если `force_full_sync=true` → `updated_since` остается пустым (полная синхронизация)
- `last_sync_time` хранится в `AppConfig` (секция `filamenthub`, ключ `last_sync_time_{user_id}`)

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

**Заголовки:**
```
Authorization: Bearer {access_token}
Content-Type: application/json
Accept: application/json
```

**Backend логика:**
```python
@router.get("/my-presets", response_model=PresetListResponse)
async def get_my_presets(
    current_user: User,
    db: AsyncSession,
    updated_since: datetime | None = None,
) -> PresetListResponse:
    # 1. Получаем созданные пресеты (где user_id == current_user.id)
    created_query = select(Preset).where(
        Preset.user_id == current_user.id,
        Preset.active == True,
    )
    if updated_since:
        created_query = created_query.where(Preset.updated_at >= updated_since)
    
    # 2. Получаем сохраненные пресеты (через UserSavedPreset)
    saved_query = select(Preset).join(UserSavedPreset).where(
        UserSavedPreset.user_id == current_user.id,
        Preset.active == True,
    )
    if updated_since:
        saved_query = saved_query.where(Preset.updated_at >= updated_since)
    
    # 3. Объединяем результаты (убираем дубликаты)
    all_presets = list(set(created_presets) | set(saved_presets))
    
    # 4. Возвращаем список пресетов
    return PresetListResponse(
        items=all_presets,
        total=len(all_presets)
    )
```

**Ответ API:**
```json
{
    "items": [
        {
            "id": 1,
            "name": "PLA 210°C",
            "updated_at": "2025-01-15T10:30:00.000000",
            "created_at": "2025-01-10T08:00:00.000000",
            "user_id": 1,
            "filament_id": 2,
            "is_official": false,
            "active": true,
            ...
        }
    ],
    "total": 1
}
```

#### 3.4. Обработка каждого пресета

**Шаг 3.4.1: Проверка маппинга**

```cpp
std::string bundle_preset_name = load_preset_mapping(preset_id);
```

**Что происходит:**
- Загружается маппинг из `AppConfig` (секция `filamenthub`, ключ `preset_mapping_{preset_id}`)
- Если маппинг найден → пресет уже был импортирован ранее
- Если маппинг не найден → пресет новый, нужно импортировать

**Шаг 3.4.2: Проверка существования пресета в PresetBundle**

```cpp
if (!bundle_preset_name.empty()) {
    bool preset_exists = preset_exists_in_bundle(bundle_preset_name);
    
    if (!preset_exists) {
        // Маппинг есть, но пресет был удален в OrcaSlicer
        // Удаляем маппинг и импортируем пресет заново
        remove_preset_mapping(preset_id);
    }
}
```

**Что происходит:**
- Проверяется, существует ли пресет в `PresetBundle` (пользовательские пресеты)
- Если пресет не найден → маппинг удаляется (пресет был удален пользователем)
- Если пресет найден → пресет существует, можно обновить

**Шаг 3.4.3: Импорт пресета**

```cpp
import_preset_silent(preset_id, preset_name, access_token);
```

**Процесс импорта:**
1. **Скачивание JSON из API:**
   - Запрос: `GET /api/v1/presets/{preset_id}/export/orcaslicer.json`
   - Заголовок: `Authorization: Bearer {access_token}`
   - Ответ: JSON профиль OrcaSlicer

2. **Обработка JSON:**
   - Парсинг JSON
   - Добавление постфикса `[FilamentHub]` к имени пресета
   - Проверка и исправление родительского пресета (`inherits`)

3. **Импорт в PresetBundle:**
   - Сохранение JSON во временный файл
   - Вызов `PresetBundle::import_json_presets()` с `overwrite=1`
   - Удаление временного файла

4. **Сохранение маппинга:**
   - Сохранение маппинга: `preset_id → "PLA 210°C [FilamentHub]"`
   - Обновление UI (перезагрузка пресетов)

#### 3.5. Обновление `last_sync_time`

```cpp
std::time_t now = std::time(nullptr);
std::stringstream ss;
ss << std::put_time(std::gmtime(&now), "%Y-%m-%dT%H:%M:%S.000000");
std::string current_time = ss.str();
save_last_sync_time(user_id, current_time);
```

**Что происходит:**
- Сохраняется текущее время в формате ISO 8601
- Время сохраняется в `AppConfig` (секция `filamenthub`, ключ `last_sync_time_{user_id}`)
- При следующей синхронизации это время передается в API как `updated_since`

#### 3.6. Обновление UI

```cpp
update_sync_button_state(false); // Разблокируем кнопку
update_user_info(); // Обновляем информацию о пользователе
```

**Что происходит:**
- Кнопка "Synchronize" разблокируется
- Информация о пользователе обновляется (если изменилась)

### 4. Проблема с удалением пресета

#### 4.1. Сценарий проблемы

**Шаг 1: Импорт пресета**
- Пресет `preset_id=1` импортируется как `"PLA 210°C [FilamentHub]"`
- Маппинг сохраняется: `preset_mapping_1 = "PLA 210°C [FilamentHub]"`

**Шаг 2: Удаление пресета в OrcaSlicer**
- Пользователь удаляет пресет в UI OrcaSlicer (вкладка пользовательских пресетов)
- Пресет удаляется из `PresetBundle`
- **НО:** Маппинг остается в `AppConfig`!

**Шаг 3: Следующая синхронизация**
- API возвращает пресет `preset_id=1` (обновлен)
- Код проверяет маппинг → видит `"PLA 210°C [FilamentHub]"`
- Код проверяет существование пресета → пресет не найден
- Маппинг удаляется → пресет импортируется заново

**Решение:** ✅ Добавлена проверка `preset_exists_in_bundle()`

#### 4.2. Проверка существования пресета

```cpp
bool FilamentHubPanel::preset_exists_in_bundle(const std::string& preset_name)
{
    PresetBundle* bundle = wxGetApp().preset_bundle;
    PresetCollection& filaments = bundle->filaments;
    
    // Ищем пресет по имени
    Preset* preset = filaments.find_preset2(preset_name, true);
    
    // Проверяем, что пресет существует и является пользовательским (не системным)
    if (preset != nullptr && !preset->is_system) {
        if (preset->name == preset_name) {
            return true;
        }
    }
    
    return false;
}
```

**Что происходит:**
- Ищется пресет по имени в `PresetCollection` (пользовательские пресеты)
- Проверяется, что пресет не системный (`!preset->is_system`)
- Проверяется точное совпадение имени (с учетом регистра)

### 5. Формат JSON при экспорте из FilamentHub

#### 5.1. Генерация JSON в Backend

**Файл:** `backend/app/services/orcaslicer_exporter.py`

**Функция:** `preset_to_orcaslicer_json(preset, filament, db)`

**Обязательные поля:**
```json
{
    "version": "2.3.0.0",
    "type": "filament",
    "name": "PLA 210°C",
    "from": "user",
    "instantiation": "true",
    "filament_settings_id": ["PLA 210°C"],
    "inherits": "Generic PLA @System"
}
```

**Уникальные идентификаторы:**
```json
{
    "setting_id": "FHUB000001",
    "filament_id": "FHUB000002"
}
```

**Параметры печати:**
```json
{
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
    "default_filament_colour": ["#FF0000"]
}
```

**Важные особенности:**
1. Все параметры хранятся как массивы строк (для поддержки мультиэкструдеров)
2. `inherits` должен указывать на существующий системный пресет OrcaSlicer
3. `filament_settings_id` - **КРИТИЧНО:** OrcaSlicer определяет тип профиля по наличию этого поля
4. `setting_id` и `filament_id` - уникальные идентификаторы FilamentHub

#### 5.2. Валидация JSON в OrcaSlicer

**Импорт:** `PresetBundle::import_json_presets()`

**Проверки:**
1. Наличие обязательных полей (`version`, `type`, `name`, `filament_settings_id`)
2. Существование родительского пресета (`inherits`)
3. Валидность параметров (температуры, скорости и т.д.)

**Если родительский пресет не найден:**
- В `ensure_parent_preset_exists()` происходит поиск альтернативного пресета
- Если не найден - используется fallback `"fdm_filament_common"`

### 6. Обработка ошибок

#### 6.1. Ошибка 401 (Unauthorized)

```cpp
if (http_status == 401) {
    // Токен истек или невалидный
    logout(); // Очищает токен и обновляет UI
    update_sync_button_state(false);
    wxMessageBox(_L("Your session has expired. Please login again."), ...);
    return;
}
```

**Что происходит:**
- Токен удаляется из `AppConfig`
- UI обновляется (показывается форма входа)
- Показывается сообщение об ошибке

#### 6.2. Ошибка 403 (Forbidden)

```cpp
if (http_status == 403) {
    // Доступ запрещен
    update_sync_button_state(false);
    wxMessageBox(_L("Access denied. Please check your permissions."), ...);
    return;
}
```

**Что происходит:**
- Кнопка разблокируется
- Показывается сообщение об ошибке

#### 6.3. Ошибка 500+ (Server Error)

```cpp
if (http_status >= 500) {
    // Ошибка сервера
    update_sync_button_state(false);
    wxMessageBox(_L("Server error. Please try again later."), ...);
    return;
}
```

**Что происходит:**
- Кнопка разблокируется
- Показывается сообщение об ошибке

### 7. Чеклист проверки

- [x] Автоматическая синхронизация при открытии вкладки (если авторизован)
- [x] Автоматическая синхронизация после логина (force_full_sync=true)
- [x] Синхронизация по кнопке "Synchronize"
- [x] Проверка существования пресета в PresetBundle (исправление проблемы с удалением)
- [x] Обновление маппинга после успешного импорта
- [x] Обработка ошибок (401, 403, 500+)
- [x] Обновление `last_sync_time` после успешной синхронизации
- [x] Валидация JSON при экспорте из FilamentHub
- [x] Проверка родительского пресета (`inherits`)
- [x] Обработка пустого списка пресетов (обновление состояния кнопки)

### 8. Тестирование

**Сценарий 1: Первая синхронизация**
1. Пользователь авторизуется в FilamentHub
2. Открывается вкладка FilamentHub
3. Автоматически запускается синхронизация
4. Пресеты импортируются в OrcaSlicer
5. Маппинг сохраняется в AppConfig
6. `last_sync_time` обновляется

**Сценарий 2: Инкрементальная синхронизация**
1. Пользователь нажимает кнопку "Synchronize"
2. Загружается `last_sync_time` из AppConfig
3. Запрос к API с параметром `updated_since`
4. API возвращает только обновленные пресеты
5. Обновленные пресеты переимпортируются
6. Маппинг обновляется
7. `last_sync_time` обновляется

**Сценарий 3: Удаление пресета**
1. Пользователь удаляет пресет в OrcaSlicer
2. Пресет удаляется из PresetBundle
3. Маппинг остается в AppConfig
4. Пользователь нажимает кнопку "Synchronize"
5. Код проверяет маппинг → видит что он есть
6. Код проверяет существование пресета → пресет не найден
7. Маппинг удаляется
8. Пресет импортируется заново
9. Маппинг обновляется

**Сценарий 4: Изменение имени пресета в FilamentHub**
1. Пользователь изменяет имя пресета в FilamentHub (например, "PLA 210°C" → "PLA 215°C")
2. Пользователь нажимает кнопку "Synchronize"
3. API возвращает обновленный пресет
4. Пресет импортируется с новым именем: "PLA 215°C [FilamentHub]"
5. Маппинг обновляется: `preset_mapping_1 = "PLA 215°C [FilamentHub]"`
6. Старый пресет "PLA 210°C [FilamentHub]" остается в OrcaSlicer (нужно удалить вручную)

**Проблема:** Старый пресет остается в OrcaSlicer при изменении имени.

**Решение:** Можно добавить проверку по `setting_id` для удаления старых пресетов, но это сложнее и может быть сделано позже.

## ✅ Итоговый статус

- ✅ Автоматическая синхронизация при открытии вкладки
- ✅ Автоматическая синхронизация после логина
- ✅ Синхронизация по кнопке "Synchronize"
- ✅ Проверка существования пресета в PresetBundle
- ✅ Обновление маппинга после успешного импорта
- ✅ Обработка ошибок
- ✅ Обновление `last_sync_time`
- ✅ Валидация JSON при экспорте
- ⚠️ Удаление старых пресетов при изменении имени (не реализовано, но не критично)

## 🔧 Рекомендации для дальнейшего улучшения

1. **Удаление старых пресетов при изменении имени:**
   - Проверять пресеты по `setting_id` вместо имени
   - Удалять старые пресеты при изменении имени

2. **Обработка конфликтов имен:**
   - Если пресет с таким именем уже существует, добавлять суффикс (например, "PLA 210°C [FilamentHub] (1)")

3. **Улучшение логирования:**
   - Добавить больше логов для отладки
   - Логировать все этапы синхронизации

4. **Обработка сетевых ошибок:**
   - Повторные попытки при сетевых ошибках
   - Таймауты для запросов

5. **Прогресс синхронизации:**
   - Показывать прогресс синхронизации (сколько пресетов обработано)
   - Обновлять UI в реальном времени

