# Система QR-кодов для FilamentHub

## 📋 Обзор

Система QR-кодов позволяет производителям автоматически получать QR-коды для своих материалов. При создании нового филамента верифицированным брендом автоматически генерируется QR-код, который можно скачать и распечатать на наклейках для катушек.

**Пользователь сканирует QR-код → Открывается сайт → Официальный пресет автоматически подтягивается в профиль пользователя → Импорт в OrcaSlicer**

## 🎯 Концепция

### Автоматическая генерация QR-кодов для верифицированных брендов

**Когда производитель создает новый филамент:**
1. ✅ Филамент создается в системе
2. ✅ **АВТОМАТИЧЕСКИ** генерируется уникальный QR-код
3. ✅ QR-код связывается с филаментом (через `short_code`)
4. ✅ Производитель может скачать QR-код в высоком разрешении для печати
5. ✅ QR-код можно распечатать на наклейках и разместить на катушках

**Когда пользователь сканирует QR-код:**
1. 📱 Открывается мобильная версия сайта FilamentHub
2. 🔍 Определяется материал по короткому коду
3. 📊 Отображается информация о материале и официальный пресет
4. ⚡ **Автоматически подтягивается официальный пресет в профиль пользователя**
5. 🖨️ Если пользователь авторизован в OrcaSlicer → автоматический импорт профиля
6. 📈 Инкрементируется счетчик сканирований

## 🎯 Цели системы

1. **Автоматизация для производителей** - QR-код создается автоматически, не нужно ничего делать вручную
2. **Упрощение поиска материалов** - быстрое получение информации о филаменте по QR-коду
3. **Автоматический импорт профилей** - сканирование → профиль уже в системе пользователя
4. **Аналитика для производителей** - отслеживание сканирований и популярности материалов
5. **Маркетинг** - производители могут размещать QR-коды на упаковке без дополнительных действий

## 🎯 Цели системы

1. **Упрощение поиска материалов** - быстрое получение информации о филаменте по QR-коду
2. **Автоматический импорт профилей** - сканирование → импорт в OrcaSlicer
3. **Аналитика для производителей** - отслеживание сканирований и популярности материалов
4. **Маркетинг** - производители могут размещать QR-коды на упаковке

## 📊 Текущее состояние

### ✅ Уже реализовано:
- Поле `scans_count` в модели `Filament` для отслеживания сканирований
- UI заглушка в `BrandProfilePage` с отображением статистики
- Базовая структура для QR-кодов

### ❌ Что нужно реализовать:

## 🔧 Backend компоненты

### 1. Автоматическая генерация QR-кодов при создании филамента

**Триггер:** При создании нового филамента верифицированным брендом (`brand.verified == True`)

**Логика:**
```python
# В эндпоинте POST /api/v1/filaments
async def create_filament(data: FilamentCreate, brand: Brand):
    # Создаем филамент
    filament = Filament(**data.dict())
    
    # Если бренд верифицирован - автоматически генерируем QR-код
    if brand.verified:
        short_code = generate_short_code(filament.id)  # FHUB-ABC123
        filament.qr_code = short_code  # Сохраняем короткий код
        
        # Генерируем QR-код и сохраняем в кэш/файловую систему
        qr_image = generate_qr_code_image(short_code)
        await save_qr_code_image(filament.id, qr_image)
    
    await db.commit()
    return filament
```

**Модель Filament (добавить поле):**
```python
class Filament(Base):
    # ... существующие поля ...
    
    qr_code: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True, index=True)
    # qr_code: короткий код для QR-кода (например: "FHUB-ABC123")
    # Автоматически генерируется для верифицированных брендов
```

### 2. Генерация QR-кодов

**Библиотека:** `qrcode[pil]` (Python)

**Эндпоинты:**
```
GET /api/v1/filaments/{id}/qr-code
  - Генерирует QR-код для материала
  - Возвращает изображение (PNG/SVG)
  - Параметры: size, format (png/svg)
  - Права: только brand владелец материала

GET /api/v1/filaments/{id}/qr-code/download
  - Скачивание QR-кода в высоком разрешении
  - Форматы: PNG (300x300px, 600x600px, 1200x1200px)
  - Права: только brand владелец материала
```

