# Двусторонняя синхронизация OrcaSlicer ↔ FilamentHub

## 📋 Обзор

**Цель:** Реализовать двустороннюю синхронизацию профилей между OrcaSlicer и FilamentHub, позволяя пользователям:
- **Импортировать** профили из OrcaSlicer в FilamentHub как черновики (принтеры, печать, филаменты)
- **Экспортировать** профили из FilamentHub в OrcaSlicer (уже реализовано)
- **Синхронизировать** бандлы (если есть все 3 типа пресетов: printer + print + filament)
- **Синхронизировать** отдельные пресеты (если нет всех 3 типов)

**Статус:** 
- ✅ Односторонняя синхронизация (FilamentHub → OrcaSlicer) реализована
- ⏳ Обратная синхронизация (OrcaSlicer → FilamentHub) - **В РАЗРАБОТКЕ**

**Ключевые концепции:**
- **Черновики Filament:** Импортируем как черновики (`active=False`) с служебным брендом, пользователь может активировать и привязать к своему бренду через UI
- **Print Settings:** Не требуют UI для редактирования - храним в JSON, отдаем обратно в OrcaSlicer
- **Бандлы:** Группировка профилей (printer + print + filament) если есть все 3 типа

**⚠️ ВАЖНО: Архитектурный подход**
- **OrcaSlicer - открытый проект**, поэтому **минимизируем сложную логику в C++ коде**!
- **Вся бизнес-логика на Backend (Python FastAPI)** - создание черновиков, преобразование форматов, валидация, маппинг
- **C++ (OrcaSlicer)** - получение профилей из OrcaSlicer и отправка на Backend через API (простая логика)
- **Frontend (React)** - UI для управления (активация черновиков, привязка к брендам) - опционально
- **Главное:** Не раскрывать внутреннюю логику сервиса в C++ коде, вся бизнес-логика на Backend

---

## ✅ Проверка готовности Backend, Frontend и БД

### Backend (Python FastAPI)

#### ✅ Что уже есть:

1. **Модели данных:**
   - ✅ `Preset` - модель для пресетов филаментов
     - ✅ `orcaslicer_settings` (JSON) - для хранения расширенных параметров
     - ✅ `user_id` - для привязки к пользователю
     - ✅ `active` - для черновиков
     - ✅ `moderation_status` - для статуса модерации
   - ✅ `Filament` - модель для материалов
     - ✅ `brand_id` - обязательное поле (проблема для пользовательских материалов)
     - ✅ `active` - для черновиков
   - ✅ `PrinterProfile` - модель для профилей принтера
     - ✅ `external_id` - для маппинга с OrcaSlicer
     - ✅ `owner_user_id` - для привязки к пользователю
     - ✅ `source` - для указания источника
     - ✅ `orcaslicer_settings` (JSON) - для хранения полного JSON
   - ✅ `PrintProfile` - модель для профилей печати
     - ✅ `external_id` - для маппинга с OrcaSlicer
     - ✅ `owner_user_id` - для привязки к пользователю
     - ✅ `source` - для указания источника
     - ✅ `orcaslicer_settings` (JSON) - для хранения полного JSON
   - ✅ `User` - модель пользователя
     - ✅ `allow_printer_profiles_import` - разрешение на импорт профилей принтера
     - ✅ `allow_printer_profiles_export` - разрешение на экспорт профилей принтера
     - ✅ `allow_print_profiles_import` - разрешение на импорт профилей печати
     - ✅ `allow_print_profiles_export` - разрешение на экспорт профилей печати
     - ❌ `allow_filament_presets_import` - **НЕТ** (нужно добавить)

2. **Эндпоинты:**
   - ✅ `POST /api/v1/orcaslicer/printer-profiles/import` - импорт профилей принтера
   - ✅ `POST /api/v1/orcaslicer/print-profiles/import` - импорт профилей печати
   - ✅ `GET /api/v1/orcaslicer/printer-profiles` - список профилей принтера для синхронизации
   - ✅ `GET /api/v1/orcaslicer/print-profiles` - список профилей печати для синхронизации
   - ✅ `GET /api/v1/auth/my-presets` - список пресетов пользователя (для экспорта)
   - ❌ `POST /api/v1/orcaslicer/filaments/import` - **НЕТ** (нужно добавить)

3. **Схемы (Pydantic):**
   - ✅ `OrcaPrinterProfilePayload` - payload для импорта профилей принтера
   - ✅ `OrcaPrintProfilePayload` - payload для импорта профилей печати
   - ✅ `OrcaSyncResult` - результат синхронизации
   - ✅ `PrinterProfileSyncRequest` / `PrinterProfileSyncResponse`
   - ✅ `PrintProfileSyncRequest` / `PrintProfileSyncResponse`
   - ❌ `OrcaFilamentPresetPayload` - **НЕТ** (нужно добавить)
   - ❌ `FilamentPresetSyncRequest` / `FilamentPresetSyncResponse` - **НЕТ** (нужно добавить)

4. **Сервисы:**
   - ✅ `orcaslicer_service.py` - сервис для работы с OrcaSlicer (правила обработки удалённых пресетов)
   - ✅ `preset_moderation.py` - валидация текстовых полей

#### ❌ Что нужно добавить:

1. **Модель Preset:**
   - ❌ `external_id: str | None` - для маппинга с OrcaSlicer (как в PrinterProfile и PrintProfile)
   - ❌ `source: str` - для указания источника ("user", "system", "orcaslicer")
   - ⚠️ **Важно:** Добавить миграцию для этих полей

2. **Модель Filament:**
   - ⚠️ **ПРОБЛЕМА:** `brand_id` обязателен (NOT NULL), но для импорта из OrcaSlicer нужно создавать пользовательские Filament без бренда
   - **Решение (концепция черновиков):** 
     - Импортируем Filament как **черновик** (`active=False`) с `brand_id=1` (служебный бренд "User Materials")
     - Пользователь может позже **активировать** черновик и **привязать к своему бренду** через UI (изменив `brand_id` и установив `active=True`)
     - Это удобно, потому что:
       - Не требует немедленного выбора бренда при импорте
       - Позволяет пользователю подготовить материал перед публикацией
       - Соответствует концепции черновиков для других сущностей (Preset, PrinterProfile, PrintProfile)
     - **Миграция:** Создать служебный бренд "User Materials" (id=1) для всех пользовательских материалов из OrcaSlicer
     - **Эндпоинт:** `PATCH /api/v1/filaments/{filament_id}` уже поддерживает обновление `brand_id` и `active` (см. `backend/app/api/v1/endpoints/filaments.py`)

3. **Модель User:**
   - ❌ `allow_filament_presets_import: bool` - разрешение на импорт пресетов филаментов (по умолчанию True)
   - ⚠️ **Важно:** Добавить миграцию для этого поля

4. **Эндпоинт:**
   - ❌ `POST /api/v1/orcaslicer/filaments/import` - импорт пресетов филаментов из OrcaSlicer

5. **Схемы:**
   - ❌ `OrcaFilamentPresetPayload` - payload для импорта пресета филамента
   - ❌ `FilamentPresetSyncRequest` - запрос на импорт пресетов филаментов
   - ❌ `FilamentPresetSyncResponse` - ответ на импорт пресетов филаментов

6. **Функция upsert:**
   - ❌ `_upsert_filament_preset()` - функция для создания/обновления пресета филамента из OrcaSlicer

### C++ Client (OrcaSlicer)

#### ✅ Что уже есть:

