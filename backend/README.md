# FilamentHub Backend

FastAPI backend для FilamentHub платформы.

## 🚀 Quick Start

### Локальная разработка (без Docker)

1. **Установка зависимостей:**

```bash
cd backend

# Создать virtual environment
python -m venv venv

# Активировать (Windows PowerShell)
.\venv\Scripts\Activate.ps1

# Активировать (Linux/Mac)
source venv/bin/activate

# Установить зависимости
pip install -e ".[dev]"
```

2. **Настройка окружения:**

```bash
# Скопировать env.example в .env
cp env.example .env

# Отредактировать .env (установить DATABASE_URL и SECRET_KEY)
```

3. **Запуск PostgreSQL и Redis (Docker Compose):**

```bash
docker-compose up -d
```

4. **Запуск приложения:**

```bash
uvicorn app.main:app --reload
```

Приложение будет доступно на http://localhost:8000

- API Docs: http://localhost:8000/api/v1/docs
- Health Check: http://localhost:8000/health

---

### Разработка в Docker (все в контейнерах)

1. **Раскомментировать backend service в docker-compose.yml**

2. **Запустить все сервисы:**

```bash
docker-compose up --build
```

---

## 📁 Структура проекта

```
backend/
├── app/
│   ├── api/
│   │   └── v1/
│   │       ├── endpoints/      # API эндпоинты
│   │       │   ├── brands.py
│   │       │   ├── filaments.py
│   │       │   ├── presets.py
│   │       │   └── ...
│   │       └── api.py          # Router aggregator
│   ├── core/
│   │   ├── config.py           # Настройки
│   │   ├── security.py         # JWT, password hashing
│   │   └── logging.py          # Логирование
│   ├── db/
│   │   ├── base.py             # SQLAlchemy Base
│   │   └── session.py          # Database session
│   ├── models/                 # SQLAlchemy модели
│   │   ├── brand.py
│   │   ├── filament.py
│   │   ├── preset.py
│   │   ├── user.py
│   │   └── ...
│   ├── schemas/                # Pydantic схемы
│   │   ├── brand.py
│   │   ├── filament.py
│   │   ├── preset.py
│   │   └── ...
│   ├── services/               # Бизнес-логика
│   │   ├── brand_service.py
│   │   ├── filament_service.py
│   │   └── ...
│   └── main.py                 # FastAPI app
├── alembic/                    # Database migrations
├── tests/                      # Тесты
├── pyproject.toml              # Dependencies
├── docker-compose.yml          # Docker setup
├── Dockerfile                  # Docker image
└── README.md                   # This file
```

---

## 🛠️ Development

### Создание миграций (Alembic)

```bash
# Инициализация Alembic (уже сделано)
alembic init alembic

# Создать новую миграцию
alembic revision --autogenerate -m "Add Brand model"

# Применить миграции
alembic upgrade head

# Откатить последнюю миграцию
alembic downgrade -1
```

### Тестирование

```bash
# Запустить все тесты
pytest

# С покрытием
pytest --cov=app --cov-report=html

# Конкретный тест
pytest tests/test_brands.py
```

### Линтинг и форматирование

```bash
# Ruff (линтер)
ruff check .

# Ruff (автофикс)
ruff check --fix .

# Black (форматирование)
black .

# MyPy (type checking)
mypy app/
```

---

## 🔧 Полезные команды

### Docker

```bash
# Пересобрать и запустить
docker-compose up --build

# Остановить
docker-compose down

# Посмотреть логи
docker-compose logs -f backend

# Войти в контейнер
docker-compose exec backend bash
```

### Database

```bash
# Подключиться к PostgreSQL
docker-compose exec postgres psql -U filamenthub -d filamenthub

# Сбросить базу (осторожно!)
docker-compose down -v
docker-compose up -d postgres
alembic upgrade head
```

---

## 📝 TODO

- [ ] Настроить Alembic
- [ ] Создать модели (Brand, Filament, Preset, User)
- [ ] Создать CRUD эндпоинты
- [ ] Добавить JWT authentication
- [ ] Портировать G-code парсеры из PHP
- [ ] Написать тесты

---

## 🐛 Troubleshooting

### Ошибка подключения к PostgreSQL

Убедитесь что PostgreSQL запущен:

```bash
docker-compose ps
```

Проверьте DATABASE_URL в .env файле.

### Ошибка импорта модулей

Убедитесь что backend/ установлен в editable mode:

```bash
pip install -e .
```

### CORS ошибки

Добавьте URL фронтенда в `CORS_ORIGINS` в `.env` файле.

---

**Статус:** 🟢 База проекта готова, начинаем разработку!

