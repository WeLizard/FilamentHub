# Анализ пути получения профилей (Presets) в FilamentHub

## 📊 Полный путь данных: БД → Backend → API → Frontend

### 1. База данных (PostgreSQL)

#### Таблица `presets`
```sql
CREATE TABLE presets (
    id SERIAL PRIMARY KEY,
    filament_id INTEGER REFERENCES filaments(id),
    user_id INTEGER REFERENCES users(id),
    name VARCHAR(200),
    description TEXT,
    is_official BOOLEAN DEFAULT FALSE,
    
    -- Print settings
    extruder_temp FLOAT,
    bed_temp FLOAT,
    print_speed FLOAT,
    travel_speed FLOAT,
    
    -- Advanced settings
    layer_height FLOAT,
    first_layer_height FLOAT,
    flow_rate FLOAT,
    fan_speed INTEGER,
    retraction_length FLOAT,
    retraction_speed FLOAT,
    
    -- Extended OrcaSlicer parameters (JSON)
    orcaslicer_settings JSONB,
    
    -- Rating & usage
    rating FLOAT,
    usage_count INTEGER DEFAULT 0,
    
    -- Moderation
    moderation_status VARCHAR(20) DEFAULT 'pending',
    moderation_reason TEXT,
    moderated_by INTEGER,
    moderated_at TIMESTAMP WITH TIME ZONE,
    
    -- Status
    active BOOLEAN DEFAULT TRUE,
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

#### Таблица `user_saved_presets` (связь Many-to-Many)
```sql
CREATE TABLE user_saved_presets (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    preset_id INTEGER REFERENCES presets(id),
    saved_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(user_id, preset_id)
);
```

---

### 2. Backend (FastAPI + SQLAlchemy)

#### 2.1 Модель данных (`app/models/preset.py`)

```python
class Preset(Base):
    __tablename__ = "presets"
    
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    filament_id: Mapped[int] = mapped_column(ForeignKey("filaments.id"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True, nullable=True)
    
    # Основные поля
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_official: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    
    # Параметры печати
    extruder_temp: Mapped[float] = mapped_column(Float)
    bed_temp: Mapped[float] = mapped_column(Float)
    print_speed: Mapped[float] = mapped_column(Float)
    travel_speed: Mapped[float | None] = mapped_column(Float, nullable=True)
    
    # Продвинутые настройки
    layer_height: Mapped[float | None] = mapped_column(Float, nullable=True)
    first_layer_height: Mapped[float | None] = mapped_column(Float, nullable=True)
    flow_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    fan_speed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retraction_length: Mapped[float | None] = mapped_column(Float, nullable=True)
    retraction_speed: Mapped[float | None] = mapped_column(Float, nullable=True)
    
    # Расширенные параметры OrcaSlicer (JSON)
    orcaslicer_settings: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    
    # Рейтинг и статистика
    rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # Модерация
    moderation_status: Mapped[PresetModerationStatus] = mapped_column(
        SQLEnum(PresetModerationStatus),
        default=PresetModerationStatus.PENDING,
        nullable=False,
        index=True
    )
    
    # Relationships
    filament: Mapped["Filament"] = relationship("Filament", back_populates="presets")
    user: Mapped["User"] = relationship("User", back_populates="presets")
    saved_by_users: Mapped[list["UserSavedPreset"]] = relationship(
        "UserSavedPreset", back_populates="preset", cascade="all, delete-orphan"
    )
```

#### 2.2 Схемы валидации (`app/schemas/preset.py`)

**PresetResponse** - схема ответа API:
```python
class PresetResponse(PresetBase):
    id: int
    filament_id: int
    user_id: int | None = None
    active: bool
    moderation_status: str  # pending, approved, rejected
    moderation_reason: str | None = None
    moderated_by: int | None = None
    moderated_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
```

**PresetListResponse** - схема списка:
```python
class PresetListResponse(BaseModel):
    items: list[PresetResponse]
    total: int
    page: int
    size: int
    pages: int
```

---

### 3. API Endpoints (FastAPI)

#### 3.1 Основные эндпоинты (`app/api/v1/endpoints/presets.py`)

##### `GET /api/v1/presets/` - Список пресетов
```python
@router.get("/", response_model=PresetListResponse)
async def list_presets(
    db: AsyncSession,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    active_only: bool = Query(True),
    filament_id: int | None = Query(None, gt=0),
    is_official: bool | None = Query(None),
    user_id: int | None = Query(None, gt=0),
) -> PresetListResponse:
```

**SQL запрос:**
```python
# Базовая выборка
query = select(Preset)

# Фильтры
if active_only:
    query = query.where(Preset.active == True)
if filament_id:
    query = query.where(Preset.filament_id == filament_id)
if is_official is not None:
    query = query.where(Preset.is_official == is_official)
if user_id is not None:
    # Показываем ВСЕ пресеты пользователя (включая неодобренные)
    query = query.where(Preset.user_id == user_id)
else:
    # Показываем только одобренные пресеты
    query = query.where(
        or_(
            Preset.moderation_status == PresetModerationStatus.APPROVED,
            Preset.is_official == True  # Официальные всегда видимы
        )
    )

# Пагинация
offset = (page - 1) * size
query = query.offset(offset).limit(size)

# Выполнение
result = await db.execute(query)
presets = result.scalars().all()
```

##### `GET /api/v1/presets/{preset_id}` - Получить пресет по ID
```python
@router.get("/{preset_id}", response_model=PresetResponse)
async def get_preset(
    preset_id: int,
    db: AsyncSession,
) -> PresetResponse:
```

**SQL запрос:**
```python
result = await db.execute(select(Preset).where(Preset.id == preset_id))
preset = result.scalar_one_or_none()
```

##### `GET /api/v1/presets/{preset_id}/export/orcaslicer.json` - Экспорт в OrcaSlicer
```python
@router.get("/{preset_id}/export/orcaslicer.json")
async def export_preset_json(
    preset_id: int,
    db: AsyncSession,
) -> Response:
```

**Процесс:**
1. Загружает preset с filament и brand (eager loading)
2. Вызывает `preset_to_orcaslicer_json(preset, preset.filament)`
3. Возвращает JSON файл с правильными заголовками

#### 3.2 Эндпоинт для синхронизации (`app/api/v1/endpoints/auth.py`)

##### `GET /api/v1/auth/my-presets` - Все пресеты пользователя (созданные + сохраненные)
```python
@router.get("/my-presets", response_model=PresetListResponse)
async def get_my_presets(
    current_user: User,
    db: AsyncSession,
    updated_since: datetime | None = Query(None),
) -> PresetListResponse:
```

**SQL запросы:**

1. **Созданные пресеты** (где `user_id == current_user.id`):
```python
created_query = select(Preset).where(
    Preset.user_id == current_user.id,
    Preset.active == True,
)
if updated_since:
    created_query = created_query.where(Preset.updated_at >= updated_since)

created_result = await db.execute(created_query.options(selectinload(Preset.filament)))
created_presets = created_result.scalars().all()
```

2. **Сохраненные пресеты** (через `user_saved_presets`):
```python
saved_query = select(UserSavedPreset).where(
    UserSavedPreset.user_id == current_user.id,
)
if updated_since:
    saved_query = saved_query.join(Preset).where(
        or_(
            UserSavedPreset.saved_at >= updated_since,
            Preset.updated_at >= updated_since,
        ),
    )
else:
    saved_query = saved_query.join(Preset)

saved_result = await db.execute(
    saved_query.options(selectinload(UserSavedPreset.preset).selectinload(Preset.filament))
)
saved_presets_relations = saved_result.scalars().all()
```

3. **Объединение и дедупликация:**
```python
preset_ids: set[int] = set()
presets_dict: dict[int, Preset] = {}

# Добавляем созданные
for preset in created_presets:
    preset_ids.add(preset.id)
    presets_dict[preset.id] = preset

# Добавляем сохраненные (без дубликатов)
for saved_preset_relation in saved_presets_relations:
    preset = saved_preset_relation.preset
    if preset.active and preset.id not in preset_ids:
        preset_ids.add(preset.id)
        presets_dict[preset.id] = preset

# Формируем итоговый список
presets_list = [presets_dict[pid] for pid in sorted(preset_ids)]
```

---

### 4. Frontend (React + TypeScript)

#### 4.1 API Client (`frontend/src/api/client.ts`)

**Axios instance:**
```typescript
const api = axios.create({
  baseURL: '/api/v1',
  headers: {
    'Content-Type': 'application/json',
  },
});

// Interceptor для добавления токена
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});
```

**Presets API:**
```typescript
export const presetsAPI = {
  list: async (params?: {
    page?: number;
    size?: number;
    active_only?: boolean;
    filament_id?: number;
    is_official?: boolean;
    user_id?: number;
  }) => {
    const response = await api.get<ListResponse<Preset>>('/presets/', { params });
    return response.data;
  },

  get: async (id: number) => {
    const response = await api.get<Preset>(`/presets/${id}`);
    return response.data;
  },

  // ... другие методы
};
```

#### 4.2 TypeScript типы (`frontend/src/types/api.ts`)

```typescript
export interface Preset {
  id: number;
  filament_id: number;
  name: string;
  description: string | null;
  is_official: boolean;
  extruder_temp: number;
  bed_temp: number;
  print_speed: number;
  travel_speed: number | null;
  layer_height: number | null;
  first_layer_height: number | null;
  flow_rate: number | null;
  fan_speed: number | null;
  retraction_length: number | null;
  retraction_speed: number | null;
  orcaslicer_settings: Record<string, any> | null;
  rating: number | null;
  usage_count: number;
  active: boolean;
  moderation_status: string;
  created_at: string;
  updated_at: string;
  source?: 'own' | 'saved'; // UI helper
  user_id?: number | null;
}