1. **FilamentHubClient:**
   - ✅ `import_printer_profiles()` - отправка профилей принтера на сервер
   - ✅ `import_print_profiles()` - отправка профилей печати на сервер
   - ✅ `get_my_presets()` - получение списка пресетов пользователя
   - ✅ `get_my_printer_profiles()` - получение списка профилей принтера
   - ✅ `get_my_print_profiles()` - получение списка профилей печати
   - ✅ `download_profile()` - скачивание пресета филамента
   - ❌ `import_filament_presets()` - **НЕТ** (нужно добавить)

2. **FilamentHubPanel:**
   - ✅ `synchronize_presets()` - синхронизация пресетов из FilamentHub в OrcaSlicer
   - ✅ `process_preset_import_queue()` - обработка очереди импорта пресетов
   - ✅ `import_preset_silent_with_callback()` - импорт пресета без UI
   - ❌ `export_profiles_to_filamenthub()` - **НЕТ** (нужно добавить)
   - ❌ `export_printer_profile()` - **НЕТ** (нужно добавить)
   - ❌ `export_print_profile()` - **НЕТ** (нужно добавить)
   - ❌ `export_filament_preset()` - **НЕТ** (нужно добавить)

### Frontend (React)

#### ✅ Что уже есть:

- ✅ Каталог материалов с фильтрацией
- ✅ Создание/редактирование материалов (через модальные окна)
- ✅ Создание/редактирование пресетов (через модальные окна)
- ✅ Профиль пользователя и бренда
- ✅ Админ панель

#### ⚠️ Что нужно проверить:

- ⚠️ Нужен ли специальный UI для экспорта/импорта из OrcaSlicer?
  - **Ответ:** Нет, достаточно кнопки "Экспортировать в FilamentHub" в FilamentHubPanel (C++)

#### ✅ Что уже поддерживается:

- ✅ **Черновики Filament:** 
  - `PATCH /api/v1/filaments/{filament_id}` поддерживает обновление `brand_id` и `active`
  - Пользователь может активировать черновик и привязать к своему бренду через UI
  - Черновики не отображаются в публичном каталоге (фильтр по `active=True`)

- ✅ **Print Settings:**
  - Не требуют UI для редактирования - просто храним в `PrintProfile.orcaslicer_settings` (JSON)
  - При экспорте в OrcaSlicer отдаем полный JSON обратно
  - Все параметры print settings хранятся в `orcaslicer_settings` (см. структуру ниже)

### База данных (PostgreSQL)

#### ✅ Что уже есть:

1. **Таблицы:**
   - ✅ `presets` - таблица пресетов
   - ✅ `filaments` - таблица материалов
   - ✅ `printer_profiles` - таблица профилей принтера
   - ✅ `print_profiles` - таблица профилей печати
   - ✅ `users` - таблица пользователей
   - ✅ `brands` - таблица брендов

2. **Поля:**
   - ✅ Индексы на `external_id`, `owner_user_id`, `user_id`
   - ✅ JSON поля для `orcaslicer_settings`

#### ❌ Что нужно добавить:

1. **Таблица `presets`:**
   - ❌ `external_id VARCHAR(200)` - для маппинга с OrcaSlicer (nullable, index)
   - ❌ `source VARCHAR(50)` - для указания источника (nullable, default="user")

2. **Таблица `users`:**
   - ❌ `allow_filament_presets_import BOOLEAN` - разрешение на импорт пресетов филаментов (default=True)

3. **Таблица `filaments`:**
   - ⚠️ **ПРОБЛЕМА:** `brand_id INTEGER NOT NULL` - обязательное поле
   - **Решение (черновики):** 
     - Импортируем Filament как черновик (`active=False`) с `brand_id=1` (служебный бренд "User Materials")
     - Пользователь может активировать и привязать к своему бренду через UI
   - **Миграция:** Создать служебный бренд "User Materials" (id=1)

4. **Таблица `brands`:**
   - ⚠️ Создать запись для служебного бренда "User Materials" (id=1) для черновиков из OrcaSlicer

---

## 🔧 Что нужно реализовать

### Фаза 1: Подготовка БД и моделей (Backend)

1. **Миграция для Preset:**
   ```sql
   ALTER TABLE presets
   ADD COLUMN external_id VARCHAR(200) NULL,
   ADD COLUMN source VARCHAR(50) NULL DEFAULT 'user';
   
   CREATE INDEX idx_presets_external_id ON presets(external_id);
   ```

2. **Миграция для User:**
   ```sql
   ALTER TABLE users
   ADD COLUMN allow_filament_presets_import BOOLEAN NOT NULL DEFAULT TRUE;
   ```

3. **Решение проблемы с Filament (концепция черновиков):**
   - **Создать служебный бренд "User Materials" для черновиков:**
     ```sql
     INSERT INTO brands (id, name, slug, verified, active, description)
     VALUES (1, 'User Materials', 'user-materials', FALSE, TRUE, 'User-imported materials from OrcaSlicer (drafts)')
     ON CONFLICT (id) DO NOTHING;
     ```
   - **Логика:**
     - Импортируем Filament как черновик (`active=False`) с `brand_id=1`
     - Пользователь может активировать и привязать к своему бренду через UI (`PATCH /api/v1/filaments/{filament_id}`)
     - Черновики не отображаются в публичном каталоге (фильтр по `active=True`)
     - Это удобно, потому что не требует немедленного выбора бренда при импорте

4. **Обновление моделей:**
   - Добавить `external_id` и `source` в модель `Preset`
   - Добавить `allow_filament_presets_import` в модель `User`
   - Обновить Pydantic схемы

### Фаза 2: Backend эндпоинты и схемы

1. **Создать схемы:**
   ```python
   # backend/app/schemas/orca_sync.py
   
   class OrcaFilamentPresetPayload(BaseModel):
       """Payload для импорта пресета филамента из OrcaSlicer."""
       
       external_id: str | None = None
       fhub_id: int | None = None
       name: str
       slug: str | None = None
       description: str | None = None
       
       # Filament данные
       filament_id: int | None = None
       filament_name: str | None = None
       material_type: str | None = None
       
       # Базовые параметры
       extruder_temp: float | None = None
       bed_temp: float | None = None
       
       # OrcaSlicer JSON формат
       orcaslicer_settings: dict[str, Any] = Field(default_factory=dict)
       
       # Метаданные
       source: str | None = None
       active: bool | None = Field(default=False)
       notes: str | None = None
   
   class FilamentPresetSyncRequest(BaseModel):
       """Запрос на импорт пресетов филаментов."""
       profiles: list[OrcaFilamentPresetPayload]
   
   class FilamentPresetSyncResponse(BaseModel):
       """Результат импорта пресетов филаментов."""
       results: list[OrcaSyncResult]
   ```

2. **Создать эндпоинт:**
   ```python
   # backend/app/api/v1/endpoints/orca_sync.py
   
   @router.post(
       "/filaments/import",
       response_model=FilamentPresetSyncResponse,
       status_code=status.HTTP_200_OK,
   )
   async def import_filament_presets(
       payload: FilamentPresetSyncRequest,
       current_user: Annotated[User, Depends(get_current_active_user)],
       db: Annotated[AsyncSession, Depends(get_db)],
   ) -> FilamentPresetSyncResponse:
       """Import or update filament presets submitted by OrcaSlicer."""
       # Проверяем разрешение на импорт
       if not current_user.allow_filament_presets_import:
           raise HTTPException(
               status_code=status.HTTP_403_FORBIDDEN,
               detail="Импорт пресетов филаментов отключен в настройках пользователя",
           )
       
       results: list[OrcaSyncResult] = []
       
       for item in payload.profiles:
           try:
               result = await _upsert_filament_preset(
                   payload=item,
                   current_user=current_user,
                   db=db,
               )
           except Exception as exc:
               logger.exception("Unexpected error while syncing filament preset")
               result = OrcaSyncResult(
                   external_id=getattr(item, "external_id", None),
                   fhub_id=getattr(item, "fhub_id", None),
                   status="error",
                   message=f"Unexpected error: {exc}",
               )
           results.append(result)
       
       await db.commit()
       return FilamentPresetSyncResponse(results=results)
   ```

