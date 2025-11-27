# FilamentHub - Состояние проекта (Ноябрь 2025)

> **Дата обновления:** 2025-11-20  
> **Анализ:** Полный технический аудит Backend, Frontend, OrcaSlicer Integration

---

## 📊 Общая статистика

### База данных (PostgreSQL)
- **Таблицы:** 20
- **Филаменты:** 36
- **Бренды:** 7
- **Пресеты:** 19
- **Пользователи:** 9
- **Принтеры:** 338
- **Поле `slug` восстановлено:** ✅ Все 36 филаментов имеют уникальные slug

### Архитектура
```
FilamentHub/
├── backend/              # Python FastAPI (~95% готов)
├── frontend/             # React TypeScript (~85% готов)
├── docs/OrcaSlicer/      # Форк OrcaSlicer (~85% интеграция)
└── docs/                 # Документация и референсы
```

---

## 🎯 Backend (Python FastAPI) - 95%

### ✅ Реализовано

#### Модели данных (SQLAlchemy)
1. **User** - Пользователи системы (21 поле)
   - JWT аутентификация с refresh tokens
   - Роли: user, brand, admin
   - Email verification (частично)
   - Привязка к бренду (brand_id)
   - Настройки синхронизации OrcaSlicer

2. **Brand** - Производители (10 полей)
   - Верификация брендов
   - Slug для URL
   - Logo upload

3. **Filament** - Материалы (19 полей) ✅ slug восстановлен
   - Material type (PLA, PETG, ABS и т.д.)
   - Цвет (hex + name)
   - Visual settings (JSON) для сложных цветов
   - QR-коды (автогенерация для верифицированных брендов)
   - Views/scans counter

4. **Preset** - Пресеты настроек (31 поле)
   - OrcaSlicer settings (JSONB) - 113+ параметров
   - Weighted presets (генеративные)
   - Модерация (pending/approved/rejected)
   - Рейтинги и статистика
   - Привязка к принтерам (many-to-many)
   - External ID для синхронизации

5. **Printer** - Принтеры (24 поля)
   - Импорт из OrcaSlicer bundles
   - Slug для URL
   - Технические характеристики

6. **PrinterProfile** - Профили принтеров (23 поля)
   - Settings (JSON)
   - Default print profile slug

7. **PrintProfile** - Профили печати (22 поля)
   - Settings (JSON)
   - Привязка к принтерам и материалам

8. **BrandRequest** - Заявки на бренд (20 полей)
   - CREATE и JOIN типы
   - Загрузка файлов-доказательств (до 10 файлов)
   - Workflow: создание → одобрение/отклонение

9. **PrinterRequest** - Заявки на принтеры (22 поля)
   - Загрузка доказательств
   - Автосоздание принтера при одобрении

10. **Notification** - Уведомления (10 полей)
    - Типы: PRESET_UPDATED, PRESET_DELETED, BRAND_VERIFIED
    - Read/unread статус

11. **FilamentReview** - Отзывы (11 полей)
12. **UserSavedPreset** - Избранные пресеты (5 полей)
13. **MaterialMapping** - Маппинг типов материалов (9 полей)
14. **Feedback** - Обратная связь (12 полей)
15. **BadWord** - Словарь для модерации (5 полей)

#### API Endpoints (19 модулей)

**Аутентификация (`/api/v1/auth/`):**
- ✅ POST `/register` - Регистрация
- ✅ POST `/login` - Вход (JWT tokens)
- ✅ POST `/refresh` - Обновление токена
- ✅ GET `/me` - Текущий пользователь
- ✅ GET `/my-presets` - Пресеты пользователя для OrcaSlicer
- ✅ POST `/forgot-password` - Сброс пароля
- ✅ POST `/reset-password` - Установка нового пароля
- ✅ DELETE `/me` - Удаление аккаунта

**Бренды (`/api/v1/brands/`):**
- ✅ CRUD операции
- ✅ Верификация (только admin)
- ✅ Список материалов бренда

