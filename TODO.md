# FilamentHub - TODO List

> **Последнее обновление:** 2025-11-12  
> **Текущий фокус:** 
> - ✅ Backend API ~95% (завершение мелких задач, уведомления, weighted presets)
> - 🔥 Frontend Integration ~85% (улучшение UX, админ-панель, уведомления, weighted presets)
> - 🔥 OrcaSlicer Integration ~87% (FilamentHubPanel, WebView, авторизация, синхронизация пресетов, badge уведомлений, экспорт filament/printer/print profiles)

---

## 📊 Общий прогресс MVP

```
✅ Фаза 0: Планирование                 [████████████████████] 100%
✅ Фаза 1: Backend API                  [███████████████████░]  95%
🔥 Фаза 3: Web UI                       [██████████████████░░]  85%
🔥 Фаза 2: OrcaSlicer Integration       [██████████████████░░]  87%
⏳ Фаза 4: Публичный запуск             [░░░░░░░░░░░░░░░░░░░░]   0%
```

**Детализация прогресса:**
- ✅ Backend: Все основные эндпоинты, модели, миграции, тесты, OrcaSlicer экспорт, Brand Requests система, уведомления, weighted presets, API для количества непрочитанных уведомлений
- ✅ Frontend: Каталог, создание материалов/пресетов, профиль, админ панель, полный UI для OrcaSlicer параметров, Brand Requests система, Brand Profile Page, уведомления, weighted presets в UI
- 🔥 OrcaSlicer: Изучен код, собран локально, экспорт работает, интеграция в UI ~87% (FilamentHubPanel, WebView, авторизация, синхронизация пресетов, badge уведомлений, исправление проблемы с обновлением не-FilamentHub пресетов, экспорт filament/printer/print profiles)

**Статус:**
- ✅ Completed (Завершено)
- 🔥 In Progress (В работе)
- 👀 Learning (Изучаем параллельно)
- ⏳ Pending (Ожидает)
- 💤 Deferred (Отложено на потом)

---

## ✅ ФАЗА 0: Планирование [ЗАВЕРШЕНА]

- [x] Изучить 3dcalc (PHP), Spoolman, OrcaSlicer
- [x] Выбрать стек: Python FastAPI + PostgreSQL
- [x] Создать ROADMAP.md
- [x] Создать .cursor/rules/
- [x] Создать AGENTS.md
- [x] Уточнить видение с OrcaSlicer интеграцией
- [x] Определить MVP scope (заглушки для Spoolman/Calculator)

**Результат:** ✅ Полное понимание проекта

---

## 🔥 ФАЗА 1: Backend API MVP (Месяц 1-3)

**Прогресс:** 95% (Все основные модели, эндпоинты, тесты, документация, rate limiting, refresh tokens, email verification (частично), модерация, brand requests, saved presets, filament reviews (частично), OrcaSlicer экспорт, удаление аккаунтов, админ панель)

### 1.1 Настройка проекта ✅
**Задачи на эту неделю:**

- [x] Создать структуру `backend/` проекта
  ```
  backend/
  ├── app/
  │   ├── main.py
  │   ├── core/ (config, security, dependencies)
  │   ├── api/v1/
  │   ├── models/
  │   ├── schemas/
  │   ├── services/
  │   └── db/
  ├── tests/
  ├── alembic/
  ├── .env.example
  ├── pyproject.toml
  └── docker-compose.yml
  ```
- [x] Настроить `pyproject.toml` (FastAPI, SQLAlchemy, Alembic, pytest)
- [x] Создать `docker-compose.yml` (PostgreSQL 15 + Redis 7)
- [x] Создать `.env.example` с переменными
- [x] Поднять Docker контейнеры локально
- [x] Проверить подключение к PostgreSQL
- [x] Инициализировать Alembic
- [x] Создать первую миграцию (init)

### 1.2 Базовые модели ✅
**После 1.1:**

- [x] `app/models/user.py` - User (id, email, username, role, api_key)
- [x] `app/models/brand.py` - Brand (id, name, verified, timestamps)
- [x] `app/models/filament.py` - Filament (основной)
- [x] `app/models/printer.py` - Printer
- [x] `app/models/preset.py` - Preset (settings JSON, rating)
- [x] `app/models/filament_review.py` - FilamentReview (reviews from users)
- [x] `app/models/user_saved_preset.py` - UserSavedPreset (favorites)
- [x] Relationships (Brand→Filaments, Filament→Presets, User→Reviews)
- [x] Миграции Alembic для всех моделей
- [x] Индексы (brand_id, material_type, printer_id)

### 1.3 Pydantic Schemas ✅

- [x] `app/schemas/brand.py` (BrandCreate, BrandResponse)
- [x] `app/schemas/filament.py` (FilamentCreate, FilamentResponse, FilamentList)
- [x] `app/schemas/preset.py` (PresetCreate, PresetResponse)
- [x] `app/schemas/user.py` (UserCreate, Token, TokenData)
- [x] Validators (email, color_hex, temperatures)