3. **Реализовать функцию upsert:**
   ```python
   # backend/app/api/v1/endpoints/orca_sync.py
   
   async def _upsert_filament_preset(
       *,
       payload: OrcaFilamentPresetPayload,
       current_user: User,
       db: AsyncSession,
   ) -> OrcaSyncResult:
       """Создать или обновить Filament Preset из OrcaSlicer."""
       
       # 1. Найти или создать Filament
       USER_MATERIALS_BRAND_ID = 1  # Служебный бренд для пользовательских материалов
       
       filament = None
       if payload.filament_id:
           filament = await db.get(Filament, payload.filament_id)
           # Проверяем права доступа
           if filament and filament.brand_id != USER_MATERIALS_BRAND_ID and current_user.brand_id != filament.brand_id:
               return OrcaSyncResult(
                   external_id=payload.external_id,
                   fhub_id=payload.filament_id,
                   status="error",
                   message="Недостаточно прав для доступа к этому материалу",
               )
       elif payload.filament_name:
           # Ищем по имени в служебном бренде
           result = await db.execute(
               select(Filament).where(
                   Filament.name == payload.filament_name,
                   Filament.brand_id == USER_MATERIALS_BRAND_ID,
               )
           )
           filament = result.scalar_one_or_none()
       
       if not filament:
           # Создаем новый Filament (черновик) в служебном бренде
           from app.services.slug_service import generate_unique_slug
           
           filament_name = payload.filament_name or f"Imported from OrcaSlicer"
           material_type = payload.material_type or "PLA"
           
           slug = await generate_unique_slug(
               db=db,
               model=Filament,
               source=filament_name,
               fallback=f"filament-{current_user.id}",
           )
           
           filament = Filament(
               name=filament_name,
               slug=slug,
               material_type=material_type,
               brand_id=USER_MATERIALS_BRAND_ID,  # Служебный бренд "User Materials" (id=1)
               diameter=1.75,  # По умолчанию
               active=False,  # Черновик - пользователь может активировать и привязать к своему бренду через UI
               source="orcaslicer",
           )
           db.add(filament)
           await db.flush()
           
           logger.info(
               f"Created draft Filament (id={filament.id}, name='{filament_name}') "
               f"for user {current_user.id}. User can activate and assign to their brand via UI."
           )
       
       # 2. Найти или создать Preset
       preset = None
       if payload.fhub_id:
           preset = await db.get(Preset, payload.fhub_id)
           if preset and preset.user_id != current_user.id and current_user.role != UserRole.ADMIN:
               return OrcaSyncResult(
                   external_id=payload.external_id,
                   fhub_id=payload.fhub_id,
                   status="error",
                   message="Недостаточно прав для обновления этого пресета",
               )
       elif payload.external_id:
           # Ищем по external_id
           result = await db.execute(
               select(Preset).where(
                   Preset.external_id == payload.external_id,
                   Preset.user_id == current_user.id,
               )
           )
           preset = result.scalar_one_or_none()
       
       if preset:
           # Обновляем существующий пресет
           preset.name = payload.name
           preset.extruder_temp = payload.extruder_temp or preset.extruder_temp
           preset.bed_temp = payload.bed_temp or preset.bed_temp
           preset.orcaslicer_settings = payload.orcaslicer_settings or preset.orcaslicer_settings
           preset.updated_at = datetime.now(timezone.utc)
           
           return OrcaSyncResult(
               external_id=payload.external_id,
               fhub_id=preset.id,
               status="updated",
               message="Preset updated",
           )
       else:
           # Создаем новый пресет (черновик)
           from app.services.slug_service import generate_unique_slug
           
           slug = await generate_unique_slug(
               db=db,
               model=Preset,
               source=payload.slug or payload.name,
               fallback=f"preset-{current_user.id}",
           )
           
           preset = Preset(
               name=payload.name,
               slug=slug,
               filament_id=filament.id,
               user_id=current_user.id,
               extruder_temp=payload.extruder_temp or 210.0,
               bed_temp=payload.bed_temp or 60.0,
               print_speed=80.0,  # Значения по умолчанию
               travel_speed=150.0,
               orcaslicer_settings=payload.orcaslicer_settings or {},
               is_official=False,
               active=False,  # Черновик
               moderation_status=PresetModerationStatus.PENDING,
               source=payload.source or "orcaslicer",
               external_id=payload.external_id,
           )
           db.add(preset)
           await db.flush()
           
           return OrcaSyncResult(
               external_id=payload.external_id,
               fhub_id=preset.id,
               status="created",
               message="Preset created as draft",
           )
   ```

### Фаза 3: C++ Client и Panel (МИНИМАЛЬНАЯ ЛОГИКА В C++)

**ВАЖНО:** Вся бизнес-логика на Backend, C++ только для получения профилей и отправки на API!

**Подход:**
1. **C++ получает профили из OrcaSlicer (PresetBundle)**
2. **C++ отправляет профили на Backend через API** (простая логика, без бизнес-правил)
3. **Backend обрабатывает и создает черновики** (вся бизнес-логика здесь)
4. **Backend возвращает маппинги `external_id → fhub_id`**
5. **C++ сохраняет маппинги в AppConfig**

**Что нужно в C++:**
1. **Метод в FilamentHubClient для отправки filament presets:**
   ```cpp
   // docs/OrcaSlicer/src/slic3r/Utils/FilamentHubClient.hpp
   void import_filament_presets(
       const std::string& access_token,
       const std::string& presets_json,
       std::function<void(std::string /* json_body */, unsigned /* http_status */)> on_complete,
       std::function<void(std::string /* body */, std::string /* error */, unsigned /* http_status */)> on_error
   ) const;
   ```

2. **Метод в FilamentHubPanel для экспорта профилей:**
   ```cpp
   // FilamentHubPanel.cpp
   void export_profiles_to_filamenthub();
   // - Получает профили из PresetBundle
   // - Формирует JSON (простая сериализация)
   // - Отправляет на Backend через API
   // - Сохраняет маппинги в AppConfig
   ```

---

## 🔄 Как работает текущая синхронизация (FilamentHub → OrcaSlicer)

### 1. Архитектура

```
[FilamentHub Backend] → [OrcaSlicer C++ Client] → [PresetBundle] → [OrcaSlicer UI]
```

**Основные компоненты:**
- **Backend:** `GET /api/v1/auth/my-presets` - возвращает список пресетов пользователя
- **C++ Client:** `FilamentHubClient::get_my_presets()` - делает HTTP запрос
- **Panel:** `FilamentHubPanel::synchronize_presets()` - вызывает клиент и импортирует пресеты
- **Import:** `PresetBundle::import_json_presets()` - импортирует JSON профили в OrcaSlicer

### 2. Процесс синхронизации