**Структура URL в QR-коде:**
```
https://filamenthub.ru/qr/{short_code}
или
https://filamenthub.ru/filaments/{id}?qr=true
```

**Короткий код:**
- Формат: `FHUB-{base36(filament_id)}`
- Пример: `FHUB-ABC123` для материала с ID 1234567
- Преобразование ID в base36 для коротких URL

### 3. Обработка сканирований и автоматический импорт пресета

**Эндпоинты:**
```
GET /api/v1/qr/{short_code}
  - Редирект на страницу материала
  - Инкрементирует scans_count
  - Логирует сканирование (опционально)
  - Если пользователь авторизован → автоматически добавляет официальный пресет в профиль

POST /api/v1/qr/{short_code}/scan
  - Регистрирует сканирование
  - Инкрементирует scans_count
  - Возвращает данные материала и пресетов
  - **Автоматически добавляет официальный пресет в профиль пользователя** (если авторизован)
  - Опционально: сохраняет метаданные (user_agent, IP, timestamp)
```

**Логика автоматического импорта пресета:**
```python
@router.post("/qr/{short_code}/scan")
async def handle_qr_scan(
    short_code: str,
    current_user: User = Depends(get_current_active_user_optional),  # Опциональная авторизация
    db: AsyncSession = Depends(get_db)
):
    # Получаем материал по короткому коду
    filament = await get_filament_by_qr_code(short_code, db)
    
    # Инкрементируем счетчик
    filament.scans_count += 1
    
    # Если пользователь авторизован
    if current_user:
        # Находим официальный пресет для материала
        official_preset = await get_official_preset(filament.id, db)
        
        if official_preset:
            # Проверяем, нет ли уже этого пресета в профиле пользователя
            existing = await db.execute(
                select(UserSavedPreset).where(
                    UserSavedPreset.user_id == current_user.id,
                    UserSavedPreset.preset_id == official_preset.id
                )
            )
            
            if not existing.scalar_one_or_none():
                # Добавляем пресет в профиль пользователя
                saved_preset = UserSavedPreset(
                    user_id=current_user.id,
                    preset_id=official_preset.id,
                    source='qr_scan'  # Метка источника
                )
                db.add(saved_preset)
                
                # Логируем событие
                await log_event('preset_auto_added_from_qr', {
                    'user_id': current_user.id,
                    'preset_id': official_preset.id,
                    'filament_id': filament.id
                })
    
    await db.commit()
    
    return {
        'filament': filament,
        'preset_added': official_preset is not None if current_user else False
    }
```

**Модель для логирования сканирований (опционально):**
```python
class QRScan(Base):
    id: int
    filament_id: int
    scanned_at: datetime
    user_id: int | None  # Если пользователь авторизован
    ip_address: str | None
    user_agent: str | None
    referer: str | None
```

### 3. Статистика сканирований

**Эндпоинты:**
```
GET /api/v1/brands/{id}/qr-stats
  - Статистика по всем материалам бренда
  - Фильтры: date_from, date_to, filament_id
  - Права: только brand владелец

GET /api/v1/filaments/{id}/qr-stats
  - Детальная статистика по материалу
  - Графики по дням/неделям/месяцам
  - Права: только brand владелец материала
```

## 🎨 Frontend компоненты

### 1. Автоматическое отображение QR-кода в профиле бренда

**Файл:** `frontend/src/pages/BrandProfilePage.tsx`

**Изменения:**
- После создания филамента автоматически показывается QR-код
- QR-код виден сразу в карточке материала
- Кнопка "Скачать QR-код" для печати наклейки

**Компонент:** `QRCodeCard` - уже есть, нужно доработать

**Функционал:**
- ✅ Превью QR-кода в карточке материала (если бренд верифицирован)
- ✅ Кнопка "Скачать QR-код" с выбором размера (300x300, 600x600, 1200x1200px)
- ✅ Копирование короткого кода в буфер обмена
- ✅ Информация о количестве сканирований

**Компонент:** `QRCodeGenerator` или интеграция библиотеки `qrcode.react`