### 1.4 REST API Endpoints 🔥

#### Auth ✅
- [x] `POST /api/v1/auth/register` (с rate limiting)
- [x] `POST /api/v1/auth/login` (JWT, с rate limiting)
- [x] `POST /api/v1/auth/refresh` (refresh token)
- [x] `POST /api/v1/auth/api-key` (генерация API ключа)
- [x] `GET /api/v1/auth/me` (текущий пользователь)
- [x] `PATCH /api/v1/auth/me` (обновление профиля)
- [x] `DELETE /api/v1/auth/me` (удаление аккаунта)
- [x] `GET /api/v1/auth/deletion-stats` (статистика удалений)
- [x] `POST /api/v1/auth/verify-email` (верификация email)

#### Brands ✅
- [x] `GET /api/v1/brands/` (список с пагинацией)
- [x] `GET /api/v1/brands/{id}`
- [x] `POST /api/v1/brands/` (admin only)
- [x] `PATCH /api/v1/brands/{id}` (admin only)
- [x] `DELETE /api/v1/brands/{id}` (admin only)

#### Brand Requests ✅
- [x] `POST /api/v1/brand-requests/` (создание заявки)
- [x] `GET /api/v1/brand-requests/my` (мои заявки)
- [x] `GET /api/v1/brand-requests/` (список для админов)
- [x] `GET /api/v1/brand-requests/{id}` (детали заявки)
- [x] `PATCH /api/v1/brand-requests/{id}` (обновление заявки)
- [x] `DELETE /api/v1/brand-requests/{id}` (удаление заявки админом вместе с файлами)
- [x] `POST /api/v1/brand-requests/{id}/upload` (загрузка файлов с оригинальными именами)
- [x] `DELETE /api/v1/brand-requests/{id}/files/{file_path}` (удаление файла из заявки)
- [x] При одобрении заявки: изменение роли пользователя на `brand`, привязка к бренду
- [x] При одобрении CREATE заявки: создание нового бренда и привязка пользователя
- [x] Отображение названия бренда вместо ID в JOIN заявках
- [x] Загрузка файлов с сохранением оригинальных имен
- [x] Валидация количества файлов (максимум 10 на заявку)
- [x] Автоматическая очистка старых файлов (через 30 дней)

#### Saved Presets ✅
- [x] `GET /api/v1/saved-presets/` (список избранных)
- [x] `POST /api/v1/saved-presets/` (добавить в избранное)
- [x] `DELETE /api/v1/saved-presets/{preset_id}` (удалить из избранного)

#### Admin ✅
- [x] `GET /api/v1/admin/stats` (статистика системы)
- [x] `GET /api/v1/admin/brands` (список брендов с фильтрацией)
- [x] `POST /api/v1/admin/brands/{id}/verify` (верификация бренда)
- [x] `POST /api/v1/admin/brands/{id}/unverify` (снятие верификации)
- [x] `GET /api/v1/admin/presets/pending` (пресеты на модерации)
- [x] `POST /api/v1/admin/presets/{id}/approve` (одобрение пресета)
- [x] `POST /api/v1/admin/presets/{id}/reject` (отклонение пресета)
- [x] `GET /api/v1/admin/users` (список пользователей с информацией о брендах)
- [x] `POST /api/v1/admin/users/{id}/activate` (активация пользователя)
- [x] `POST /api/v1/admin/users/{id}/deactivate` (деактивация пользователя)
- [x] `POST /api/v1/admin/users/{id}/promote-admin` (повышение до админа)
- [x] `POST /api/v1/admin/users/{id}/unlink-brand` (отвязка пользователя от бренда)
- [x] `POST /api/v1/admin/users/{id}/link-brand` (привязка пользователя к бренду)
- [x] `POST /api/v1/admin/users/{id}/demote-user` (понижение до обычного пользователя)
- [x] `GET /api/v1/admin/brand-requests` (список заявок на бренд с фильтрацией)
- [x] `GET /api/v1/admin/brand-requests/{id}` (детали заявки)
- [x] `PATCH /api/v1/admin/brand-requests/{id}` (одобрение/отклонение заявки)
- [x] `DELETE /api/v1/admin/brand-requests/{id}` (удаление заявки вместе с файлами)
- [x] `GET /api/v1/admin/printer-requests` (список заявок на принтеры)
- [x] `GET /api/v1/admin/printer-requests/{id}` (детали заявки на принтер)
- [x] `PATCH /api/v1/admin/printer-requests/{id}` (одобрение/отклонение заявки на принтер)

#### Filaments ✅
- [x] `GET /api/v1/filaments/` (фильтры: type, brand_id, color, search, пагинация)
- [x] `GET /api/v1/filaments/{id}`
- [x] `POST /api/v1/filaments/` (brand auth)
- [x] `PATCH /api/v1/filaments/{id}` (brand auth)
- [x] `DELETE /api/v1/filaments/{id}` (brand auth)
- [x] `GET /api/v1/filaments/{id}/presets` (пресеты для материала)