**Шаг 1:** Получение списка пресетов с сервера
```cpp
// FilamentHubPanel.cpp
FilamentHubClient client;
client.get_my_presets(
    access_token,
    updated_since,  // Инкрементальная синхронизация
    [this, ...](std::string json_body, unsigned http_status) {
        // Обработка ответа
    }
);
```

**Шаг 2:** Парсинг JSON и добавление в очередь импорта
```cpp
nlohmann::json presets_json = nlohmann::json::parse(json_body);
for (auto& preset : presets_json["items"]) {
    m_preset_import_queue.push_back({
        preset["id"].get<int>(),
        preset["name"].get<std::string>(),
        preset["filament"]["name"].get<std::string>()
    });
}
```

**Шаг 3:** Импорт каждого пресета через PresetBundle
```cpp
PresetBundle* bundle = wxGetApp().preset_bundle;
bool success = bundle->import_json_presets(
    Preset::TYPE_FILAMENT,
    preset_json_string,  // JSON профиль OrcaSlicer
    preset_name,
    preset_type,
    false,  // delete_existing
    nullptr,  // preset_imported_callback
    nullptr   // preset_removed_callback
);
```

**Шаг 4:** Сохранение маппинга preset_id → bundle_preset_name
```cpp
// Сохраняем в AppConfig для отслеживания синхронизированных пресетов
std::string mapping_key = CONFIG_KEY_PRESET_MAPPING + "/" + std::to_string(preset_id);
app_config->set(mapping_key, bundle_preset_name);
```

### 3. Формат данных

**Backend возвращает:**
```json
{
  "items": [
    {
      "id": 1,
      "name": "PLA Red",
      "filament": {
        "id": 10,
        "name": "PLA Red",
        "material_type": "PLA"
      },
      "orcaslicer_settings": {
        "version": "2.3.0.0",
        "type": "filament",
        "name": "PLA Red",
        "inherits": "Generic PLA @System",
        "filament_settings_id": ["PLA Red"],
        "nozzle_temperature": ["210"],
        "bed_temperature": ["60"],
        // ... остальные параметры
      }
    }
  ],
  "total": 1
}
```

**OrcaSlicer импортирует:**
- JSON профиль с полями `type`, `name`, `inherits`, `filament_settings_id`
- Все параметры в виде массивов строк (OrcaSlicer формат)
- Профиль добавляется в `PresetBundle` с постфиксом `[FilamentHub]`

---

## 🔄 Обратная синхронизация (OrcaSlicer → FilamentHub) - ПЛАН

### 1. Архитектура

```
[OrcaSlicer PresetBundle] → [C++ Export] → [FilamentHub Backend API] → [FilamentHub Database]
```

**Основные компоненты:**
- **C++ Export:** Экспорт профилей из `PresetBundle` в JSON формат
- **C++ Client:** `FilamentHubClient::import_printer_profiles()`, `import_print_profiles()`, `import_filament_presets()`
- **Backend:** `POST /api/v1/orcaslicer/printer-profiles/import`, `/print-profiles/import`, `/filaments/import`
- **Service:** Обработка импорта, создание черновиков, сопоставление с существующими профилями

### 2. Типы профилей

OrcaSlicer поддерживает **3 типа профилей**:

1. **Printer Profiles** (`Preset::TYPE_PRINTER`)
   - Настройки принтера (машина + сопло)
   - Тип JSON: `"type": "machine"`
   - Соответствие FilamentHub: `PrinterProfile`

2. **Print Profiles** (`Preset::TYPE_PRINT`)
   - Настройки печати (слои, скорость, поддержки и т.д.)
   - Тип JSON: `"type": "process"`
   - Соответствие FilamentHub: `PrintProfile`

3. **Filament Presets** (`Preset::TYPE_FILAMENT`)
   - Настройки материала (температуры, охлаждение и т.д.)
   - Тип JSON: `"type": "filament"`
   - Соответствие FilamentHub: `Preset` (уже реализовано частично)

### 3. Бандлы vs Отдельные пресеты

#### Бандлы (Bundle)
**Условие:** Если у пользователя есть **все 3 типа** профилей, связанных между собой:
- Printer Profile связан с Print Profile (через `default_print_profile`)
- Print Profile связан с Filament Preset (через `compatible_filaments`)
- Filament Preset связан с Printer Profile (через совместимость)

**Преимущества бандла:**
- Единая структура данных
- Проще управлять связями
- Соответствует структуре OrcaSlicer Vendor Bundle

**Структура бандла в FilamentHub:**
```json
{
  "bundle_name": "My Custom Bundle",
  "printer_profile": { ... },
  "print_profile": { ... },
  "filament_preset": { ... },
  "relationships": {
    "printer_to_print": "default_print_profile_slug",
    "print_to_filament": ["filament_slug1", "filament_slug2"]
  }
}
```

#### Отдельные пресеты
**Условие:** Если у пользователя нет всех 3 типов, или они не связаны между собой.

**Обработка:**
- Каждый тип профиля импортируется отдельно
- Связи между профилями сохраняются, но не требуются
- Пользователь может позже связать профили вручную

### 4. Процесс обратной синхронизации

#### Этап 1: Экспорт профилей из OrcaSlicer (C++)

**4.1.1 Получение списка профилей из PresetBundle**

```cpp
// FilamentHubPanel.cpp
void FilamentHubPanel::export_profiles_to_filamenthub()
{
    PresetBundle* bundle = wxGetApp().preset_bundle;
    if (!bundle) {
        BOOST_LOG_TRIVIAL(error) << "FilamentHub: preset_bundle is null";
        return;
    }
    
    // Экспортируем только пользовательские пресеты (не системные)
    std::vector<PrinterProfileData> printer_profiles;
    std::vector<PrintProfileData> print_profiles;
    std::vector<FilamentPresetData> filament_presets;
    
    // 1. Экспорт Printer Profiles
    const PresetCollection& printer_collection = bundle->printers;
    for (const Preset& preset : printer_collection) {
        if (preset.is_user() && !preset.is_system) {
            PrinterProfileData profile = export_printer_profile(preset);
            printer_profiles.push_back(profile);
        }
    }
    
    // 2. Экспорт Print Profiles
    const PresetCollection& print_collection = bundle->prints;
    for (const Preset& preset : print_collection) {
        if (preset.is_user() && !preset.is_system) {
            PrintProfileData profile = export_print_profile(preset);
            print_profiles.push_back(profile);
        }
    }
    
    // 3. Экспорт Filament Presets
    const PresetCollection& filament_collection = bundle->filaments;
    for (const Preset& preset : filament_collection) {
        // Пропускаем пресеты, которые уже синхронизированы из FilamentHub
        if (preset.name.find("[FilamentHub]") != std::string::npos) {
            continue;
        }
        
        if (preset.is_user() && !preset.is_system) {
            FilamentPresetData preset_data = export_filament_preset(preset);
            filament_presets.push_back(preset_data);
        }
    }
    
    // 4. Отправка на сервер
    send_profiles_to_server(printer_profiles, print_profiles, filament_presets);
}
```

**4.1.2 Экспорт Printer Profile**

