# FilamentHub - План интеграции с OrcaSlicer

> **Дата создания:** 2025-01-XX  
> **Статус:** 🧠 Концепция (до сборки OrcaSlicer)  
> **Цель:** Интегрировать FilamentHub API в OrcaSlicer для импорта профилей материалов

---

## 🎯 Цель интеграции

**Проблема:** Пользователи должны вручную вводить настройки материалов или искать профили в интернете.

**Решение:** Прямая интеграция FilamentHub в OrcaSlicer - пользователь может:
- Искать материалы по бренду/названию
- Импортировать профили напрямую из FilamentHub
- Синхронизировать пресеты с облаком
- Получать обновленные настройки от производителей

---

## 📋 Оглавление

1. [Архитектура интеграции](#архитектура-интеграции)
2. [Точки интеграции в OrcaSlicer](#точки-интеграции-в-orcaslicer)
3. [Технические требования](#технические-требования)
4. [Реализация](#реализация)
5. [UI/UX концепция](#uiux-концепция)
6. [API взаимодействие](#api-взаимодействие)
7. [Этапы разработки](#этапы-разработки)

---

## 🏗️ Архитектура интеграции

### Варианты интеграции:

#### Вариант 1: Модуль в OrcaSlicer (рекомендуется) ⭐

```
OrcaSlicer
├── GUI (wxWidgets)
│   ├── Existing Preset Selector
│   └── [+] FilamentHub Integration Module
│       ├── Search Dialog
│       ├── Profile Browser
│       └── Import Handler
├── Core (C++)
│   ├── Preset Manager (existing)
│   └── [+] FilamentHub Client
│       ├── HTTP Client (libcurl)
│       ├── JSON Parser (nlohmann/json)
│       └── Profile Converter
└── Resources
    └── profiles/ (existing JSON files)
        └── filamenthub/ (imported profiles)
```

**Преимущества:**
- ✅ Прямая интеграция в UI
- ✅ Работает "из коробки"
- ✅ Не требует внешних инструментов
- ✅ Максимальный UX

**Недостатки:**
- ❌ Требует изменений в коде OrcaSlicer
- ❌ Нужен форк или PR в репозиторий
- ❌ Больше работы по поддержке

#### Вариант 2: Плагин/Расширение

```
OrcaSlicer (без изменений)
    └── Plugins/
        └── filamenthub.dll (наш плагин)
            ├── GUI Extension
            └── API Client
```

**Преимущества:**
- ✅ Не требует изменений в OrcaSlicer
- ✅ Независимая разработка
- ✅ Легко обновлять

**Недостатки:**
- ❌ OrcaSlicer может не поддерживать плагины
- ❌ Нужен API для расширений
- ❌ Может быть сложнее интегрировать в UI

#### Вариант 3: Внешний инструмент (CLI) + Автоимпорт

```
FilamentHub CLI Tool (C++)
    ├── Search profiles
    ├── Download JSON
    └── Place in OrcaSlicer profiles/

OrcaSlicer (без изменений)
    └── Profiles/
        └── filamenthub/ (auto-detected)
```

**Преимущества:**
- ✅ Не требует изменений в OrcaSlicer
- ✅ Простая реализация
- ✅ Работает сразу

**Недостатки:**
- ❌ Худший UX (нужен отдельный инструмент)
- ❌ Нет интеграции в UI
- ❌ Ручной импорт

---

## 🎯 Точки интеграции в OrcaSlicer

### 1. UI: Выбор материала (Filament Preset)

**Где:** `src/slic3r/GUI/PresetComboBoxes.cpp` или похожие файлы

**Текущий UI:**
```
[▼] Filament Preset
    ├── Generic PLA
    ├── Generic PETG
    └── ...
```

**Новый UI:**
```
[▼] Filament Preset
    ├── Generic PLA
    ├── Generic PETG
    ├── ────────────────────
    ├── [🔍 Search FilamentHub...]  ← Новая опция
    └── ────────────────────
```

**Действие:** При клике открывается диалог поиска FilamentHub.

---

### 2. UI: Диалог поиска FilamentHub

**Новый компонент:** `FilamentHubSearchDialog`

**Функционал:**
- Поиск по бренду
- Поиск по названию материала
- Фильтры (тип пластика, производитель)
- Просмотр деталей профиля
- Кнопка "Import" (импорт в OrcaSlicer)

**UI концепция:**
```
┌─────────────────────────────────────────┐
│  🔍 FilamentHub - Search Materials      │
├─────────────────────────────────────────┤
│  Brand: [▼ Select Brand...]             │
│  Name:  [Search...           ] [Search]│
│                                         │
│  ┌───────────────────────────────────┐ │
│  │ Results:                          │ │
│  ├───────────────────────────────────┤ │
│  │ ☑ Polymaker PLA Pro               │ │
│  │   Brand: Polymaker                │ │
│  │   Type: PLA                       │ │
│  │   [View Details] [Import]        │ │
│  ├───────────────────────────────────┤ │
│  │ ☑ eSUN PLA+                      │ │
│  │   Brand: eSUN                    │ │
│  │   Type: PLA+                     │ │
│  │   [View Details] [Import]        │ │
│  └───────────────────────────────────┘ │
│                                         │
│  [Cancel]                    [Import]   │
└─────────────────────────────────────────┘
```

---

### 3. Core: Менеджер профилей

**Где:** `src/libslic3r/Preset.cpp` или `PresetBundle.cpp`

**Изменения:**
- Добавить метод `importFromFilamentHub(profile_json)`
- Добавить путь `filamenthub/` для импортированных профилей
- Автоматическое обнаружение профилей из FilamentHub

---

### 4. Core: HTTP клиент для FilamentHub API

**Новый компонент:** `FilamentHubClient`

**Функционал:**
- GET `/api/v1/filaments` - поиск материалов
- GET `/api/v1/filaments/{id}` - детали материала
- GET `/api/v1/filaments/{id}/presets` - пресеты для материала
- POST `/api/v1/filaments/{id}/presets` - загрузка пресета (для пользователей)

**Реализация:**
- Использовать `libcurl` (уже в зависимостях OrcaSlicer)
- JSON парсинг: `nlohmann/json` (уже используется)

---

## 🔧 Технические требования

### Зависимости (уже есть в OrcaSlicer):

1. **libcurl** ✅
   - HTTP клиент для запросов к FilamentHub API
   - Уже включен в зависимости OrcaSlicer

2. **nlohmann/json** ✅
   - Парсинг JSON ответов от API
   - Уже используется в OrcaSlicer

3. **wxWidgets** ✅
   - GUI компоненты (диалоги, кнопки, списки)
   - Уже используется в OrcaSlicer

### Новые зависимости (если нужно):

1. **Асинхронность (опционально):**
   - Можно использовать `std::async` для неблокирующих запросов
   - Или `libcurl` в асинхронном режиме

2. **Кеширование (опционально):**
   - Локальный кеш поиска
   - Сохранение загруженных профилей

---

## 💻 Реализация

### Этап 1: HTTP клиент (Core)

**Файл:** `src/libslic3r/FilamentHubClient.hpp` / `.cpp`

```cpp
class FilamentHubClient {
public:
    FilamentHubClient(const std::string& base_url = "http://localhost:8000/api/v1");
    
    // Поиск материалов
    std::vector<FilamentProfile> searchFilaments(
        const std::string& brand = "",
        const std::string& name = ""
    );
    
    // Получить детали материала
    FilamentProfile getFilament(int filament_id);
    
    // Получить пресеты для материала
    std::vector<PresetProfile> getPresets(int filament_id);
    
private:
    std::string base_url_;
    std::string performRequest(const std::string& endpoint);
};
```

---

### Этап 2: Конвертер профилей (Core)

**Файл:** `src/libslic3r/FilamentHubProfileConverter.hpp` / `.cpp`

**Задача:** Преобразовать JSON из FilamentHub API в формат OrcaSlicer профиля.

**Формат FilamentHub:**
```json
{
  "id": 1,
  "name": "PLA Pro",
  "brand": { "id": 1, "name": "Polymaker" },
  "material_type": "PLA",
  "presets": [
    {
      "id": 1,
      "printer_model": "Prusa i3",
      "nozzle_diameter": 0.4,
      "temperature_nozzle": 220,
      "temperature_bed": 60,
      ...
    }
  ]
}
```

**Формат OrcaSlicer:**
```json
{
  "type": "filament",
  "name": "Polymaker PLA Pro (FilamentHub)",
  "inherits": "fdm_filament_common",
  "compatible_printers": ["Prusa i3"],
  "setting_id": "FilamentHub_1",
  "overrides": {
    "nozzle_diameter": [0.4],
    "temperature": 220,
    "bed_temperature": 60,
    ...
  }
}
```

---

### Этап 3: UI диалог поиска (GUI)

**Файл:** `src/slic3r/GUI/FilamentHubSearchDialog.hpp` / `.cpp`

**Компоненты:**
- `wxTextCtrl` - поиск по названию
- `wxComboBox` - выбор бренда
- `wxListCtrl` - результаты поиска
- `wxButton` - Import, Cancel

**Интеграция:**
- Вызывается из `PresetComboBoxes.cpp`
- После импорта обновляет список пресетов

---

### Этап 4: Интеграция в PresetComboBox

**Файл:** `src/slic3r/GUI/PresetComboBoxes.cpp`

**Изменения:**
```cpp
void PresetComboBoxes::fill_filament_preset_combobox() {
    // ... existing code ...
    
    // Добавить разделитель
    append_separator();
    
    // Добавить опцию FilamentHub
    append("🔍 Search FilamentHub...", FILAMENTHUB_SEARCH_ID);
}

void PresetComboBoxes::on_filament_preset_select() {
    if (selected_id == FILAMENTHUB_SEARCH_ID) {
        // Открыть диалог поиска
        FilamentHubSearchDialog dialog(this);
        if (dialog.ShowModal() == wxID_OK) {
            // Импортировать выбранный профиль
            import_filamenthub_profile(dialog.get_selected_profile());
            // Обновить список пресетов
            fill_filament_preset_combobox();
        }
    }
    // ... existing code ...
}
```

---

## 🎨 UI/UX концепция

### Сценарий использования:

1. **Пользователь выбирает материал:**
   - Открывает выпадающий список "Filament Preset"
   - Видит опцию "🔍 Search FilamentHub..."
   - Кликает на неё

2. **Открывается диалог поиска:**
   - Вводит название (например, "PLA Pro")
   - Или выбирает бренд
   - Видит результаты поиска

3. **Выбирает профиль:**
   - Просматривает детали (температуры, скорости)
   - Кликает "View Details" для полной информации
   - Кликает "Import"

4. **Профиль импортируется:**
   - Сохраняется в `resources/profiles/filament/filamenthub/`
   - Появляется в списке пресетов
   - Можно использовать сразу

---

## 🔌 API взаимодействие

### Endpoints FilamentHub (уже есть):

#### 1. Поиск материалов
```
GET /api/v1/filaments?brand_id=1&name=PLA
```

**Ответ:**
```json
{
  "items": [
    {
      "id": 1,
      "name": "PLA Pro",
      "brand": { "id": 1, "name": "Polymaker" },
      "material_type": "PLA",
      "created_at": "2025-01-XX"
    }
  ],
  "total": 1,
  "page": 1,
  "per_page": 20
}
```

#### 2. Детали материала
```
GET /api/v1/filaments/1
```

**Ответ:**
```json
{
  "id": 1,
  "name": "PLA Pro",
  "brand": { "id": 1, "name": "Polymaker" },
  "material_type": "PLA",
  "description": "...",
  "presets": [...]
}
```

#### 3. Пресеты для материала
```
GET /api/v1/filaments/1/presets?printer_id=1&nozzle_diameter=0.4
```

**Ответ:**
```json
{
  "items": [
    {
      "id": 1,
      "filament_id": 1,
      "printer_id": 1,
      "nozzle_diameter": 0.4,
      "temperature_nozzle": 220,
      "temperature_bed": 60,
      "flow_rate": 100,
      "retraction_length": 0.8,
      ...
    }
  ]
}
```

---

## 📋 Этапы разработки

### Фаза 1: Proof of Concept (2-3 недели)

**Цель:** Доказать концепцию интеграции

**Задачи:**
1. ✅ Собрать OrcaSlicer локально
2. ⏳ Изучить код PresetComboBoxes
3. ⏳ Создать простой HTTP клиент (libcurl)
4. ⏳ Реализовать конвертер FilamentHub → OrcaSlicer JSON
5. ⏳ Создать минимальный UI диалог
6. ⏳ Импортировать один профиль вручную

**Результат:** Работающий прототип с одним профилем

---

### Фаза 2: Базовая интеграция (3-4 недели)

**Цель:** Полная интеграция в UI

**Задачи:**
1. Интеграция в PresetComboBox
2. Диалог поиска (UI)
3. Поиск по API (реализация)
4. Импорт профилей (автоматический)
5. Обновление списка пресетов

**Результат:** Работающая интеграция в UI

---

### Фаза 3: Продвинутые функции (4-6 недель)

**Цель:** Полнофункциональная интеграция

**Задачи:**
1. Фильтры поиска (тип пластика, производитель)
2. Кеширование результатов
3. Синхронизация профилей (обновления)
4. Офлайн режим (кеш)
5. Обработка ошибок (нет интернета, API недоступен)

**Результат:** Production-ready интеграция

---

### Фаза 4: Оптимизация и тестирование (2-3 недели)

**Цель:** Стабильность и производительность

**Задачи:**
1. Оптимизация HTTP запросов
2. Асинхронная загрузка (неблокирующий UI)
3. Unit тесты
4. UI тесты
5. Документация

**Результат:** Готовая к релизу интеграция

---

## 🚧 Потенциальные проблемы и решения

### Проблема 1: Формат профилей отличается

**Решение:**
- Создать маппинг полей FilamentHub → OrcaSlicer
- Использовать существующие пресеты OrcaSlicer как базовые
- Дополнять недостающие поля значениями по умолчанию

---

### Проблема 2: Отсутствие интернета

**Решение:**
- Проверять доступность API при старте
- Кешировать последние результаты поиска
- Показывать предупреждение, если API недоступен
- Позволить использовать уже импортированные профили

---

### Проблема 3: Конфликты версий профилей

**Решение:**
- Уникальные имена: `{Brand}_{Name}_FilamentHub_{ID}`
- Отдельная папка `filamenthub/` для импортированных
- Возможность обновить профиль (заменить старый)

---

### Проблема 4: Лицензия и форк

**Решение:**
- Создать форк OrcaSlicer с интеграцией
- Либо создать PR в официальный репозиторий (если они открыты для интеграций)
- Либо создать плагин (если OrcaSlicer поддерживает)

---

## ✅ Чеклист готовности

### Backend (FilamentHub):
- [x] API endpoints готовы
- [x] JSON формат определен
- [ ] Документация API (Swagger)
- [ ] Rate limiting настроен
- [ ] CORS настроен для OrcaSlicer

### OrcaSlicer:
- [ ] Собрать локально
- [ ] Изучить код PresetComboBoxes
- [ ] Изучить формат JSON профилей
- [ ] Создать HTTP клиент
- [ ] Создать конвертер профилей
- [ ] Создать UI диалог
- [ ] Интегрировать в PresetComboBox

---

## 📚 Следующие шаги (после сборки OrcaSlicer)

1. **Изучить код:**
   - `src/slic3r/GUI/PresetComboBoxes.cpp`
   - `src/libslic3r/Preset.cpp`
   - `src/libslic3r/PresetBundle.cpp`

2. **Изучить формат профилей:**
   - `resources/profiles/filament/*.json`
   - Понять структуру полей

3. **Создать Proof of Concept:**
   - Простой HTTP клиент
   - Конвертер одного профиля
   - Минимальный UI

---

**Этот план будет уточняться после успешной сборки OrcaSlicer и изучения кода.**

