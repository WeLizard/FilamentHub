# 🛠️ Инструкции по разработке FilamentHub

Полезные команды и инструкции для разработки проекта.

---

## 🐳 Docker

### Проверка статуса контейнеров

```bash
# Список всех контейнеров
docker ps -a

# Статус контейнеров через docker-compose
cd backend
docker-compose ps
```

### Просмотр логов

```bash
cd backend

# Все сервисы
docker-compose logs -f

# Только backend
docker-compose logs -f backend

# Только PostgreSQL
docker-compose logs -f postgres

# Только Redis
docker-compose logs -f redis

# Последние 50 строк логов backend
docker logs filamenthub_backend --tail 50

# Поиск ошибок в логах
docker logs filamenthub_backend 2>&1 | grep -i error
```

### Управление контейнерами

```bash
cd backend

# Запустить все сервисы
docker-compose up -d

# Остановить все сервисы
docker-compose stop

# Перезапустить контейнер
docker-compose restart backend

# Пересобрать и перезапустить
docker-compose up -d --build backend

# Остановить и удалить контейнеры (БД сохранится в volumes)
docker-compose down

# Остановить и удалить всё включая volumes (⚠️ удалит данные!)
docker-compose down -v
```

### Доступ к БД

```bash
cd backend

# Подключиться к PostgreSQL через psql
docker-compose exec postgres psql -U filamenthub -d filamenthub

# Полезные SQL команды:
# \dt          - список таблиц
# \d table_name - структура таблицы
# SELECT * FROM users LIMIT 5;
# \q           - выход
```

### Доступ к Redis

```bash
cd backend

# Подключиться к Redis CLI
docker-compose exec redis redis-cli

# Полезные команды:
# KEYS *       - список всех ключей
# GET key      - получить значение
# FLUSHALL     - очистить всё (⚠️ осторожно!)
# PING         - проверить подключение
# QUIT         - выход
```

### Исправление проблем

```bash
# Если контейнер не запускается:
docker-compose logs backend

# Если нужно пересоздать БД (⚠️ удалит данные):
docker-compose down -v
docker-compose up -d

# Проверить использование ресурсов
docker stats
```

---

## 🎨 Frontend

### Запуск в режиме разработки

```bash
cd frontend

# Установить зависимости (если еще не установлены)
npm install

# Запустить dev сервер
npm run dev

# Откроется на http://localhost:5173
```

### Сборка для продакшена

```bash
cd frontend

# Собрать проект
npm run build

# Результат будет в dist/
```

### Проверка кода

```bash
cd frontend

# Проверить TypeScript ошибки
npm run type-check

# Линтинг (если настроен)
npm run lint
```

### Установка новых зависимостей

```bash
cd frontend

# Установить пакет
npm install package-name

# Установить dev зависимость
npm install -D package-name
```

### Исправление проблем

```bash
# Очистить кэш и переустановить зависимости
cd frontend
rm -rf node_modules package-lock.json
npm install

# Windows PowerShell:
cd frontend
Remove-Item -Recurse -Force node_modules, package-lock.json
npm install
```

---

## 🐍 Backend

### Запуск локально (без Docker)

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

# Создать .env файл из примера
cp env.example .env

# Отредактировать .env (установить DATABASE_URL и SECRET_KEY)

# Применить миграции
alembic upgrade head

# Запустить сервер
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Работа с миграциями

```bash
cd backend

# Создать новую миграцию
alembic revision --autogenerate -m "описание изменений"

# Применить миграции
alembic upgrade head

# Откатить последнюю миграцию
alembic downgrade -1

# Посмотреть текущую версию
alembic current

# Посмотреть историю миграций
alembic history
```

### Тесты

```bash
cd backend

# Запустить все тесты
pytest

# Запустить с покрытием
pytest --cov=app

# Запустить конкретный тест
pytest tests/test_brands.py::test_create_brand
```

### Проверка кода

```bash
cd backend

# Форматирование (если настроен black)
black app/

# Проверка типов (если настроен mypy)
mypy app/
```

---

## 🔍 Отладка

### Проверка работы API

```bash
# Проверить health endpoint
curl http://localhost:8000/api/v1/health

# Windows PowerShell:
Invoke-WebRequest -Uri http://localhost:8000/api/v1/brands -Method GET

# Проверить документацию API
# Открой в браузере: http://localhost:8000/docs
```

### Логи Backend в Docker

```bash
# Следить за логами в реальном времени
docker logs -f filamenthub_backend

# Поиск ошибок
docker logs filamenthub_backend 2>&1 | Select-String -Pattern "error|Error|ERROR" -Context 2,2
```

### Логи Frontend

```bash
# Логи выводятся в консоль браузера (F12 → Console)
# Также в терминале где запущен npm run dev
```

### Проверка подключения к БД

```bash
cd backend
docker-compose exec postgres psql -U filamenthub -d filamenthub -c "SELECT version();"
```

---

## 📋 Полезные команды

### Очистка

```bash
# Удалить все остановленные контейнеры
docker container prune

# Удалить неиспользуемые образы
docker image prune

# Удалить неиспользуемые volumes (⚠️ осторожно!)
docker volume prune

# Очистить всё неиспользуемое
docker system prune -a
```

### Проверка портов

```bash
# Windows PowerShell - проверить какие порты заняты
netstat -ano | findstr :8000
netstat -ano | findstr :5173
netstat -ano | findstr :5432

# Linux/Mac
lsof -i :8000
lsof -i :5173
lsof -i :5432
```

### Перезапуск всего проекта

```bash
# Остановить всё
cd backend
docker-compose down

# Очистить кэш frontend (если нужно)
cd ../frontend
rm -rf node_modules/.vite

# Запустить backend
cd ../backend
docker-compose up -d

# Запустить frontend
cd ../frontend
npm run dev
```

---

## 🚨 Частые проблемы

### Backend не запускается

1. Проверить логи: `docker-compose logs backend`
2. Проверить что PostgreSQL запущен: `docker-compose ps postgres`
3. Проверить `.env` файл существует и правильно настроен
4. Проверить что порт 8000 свободен

### Frontend не подключается к Backend

1. Проверить что Backend запущен: `curl http://localhost:8000/api/v1/health`
2. Проверить настройки CORS в `backend/app/core/config.py`
3. Проверить proxy в `frontend/vite.config.ts`

### Ошибка подключения к БД

1. Проверить что PostgreSQL контейнер работает: `docker-compose ps postgres`
2. Проверить `DATABASE_URL` в `.env`
3. Проверить что миграции применены: `docker-compose exec backend alembic upgrade head`
4. Проверить логи PostgreSQL: `docker-compose logs postgres`

### Порт уже занят

Изменить порт в `docker-compose.yml`:
```yaml
ports:
  - "8001:8000"  # Внешний:Внутренний
```

Или остановить процесс занимающий порт (Windows):
```powershell
# Найти процесс
netstat -ano | findstr :8000

# Остановить процесс (замени PID на реальный)
taskkill /PID <PID> /F
```

---

## 📚 Дополнительные ресурсы

- **API документация:** http://localhost:8000/docs (Swagger UI)
- **API альтернативная:** http://localhost:8000/redoc (ReDoc)
- **Frontend:** http://localhost:5173
- **Backend:** http://localhost:8000

---

**Последнее обновление:** 2025-01-XX