export interface ListResponse<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
  pages: number;
}
```

#### 4.3 Использование на страницах

##### `ProfilePage.tsx` - Профиль пользователя

**Загрузка созданных пресетов:**
```typescript
const { data: userPresetsData } = useQuery({
  queryKey: ['user-presets', user?.id],
  queryFn: () => presetsAPI.list({ 
    active_only: true, 
    page: 1, 
    size: 100, 
    user_id: user?.id 
  }),
  enabled: !!user?.id,
});
```

**Загрузка сохраненных пресетов:**
```typescript
const { data: savedPresetsData } = useQuery({
  queryKey: ['saved-presets', user?.id],
  queryFn: () => savedPresetsAPI.list(),
  enabled: !!user?.id,
});

// Загружаем детали сохраненных пресетов
const savedPresetIds = savedPresetsData?.items.map(sp => sp.preset_id) || [];
const { data: savedPresetsDetails } = useQuery({
  queryKey: ['saved-presets-details', savedPresetIds],
  queryFn: async () => {
    const details = await Promise.all(
      savedPresetIds.map(presetId => presetsAPI.get(presetId))
    );
    return details;
  },
  enabled: savedPresetIds.length > 0,
});
```

**Объединение пресетов:**
```typescript
const allMyPresets = useMemo(() => {
  const created = (userPresetsData?.items || []).map(p => ({ ...p, source: 'own' as const }));
  const saved = (savedPresetsDetails || []).map(p => ({ ...p, source: 'saved' as const }));
  return [...created, ...saved];
}, [userPresetsData, savedPresetsDetails]);
```

---

## 🔄 Полный flow получения профилей

### Сценарий 1: Получение списка пресетов (публичные)

```
Frontend → API Client → Backend API → SQLAlchemy → PostgreSQL
   ↓           ↓            ↓             ↓            ↓
