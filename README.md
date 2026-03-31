# FilamentHub

FilamentHub — платформа для управления филаментами, пресетами и профилями 3D-печати с прямой интеграцией в OrcaSlicer.

- Сайт: [filamenthub.ru](https://filamenthub.ru)
- Карта документации: [docs/INDEX.md](docs/INDEX.md)
- OrcaSlicer fork: [WeLizard/OrcaSlicer](https://github.com/WeLizard/OrcaSlicer)

## О проекте

FilamentHub — это не магазин и не просто каталог филаментов. Это платформа между тремя сторонами:

- производителями филамента, которым нужен нормальный способ публиковать официальные пресеты для своих материалов;
- сообществом, которое накапливает рабочие настройки под реальные связки `принтер + филамент`;
- самим OrcaSlicer, чтобы эти данные не жили в виде разрозненных JSON-файлов, а были доступны прямо внутри слайсера.

Проект объединяет:

- каталог брендов, материалов и пресетов;
- личный кабинет пользователя с катушками, принтерами, профилями и настройками синхронизации;
- брендовый контур с верификацией и официальными пресетами;
- двустороннюю интеграцию с OrcaSlicer;
- сервисные функции вокруг 3D-печати: QR-коды, Spoolman-совместимый API, калькулятор стоимости, wiki и уведомления.

## Какую проблему решает

В реальной 3D-печати настройки обычно живут в хаосе:

- пресеты разбросаны по Discord, форумам, GitHub и локальным JSON-файлам;
- у производителей нет единого канала для публикации официальных профилей материалов;
- пользователи вручную импортируют и экспортируют настройки в слайсер;
- сложно понять, что реально работало для конкретной связки `принтер + филамент`;
- неудобно переносить рабочие пресеты между устройствами и профилями;
- остатки катушек и расход материала часто ведутся отдельно или вообще не отслеживаются.

Если коротко: FilamentHub убирает хаос вокруг филаментов, пресетов, профилей и их синхронизации с OrcaSlicer.

## Ключевые возможности

### Веб-платформа

- каталог брендов, филаментов и пресетов;
- личный кабинет пользователя;
- управление сохранёнными пресетами и флагами синхронизации;
- профили принтеров и профили печати;
- калькулятор стоимости печати;
- wiki-раздел и база знаний;
- уведомления и сбор обратной связи;
- OAuth-авторизация.

### Интеграция с OrcaSlicer

- встроенная панель FilamentHub внутри OrcaSlicer;
- WebView bridge между React frontend и C++-частью слайсера;
- двусторонняя синхронизация filament / printer / print profiles;
- импорт и экспорт профилей без ручного перекидывания JSON-файлов;
- поддержка multi-printer сценариев;
- база для MMU / Happy Hare интеграции.

### Работа с материалами и катушками

- учёт катушек и остатков;
- Spoolman-compatible API и WebSocket-слой;
- связка пресетов с конкретными материалами, брендами и линейками;
- сохранение официальных и community-пресетов в профиль пользователя.

### Для брендов и производителей

- брендовый профиль и верификация;
- публикация официальных пресетов;
- QR-коды для филаментов;
- QR-сценарий, при котором пользователь может открыть материал и автоматически получить связанный официальный пресет;
- база для будущих vendor bundles.

## Технологический стек

### Frontend

- React 19
- TypeScript
- Vite
- Tailwind CSS 4
- TanStack Query
- react-i18next

### Backend

- Python 3.11
- FastAPI
- SQLAlchemy 2.0 async
- PostgreSQL 15
- Redis 7
- Alembic

### OrcaSlicer integration

- C++17
- wxWidgets
- CMake
- OrcaSlicer submodule / fork

### Инфраструктура

- Docker Compose
- Nginx
- WebSocket для Spoolman-совместимых сценариев

## Структура репозитория

```text
filamenthub/
├── backend/              # FastAPI backend, models, services, migrations
├── frontend/             # React frontend
├── submodule/OrcaSlicer/ # OrcaSlicer integration / fork
├── docs/                 # Документация, roadmap, TODO, архитектурные заметки
├── scripts/              # Локальные utility/deploy/start scripts
└── HANDOFF.md            # Текущий рабочий контекст между сессиями
```

## Быстрый старт для разработки

Рекомендуемый dev-способ:

1. Создать локальный `.env`:

```bash
cp .env.template .env
```

Для PowerShell:

```powershell
Copy-Item .env.template .env
```

2. Поднять dev-окружение:

```bash
docker compose -f docker-compose.dev.yml up -d
```

3. Проверить сервисы:

- frontend: `http://localhost:3000`
- backend: `http://localhost:8001`
- swagger: `http://localhost:8001/api/v1/docs`

Для остановки:

```bash
docker compose -f docker-compose.dev.yml down
```

## Локальная разработка без Docker

### Backend

```bash
cd backend
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1

# Linux/macOS:
# source .venv/bin/activate

pip install -e .[dev]
uvicorn app.main:app --reload --host 0.0.0.0 --port 8001
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

## Документация

Основная точка входа:

- [docs/INDEX.md](docs/INDEX.md)

Полезные документы:

- [docs/current/TODO_CONSOLIDATED.md](docs/current/TODO_CONSOLIDATED.md)
- [docs/current/ROADMAP.md](docs/current/ROADMAP.md)
- [docs/current/DEPLOY.md](docs/current/DEPLOY.md)
- [HANDOFF.md](HANDOFF.md)

## Текущий фокус проекта

Сейчас проект развивается в нескольких ключевых направлениях:

- стабилизация и UX двусторонней синхронизации OrcaSlicer ↔ FilamentHub;
- развитие printer / print profile ecosystem;
- Happy Hare / MMU сценарии;
- рекомендованные пресеты;
- vendor bundles;
- дальнейшее движение от fork-подхода к более формализованной plugin/API-модели в будущем.