```cpp
PrinterProfileData FilamentHubPanel::export_printer_profile(const Preset& preset)
{
    PrinterProfileData profile;
    
    // Базовые поля
    profile.external_id = preset.setting_id;  // Уникальный ID в OrcaSlicer
    profile.name = preset.name;
    profile.description = preset.description;
    
    // OrcaSlicer JSON формат
    nlohmann::json orcaslicer_json = preset.config.to_json();
    profile.orcaslicer_settings = orcaslicer_json;
    
    // Извлекаем метаданные
    if (orcaslicer_json.contains("printer_model")) {
        profile.printer_model = orcaslicer_json["printer_model"].get<std::string>();
    }
    if (orcaslicer_json.contains("nozzle_diameter")) {
        std::string nozzle_str = orcaslicer_json["nozzle_diameter"].get<std::string>();
        profile.nozzle_diameters = parse_nozzle_diameters(nozzle_str);
    }
    if (orcaslicer_json.contains("printable_area")) {
        profile.printable_area = parse_printable_area(orcaslicer_json["printable_area"]);
    }
    if (orcaslicer_json.contains("printable_height")) {
        profile.printable_height_mm = std::stof(orcaslicer_json["printable_height"].get<std::string>());
    }
    if (orcaslicer_json.contains("default_print_profile")) {
        profile.default_print_profile = orcaslicer_json["default_print_profile"].get<std::string>();
    }
    
    // G-code
    if (orcaslicer_json.contains("start_gcode")) {
        profile.start_gcode = orcaslicer_json["start_gcode"].get<std::string>();
    }
    if (orcaslicer_json.contains("end_gcode")) {
        profile.end_gcode = orcaslicer_json["end_gcode"].get<std::string>();
    }
    
    // Проверяем, был ли этот профиль уже синхронизирован
    std::string mapping_key = CONFIG_KEY_PRINTER_PROFILE_MAPPING + "/" + profile.external_id;
    std::string fhub_id_str = app_config->get(mapping_key);
    if (!fhub_id_str.empty()) {
        profile.fhub_id = std::stoi(fhub_id_str);
    }
    
    return profile;
}
```

**4.1.3 Экспорт Print Profile**

```cpp
PrintProfileData FilamentHubPanel::export_print_profile(const Preset& preset)
{
    PrintProfileData profile;
    
    // Базовые поля
    profile.external_id = preset.setting_id;
    profile.name = preset.name;
    profile.description = preset.description;
    
    // OrcaSlicer JSON формат
    nlohmann::json orcaslicer_json = preset.config.to_json();
    profile.orcaslicer_settings = orcaslicer_json;
    
    // Извлекаем метаданные
    if (orcaslicer_json.contains("layer_height")) {
        std::string layer_str = orcaslicer_json["layer_height"].get<std::string>();
        profile.layer_height_mm = std::stof(layer_str);
    }
    if (orcaslicer_json.contains("compatible_printers_condition")) {
        profile.compatible_printers_condition = orcaslicer_json["compatible_printers_condition"].get<std::string>();
    }
    if (orcaslicer_json.contains("compatible_printers")) {
        profile.compatible_printers = parse_compatible_printers(orcaslicer_json["compatible_printers"]);
    }
    
    // Проверяем маппинг
    std::string mapping_key = CONFIG_KEY_PRINT_PROFILE_MAPPING + "/" + profile.external_id;
    std::string fhub_id_str = app_config->get(mapping_key);
    if (!fhub_id_str.empty()) {
        profile.fhub_id = std::stoi(fhub_id_str);
    }
    
    return profile;
}
```

**4.1.4 Экспорт Filament Preset**

```cpp
FilamentPresetData FilamentHubPanel::export_filament_preset(const Preset& preset)
{
    FilamentPresetData preset_data;
    
    // Базовые поля
    preset_data.external_id = preset.setting_id;
    preset_data.name = preset.name;
    
    // OrcaSlicer JSON формат
    nlohmann::json orcaslicer_json = preset.config.to_json();
    preset_data.orcaslicer_settings = orcaslicer_json;
    
    // Извлекаем базовые параметры для Filament
    if (orcaslicer_json.contains("nozzle_temperature")) {
        std::vector<std::string> temps = orcaslicer_json["nozzle_temperature"].get<std::vector<std::string>>();
        if (!temps.empty()) {
            preset_data.extruder_temp = std::stoi(temps[0]);
        }
    }
    if (orcaslicer_json.contains("bed_temperature")) {
        std::vector<std::string> temps = orcaslicer_json["bed_temperature"].get<std::vector<std::string>>();
        if (!temps.empty()) {
            preset_data.bed_temp = std::stoi(temps[0]);
        }
    }
    
    // Определяем material_type из inherits
    if (orcaslicer_json.contains("inherits")) {
        std::string inherits = orcaslicer_json["inherits"].get<std::string>();
        preset_data.material_type = map_orcaslicer_inherits_to_material_type(inherits);
    }
    
    // Имя филамента (используем имя пресета или извлекаем из JSON)
    preset_data.filament_name = preset.name;
    if (orcaslicer_json.contains("filament_id")) {
        std::vector<std::string> filament_ids = orcaslicer_json["filament_id"].get<std::vector<std::string>>();
        if (!filament_ids.empty()) {
            // Можно использовать filament_id как имя материала
            preset_data.filament_name = filament_ids[0];
        }
    }
    
    // Проверяем маппинг
    std::string mapping_key = CONFIG_KEY_PRESET_MAPPING + "/" + preset_data.external_id;
    std::string fhub_id_str = app_config->get(mapping_key);
    if (!fhub_id_str.empty()) {
        preset_data.fhub_id = std::stoi(fhub_id_str);
    }
    
    return preset_data;
}
```

#### Этап 2: JavaScript API для получения профилей (C++ - МИНИМАЛЬНЫЕ ИЗМЕНЕНИЯ)

**⚠️ ВАЖНО:** Вся логика экспорта на Frontend и Backend, C++ только предоставляет JavaScript API!

**4.2.1 JavaScript API для получения профилей из OrcaSlicer**

```cpp
// FilamentHubPanel.cpp - добавить JavaScript API для получения профилей

void FilamentHubPanel::setup_javascript_api()
{
    if (m_browser == nullptr) {
        return;
    }
    
    // Регистрируем JavaScript API для получения профилей
    wxString js_code = R"(
        window.filamenthub = window.filamenthub || {};
        
        // Получить все профили принтеров
        window.filamenthub.getPrinterProfiles = function() {
            return new Promise((resolve, reject) => {
                wx.postMessage({
                    command: 'get_printer_profiles',
                    callback_id: 'printer_profiles_' + Date.now()
                });
                
                // Ожидаем ответ от C++ через window.wx.onMessage
                window.wx.onMessage = function(message) {
                    if (message.command === 'printer_profiles_response') {
                        resolve(message.data);
                    } else if (message.command === 'printer_profiles_error') {
                        reject(new Error(message.error));
                    }
                };
            });
        };
        
        // Получить все профили печати
        window.filamenthub.getPrintProfiles = function() {
            // Аналогично getPrinterProfiles
        };
        
        // Получить все пресеты филаментов
        window.filamenthub.getFilamentPresets = function() {
            // Аналогично getPrinterProfiles
        };
    )";
    
    WebView::RunScript(m_browser, js_code);
}

// Обработчик сообщений от JavaScript
void FilamentHubPanel::on_javascript_message(const wxString& message)
{
    nlohmann::json msg = nlohmann::json::parse(message.ToUTF8().data());
    std::string command = msg["command"].get<std::string>();
    
    if (command == "get_printer_profiles") {
        // Получаем профили принтеров из PresetBundle
        PresetBundle* bundle = wxGetApp().preset_bundle;
        if (bundle == nullptr) {
            send_javascript_response("printer_profiles_error", "PresetBundle not available");
            return;
        }
        
        nlohmann::json profiles = nlohmann::json::array();
        for (const auto& preset : bundle->printers) {
            nlohmann::json profile;
            profile["external_id"] = preset.setting_id;
            profile["name"] = preset.name;
            profile["orcaslicer_settings"] = preset.config.to_json();
            // ... другие поля
            profiles.push_back(profile);
        }
        
        send_javascript_response("printer_profiles_response", profiles.dump());
    }
    // ... аналогично для print_profiles и filament_presets
}
```

