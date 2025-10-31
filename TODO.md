# FilamentHub - TODO List

> **Последнее обновление:** 2025-10-31  
> **Текущий фокус:** 🔥 Фаза 1 - Backend API (Месяц 1-3)  
> **Параллельно:** 👀 Изучение OrcaSlicer (Месяц 1+)

---

## 📊 Общий прогресс MVP

```
✅ Фаза 0: Планирование                 [████████████████████] 100%
🔥 Фаза 1: Backend API                  [█░░░░░░░░░░░░░░░░░░░]   5%
👀 Фаза 2: OrcaSlicer Integration       [░░░░░░░░░░░░░░░░░░░░]   0%
⏳ Фаза 3: Web UI                       [░░░░░░░░░░░░░░░░░░░░]   0%
⏳ Фаза 4: Публичный запуск             [░░░░░░░░░░░░░░░░░░░░]   0%
```

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

**Прогресс:** 5% (Структура правил готова, код ещё нет)

### 1.1 Настройка проекта ⏳
**Задачи на эту неделю:**

- [ ] Создать структуру `backend/` проекта
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
- [ ] Настроить `pyproject.toml` (FastAPI, SQLAlchemy, Alembic, pytest)
- [ ] Создать `docker-compose.yml` (PostgreSQL 15 + Redis 7)
- [ ] Создать `.env.example` с переменными
- [ ] Поднять Docker контейнеры локально
- [ ] Проверить подключение к PostgreSQL
- [ ] Инициализировать Alembic
- [ ] Создать первую миграцию (init)

### 1.2 Базовые модели ⏳
**После 1.1:**

- [ ] `app/models/user.py` - User (id, email, username, role, api_key)
- [ ] `app/models/brand.py` - Brand (id, name, verified, timestamps)
- [ ] `app/models/filament.py` - Filament (основной)
- [ ] `app/models/printer.py` - Printer
- [ ] `app/models/preset.py` - Preset (settings JSON, rating)
- [ ] Relationships (Brand→Filaments, Filament→Presets)
- [ ] Миграции Alembic для всех моделей
- [ ] Индексы (brand_id, material_type, printer_id)

### 1.3 Pydantic Schemas ⏳

- [ ] `app/schemas/brand.py` (BrandCreate, BrandResponse)
- [ ] `app/schemas/filament.py` (FilamentCreate, FilamentResponse, FilamentList)
- [ ] `app/schemas/preset.py` (PresetCreate, PresetResponse)
- [ ] `app/schemas/user.py` (UserCreate, Token, TokenData)
- [ ] Validators (email, color_hex, temperatures)

### 1.4 REST API Endpoints ⏳

#### Auth
- [ ] `POST /api/v1/auth/register`
- [ ] `POST /api/v1/auth/login` (JWT)
- [ ] `POST /api/v1/auth/api-key` (для OrcaSlicer)
- [ ] `GET /api/v1/auth/me`

#### Brands
- [ ] `GET /api/v1/brands/` (список с пагинацией)
- [ ] `GET /api/v1/brands/{id}`
- [ ] `POST /api/v1/brands/` (admin only)

#### Filaments
- [ ] `GET /api/v1/filaments/` (фильтры: type, brand_id, color)
- [ ] `GET /api/v1/filaments/{id}`
- [ ] `POST /api/v1/filaments/` (brand auth)
- [ ] `PUT /api/v1/filaments/{id}`
- [ ] `GET /api/v1/filaments/{id}/presets`

#### Presets
- [ ] `GET /api/v1/presets/` (фильтры: filament_id, printer_id)
- [ ] `GET /api/v1/presets/{id}`
- [ ] `POST /api/v1/presets/` (auth)
- [ ] `GET /api/v1/presets/recommend` (weighted average)

#### Printers
- [ ] `GET /api/v1/printers/`
- [ ] `GET /api/v1/printers/{id}`

### 1.5 Заглушки (MVP scope) 💤

#### Spoolman Integration (заглушка)
- [ ] `GET /api/v1/spoolman/sync` → `{"status": "TODO", "message": "Будет реализовано в Фазе 5"}`
- [ ] Создать модели для future (Spool, InventoryItem)
- [ ] Документировать планируемый API

#### Calculator (заглушка)
- [ ] `POST /api/v1/calculator/estimate` → простая формула
  - Принимает: `weight_g`, `time_sec`, `price_per_kg`
  - Возвращает: `cost_material`, `cost_total`
  - **БЕЗ** G-code парсинга (будет в Фазе 6)

### 1.6 Service Layer ⏳