### 2. Страница обработки QR-кода (мобильная версия)

**Роут:** `/qr/:shortCode` или `/filaments/:id?qr=true`

**Функционал:**
- Автоматическое определение материала по короткому коду
- Отображение информации о материале
- Кнопка "Импортировать в OrcaSlicer"
- Список пресетов для материала
- Редирект на страницу материала после импорта

**Компонент:** `QRScanPage.tsx`

### 3. Мобильная версия

**Особенности:**
- Оптимизация для мобильных устройств
- Быстрая загрузка страницы после сканирования
- Возможность сканирования QR-кода с сайта (камера)

## 📦 Зависимости

### Backend:
```python
# requirements.txt
qrcode[pil]>=7.4.2  # Генерация QR-кодов
Pillow>=10.0.0      # Обработка изображений (входит в qrcode[pil])
```

### Frontend:
```json
// package.json
{
  "qrcode.react": "^3.1.0",  // Генерация QR-кодов на клиенте
  "qrcode": "^1.5.3"          // Генерация QR-кодов (опционально)
}
```

## 🔐 Безопасность

### Защита от злоупотреблений:
1. **Rate limiting** на эндпоинты сканирования
2. **Валидация short_code** - проверка формата и существования материала
3. **Логирование подозрительной активности** - множественные сканирования с одного IP
4. **Ограничение генерации QR-кодов** - только для активных материалов

### Оптимизация:
1. **Кэширование QR-кодов** - Redis для хранения сгенерированных изображений
2. **CDN для статических QR-кодов** - быстрая загрузка изображений
3. **Инкрементация scans_count** - асинхронная обработка через очередь задач

## 🗄️ База данных

### Миграция для таблицы QR-сканирований (опционально):
```sql
CREATE TABLE qr_scans (
    id SERIAL PRIMARY KEY,
    filament_id INTEGER NOT NULL REFERENCES filaments(id),
    scanned_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    user_id INTEGER REFERENCES users(id),
    ip_address INET,
    user_agent TEXT,
    referer TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_qr_scans_filament_id ON qr_scans(filament_id);
CREATE INDEX idx_qr_scans_scanned_at ON qr_scans(scanned_at);
CREATE INDEX idx_qr_scans_user_id ON qr_scans(user_id);
```

## 📱 Интеграция с OrcaSlicer через QR-код

### Автоматический импорт профиля:

**Сценарий 1: Пользователь авторизован на сайте**
1. Пользователь сканирует QR-код на мобильном устройстве
2. Открывается страница FilamentHub `/qr/{short_code}`
3. **Автоматически вызывается POST /qr/{short_code}/scan**
4. **Официальный пресет автоматически добавляется в профиль пользователя**
5. Показывается уведомление: "Пресет добавлен в ваш профиль!"
6. Кнопка "Импортировать в OrcaSlicer" (если приложение установлено)

**Сценарий 2: Пользователь НЕ авторизован**
1. Пользователь сканирует QR-код
2. Открывается страница с материалом
3. Предложение авторизоваться для автоматического импорта пресета
4. После авторизации → пресет добавляется автоматически

**Сценарий 3: Пользователь в OrcaSlicer (WebView)**
1. Сканирование QR-кода открывает FilamentHub в WebView OrcaSlicer
2. Если пользователь авторизован в OrcaSlicer → автоматический импорт профиля
3. Профиль появляется в dropdown "Профиль прутка"

### API для импорта:
```
POST /api/v1/qr/{short_code}/scan
  - Регистрирует сканирование
  - Если пользователь авторизован → автоматически добавляет официальный пресет
  - Возвращает: { filament, preset_added: bool, preset: Preset }

GET /api/v1/qr/{short_code}/preset
  - Возвращает официальный пресет для материала
  - Формат: OrcaSlicer JSON профиль
  - Используется для импорта в OrcaSlicer
```

## 📊 Аналитика

### Метрики для производителей:
- Общее количество сканирований
- Уникальные сканирования (по IP или user_id)
- Популярные материалы
- География сканирований (по IP, опционально)
- Время сканирований (часы/дни недели)