#### Presets ✅
- [x] `GET /api/v1/presets/` (фильтры: filament_id, printer_id, user_id, is_official)
- [x] `GET /api/v1/presets/{id}`
- [x] `POST /api/v1/presets/` (auth)
- [x] `PATCH /api/v1/presets/{id}` (auth)
- [x] `DELETE /api/v1/presets/{id}` (auth)
- [x] `GET /api/v1/presets/recommend` (weighted average)
- [x] `POST /api/v1/presets/{id}/increment-usage` (увеличение счетчика использования)
- [x] `GET /api/v1/presets/{id}/export/orcaslicer.json` (экспорт профиля OrcaSlicer)
- [x] `GET /api/v1/presets/{id}/export/orcaslicer.info` (экспорт .info файла)
- [x] `POST /api/v1/orcaslicer/deleted-presets` (отправка локально удалённых пресетов из OrcaSlicer)
- [x] `GET /api/v1/notifications/unread-count` (количество непрочитанных уведомлений)

#### Printers ✅
- [x] `GET /api/v1/printers/` (список с пагинацией)
- [x] `GET /api/v1/printers/{id}`
- [x] `POST /api/v1/printers/` (admin only)
- [x] `PATCH /api/v1/printers/{id}` (admin only)
- [x] `DELETE /api/v1/printers/{id}` (admin only)

#### Printer Requests ✅
- [x] `POST /api/v1/printer-requests/` (создание заявки на принтер)
- [x] `GET /api/v1/printer-requests/` (мои заявки)
- [x] `GET /api/v1/printer-requests/{id}` (детали заявки)
- [x] `POST /api/v1/printer-requests/{id}/upload` (загрузка файлов)
- [x] `DELETE /api/v1/printer-requests/{id}/files/{file_path}` (удаление файла)
- [x] `GET /api/v1/admin/printer-requests` (список для админов)
- [x] `GET /api/v1/admin/printer-requests/{id}` (детали для админа)
- [x] `PATCH /api/v1/admin/printer-requests/{id}` (одобрение/отклонение)

#### QR Codes ✅
- [x] `POST /api/v1/filaments/` автоматически генерирует QR-код для верифицированных брендов
- [x] `GET /api/v1/qr/filaments/{id}/qr-code` (получение изображения QR-кода)
- [x] `GET /api/v1/qr/filaments/{id}/qr-code/download` (скачивание QR-кода)
- [x] Поле `qr_code` в модели Filament (короткий код типа `FH-XXX` или `FH-XXX-XXX`)
- [x] Генерация короткого кода с динамическим форматом (base36)
- [x] UI для отображения и скачивания QR-кодов в профиле бренда

#### Notifications ✅
- [x] Модель `Notification` с типами (preset_updated, preset_deleted, preset_locally_deleted, brand_verified, brand_request_approved, brand_request_rejected)
- [x] Сервис `notification_service.py` для создания уведомлений
- [x] Сервис `orcaslicer_service.py` для обработки локально удалённых пресетов
- [x] `GET /api/v1/notifications/` (список уведомлений пользователя)
- [x] `GET /api/v1/notifications/unread-count` (количество непрочитанных)
- [x] `POST /api/v1/notifications/{id}/mark-read` (отметить как прочитанное)
- [x] `POST /api/v1/notifications/mark-all-read` (отметить все как прочитанные)
- [x] `POST /api/v1/orcaslicer/deleted-presets` (отправка локально удалённых пресетов из OrcaSlicer)
- [x] Интеграция в endpoints (presets, admin) для автоматической отправки уведомлений
- [x] Frontend компонент `Notifications.tsx` с отображением и навигацией
- [x] Frontend компонент `DeletedPresetsModal.tsx` для обработки локально удалённых пресетов
- [x] OrcaSlicer: API метод `get_unread_notifications_count()` для получения количества непрочитанных уведомлений
- [x] OrcaSlicer: Badge с количеством непрочитанных уведомлений на кнопке уведомлений

#### Weighted Presets ✅
- [x] Поле `is_weighted` в модели `Preset` (Boolean, индекс)
- [x] Сервис `weighted_preset_service.py` для автоматического создания/обновления взвешенных пресетов
- [x] Алгоритм на основе закона больших чисел и метода Ферми (weighted average)
- [x] Минимальное количество пресетов для генерации: 4
- [x] Автоматическое обновление при создании/изменении/удалении пресетов
- [x] Исключение weighted presets из расчета (предотвращение рекурсии)
- [x] Frontend: отображение в каталоге (carousel), тег "Генеративный" в профиле

### 1.5 Заглушки (MVP scope) 💤

#### Spoolman Integration (заглушка) ✅
- [x] `GET /api/v1/spoolman/sync` → `{"status": "TODO", "message": "Будет реализовано в Фазе 5"}`
- [ ] Создать модели для future (Spool, InventoryItem)
- [x] Документировать планируемый API