useQuery  presetsAPI   GET /presets/  select(Preset)  SELECT FROM presets
   ↓           ↓            ↓             ↓            ↓
UI Render  ListResponse  PresetListResponse  ORM Objects  Database Rows
```

**Детали:**
1. Frontend: `useQuery` вызывает `presetsAPI.list()`
2. API Client: делает HTTP GET `/api/v1/presets/`
3. Backend: эндпоинт `list_presets()` строит SQL запрос
4. SQLAlchemy: выполняет `SELECT * FROM presets WHERE ...`
5. PostgreSQL: возвращает строки из БД
6. SQLAlchemy: маппит в объекты Python `Preset`
7. Backend: валидирует через `PresetResponse.model_validate()`
8. API Client: получает JSON ответ
9. Frontend: типизирует через TypeScript `Preset[]`
10. UI: рендерит компоненты

### Сценарий 2: Синхронизация пресетов в OrcaSlicer

```
OrcaSlicer → C++ Client → Backend API → SQLAlchemy → PostgreSQL
     ↓            ↓            ↓             ↓            ↓
WebView    FilamentHubClient  GET /auth/my-presets  UNION queries  SELECT + JOIN
     ↓            ↓            ↓             ↓            ↓
JSON Import  nlohmann::json  PresetListResponse  ORM Objects  Database Rows
```

**Детали:**
1. OrcaSlicer: WebView загружает FilamentHub
2. C++ Client: вызывает `get_my_presets(access_token, updated_since)`
3. Backend: эндпоинт `get_my_presets()` выполняет:
   - Запрос созданных пресетов
   - Запрос сохраненных пресетов (через JOIN)
   - Объединение и дедупликация
4. PostgreSQL: два SELECT запроса
5. Backend: объединяет результаты в список
6. C++: парсит JSON через `nlohmann::json`
7. OrcaSlicer: импортирует каждый пресет через `import_json_presets()`

### Сценарий 3: Экспорт пресета в OrcaSlicer JSON

```
Frontend → API Client → Backend API → OrcaSlicer Exporter → JSON Response
   ↓           ↓            ↓                 ↓                   ↓