### Визуализация:
- График сканирований по дням
- Топ материалов по сканированиям
- Географическая карта (если доступна геолокация)

## 🚀 Поэтапная реализация

### Этап 1: Автоматическая генерация QR-кодов (1-2 недели) ⭐ ПРИОРИТЕТ

**Backend:**
- [ ] Добавить поле `qr_code` в модель `Filament`
- [ ] Функция генерации короткого кода `generate_short_code(filament_id)`
- [ ] Логика автоматической генерации при создании филамента (для верифицированных брендов)
- [ ] Миграция БД для добавления поля `qr_code`
- [ ] Эндпоинт `GET /api/v1/filaments/{id}/qr-code` (генерация/возврат)
- [ ] Эндпоинт `GET /api/v1/filaments/{id}/qr-code/download` (скачивание)

**Frontend:**
- [ ] Обновить `CreateFilamentModal` - показывать QR-код после создания
- [ ] Обновить `QRCodeCard` - отображать QR-код для верифицированных брендов
- [ ] Кнопка скачивания QR-кода с выбором размера
- [ ] Превью QR-кода в карточке материала

### Этап 2: Обработка сканирований и автоматический импорт (1 неделя) ⭐ ПРИОРИТЕТ

**Backend:**
- [ ] Эндпоинт `GET /api/v1/qr/{short_code}` (редирект + инкремент)
- [ ] Эндпоинт `POST /api/v1/qr/{short_code}/scan` (регистрация + автоматический импорт)
- [ ] Логика автоматического добавления официального пресета в профиль пользователя
- [ ] Проверка на дубликаты (не добавлять пресет дважды)

**Frontend:**
- [ ] Страница `/qr/:shortCode` - обработка сканирования
- [ ] Мобильная оптимизация страницы
- [ ] Уведомление о добавлении пресета в профиль
- [ ] Кнопка "Импортировать в OrcaSlicer"

### Этап 3: Статистика и аналитика (1 неделя)
- [ ] Таблица `qr_scans` для детального логирования (опционально)
- [ ] Эндпоинты статистики для брендов
- [ ] Графики сканирований в профиле бренда
- [ ] Экспорт статистики (CSV/JSON)

### Этап 4: Оптимизация и интеграция (1 неделя)
- [ ] Кэширование QR-кодов в Redis
- [ ] Интеграция с OrcaSlicer (автоматический импорт через WebView)
- [ ] SEO оптимизация для страниц QR-кодов
- [ ] Deep links для открытия OrcaSlicer

### Этап 5: Расширенные функции (опционально)
- [ ] Географическая аналитика
- [ ] Уведомления производителям о новых сканированиях
- [ ] A/B тестирование дизайна QR-кодов
- [ ] Интеграция с типографией для печати QR-кодов
- [ ] Массовое скачивание QR-кодов для всех материалов бренда

## 📝 Примеры использования

### Автоматическая генерация QR-кода при создании филамента (Backend):
```python
import qrcode
from io import BytesIO
import base36

def generate_short_code(filament_id: int) -> str:
    """Генерирует короткий код для QR-кода: FHUB-ABC123"""
    base36_id = base36.dumps(filament_id).upper()
    return f"FHUB-{base36_id}"

async def create_filament_with_qr(data: FilamentCreate, brand: Brand, db: AsyncSession):
    """Создает филамент и автоматически генерирует QR-код для верифицированных брендов"""
    filament = Filament(**data.dict(), brand_id=brand.id)
    
    # Если бренд верифицирован - автоматически генерируем QR-код
    if brand.verified:
        short_code = generate_short_code(filament.id)  # Временно используем ID (потом обновим после commit)
        
        # Сохраняем филамент сначала
        db.add(filament)
        await db.flush()  # Получаем ID
        
        # Теперь генерируем правильный код с реальным ID
        short_code = generate_short_code(filament.id)
        
        # Проверяем уникальность (на случай коллизий)
        existing = await db.execute(
            select(Filament).where(Filament.qr_code == short_code)
        )
        if existing.scalar_one_or_none():
            # Если коллизия - добавляем суффикс
            short_code = f"{short_code}-{filament.id % 1000}"
        
        filament.qr_code = short_code
        
        # Генерируем QR-код изображение и сохраняем в кэш/файловую систему
        qr_image = generate_qr_code_image(short_code)
        await save_qr_code_image(filament.id, qr_image)
    
    await db.commit()
    await db.refresh(filament)
    return filament

def generate_qr_code_image(short_code: str, size: int = 300) -> BytesIO:
    """Генерирует изображение QR-кода"""
    url = f"https://filamenthub.ru/qr/{short_code}"
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Масштабируем до нужного размера
    if size != 300:
        img = img.resize((size, size), Image.Resampling.LANCZOS)
    
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    return buffer
```