**4.2.2 Frontend (React) - Экспорт профилей**

```typescript
// frontend/src/components/OrcaSlicerExport.tsx

export function OrcaSlicerExport() {
  const handleExportProfiles = async () => {
    try {
      // 1. Получаем профили из OrcaSlicer через JavaScript API
      const printerProfiles = await (window as any).filamenthub.getPrinterProfiles();
      const printProfiles = await (window as any).filamenthub.getPrintProfiles();
      const filamentPresets = await (window as any).filamenthub.getFilamentPresets();
      
      // 2. Отправляем на Backend через API
      const response = await fetch('/api/v1/orcaslicer/filaments/import', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${getAccessToken()}`,
        },
        body: JSON.stringify({
          profiles: filamentPresets.map(preset => ({
            external_id: preset.external_id,
            name: preset.name,
            filament_name: preset.filament_name,
            material_type: preset.material_type,
            extruder_temp: preset.extruder_temp,
            bed_temp: preset.bed_temp,
            orcaslicer_settings: preset.orcaslicer_settings,
            source: 'orcaslicer',
            active: false, // Черновик
          })),
        }),
      });
      
      const result = await response.json();
      
      // 3. Сохраняем маппинги external_id → fhub_id
      for (const item of result.results) {
        if (item.status === 'created' || item.status === 'updated') {
          // Сохраняем маппинг через JavaScript API
          await (window as any).filamenthub.saveMapping(
            'filament',
            item.external_id,
            item.fhub_id
          );
        }
      }
      
      // 4. Показываем уведомление
      showNotification('Профили успешно экспортированы в FilamentHub');
    } catch (error) {
      console.error('Failed to export profiles:', error);
      showNotification('Ошибка при экспорте профилей', 'error');
    }
  };
  
  return (
    <Button onClick={handleExportProfiles}>
      Экспортировать профили в FilamentHub
    </Button>
  );
}
```

#### Этап 3: Обработка на сервере (Backend)

**4.3.1 Эндпоинты импорта** (уже частично реализованы)

- `POST /api/v1/orcaslicer/printer-profiles/import` - ✅ Реализовано
- `POST /api/v1/orcaslicer/print-profiles/import` - ✅ Реализовано
- `POST /api/v1/orcaslicer/filaments/import` - ⏳ **НУЖНО РЕАЛИЗОВАТЬ**

**4.3.2 Импорт Filament Presets** (нужно реализовать)

См. код в разделе "Фаза 2: Backend эндпоинты и схемы" выше.

### 5. Обновление уже импортированных пресетов

**Проверка обновлений:**
- Сравниваем `updated_at` в FilamentHub с временем последней синхронизации
- Если `updated_at` > `last_sync_time`, пресет был изменен в FilamentHub
- Если `updated_at` < `last_sync_time`, пресет был изменен в OrcaSlicer (локально)

**Стратегия:**
1. **Если пресет был изменен в FilamentHub:**
   - OrcaSlicer перезаписывает локальную версию при следующей синхронизации
   - Пользователь получает уведомление об обновлении

2. **Если пресет был изменен в OrcaSlicer:**
   - OrcaSlicer отправляет обновленную версию на сервер
   - Backend обновляет пресет в FilamentHub (если пользователь имеет права)

3. **Конфликты:**
   - Если пресет изменен в обоих местах одновременно, приоритет у FilamentHub
   - Пользователь может выбрать, какую версию сохранить (в будущем)

### 6. Удаление пресетов

**Уже реализовано:**
- ✅ Обнаружение локально удалённых пресетов в OrcaSlicer
- ✅ Отправка списка удалённых пресетов на сервер (`POST /api/v1/orcaslicer/deleted-presets`)
- ✅ Уведомления пользователя об удалённых пресетах
- ✅ Правила обработки (always_restore, always_delete, always_ask)

**Нужно реализовать:**
- ⏳ Удаление пресетов из OrcaSlicer, если они удалены на FilamentHub (при синхронизации)

---

## 📝 Детальный план реализации

### Фаза 1: Подготовка (Backend)

**Задачи:**
1. ✅ Добавить разрешения импорта/экспорта в модель `User`:
   - `allow_printer_profiles_import` ✅
   - `allow_print_profiles_import` ✅
   - `allow_filament_presets_import` ⏳ **НУЖНО ДОБАВИТЬ**
   - `allow_printer_profiles_export` ✅
   - `allow_print_profiles_export` ✅
   - `allow_filament_presets_export` ✅ (не нужен, используется через `/api/v1/auth/my-presets`)

2. ✅ Создать эндпоинты импорта:
   - `POST /api/v1/orcaslicer/printer-profiles/import` ✅
   - `POST /api/v1/orcaslicer/print-profiles/import` ✅
   - `POST /api/v1/orcaslicer/filaments/import` ⏳ **НУЖНО РЕАЛИЗОВАТЬ**

3. ✅ Создать Pydantic схемы:
   - `OrcaPrinterProfilePayload` ✅
   - `OrcaPrintProfilePayload` ✅
   - `OrcaFilamentPresetPayload` ⏳ **НУЖНО РЕАЛИЗОВАТЬ**

4. ✅ Реализовать логику upsert для каждого типа профиля:
   - `_upsert_printer_profile()` ✅
   - `_upsert_print_profile()` ✅
   - `_upsert_filament_preset()` ⏳ **НУЖНО РЕАЛИЗОВАТЬ**

### Фаза 2: Экспорт из OrcaSlicer (C++)

**Задачи:**
1. ⏳ Создать функции экспорта профилей:
   - `export_printer_profile()` - экспорт Printer Profile в JSON
   - `export_print_profile()` - экспорт Print Profile в JSON
   - `export_filament_preset()` - экспорт Filament Preset в JSON

2. ⏳ Реализовать логику определения связей между профилями:
   - Определение бандлов (если есть все 3 типа)
   - Определение отдельных пресетов (если нет всех 3 типов)

3. ⏳ Добавить кнопку "Экспортировать в FilamentHub" в FilamentHubPanel:
   - Ручной экспорт выбранных профилей
   - Автоматический экспорт при первой синхронизации

4. ⏳ Реализовать отправку профилей на сервер:
   - Использовать `FilamentHubClient::import_printer_profiles()`
   - Использовать `FilamentHubClient::import_print_profiles()`
   - Использовать `FilamentHubClient::import_filament_presets()` (нужно добавить)

### Фаза 3: Обработка ответов и маппинги (C++)

**Задачи:**
1. ⏳ Реализовать обработку ответов сервера:
   - Сохранение маппингов `external_id → fhub_id` в AppConfig
   - Обновление маппингов при изменении профилей

2. ⏳ Реализовать проверку обновлений:
   - Сравнение `updated_at` для определения, что изменилось
   - Уведомления пользователя об обновлениях

3. ⏳ Реализовать обработку удалений:
   - Удаление пресетов из OrcaSlicer, если они удалены на FilamentHub
   - Уведомления пользователя об удалениях

### Фаза 4: Бандлы (опционально, после базовой синхронизации)

**Задачи:**
1. ⏳ Определить логику создания бандлов:
   - Группировка профилей по связям
   - Создание единой структуры бандла

2. ⏳ Реализовать экспорт бандлов:
   - Отправка бандла как единого объекта
   - Обработка бандла на сервере

3. ⏳ Реализовать импорт бандлов:
   - Импорт всех 3 типов профилей из бандла
   - Восстановление связей между профилями

---

## 🔧 Технические детали

### Структура данных для импорта Filament Preset

```python
class OrcaFilamentPresetPayload(BaseModel):
    """Payload для импорта пресета филамента из OrcaSlicer."""
    
    external_id: str | None = Field(
        default=None, description="Уникальный ID пресета в OrcaSlicer"
    )
    fhub_id: int | None = Field(
        default=None, ge=1, description="ID существующего пресета в FilamentHub"
    )
    name: str = Field(..., max_length=200)
    slug: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=10_000)
    
    # Filament данные
    filament_id: int | None = Field(default=None, ge=1)
    filament_name: str | None = Field(default=None, max_length=200)
    material_type: str | None = Field(default=None, max_length=50)
    
    # Базовые параметры
    extruder_temp: float | None = Field(default=None, ge=0, le=500)
    bed_temp: float | None = Field(default=None, ge=0, le=200)
    
    # OrcaSlicer JSON формат
    orcaslicer_settings: dict[str, Any] = Field(default_factory=dict)
    
    # Метаданные
    source: str | None = Field(default=None, max_length=50)
    active: bool | None = Field(
        default=False, description="Импортируется как черновик (False)"
    )
    notes: str | None = Field(default=None, max_length=10_000)