Download   GET /presets/  export_preset_json  preset_to_orcaslicer_json  JSON File
   ↓           ↓            ↓                 ↓                   ↓
   ↓      Response File  Load Preset + Filament  Map to OrcaSlicer format  Download
```

**Детали:**
1. Frontend: клик на "Download" → `presetsAPI.exportOrcaSlicer(presetId)`
2. API Client: GET `/api/v1/presets/{id}/export/orcaslicer.json`
3. Backend: эндпоинт загружает preset с filament и brand
4. Exporter: вызывает `preset_to_orcaslicer_json(preset, filament)`
5. Exporter: преобразует данные в формат OrcaSlicer:
   - Маппит material_type → `"Generic PLA @System"` (inherits)
   - Конвертирует все значения в массивы строк
   - Добавляет расширенные параметры из `orcaslicer_settings`
6. Backend: возвращает JSON файл с правильными заголовками
7. Frontend: скачивает файл

---

## 📋 Важные моменты

### Модерация пресетов
- **Официальные** пресеты (`is_official=True`) автоматически одобрены
- **Пользовательские** пресеты требуют модерации (`moderation_status`)
- В публичных списках показываются только **одобренные** пресеты
- Пользователь видит **все свои** пресеты (включая неодобренные)

### Пагинация
- Все списки поддерживают пагинацию (`page`, `size`)
- Максимальный размер страницы: 100 элементов
- По умолчанию: `page=1`, `size=50`

### Инкрементальная синхронизация
- Параметр `updated_since` позволяет получить только измененные пресеты
- Полезно для синхронизации в OrcaSlicer
- Работает как для созданных, так и для сохраненных пресетов

### Eager Loading
- Используется `selectinload()` для загрузки связанных объектов
- `Preset.filament` и `Filament.brand` загружаются одним запросом
- Избегаем N+1 query problem

### Расширенные параметры
- Поле `orcaslicer_settings` (JSONB) хранит параметры, которых нет в базовых полях
- При экспорте эти параметры добавляются в JSON
- Позволяет хранить любые параметры OrcaSlicer

---

## 🎯 Выводы

1. **Архитектура:** Clean separation между слоями (DB → Model → Schema → API → Client → UI)
2. **Типизация:** TypeScript на фронтенде + Pydantic на бэкенде
3. **Производительность:** Eager loading, пагинация, индексы в БД
4. **Гибкость:** JSON поле для расширенных параметров
5. **Безопасность:** Модерация, права доступа, фильтрация