#### Calculator (заглушка) ✅
- [x] `POST /api/v1/calculator/estimate` → простая формула
  - Принимает: `weight_g`, `time_sec`, `price_per_kg`
  - Возвращает: `cost_material`, `cost_total`
  - **БЕЗ** G-code парсинга (будет в Фазе 6)

### 1.6 Service Layer ✅

- [x] `app/services/brand_service.py`
- [x] `app/services/filament_service.py`
- [x] `app/services/preset_service.py`
- [x] `app/services/preset_recommender.py` (weighted average алгоритм)
- [x] `app/services/orcaslicer_exporter.py` (экспорт в OrcaSlicer формат)
- [x] `app/services/email_validator.py` (валидация email доменов, нормализация URL сайтов)
- [x] `app/services/file_service.py` (загрузка файлов для brand requests с оригинальными именами, валидация, очистка старых файлов)
- [x] `app/services/account_deletion.py` (удаление аккаунтов)
- [x] `app/services/qr_service.py` (генерация QR-кодов и коротких кодов)
- [x] `app/services/notification_service.py` (создание и управление уведомлениями)
- [x] `app/services/orcaslicer_service.py` (обработка локально удалённых пресетов из OrcaSlicer)
- [x] `app/services/weighted_preset_service.py` (автоматическое создание/обновление взвешенных пресетов)
- [x] `app/core/security.py` (JWT, password hashing, email verification tokens)

### 1.7 Testing ✅

- [x] Pytest setup
- [x] Tests для моделей
- [x] Tests для API (базовые эндпоинты)
- [x] Coverage 58%+ (33 из 38 тестов проходят, auth тесты имеют известную проблему с passlib/bcrypt)

### 1.8 Documentation ✅

- [x] Swagger (автогенерация FastAPI) - работает на `/api/v1/docs`
- [ ] README.md для backend
- [x] API examples в Swagger (автоматически из Pydantic схем)

### 1.9 Security Improvements 🔥

#### Rate Limiting ✅
- [x] Добавить slowapi для rate limiting
- [x] Ограничить `/api/v1/auth/login` (5 попыток/минуту)
- [x] Ограничить `/api/v1/auth/register` (3 попытки/минуту)
- [ ] Настроить Redis для хранения лимитов (пока используется in-memory)

#### Password Validation ⏳
- [ ] Усилить валидацию пароля (цифры + буквы + спецсимволы)
- [ ] Обновить Pydantic схему `UserCreate.password`
- [ ] Обновить frontend валидацию пароля
- [ ] Добавить проверку на утечку паролей (опционально, через API)

#### Token Management ✅
- [x] Реализовать refresh tokens (настройки есть, логика не реализована)
- [x] Добавить endpoint `/api/v1/auth/refresh`
- [x] Обновить frontend для автоматического обновления токенов
- [ ] Добавить endpoint `/api/v1/auth/logout` (blacklist токенов)

#### Production Security
- [ ] Генерация сильного SECRET_KEY при первом запуске
- [ ] HTTPS only для production (CORS настройки)
- [x] Email верификация (токены генерируются, отправка email - TODO)
  - [x] Генерация токенов верификации
  - [x] Endpoint для верификации `/api/v1/auth/verify-email`
  - [x] Логика автоматического присвоения роли brand при верификации
  - [ ] Отправка email с токеном (нужен SMTP сервер)

**Цель Фазы 1:** Работающий Backend API с заглушками

---

## 🔥 ФАЗА 2: OrcaSlicer Integration (Месяц 3-6) ⭐

**Прогресс:** 85% (изучен код, собран локально, экспорт работает, форк создан и настроен, интеграция в UI ~85%: FilamentHubPanel, WebView, авторизация, синхронизация пресетов, badge уведомлений, экспорт filament presets)

### 2.1 Изучение OrcaSlicer ✅

**Параллельно с Backend разработкой:**

- [x] Клонировать https://github.com/SoftFever/OrcaSlicer
- [x] Прочитать `OrcaSlicer-main/CLAUDE.md`
- [x] Прочитать `OrcaSlicer-main/AGENTS.md`
- [x] Изучить структуру `src/slic3r/GUI/`
- [x] Найти код tabs: `Tab.cpp`, `MainFrame.cpp`
- [x] Найти код "Профиль прутка" dropdown
- [x] Изучить как работает HTTP (libcurl примеры)
- [x] Компилировать OrcaSlicer локально (Windows) - версия 2.3.2dev
- [x] Изучить структуру профилей OrcaSlicer (JSON формат, массивы строк)
- [x] Изучить все параметры OrcaSlicer для филаментов (113+ параметров)
- [x] Реализовать экспорт профилей в формате OrcaSlicer (.json и .info)
- [x] Изучить интеграцию BambuLab в OrcaSlicer (для понимания архитектуры)

**Дедлайн:** 2 недели (изучаем вечерами пока делаем Backend)

### 2.2 Форк и Proof-of-Concept ✅