```

### Маппинг OrcaSlicer → FilamentHub

**Printer Profile:**
```cpp
OrcaSlicer                          FilamentHub
─────────────────────────────────────────────────────────
preset.setting_id              →   PrinterProfile.external_id
preset.name                    →   PrinterProfile.name
preset.config.to_json()        →   PrinterProfile.orcaslicer_settings
config["nozzle_diameter"]      →   PrinterProfile.nozzle_diameters
config["printable_area"]       →   PrinterProfile.printable_area
config["printable_height"]     →   PrinterProfile.printable_height_mm
config["start_gcode"]          →   PrinterProfile.start_gcode
config["end_gcode"]            →   PrinterProfile.end_gcode
```

**Print Profile:**
```cpp
OrcaSlicer                          FilamentHub
─────────────────────────────────────────────────────────
preset.setting_id              →   PrintProfile.external_id
preset.name                    →   PrintProfile.name
preset.config.to_json()        →   PrintProfile.orcaslicer_settings
config["layer_height"]         →   PrintProfile.layer_height_mm
config["compatible_printers"]  →   PrintProfile.compatible_printers
config["compatible_printers_condition"] → PrintProfile.extra_metadata["compatible_printers_condition"]
```

**Filament Preset:**
```cpp
OrcaSlicer                          FilamentHub
─────────────────────────────────────────────────────────
preset.setting_id              →   Preset.external_id
preset.name                    →   Preset.name
preset.config.to_json()        →   Preset.orcaslicer_settings
config["nozzle_temperature"][0] →  Preset.extruder_temp
config["bed_temperature"][0]   →   Preset.bed_temp
config["inherits"]             →   Filament.material_type (через маппинг)
```

### Маппинг material_type из OrcaSlicer inherits

```cpp
std::string FilamentHubPanel::map_orcaslicer_inherits_to_material_type(const std::string& inherits)
{
    // Маппинг системных пресетов OrcaSlicer на material_type FilamentHub
    if (inherits.find("PLA") != std::string::npos) {
        return "PLA";
    } else if (inherits.find("PETG") != std::string::npos) {
        return "PETG";
    } else if (inherits.find("ABS") != std::string::npos) {
        return "ABS";
    } else if (inherits.find("TPU") != std::string::npos) {
        return "TPU";
    } else if (inherits.find("ASA") != std::string::npos) {
        return "ASA";
    }
    // ... остальные типы
    
    return "PLA";  // По умолчанию
}
```

### Концепция черновиков для Filament

**Проблема:**
- `Filament.brand_id` обязателен (NOT NULL)
- Для импорта из OrcaSlicer нужно создавать пользовательские Filament без бренда

**Решение (черновики):**
- **Импортируем Filament как черновик** (`active=False`) с `brand_id=1` (служебный бренд "User Materials")
- Пользователь может **активировать** черновик и **привязать к своему бренду** через UI (`PATCH /api/v1/filaments/{filament_id}`)
- Черновики не отображаются в публичном каталоге (фильтр по `active=True`)
- Это удобно, потому что:
  - Не требует немедленного выбора бренда при импорте
  - Позволяет пользователю подготовить материал перед публикацией
  - Соответствует концепции черновиков для других сущностей (Preset, PrinterProfile, PrintProfile)

**Миграция:**
```sql
-- Создаем служебный бренд для черновиков из OrcaSlicer
INSERT INTO brands (id, name, slug, verified, active, description)
VALUES (1, 'User Materials', 'user-materials', FALSE, TRUE, 'User-imported materials from OrcaSlicer (drafts)')
ON CONFLICT (id) DO NOTHING;
```

**Активация черновика через UI:**
```python
# PATCH /api/v1/filaments/{filament_id}
# Пользователь может обновить:
# - brand_id: привязать к своему бренду
# - active: активировать (сделать видимым в каталоге)
# - name, description, color_name и т.д.
```

**Пример активации:**
```python
# Пользователь активирует черновик и привязает к своему бренду
PATCH /api/v1/filaments/123
{
  "brand_id": 5,  # ID бренда пользователя
  "active": True,  # Активировать (сделать видимым в каталоге)
  "name": "My Custom PLA Red",  # Обновить имя
  "color_name": "Red",  # Добавить цвет
}
```

### Print Settings (Print Profiles)

**Особенности:**
- **Не требуют UI для редактирования** - просто храним в `PrintProfile.orcaslicer_settings` (JSON)
- При экспорте в OrcaSlicer отдаем полный JSON обратно
- Все параметры print settings хранятся в `orcaslicer_settings` (см. структуру ниже)

**Структура Print Preset (из orca_bundles):**
```json
{
  "type": "process",
  "name": "0.20mm Standard @BBL A1",
  "inherits": "fdm_process_single_0.20",
  "from": "system",
  "setting_id": "GP079",
  "instantiation": "true",
  "description": "It has a general layer height, and results in general layer lines and printing quality. It is suitable for most general printing cases.",
  "default_acceleration": ["6000"],
  "elefant_foot_compensation": "0.075",
  "travel_speed": ["700"],
  "compatible_printers": ["Bambu Lab A1 0.4 nozzle"]
}
```

**Поля Print Preset:**
- **Мета-поля:**
  - `type`: `"process"` (всегда)
  - `name`: название пресета (например, "0.20mm Standard @BBL A1")
  - `inherits`: базовый пресет (например, "fdm_process_single_0.20")
  - `from`: источник (`"system"` или `"user"`)
  - `setting_id`: внутренний ID (например, "GP079")
  - `instantiation`: `"true"`/`"false"` (boolean)
  - `compatible_printers`: список совместимых принтеров (массив строк)
  - `compatible_printers_condition`: условие совместимости (строка)

- **Параметры печати (десятки ключей):**
  - `layer_height`: высота слоя (строка, например "0.20")
  - `wall_loops`: количество стен (строка)
  - `bridge_flow`: поток для мостов (строка, часто с `%`)
  - `speed_*`: скорости (массивы строк)
  - `acceleration_*`: ускорения (массивы строк)
  - `ironing_*`: параметры глажения (строки)
  - `seam_position`: позиция шва (строка)
  - `draft_shield`: защита от сквозняков (строка)
  - И многие другие параметры...

**Хранение в FilamentHub:**
```python
# PrintProfile модель
class PrintProfile(Base):
    # ...
    name: str  # "0.20mm Standard @BBL A1"
    slug: str  # Уникальный slug
    category: str | None  # "standard" (извлекается из имени)
    layer_height_mm: float | None  # 0.20 (нормализованное значение)
    compatible_printers: list[str] | None  # ["Bambu Lab A1 0.4 nozzle"]
    orcaslicer_settings: dict  # Полный JSON со всеми параметрами
    source: str  # "system" или "user"
    external_id: str | None  # "GP079" (для маппинга)
