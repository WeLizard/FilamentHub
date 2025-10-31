# 🛠️ Setup Guide

## Первый запуск (пошагово)

### Шаг 1: Проверка окружения

Убедитесь что установлены:
- Python 3.11+
- Docker и Docker Compose (или локальный PostgreSQL)

```bash
python --version  # Должно быть 3.11+
docker --version  # Если используете Docker
```

### Шаг 2: Создание virtual environment

```bash
cd backend
python -m venv venv

# Windows PowerShell
.\venv\Scripts\Activate.ps1

# Windows CMD
venv\Scripts\activate.bat

# Linux/Mac
source venv/bin/activate
```

### Шаг 3: Установка зависимостей

```bash
pip install --upgrade pip
pip install -e ".[dev]"
```

### Шаг 4: Запуск PostgreSQL и Redis (Docker)

```bash
docker-compose up -d
```

Если Docker не установлен, можно использовать локальный PostgreSQL:
- Установите PostgreSQL
- Создайте базу `filamenthub`
- Пользователь `filamenthub` с паролем `filamenthub_dev_password`

### Шаг 5: Настройка .env файла

```bash
# Скопировать шаблон
cp env.example .env

# Отредактировать .env (используйте любой текстовый редактор)
notepad .env  # Windows
nano .env     # Linux/Mac
```

**Минимальный .env:**

```env
DATABASE_URL=postgresql+asyncpg://filamenthub:filamenthub_dev_password@localhost:5432/filamenthub
SECRET_KEY=dev-secret-key-12345-change-in-production
REDIS_URL=redis://localhost:6379/0
DEBUG=True
```

### Шаг 6: Создание таблиц в БД

```bash
# Создать миграцию (первый раз)
alembic revision --autogenerate -m "Initial migration"

# Применить миграцию
alembic upgrade head
```

Если возникла ошибка `alembic revision`, возможно нужно создать первую миграцию вручную:

```bash
# Создать пустую миграцию
alembic revision -m "Initial migration"

# Отредактировать файл в alembic/versions/XXXX_initial_migration.py
# Добавить код для создания таблиц из моделей
```

Или просто создайте таблицы вручную через SQL:

```sql
-- В psql или pgAdmin
CREATE TABLE brands (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    slug VARCHAR(100) UNIQUE NOT NULL,
    description TEXT,
    website VARCHAR(255),
    logo_url VARCHAR(500),
    verified BOOLEAN DEFAULT FALSE,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE filaments (
    id SERIAL PRIMARY KEY,
    brand_id INTEGER REFERENCES brands(id),
    name VARCHAR(200) NOT NULL,
    material_type VARCHAR(50) NOT NULL,
    color_name VARCHAR(100),
    color_hex VARCHAR(7),
    diameter FLOAT DEFAULT 1.75,
    density FLOAT,
    price_per_kg FLOAT,
    spool_weight FLOAT,
    description TEXT,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_brands_name ON brands(name);
CREATE INDEX idx_brands_slug ON brands(slug);
CREATE INDEX idx_filaments_brand_id ON filaments(brand_id);
CREATE INDEX idx_filaments_material_type ON filaments(material_type);
```

### Шаг 7: Заполнение тестовыми данными

```bash
python app/db/init_data.py
```

Должно появиться:
```
Test data created successfully!
Created 4 brands and 6 filaments
```

### Шаг 8: Запуск приложения

```bash
# Вариант 1: Через run.py
python run.py

# Вариант 2: Через uvicorn
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Шаг 9: Проверка работы

Откройте в браузере:
- **Frontend:** http://localhost:8000/static/index.html
- **API Docs:** http://localhost:8000/api/v1/docs
- **Health:** http://localhost:8000/health

---

## ✅ Чеклист готовности

- [ ] Python 3.11+ установлен
- [ ] Virtual environment создан и активирован
- [ ] Зависимости установлены (`pip install -e ".[dev]"`)
- [ ] PostgreSQL запущен (Docker или локально)
- [ ] .env файл создан и настроен
- [ ] База данных создана и таблицы применены
- [ ] Тестовые данные загружены
- [ ] Приложение запускается без ошибок
- [ ] Frontend открывается в браузере

---

## 🐛 Проблемы?

Смотри **QUICKSTART.md** раздел Troubleshooting.