**Материалы (`/api/v1/filaments/`):**
- ✅ CRUD операции с полной валидацией
- ✅ Поиск и фильтрация
- ✅ Автогенерация slug (brand + name)
- ✅ Автогенерация QR-кодов для верифицированных брендов

**Пресеты (`/api/v1/presets/`):**
- ✅ CRUD операции
- ✅ Модерация (pending/approved/rejected)
- ✅ Weighted presets (автогенерация на основе закона больших чисел)
- ✅ OrcaSlicer экспорт (.json и .info)
- ✅ Фильтрация по принтеру, материалу, рейтингу
- ✅ Рекомендации

**Принтеры (`/api/v1/printers/`):**
- ✅ CRUD операции
- ✅ Импорт из OrcaSlicer bundles

**Brand Requests (`/api/v1/brand-requests/`):**
- ✅ Создание заявок (CREATE/JOIN)
- ✅ Загрузка файлов (multipart/form-data)
- ✅ Одобрение/отклонение (admin)
- ✅ Автоматическое изменение роли пользователя при одобрении

**Printer Requests (`/api/v1/printer-requests/`):**
- ✅ Создание заявок
- ✅ Загрузка файлов
- ✅ Автосоздание принтера при одобрении (admin)

**OrcaSlicer Sync (`/api/v1/orcaslicer/`):**
- ✅ POST `/filaments/sync` - Синхронизация filament presets
- ✅ POST `/printer-profiles/sync` - Синхронизация printer profiles
- ✅ POST `/print-profiles/sync` - Синхронизация print profiles
- ✅ POST `/deleted-presets` - Обработка удалённых пресетов
- ✅ POST `/deleted-presets/action` - Действие (восстановить/удалить)

**QR-коды (`/api/v1/qr/`):**
- ✅ GET `/{short_code}` - Информация по QR-коду
- ✅ GET `/{short_code}/download` - Скачивание PNG

**Уведомления (`/api/v1/notifications/`):**
- ✅ GET `/` - Список уведомлений
- ✅ GET `/unread-count` - Количество непрочитанных
- ✅ PUT `/{id}/read` - Отметить прочитанным
- ✅ PUT `/mark-all-read` - Отметить все прочитанными

**Админ-панель (`/api/v1/admin/`):**
- ✅ GET `/stats` - Статистика платформы
- ✅ Управление пресетами (модерация)
- ✅ Управление пользователями (привязка/отвязка от брендов, изменение ролей)
- ✅ Управление brand requests
- ✅ Управление printer requests
- ✅ Database management (экспорт/импорт)

**Калькулятор (`/api/v1/calculator/`):**
- ✅ POST `/estimate` - Базовый расчет стоимости
- ⏳ POST `/parse-gcode` - G-code парсинг (заглушка)

**Spoolman (`/api/v1/spoolman/`):**
- ✅ Endpoints созданы (заглушки)
- ⏳ Полная интеграция запланирована

#### Сервисы (13 модулей)

1. **OrcaSlicer Services:**
   - `orcaslicer_exporter.py` - Экспорт в OrcaSlicer формат
   - `orcaslicer_machine_exporter.py` - Экспорт printer profiles
   - `orcaslicer_service.py` - Управление синхронизацией
   - `orca_bundle_importer.py` - Импорт OrcaSlicer bundles

2. **Бизнес-логика:**
   - `weighted_preset_service.py` - Генеративные пресеты (Закон больших чисел + метод Ферми)
   - `preset_moderation.py` - Модерация контента
   - `preset_ratings.py` - Рейтинговая система
   - `preset_recommender.py` - Рекомендации
   - `preset_service.py` - Общая логика пресетов