- [ ] `app/services/brand_service.py`
- [ ] `app/services/filament_service.py`
- [ ] `app/services/preset_service.py`
- [ ] `app/services/preset_recommender.py` (weighted average алгоритм)
- [ ] `app/core/security.py` (JWT, password hashing)

### 1.7 Testing ⏳

- [ ] Pytest setup
- [ ] Tests для моделей
- [ ] Tests для API (все эндпоинты)
- [ ] Coverage 80%+

### 1.8 Documentation ⏳

- [ ] Swagger (автогенерация FastAPI)
- [ ] README.md для backend
- [ ] API examples в Swagger

**Цель Фазы 1:** Работающий Backend API с заглушками

---

## 👀 ФАЗА 2: OrcaSlicer Integration (Месяц 3-6) ⭐

**Прогресс:** 0% (начнём параллельно с Backend)

### 2.1 Изучение OrcaSlicer (👀 НАЧИНАЕМ СЕЙЧАС)

**Параллельно с Backend разработкой:**

- [ ] Клонировать https://github.com/SoftFever/OrcaSlicer
- [ ] Прочитать `OrcaSlicer-main/CLAUDE.md`
- [ ] Прочитать `OrcaSlicer-main/AGENTS.md`
- [ ] Изучить структуру `src/slic3r/GUI/`
- [ ] Найти код tabs: `Tab.cpp`, `MainFrame.cpp`
- [ ] Найти код "Профиль прутка" dropdown
- [ ] Изучить как работает HTTP (libcurl примеры)
- [ ] Компилировать OrcaSlicer локально (Windows)

**Дедлайн:** 2 недели (изучаем вечерами пока делаем Backend)

### 2.2 Форк и Proof-of-Concept ⏳

- [ ] Создать форк `FilamentHub/OrcaSlicer`
- [ ] Добавить тестовый HTTP запрос к localhost:8000
- [ ] Создать пустой FilamentHub tab (skeleton)
- [ ] Скомпилировать и запустить
- [ ] Протестировать базовую интеграцию

### 2.3 FilamentHub Tab Implementation ⏳

- [ ] Создать `src/slic3r/GUI/FilamentHubPanel.cpp/.h`
- [ ] UI: Авторизация (API key input)
- [ ] UI: Поиск материалов (textbox + button)
- [ ] UI: Список результатов (wxListCtrl)
- [ ] UI: Кнопка "Добавить в профили"
- [ ] HTTP клиент: GET /filaments
- [ ] HTTP клиент: POST /auth/login

### 2.4 Profile Synchronization ⏳

- [ ] Найти где хранятся .json профили
- [ ] Скачивание профилей из API
- [ ] Добавление в "Профиль прутка" menu
- [ ] Пометка "FilamentHub (синхр.)"

### 2.5 Testing & Release ⏳

- [ ] Тестирование Windows
- [ ] Собрать бинарники (Windows exe)
- [ ] GitHub Release (v0.1.0-filamenthub)
- [ ] Инструкция по установке

**Цель Фазы 2:** Работающая интеграция в OrcaSlicer

---

## ⏳ ФАЗА 3: Web UI (Месяц 7-9)

**Минимальный набор для MVP:**

- [ ] React + TypeScript + Vite setup
- [ ] Публичный каталог материалов
- [ ] Регистрация/авторизация для брендов
- [ ] Dashboard для производителей
- [ ] Добавление/редактирование материалов

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

## 🎯 Текущие задачи (На эту неделю)

### Приоритет 1: Backend Setup
1. Создать структуру проекта FastAPI
2. Настроить Docker (PostgreSQL + Redis)
3. Инициализировать Alembic
4. Создать базовые модели (User, Brand, Filament)

### Приоритет 2: OrcaSlicer Learning (параллельно)
5. Клонировать OrcaSlicer
6. Прочитать CLAUDE.md и AGENTS.md
7. Найти где tabs создаются
8. Скомпилировать локально

---

## 📝 Примечания

### Deployment Strategy:
- **MVP:** Разворачиваем локально (localhost:8000)
- **После тестирования:** VPS (Hetzner/Timeweb)

### Приоритет фич:
1. OrcaSlicer интеграция ⭐ (главное!)
2. Backend API (основа)
3. Web UI (для брендов)
4. Всё остальное (потом)

### Заглушки на MVP:
- ✅ Spoolman sync - заглушка (Фаза 5)
- ✅ Calculator - простая формула (полный в Фазе 6)
- ✅ G-code парсинг - не портируем сейчас (Фаза 6)

---

**Готовы начинать!** 🚀  
**Следующий шаг:** Создать структуру Backend проекта
