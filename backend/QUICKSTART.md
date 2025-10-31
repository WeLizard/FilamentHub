# 🚀 Quick Start - FilamentHub Backend

## Быстрый запуск (для демо)

### 1. Установка зависимостей

```bash
cd backend

# Создать virtual environment (если еще нет)
python -m venv venv

# Активировать (Windows PowerShell)
.\venv\Scripts\Activate.ps1

# Активировать (Linux/Mac)
source venv/bin/activate

# Установить зависимости
pip install -e ".[dev]"
```

### 2. Настройка базы данных

**Вариант A: Docker Compose (рекомендуется)**

```bash
# Запустить PostgreSQL и Redis
docker-compose up -d

# Проверить что контейнеры работают
docker-compose ps
```

**Вариант B: Локальный PostgreSQL**

Убедитесь что PostgreSQL запущен и создана база `filamenthub`.

### 3. Настройка .env файла

```bash
# Скопировать env.example в .env
cp env.example .env

# Отредактировать .env (установить DATABASE_URL и SECRET_KEY)
```

**Пример .env:**

```env
DATABASE_URL=postgresql+asyncpg://filamenthub:filamenthub_dev_password@localhost:5432/filamenthub
SECRET_KEY=dev-secret-key-change-in-production
REDIS_URL=redis://localhost:6379/0
DEBUG=True
```

### 4. Создание таблиц в БД

```bash
# Создать первую миграцию (если еще нет)
alembic revision --autogenerate -m "Initial migration"

# Применить миграции
alembic upgrade head
```

### 5. Заполнение тестовыми данными

```bash
# Запустить скрипт инициализации
python app/db/init_data.py
```

Должно появиться: `Test data created successfully!`

### 6. Запуск приложения

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 7. Открыть в браузере

- **Frontend (демо):** http://localhost:8000/static/index.html
- **API Docs:** http://localhost:8000/api/v1/docs
- **Health Check:** http://localhost:8000/health
- **API Root:** http://localhost:8000/api/v1/brands/

---

## 📝 Что уже работает

✅ **Models:**
- Brand (производители)
- Filament (материалы)
- Preset (настройки печати)

✅ **API Endpoints:**
- `GET /api/v1/brands/` - список производителей
- `GET /api/v1/brands/{id}` - получить производителя
- `POST /api/v1/brands/` - создать производителя
- `PATCH /api/v1/brands/{id}` - обновить производителя
- `DELETE /api/v1/brands/{id}` - удалить производителя

- `GET /api/v1/filaments/` - список материалов
- `GET /api/v1/filaments/{id}` - получить материал
- `POST /api/v1/filaments/` - создать материал
- `PATCH /api/v1/filaments/{id}` - обновить материал
- `DELETE /api/v1/filaments/{id}` - удалить материал

✅ **Frontend (заглушка):**
- Список производителей
- Список материалов
- Форма создания материала

---

## 🐛 Troubleshooting

### Ошибка подключения к PostgreSQL

```bash
# Проверить что PostgreSQL запущен
docker-compose ps

# Проверить логи
docker-compose logs postgres

# Перезапустить
docker-compose restart postgres
```

### Ошибка импорта модулей

```bash
# Убедитесь что установлен в editable mode
pip install -e .

# Проверьте PYTHONPATH
python -c "import app; print(app.__file__)"
```

### Alembic не видит модели

Убедитесь что в `alembic/env.py` есть импорт всех моделей:

```python
from app.models import Brand, Filament, Preset
```

### Порт 8000 занят

Используйте другой порт:

```bash
uvicorn app.main:app --reload --port 8001
```

---

**Готово!** 🎉 Теперь можно открыть http://localhost:8000/static/index.html и тестировать!