3. **Утилиты:**
   - `slug_service.py` - Генерация уникальных slug
   - `qr_service.py` - Генерация QR-кодов (base36)
   - `file_service.py` - Управление файлами
   - `notification_service.py` - Создание уведомлений
   - `text_moderation.py` - Фильтр мата (русский/английский)
   - `email_validator.py` - Валидация email
   - `material_mapping_service.py` - Маппинг типов материалов
   - `brand_service.py` - Логика брендов
   - `filament_service.py` - Логика материалов
   - `account_deletion.py` - Удаление аккаунтов
   - `database_service.py` - Бэкап/восстановление БД

### ⏳ В разработке

- **G-code парсеры** (портирование из PHP)
- **Email отправка** (SMTP настройка)
- **Spoolman интеграция** (full sync)

### 📦 Технологии

- **Framework:** FastAPI 0.110+
- **ORM:** SQLAlchemy 2.0 (async)
- **Database:** PostgreSQL 15
- **Cache:** Redis 7 (планируется)
- **Auth:** JWT (access + refresh tokens)
- **Validation:** Pydantic v2
- **Migrations:** Alembic
- **Testing:** pytest (58% coverage)
- **Rate Limiting:** slowapi

---

## 🎨 Frontend (React TypeScript) - 85%

### ✅ Реализовано

#### Страницы (10 компонентов)

1. **CatalogPage** - Каталог материалов
   - Поиск и фильтрация
   - Карточки материалов
   - Пагинация

2. **FilamentDetailPage** - Детали материала
   - Информация о материале
   - Список пресетов
   - Weighted пресеты
   - QR-код (для верифицированных брендов)

3. **BrandProfilePage** - Профиль бренда
   - Управление материалами
   - Создание официальных пресетов
   - QR-коды материалов
   - Только для brand users

4. **BrandDetailPage** - Публичная страница бренда

5. **ProfilePage** - Профиль пользователя
   - Мои пресеты
   - Избранное
   - Настройки
   - Удаление аккаунта

6. **AdminPanel** - Админ-панель
   - Статистика
   - Модерация пресетов
   - Управление пользователями
   - Brand requests
   - Printer requests
   - Database management

7. **DownloadPage** - Страница загрузки OrcaSlicer
8. **TermsPage** - Условия использования
9. **ConsentPage** - Политика конфиденциальности
10. **ResetPasswordPage** - Сброс пароля

#### Компоненты (48 компонентов)

**Модалки (15 компонентов):**
- `AuthModal` - Вход/регистрация
- `CreateFilamentModal` - Создание материала
- `CreatePresetModal` - Создание пресета ⭐ (8 табов, 113+ параметров OrcaSlicer)
- `EditGCodeModal` - Редактор G-code с плейсхолдерами
- `ViewPresetModal` - Просмотр пресета
- `CreateReviewModal` - Создание отзыва
- `FeedbackModal` - Обратная связь
- `ConfirmModal` - Подтверждение действий
- `ConfirmDeleteModal` - Удаление с подтверждением
- `DeleteAccountModal` - Удаление аккаунта
- `DeletedPresetsModal` - Управление удалёнными пресетами
- `ForgotPasswordModal` - Забыл пароль
- `ResetPasswordModal` - Сброс пароля
- `TermsModal` - Условия использования
- `ConsentModal` - Политика конфиденциальности

**UI компоненты:**
- `FilamentPreview` - Визуализация материала (цвет, finish, filler)
- `FilamentSummaryCard` - Карточка материала
- `CustomSelect` - Стилизованный dropdown
- `Dropdown` - Выпадающее меню
- `ColorMaterialSection` - Секция выбора цвета
- `HSLColorPicker` - Кастомный color picker
- `StarRating` - Звёздный рейтинг
- `ReviewCard` - Карточка отзыва
- `Toast` - Уведомления
- `Captcha` - CAPTCHA
- `Notifications` - Компонент уведомлений
- `PresetSyncToggle` - Переключатель синхронизации пресетов
- `Layout` - Основной layout
- `ProtectedRoute` - Защищённые маршруты