- [x] Создать форк `lizardjazz1/OrcaSlicer` на GitHub (публичный, для соблюдения AGPL-3.0)
- [x] Клонировать форк локально (`docs/OrcaSlicer`)
- [x] Настроить upstream remote (SoftFever/OrcaSlicer)
- [x] Применить правки для сборки (OpenCV, OCCT DLL) из существующей копии
- [x] Создать ветку `filamenthub-integration` для разработки
- [x] Закоммитить и запушить правки в форк (`600f782aec`)
- [x] Синхронизировать с upstream (`git fetch upstream`)
- [x] Скомпилировать и запустить (Windows) - версия 2.3.2dev работает
- [x] Соблюдение AGPL-3.0: форк публичный, копирайты сохранены, LICENSE.txt не изменен
- [x] Добавить уведомления о модификациях в измененные файлы (CMakeLists.txt)
- [x] Создать файл CHANGES.md с описанием всех модификаций
- [x] Закоммитить и запушить уведомления о модификациях (`88b7eafe59`)
- [ ] Обновить README.md форка с информацией о FilamentHub интеграции (опционально)
- [ ] Добавить тестовый HTTP запрос к localhost:8000
- [ ] Создать пустой FilamentHub tab (skeleton)
- [ ] Протестировать базовую интеграцию

### 2.3 FilamentHub Authorization Integration ✅ ~90%
**Цель:** Реализовать авторизацию в OrcaSlicer через FilamentHub (аналогично BambuLab)

**Задачи:**
- [x] Изучить существующую интеграцию BambuLab в OrcaSlicer
- [x] Создать `src/slic3r/Utils/FilamentHubClient.cpp/.h` для HTTP клиента
- [x] UI авторизации через WebView:
  - [x] Авторизация через WebView (открытие модального окна во фронтенде)
  - [x] Автоматическое сохранение токена доступа (JWT) в AppConfig
  - [x] Сохранение user_id в AppConfig
  - [x] Отображение статуса авторизации (авторизован/не авторизован) в UI
  - [x] Кнопка "Login/Logout" в верхней панели FilamentHub tab
- [x] HTTP клиент для FilamentHub API:
  - [x] POST /api/v1/auth/login (авторизация) - через фронтенд
  - [x] GET /api/v1/auth/me (проверка статуса, получение user info)
  - [x] GET /api/v1/auth/my-presets (получение пресетов пользователя)
- [x] Сохранение настроек авторизации в конфиге OrcaSlicer (AppConfig)
- [ ] POST /api/v1/auth/refresh (обновление токена) - не реализовано (не критично)

### 2.4 FilamentHub Tab Implementation ✅ ~85%
**Цель:** Добавить таб "FilamentHub" в главный UI (рядом с "Подготовка", "Принтер", "Проект")