```

**Импорт из OrcaSlicer:**
- Все параметры сохраняются в `orcaslicer_settings` (JSON)
- Базовые поля (`layer_height_mm`, `compatible_printers`) извлекаются для удобства фильтрации
- При экспорте обратно в OrcaSlicer восстанавливается полный JSON

**Экспорт в OrcaSlicer:**
- Восстанавливаем исходную структуру (`type`, `name`, `inherits`, `from`)
- Отдаем полный `orcaslicer_settings` обратно
- Это гарантирует 100% совместимость с OrcaSlicer

**Примечание:** Print Settings не требуют UI для редактирования на сайте - они просто хранятся в JSON и отдаются обратно в OrcaSlicer. Пользователь может редактировать их в OrcaSlicer, а затем экспортировать обратно в FilamentHub.

---

## ✅ Чеклист реализации

### Backend (Python FastAPI)
- [ ] **Миграция БД:** Добавить `external_id` и `source` в таблицу `presets`
- [ ] **Миграция БД:** Добавить `allow_filament_presets_import` в таблицу `users`
- [ ] **Миграция БД:** Создать служебный бренд "User Materials" (id=1)
- [ ] **Модель Preset:** Добавить поля `external_id` и `source`
- [ ] **Модель User:** Добавить поле `allow_filament_presets_import`
- [ ] **Схемы:** Создать `OrcaFilamentPresetPayload`, `FilamentPresetSyncRequest`, `FilamentPresetSyncResponse`
- [ ] **Эндпоинт:** Реализовать `POST /api/v1/orcaslicer/filaments/import`
- [ ] **Функция:** Реализовать `_upsert_filament_preset()` с логикой создания Filament при импорте
- [ ] **Тесты:** Добавить тесты для импорта filament presets

### C++ Client (OrcaSlicer)
- [ ] **FilamentHubClient:** Добавить метод `import_filament_presets()` в `FilamentHubClient`
- [ ] **FilamentHubPanel:** Реализовать экспорт Filament Preset в JSON (`export_filament_preset()`)
- [ ] **FilamentHubPanel:** Реализовать экспорт Printer Profile в JSON (`export_printer_profile()`)
- [ ] **FilamentHubPanel:** Реализовать экспорт Print Profile в JSON (`export_print_profile()`)
- [ ] **FilamentHubPanel:** Реализовать отправку filament presets на сервер
- [ ] **FilamentHubPanel:** Добавить обработку ответов сервера для filament presets
- [ ] **FilamentHubPanel:** Сохранять маппинги `external_id → fhub_id` для filament presets

### C++ Panel (OrcaSlicer)
- [ ] **UI:** Добавить кнопку "Экспортировать в FilamentHub" в FilamentHubPanel
- [ ] **Функция:** Реализовать `export_profiles_to_filamenthub()` для экспорта всех 3 типов профилей
- [ ] **Логика:** Реализовать определение бандлов (если есть все 3 типа профилей)
- [ ] **Автоматизация:** Реализовать автоматический экспорт при первой синхронизации (опционально)

### Тестирование
- [ ] Протестировать импорт filament presets из OrcaSlicer в FilamentHub
- [ ] Протестировать создание Filament при импорте (если не указан filament_id)
- [ ] Протестировать обновление уже импортированных presets
- [ ] Протестировать маппинги `external_id → fhub_id`
- [ ] Протестировать бандлы (если есть все 3 типа профилей)

---

## 📚 Референсы

### Документация
- `docs/md/orca_analytics/ORCASLICER_BUNDLE_SCHEMA.md` - Структура бандлов OrcaSlicer
- `docs/md/orca_analytics/ORCASLICER_PROFILE_EXPORT_REFERENCE.md` - Референс экспорта профилей
- `docs/md/PRESET_DATA_FLOW.md` - Поток данных пресетов
- `ROADMAP.md` - Общий план развития проекта
- `TODO.md` - Список задач

### Код
- `backend/app/api/v1/endpoints/orca_sync.py` - Эндпоинты синхронизации
- `backend/app/schemas/orca_sync.py` - Pydantic схемы для синхронизации
- `backend/app/services/orcaslicer_service.py` - Сервис для работы с OrcaSlicer
- `backend/app/models/preset.py` - Модель Preset
- `backend/app/models/filament.py` - Модель Filament
- `backend/app/models/printer_profile.py` - Модель PrinterProfile
- `backend/app/models/print_profile.py` - Модель PrintProfile
- `backend/app/models/user.py` - Модель User
- `docs/OrcaSlicer/src/slic3r/Utils/FilamentHubClient.hpp/.cpp` - C++ HTTP клиент
- `docs/OrcaSlicer/src/slic3r/GUI/FilamentHubPanel.cpp` - Панель FilamentHub в OrcaSlicer

---

## ⚠️ Известные проблемы и ограничения

1. **Filament.brand_id обязателен:**
   - **Решение (черновики):** Импортируем Filament как черновик (`active=False`) с `brand_id=1` (служебный бренд "User Materials")
   - **Активация:** Пользователь может активировать черновик и привязать к своему бренду через UI (`PATCH /api/v1/filaments/{filament_id}`)
   - **Преимущества:** Не требует немедленного выбора бренда, позволяет подготовить материал перед публикацией

2. **Preset.external_id отсутствует:**
   - **Решение:** Добавить поле `external_id` в модель `Preset` (миграция БД)
   - **Альтернатива:** Использовать `slug` для маппинга (но менее надёжно)

3. **Preset.source отсутствует:**
   - **Решение:** Добавить поле `source` в модель `Preset` (миграция БД)
   - **Важно:** Для различения источников ("user", "system", "orcaslicer")

4. **User.allow_filament_presets_import отсутствует:**
   - **Решение:** Добавить поле `allow_filament_presets_import` в модель `User` (миграция БД)

5. **C++ Client не имеет метода import_filament_presets:**
   - **Решение:** Добавить метод `import_filament_presets()` в `FilamentHubClient`

---

**Дата создания:** 2025-11-12  
**Версия:** 1.2 (обновлено с концепцией черновиков и информацией о Print Settings)  
**Статус:** В разработке

**Изменения v1.2:**
- ✅ Добавлена концепция черновиков для Filament (импорт как `active=False`, активация через UI)
- ✅ Добавлена информация о Print Settings (не требуют UI, храним в JSON)
- ✅ Добавлена структура Print Preset из orca_bundles
- ✅ Обновлено решение проблемы с `Filament.brand_id` (черновики вместо nullable)
- ✅ Добавлены примеры активации черновиков через UI