**Админ-компоненты (8 компонентов):**
- `AdminStats` - Статистика
- `AdminUsers` - Управление пользователями
- `AdminBrands` - Управление брендами
- `AdminPresets` - Модерация пресетов
- `AdminBrandRequests` - Заявки на бренд
- `AdminPrinterRequests` - Заявки на принтеры
- `AdminPrinters` - Управление принтерами
- `AdminNotifications` - Отправка уведомлений
- `AdminDatabase` - Управление БД
- `AdminFeedback` - Обратная связь

**Экспорт:**
- `ExportFromOrcaSlicerButton` - Экспорт из OrcaSlicer
- `ExportPrinterProfilesButton` - Экспорт printer profiles
- `ExportPrintProfilesButton` - Экспорт print profiles

#### Hooks (4 кастомных хука)

- `useAuth` - Аутентификация
- `useDebounce` - Debounce для поиска
- `useClickOutside` - Клик вне элемента
- `useHeaderVisible` - Видимость header
- `useOrcaSlicerNotifications` - Уведомления от OrcaSlicer

#### Контексты

- `AuthContext` - Глобальный контекст аутентификации

#### API клиент

- **TanStack Query** для кэширования
- **Axios** для HTTP
- Типизированные интерфейсы (TypeScript)

### ⏳ В разработке

- Dark/Light режимы
- Мобильная адаптация (responsive)
- PWA поддержка
- SEO оптимизация
- Реструктуризация дизайна (модульная система компонентов)

### 📦 Технологии

- **Framework:** React 18
- **Language:** TypeScript 5
- **Build:** Vite
- **UI:** shadcn/ui + TailwindCSS
- **State:** TanStack Query (React Query)
- **Forms:** React Hook Form + Zod
- **Routing:** React Router v6
- **Icons:** lucide-react

**Порт разработки:** **3000** (важно!)

---

## 🔗 OrcaSlicer Integration - 85%

### ✅ Реализовано

#### Форк OrcaSlicer
- **Repository:** `lizardjazz1/OrcaSlicer`
- **Branch:** `filamenthub-integration`
- **Базовая версия:** 2.3.2dev
- **License:** AGPL-3.0 (соблюдается)
- **Upstream:** `SoftFever/OrcaSlicer` (настроен)

#### FilamentHubPanel (C++)
**Файлы:**
- `src/slic3r/GUI/FilamentHubPanel.cpp` (~500 строк)
- `src/slic3r/GUI/FilamentHubPanel.hpp` (~100 строк)