**Задачи:**
- [x] Создать `src/slic3r/GUI/FilamentHubPanel.cpp/.h`
- [x] Добавить таб "FilamentHub" в главное окно (рядом с существующими табами)
- [x] UI компоненты через WebView:
  - [x] WebView с React фронтендом (http://localhost:3000)
  - [x] Отображение статуса авторизации (если не авторизован - предложить войти)
  - [x] Поиск материалов по бренду, типу, цвету (через фронтенд)
  - [x] Просмотр деталей материала (через фронтенд)
  - [x] Просмотр пресетов для материала (через фронтенд)
  - [x] Кнопка "Скачать" для пресета (скачивание JSON файла)
  - [x] Навигация (Catalog, Profile) в верхней панели
  - [x] Кнопка "Уведомления" с badge непрочитанных уведомлений
  - [x] Кнопка "Админ" (только для админов)
  - [x] Кнопка "Обновить" для перезагрузки WebView
- [x] HTTP клиент для FilamentHub API:
  - [x] GET /api/v1/presets/{id}/export/orcaslicer.json (экспорт профиля)
  - [x] GET /api/v1/auth/my-presets (получение пресетов пользователя)
  - [x] GET /api/v1/notifications/unread-count (количество непрочитанных уведомлений)
- [ ] GET /api/v1/filaments (поиск с фильтрами) - не требуется (через фронтенд)
- [ ] GET /api/v1/filaments/{id} (детали материала) - не требуется (через фронтенд)
- [ ] GET /api/v1/filaments/{id}/presets (пресеты материала) - не требуется (через фронтенд)

### 2.5 Profile Synchronization ✅ ~83%
**Цель:** Отображать профили пользователя из FilamentHub в dropdown "Профиль прутка" после авторизации

**Задачи:**
- [x] Найти код где формируется dropdown "Профиль прутка" (Filament Profile)
- [x] Реализовать синхронизацию профилей:
  - [x] При авторизации получать список профилей пользователя через API (`/api/v1/auth/my-presets`)
  - [x] Скачивать .json профили и импортировать через `PresetBundle::import_json_presets`
  - [x] Сохранение маппинга `preset_id → bundle_preset_name` в AppConfig
  - [x] Добавление постфикса `[FilamentHub]` к именам пресетов
  - [x] Проверка и исправление родительских пресетов (`ensure_parent_preset_exists`)
- [x] Автосинхронизация при открытии FilamentHub tab (если пользователь авторизован) - отключена для предотвращения проблем с истёкшими токенами
- [x] Автосинхронизация после авторизации
- [x] Кнопка "Синхронизировать" для ручного обновления
- [x] Инкрементальная синхронизация (через `updated_since` параметр)
- [x] Исправлена проблема с обновлением не-FilamentHub пресетов (убран вызов `load_current_presets` после каждого импорта, вызов только один раз в конце)
- [x] Реализована асинхронная очередь для импорта пресетов (предотвращение deadlock при использовании `perform_sync()`)
- [x] Реализована система обнаружения локально удалённых пресетов и отправка их на бэкенд (`POST /api/v1/orcaslicer/deleted-presets`)
- [x] Добавлен badge с количеством непрочитанных уведомлений на кнопку уведомлений
- [x] Добавлен API метод `get_unread_notifications_count()` для получения количества непрочитанных уведомлений
- [x] Добавлено обновление количества уведомлений при входе и после синхронизации
- [x] **Двусторонняя синхронизация (OrcaSlicer → FilamentHub)** (частично - filament presets):
  - [x] Backend: Добавить поле `allow_filament_presets_import` в модель `User`
  - [x] Backend: Добавить поля `external_id` и `source` в модель `Preset`
  - [x] Backend: Создать служебный бренд "User Materials" (id=1) для черновиков из OrcaSlicer
  - [x] Backend: Создать Pydantic схемы `OrcaFilamentPresetPayload`, `FilamentPresetSyncRequest`, `FilamentPresetSyncResponse`
  - [x] Backend: Реализовать эндпоинт `POST /api/v1/orcaslicer/filaments/import`
  - [x] Backend: Реализовать функцию `_upsert_filament_preset()` с логикой создания Filament при импорте
  - [x] Backend: Реализовать разрешение конфликтов на основе timestamp (новее версия выигрывает)
  - [x] C++ Client: Добавить метод `import_filament_presets()` в `FilamentHubClient`
  - [x] C++ Panel: Реализовать экспорт Filament Preset в JSON (`export_filament_presets_to_filamenthub()`)
  - [x] C++ Panel: Добавить проверку разрешений на импорт перед экспортом filament presets
  - [x] C++ Panel: Сохранять маппинги `external_id → fhub_id` для filament presets
  - [x] Документация: Создать подробную инструкцию по реализации (✅ создано в `docs/md/ORCASLICER_BIDIRECTIONAL_SYNC_IMPLEMENTATION.md`)
  - [x] C++ Panel: Добавить обработку команды `export_filament_presets` в `OnScriptMessage`
  - [x] C++ Panel: Добавить JavaScript API функцию `exportFilamentPresets` в `setup_javascript_api`
  - [x] Frontend: Реализовать компонент `ExportFromOrcaSlicerButton` для экспорта профилей из OrcaSlicer в FilamentHub
  - [x] Frontend: Интегрировать компонент экспорта в `ProfilePage.tsx`
  - [x] C++ Panel: Реализовать экспорт Printer Profile в JSON (`export_printer_profiles_to_filamenthub()`)
  - [x] C++ Panel: Реализовать экспорт Print Profile в JSON (`export_print_profiles_to_filamenthub()`)
  - [x] C++ Panel: Добавить проверку разрешений на импорт перед экспортом printer/print profiles
  - [x] C++ Panel: Сохранять маппинги `external_id → fhub_id` для printer/print profiles
  - [x] C++ Panel: Добавить обработку команд `export_printer_profiles` и `export_print_profiles` в `OnScriptMessage`
  - [x] C++ Panel: Добавить JavaScript API функции `exportPrinterProfiles` и `exportPrintProfiles` в `setup_javascript_api`
  - [ ] C++ Panel: Реализовать функцию `export_profiles_to_filamenthub()` для экспорта всех 3 типов профилей
  - [ ] C++ Panel: Реализовать определение бандлов (если есть все 3 типа профилей)
  - [ ] C++ Panel: Реализовать автоматический экспорт при первой синхронизации
- [ ] Обновление уже импортированных пресетов (проверка `updated_at`)
- [ ] Удаление пресетов из OrcaSlicer если они удалены на FilamentHub (частично реализовано - обнаружение работает, восстановление работает)
- [ ] Визуальная пометка профилей FilamentHub в dropdown (иконка/метка)
- [ ] Реализовать выпадающее меню уведомлений в WebView (временно открывает страницу уведомлений)
- [ ] Протестировать синхронизацию и обновить `material_type_base_map` с реальными именами системных пресетов

### 2.6 Testing & Release ⏳

- [ ] Тестирование Windows
- [ ] Собрать бинарники (Windows exe)
- [ ] GitHub Release (v0.1.0-filamenthub)
- [ ] Инструкция по установке

**Цель Фазы 2:** Работающая интеграция в OrcaSlicer

---

## ⏳ ФАЗА 3: Web UI (Месяц 7-9)

**Прогресс:** 75% (Базовый UI полностью реализован, интеграция с API завершена, создание пресетов с OrcaSlicer параметрами работает)

**Минимальный набор для MVP:**

- [x] React + TypeScript + Vite setup
- [x] Публичный каталог материалов с фильтрацией
- [x] Регистрация/авторизация (модальные окна)
- [x] Страницы пользовательского соглашения и согласия на обработку данных
- [x] Dashboard для администраторов (полный UI)
- [x] Проверка сложности пароля и подтверждение пароля
- [x] Капча с показом после попытки регистрации
- [x] Страница профиля пользователя с избранными пресетами
- [x] Добавление/редактирование материалов (CreateFilamentModal с API)
- [x] Добавление/редактирование пресетов (CreatePresetModal с полным UI для OrcaSlicer)
- [x] Визуализация филамента (FilamentPreview компонент)
- [x] Полная интеграция всех компонентов с реальным API
- [x] CustomSelect компонент (стилизованный dropdown)
- [x] EditGCodeModal (редактор G-code с плейсхолдерами)
- [x] Страница бренда (BrandProfilePage реализована)
  - [x] Создание/редактирование материалов через модальное окно
  - [x] Удаление материалов
  - [x] Отображение статистики
  - [x] Заявки на бренд (создание, просмотр, загрузка файлов)
  - [x] Отображение файлов с оригинальными именами
  - [x] Создание/редактирование пресетов бренда (официальные пресеты)
  - [x] Вкладка "QR-коды" для отображения и скачивания QR-кодов материалов
  - [x] Доработано создание/редактирование материалов (единообразие форм, улучшен UX)
  - [x] Улучшено отображение заявок на бренд (компактное отображение полей)
  - [x] Доработана логика присоединения к верифицированным брендам (полная заявка если нет сотрудников)
- [x] Админ-панель полностью реализована
  - [x] Управление заявками на бренды (одобрение/отклонение, удаление)
  - [x] Управление заявками на принтеры (одобрение/отклонение)
  - [x] Управление брендами (верификация, переход на страницу бренда)
  - [x] Управление пользователями (активация/деактивация, повышение до админа, понижение до пользователя, привязка/отвязка от бренда)
  - [x] Отображение информации о брендах пользователей
  - [x] Кнопки профиля и выхода в админ-панели
  - [x] Модальные окна подтверждения (ConfirmModal) вместо confirm()
- [x] Система уведомлений (компонент Notifications.tsx, интеграция с API)
- [x] Weighted Presets в UI (отображение в каталоге через carousel, тег "Генеративный" в профиле)
- [ ] Калькулятор стоимости с G-code парсингом (заглушка работает)

**Цель:** Производители могут управлять материалами через веб

---

## ⏳ ФАЗА 4: Публичный запуск (Месяц 9-10)

- [ ] Деплой на VPS (или остаться локально)
- [ ] Домен filamenthub.ru (опционально)
- [ ] SSL сертификаты
- [ ] Мониторинг (Sentry)
- [ ] Связь с @SoftFever (PR в OrcaSlicer)
- [ ] Маркетинг (Habr, соцсети)

---

## 💤 Post-MVP (Отложено)

### Фаза 5: Полная Spoolman Integration (Месяц 11-12)
- Импорт/экспорт катушек
- Двусторонняя синхронизация

### Фаза 6: G-code Calculator (Месяц 12-13)
- Портирование PHP парсеров
- Полный калькулятор с парсингом
- Премиум доступ

### Фаза 7: Рейтинги и аналитика (Месяц 13-14)
- Отзывы на пресеты
- Статистика для производителей (платная)

### Фаза 8: Расширение (Месяц 15+)
- QR-коды
- Маркетплейс (Ozon/WB ссылки)
- Другие слайсеры (PrusaSlicer, Cura)

---

## 🎯 Текущие задачи (Следующие шаги)

### Приоритет 1: Frontend Integration ✅
1. ✅ Регистрация и авторизация работают
2. ✅ Добавление/редактирование материалов (CreateFilamentModal интегрирован с API)
3. ✅ Добавление/редактирование пресетов (CreatePresetModal интегрирован с API, полный UI для OrcaSlicer параметров)
4. ✅ Brand Requests система полностью реализована (создание, загрузка файлов, одобрение админом, изменение роли)
5. ✅ Страница бренда (BrandProfilePage реализована с полным функционалом)
6. ✅ Доработано создание/редактирование материалов (единообразие форм, улучшен UX)
7. ✅ Админ-панель полностью реализована (все разделы, управление пользователями, отвязка от брендов)
8. ✅ QR-коды материалов (генерация, отображение, скачивание в профиле бренда)
9. ⏳ **СЛЕДУЮЩЕЕ:** Калькулятор стоимости с G-code парсингом (заглушка работает, нужен полный парсер)
    - [x] Backend: Базовая заглушка калькулятора (простая формула)
    - [ ] Backend: Портировать G-code парсеры из PHP (OrcaSlicer, PrusaSlicer, Cura и др.)
    - [ ] Backend: Полный калькулятор с парсингом G-code
    - [ ] Frontend: UI для загрузки G-code файла
    - [ ] Frontend: Отображение результатов расчёта
10. ✅ **ЗАВЕРШЕНО:** Система отзывов и рейтингов (звёзды/баллы)
    - [x] Backend: CRUD эндпоинты для отзывов на пресеты
    - [x] Backend: Система рейтингов (1-5 звёзд)
    - [x] Backend: Расчёт среднего рейтинга для пресетов
    - [x] Frontend: UI для создания/редактирования отзывов
    - [x] Frontend: Компонент рейтинга (звёзды)
    - [x] Frontend: Отображение отзывов на странице пресета
    - [x] Frontend: Отображение среднего рейтинга в карточках пресетов
    - [x] Frontend: Фильтрация пресетов по рейтингу
11. ✅ **ЗАВЕРШЕНО:** Привязка принтеров к пресетам
    - [x] Backend: Модель PresetPrinter (many-to-many связь)
    - [x] Backend: Обновление схем PresetCreate/PresetUpdate для работы с printer_ids
    - [x] Backend: Автоматическое создание связей при создании/обновлении пресета
    - [x] Frontend: UI для выбора принтеров при создании/редактировании пресета (множественный выбор)
    - [x] Frontend: Отображение списка принтеров в CreatePresetModal
    - [x] Frontend: Фильтрация пресетов по принтеру (работает через API)
    - [ ] Frontend: Отображение иконок/названий принтеров в карточках пресетов (можно доработать)

### Приоритет 2: Backend Security (завершение)
1. ✅ Rate limiting реализован
2. ✅ Refresh tokens реализованы
3. ⏳ Усилить валидацию паролей (цифры + буквы + спецсимволы)
4. ⏳ Добавить endpoint `/api/v1/auth/logout`

### Приоритет 3: OrcaSlicer Integration 🔥 В РАБОТЕ
**Статус:** Интеграция активно разрабатывается, прогресс ~85%
1. ✅ Реализовать экспорт профилей в формате OrcaSlicer (готово в backend)
2. ✅ Создать форк или локальную ветку для разработки (lizardjazz1/OrcaSlicer, ветка filamenthub-integration)
3. ✅ Реализовать авторизацию в OrcaSlicer через FilamentHub (через WebView, токен сохраняется в AppConfig)
4. ✅ Добавить таб "FilamentHub" в главный UI OrcaSlicer (FilamentHubPanel с WebView)
5. ✅ Реализовать синхронизацию профилей в "Профиль прутка" dropdown (асинхронная очередь, обнаружение удалённых пресетов)
6. ✅ Исправить проблему с обновлением не-FilamentHub пресетов (убран множественный вызов load_current_presets)
7. ✅ Добавить badge с количеством непрочитанных уведомлений на кнопку уведомлений
8. ✅ Реализовать экспорт filament presets из OrcaSlicer в FilamentHub (C++ метод `export_filament_presets_to_filamenthub()`)
9. ✅ Добавить проверку разрешений на импорт перед экспортом filament presets
10. ✅ Добавить JavaScript API функцию `exportFilamentPresets` в C++ для вызова экспорта из Frontend
11. ✅ Реализовать Frontend компонент `ExportFromOrcaSlicerButton` для экспорта профилей из OrcaSlicer в FilamentHub
12. ✅ Интегрировать компонент экспорта в `ProfilePage.tsx` (отображается только внутри OrcaSlicer)
13. ⏳ Реализовать выпадающее меню уведомлений в WebView (временно открывает страницу)
14. ⏳ Визуальная пометка профилей FilamentHub в dropdown (иконка/метка)
15. ⏳ Реализовать экспорт printer и print profiles (в дополнение к filament presets)
16. ⏳ Тестирование и отладка синхронизации

---

## 📝 Примечания

### Deployment Strategy:
- **MVP:** Разворачиваем локально (localhost:8000)
- **После тестирования:** VPS (Hetzner/Timeweb)

### Приоритет фич:
1. ✅ Backend API (основа) - 98% готово
2. ✅ Web UI (для брендов) - 90% готово
3. ⏳ G-code калькулятор (портировать парсеры из PHP)
4. 💤 OrcaSlicer интеграция (отложено)
5. Всё остальное (потом)

### Заглушки на MVP:
- ✅ Spoolman sync - заглушка (Фаза 5)
- ✅ Calculator - простая формула (полный в Фазе 6)
- ✅ G-code парсинг - не портируем сейчас (Фаза 6)

---

**Готовы начинать!** 🚀  
**Следующий шаг:** Создать структуру Backend проекта

---

### 🗂️ Backlog / Идеи на потом (низкий приоритет)

- [ ] (🛰️) Исследовать и при необходимости портировать идею фильтрации из RussianBadWords на Python — https://github.com/Vasiliy-Makogon/RussianBadWords
- [ ] (🛰️) Спланировать региональные фильтры брендов по странам (добавить `country_code`, автоопределение региона, fallback на глобальные бренды)