### Обработка сканирования с автоматическим импортом пресета (Backend):
```python
@router.post("/qr/{short_code}/scan")
async def handle_qr_scan(
    short_code: str,
    current_user: User | None = Depends(get_current_active_user_optional),
    db: AsyncSession = Depends(get_db),
    request: Request = None
):
    # Получаем материал по короткому коду
    result = await db.execute(
        select(Filament).where(Filament.qr_code == short_code)
    )
    filament = result.scalar_one_or_none()
    
    if not filament:
        raise HTTPException(404, "Material not found")
    
    # Инкрементируем счетчик
    filament.scans_count += 1
    
    preset_added = False
    official_preset = None
    
    # Если пользователь авторизован - автоматически добавляем официальный пресет
    if current_user:
        # Находим официальный пресет для материала
        preset_result = await db.execute(
            select(Preset).where(
                Preset.filament_id == filament.id,
                Preset.is_official == True,
                Preset.active == True
            ).order_by(Preset.created_at.desc())
            .limit(1)
        )
        official_preset = preset_result.scalar_one_or_none()
        
        if official_preset:
            # Проверяем, нет ли уже этого пресета в профиле пользователя
            existing = await db.execute(
                select(UserSavedPreset).where(
                    UserSavedPreset.user_id == current_user.id,
                    UserSavedPreset.preset_id == official_preset.id
                )
            )
            
            if not existing.scalar_one_or_none():
                # Добавляем пресет в профиль пользователя
                saved_preset = UserSavedPreset(
                    user_id=current_user.id,
                    preset_id=official_preset.id,
                    source='qr_scan'  # Метка источника
                )
                db.add(saved_preset)
                preset_added = True
    
    await db.commit()
    
    return {
        'filament': FilamentResponse.model_validate(filament),
        'preset_added': preset_added,
        'preset': PresetResponse.model_validate(official_preset) if official_preset else None
    }

@router.get("/qr/{short_code}")
async def redirect_qr_scan(
    short_code: str,
    db: AsyncSession = Depends(get_db)
):
    """Редирект на страницу материала (для прямых ссылок)"""
    result = await db.execute(
        select(Filament).where(Filament.qr_code == short_code)
    )
    filament = result.scalar_one_or_none()
    
    if not filament:
        raise HTTPException(404, "Material not found")
    
    # Инкрементируем счетчик
    filament.scans_count += 1
    await db.commit()
    
    # Редирект на страницу материала
    return RedirectResponse(f"/filaments/{filament.id}?qr=true")
```

### Отображение QR-кода (Frontend):
```tsx
import QRCode from 'qrcode.react';

<QRCode
  value={`https://filamenthub.ru/qr/${shortCode}`}
  size={256}
  level="H"
  includeMargin={true}
/>
```

## 🔗 Полезные ссылки

- [qrcode Python library](https://github.com/lincolnloop/python-qrcode)
- [qrcode.react React library](https://github.com/zpao/qrcode.react)
- [QR Code Best Practices](https://www.qr-code-generator.com/qr-code-marketing/qr-code-best-practices/)

## ⚠️ Важные замечания

1. **Короткие коды должны быть уникальными** - нужна проверка на коллизии
2. **QR-коды должны быть читаемыми** - минимум размер 300x300px для печати
3. **URL должны быть короткими** - длинные URL требуют более сложных QR-кодов
4. **Обработка ошибок** - невалидные коды должны обрабатываться корректно
5. **Производительность** - генерация QR-кодов должна быть быстрой (кэширование)