**Функционал:**
1. **WebView интеграция:**
   - Встроенный React фронтенд (http://localhost:3000)
   - Навигация: Catalog, Profile, Notifications
   - Полный UI через WebView (не нативный wxWidgets)

2. **Авторизация:**
   - Авторизация через WebView (модальное окно во фронтенде)
   - JWT токен сохраняется в AppConfig
   - Кнопка Login/Logout в верхней панели
   - Проверка статуса авторизации при запуске

3. **Синхронизация пресетов:**
   - Автоматическая синхронизация при входе
   - Ручная синхронизация (кнопка "Синхронизировать")
   - Инкрементальная синхронизация (`updated_since`)
   - Асинхронная очередь для импорта (предотвращение deadlock)
   - Маппинг `preset_id → bundle_preset_name` в AppConfig
   - Постфикс `[FilamentHub]` к именам пресетов
   - Проверка и исправление родительских пресетов

4. **Обработка удалённых пресетов:**
   - Обнаружение локально удалённых пресетов
   - Отправка на бэкенд (`POST /api/v1/orcaslicer/deleted-presets`)
   - Восстановление пресетов по запросу пользователя
   - Modal dialog для действий (Keep Deleted / Restore)

5. **Уведомления:**
   - Badge с количеством непрочитанных уведомлений
   - API метод `get_unread_notifications_count()`
   - Обновление количества при входе и после синхронизации
   - Кнопка уведомлений открывает страницу (временно)

#### FilamentHubClient (C++)
**HTTP клиент для FilamentHub API:**
- `POST /api/v1/auth/login` - через WebView
- `GET /api/v1/auth/me` - проверка статуса
- `GET /api/v1/auth/my-presets` - получение пресетов
- `GET /api/v1/notifications/unread-count` - количество уведомлений
- `GET /api/v1/presets/{id}/export/orcaslicer.json` - экспорт профиля
- `POST /api/v1/orcaslicer/deleted-presets` - отправка удалённых пресетов
- `POST /api/v1/orcaslicer/deleted-presets/action` - действие с пресетом

### ⏳ В разработке

- **Двусторонняя синхронизация (OrcaSlicer → FilamentHub):**
  - Backend: эндпоинт для импорта filament presets
  - C++ Client: экспорт всех 3 типов профилей
  - C++ Panel: кнопка "Экспортировать в FilamentHub"
  - Автоматический экспорт при первой синхронизации

- **Выпадающее меню уведомлений в WebView** (временно открывает страницу)
- **Тестирование** на Windows/Linux/macOS
- **Сборка бинарников** для релиза
- **Коммуникация с @SoftFever** (PR в основной репо)

### 📦 Технологии

- **Language:** C++ 17
- **GUI:** wxWidgets 3.2
- **HTTP:** libcurl
- **WebView:** wxWebView (Chromium на Windows)
- **JSON:** nlohmann/json
- **Build:** CMake

---

## 🗂️ Документация

### Созданные документы (docs/)

**Технические:**
- `ROADMAP.md` - Дорожная карта развития (862 строки)
- `TODO.md` - Список задач
- `PROJECT_STATUS.md` - Этот документ (текущее состояние)
- `WHY_SUBMODULE.md` - Объяснение структуры submodule
- `ORCASLICER_SUBMODULE_SETUP.md` - Настройка OrcaSlicer submodule
- `ORCASLICER_SUBMODULE_USAGE.md` - Использование OrcaSlicer submodule
- `cursor_.md` - История чата (автогенерация)

**Аналитика и дизайн:**
- `DELETED_PRESET_FINAL_APPROACH.md` - Финальный подход к удалённым пресетам
- `DELETED_PRESET_WEBVIEW_APPROACH.md` - WebView подход
- `DELETED_PRESET_NOTIFICATIONS_APPROACH.md` - Уведомления
- `DELETED_PRESET_NOTIFICATION_OPTIONS.md` - Опции уведомлений
- `DELETED_PRESET_DIALOG_PLACEMENT.md` - Размещение диалогов
- `DELETED_PRESET_UX_VARIANTS.md` - UX варианты
- `SYNC_CHAIN_ANALYSIS.md` - Анализ цепочки синхронизации
- `SYNC_EXPLANATION.md` - Объяснение синхронизации
- `SYNC_FULL_CHAIN.md` - Полная цепочка синхронизации
- `TOKEN_EXPLANATION.md` - Объяснение JWT токенов
- `IMPORT_COMPARISON.md` - Сравнение методов импорта
- `RATING_SYSTEM_LOGIC.md` - Логика рейтинговой системы
- `RATING_SYSTEM_OPTIONS.md` - Опции рейтинговой системы
- `ORCASLICER_BIDIRECTIONAL_SYNC_IMPLEMENTATION.md` - Двусторонняя синхронизация

**Референсы:**
- `3dcalc/` - Legacy PHP приложение
- `Spoolman-master/` - Референс FastAPI архитектуры
- `spoolman2slicer-main/` - Референс интеграции со слайсерами
- `OrcaSlicer/` - Форк с интеграцией FilamentHub

### Cursor Rules (.cursor/rules/)

- `project.mdc` - Основной контекст проекта
- `backend-python.mdc` - Python/FastAPI правила
- `frontend-react.mdc` - React/TypeScript правила
- `legacy-php.mdc` - Работа с PHP кодом
- `orcaslicer-integration.mdc` - Интеграция с OrcaSlicer

---

## 🔧 Инфраструктура

### Локальная разработка
- **Backend порт:** 8000 (FastAPI)
- **Frontend порт:** 3000 (Vite dev server) ⚠️ ВАЖНО
- **Database:** PostgreSQL на localhost:5432
- **Database name:** filamenthub
- **Database user:** filamenthub

### Миграции (Alembic)
- **Всего миграций:** ~32
- **Статус:** Актуальные, применены
- **Последние изменения:**
  - Добавлено поле `slug` в `filaments` (восстановлено вручную)
  - Добавлены weighted presets
  - Добавлены уведомления
  - Добавлены printer/print profiles

### MCP (Model Context Protocol)
**Доступные серверы:**
- `database-filamenthub` - PostgreSQL доступ
- `context7` - Документация библиотек
- `playwright` - Браузерная автоматизация

---

## 🎯 Приоритеты (Immediate Actions)

### Критично (Неделя 1)
1. ✅ Восстановить `slug` для филаментов - **ГОТОВО**
2. Исправить ошибки компиляции OrcaSlicer
3. Протестировать синхронизацию пресетов
4. Обновить `material_type_base_map` с реальными именами

### Важно (Неделя 2-3)
5. Реализовать выпадающее меню уведомлений в WebView
6. Доработать двустороннюю синхронизацию (OrcaSlicer → FilamentHub)
7. Портировать G-code парсеры из PHP
8. Улучшить UX создания/редактирования материалов

### Можно отложить
9. Dark/Light режимы
10. Мобильная адаптация
11. PWA поддержка
12. Интеграция со Spoolman
13. Реструктуризация дизайна (модульная система компонентов)

---

## 📈 Метрики прогресса

| Компонент | Прогресс | Статус |
|-----------|----------|--------|
| Backend API | 95% | ✅ Готов |
| Frontend UI | 85% | 🔥 Почти готов |
| OrcaSlicer Integration | 85% | 🔥 Активная разработка |
| Документация | 80% | ✅ Хорошо |
| Тестирование | 58% | ⏳ Требуется больше |
| Deployment | 0% | ❌ Не начато |

### MVP (Минимально жизнеспособный продукт)
**Статус:** ~88% готов

**Что осталось:**
- Исправить компиляцию OrcaSlicer
- Протестировать полный цикл синхронизации
- Портировать G-code парсеры
- Настроить production сервер

**Предполагаемая дата релиза:** Декабрь 2025 - Январь 2026

---

## 🚨 Известные проблемы

### Backend
- ⏳ Email verification не полностью реализована
- ⏳ G-code парсеры требуют портирования из PHP
- ⏳ Spoolman интеграция в виде заглушек

### Frontend
- ⏳ Нет темной темы
- ⏳ Не адаптирован под мобильные устройства
- ⏳ Дублирование кода в модалках (требуется рефакторинг)

### OrcaSlicer
- ⏳ Ошибки компиляции (nlohmann/json path, PresetCollection API)
- ⏳ Выпадающее меню уведомлений временно открывает страницу
- ⏳ Двусторонняя синхронизация не реализована

---

## 💡 Рекомендации

### Срочные действия
1. **Исправить компиляцию OrcaSlicer** - блокирует тестирование
2. **Обновить документацию** - актуализировать cursor_.md и ROADMAP.md
3. **Протестировать slug** - убедиться что всё работает корректно

### Средняя срочность
4. **Портировать G-code парсеры** - критично для калькулятора
5. **Улучшить UX** - единообразие форм, улучшенная валидация
6. **Добавить тесты** - повысить coverage до 80%

### Долгосрочные
7. **Реструктуризация frontend** - модульная система компонентов
8. **Мобильная версия** - адаптация под смартфоны
9. **Темная тема** - для комфорта пользователей
10. **Production deployment** - VPS, домен, SSL, мониторинг

---

**Составлено:** Cursor AI Agent  
**Дата:** 2025-11-20  
**Версия:** 1.0


