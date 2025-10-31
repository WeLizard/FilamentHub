# 🐳 Docker Setup для FilamentHub

## Быстрый старт

### 1. Перейти в директорию backend
```bash
cd backend
```

### 2. Запустить все сервисы (PostgreSQL, Redis, Backend)
```bash
docker-compose up -d
```

### 3. Проверить статус контейнеров
```bash
docker-compose ps
```

Все три сервиса должны быть в статусе `Up`:
- `filamenthub_postgres` - PostgreSQL база данных
- `filamenthub_redis` - Redis кеш
- `filamenthub_backend` - FastAPI приложение

### 4. Проверить логи backend
```bash
docker-compose logs -f backend
```

Вы должны увидеть:
- Применение миграций: `INFO [alembic.runtime.migration] Running upgrade ...`
- Загрузку тестовых данных: `Test data created successfully!`
- Запуск сервера: `Uvicorn running on http://0.0.0.0:8000`

### 5. Открыть в браузере

- **API Docs (Swagger):** http://localhost:8000/api/v1/docs
- **Health Check:** http://localhost:8000/health
- **API Root:** http://localhost:8000/

## Что происходит при запуске

1. **PostgreSQL** и **Redis** запускаются первыми
2. **Backend** ждет пока БД и Redis станут готовы (healthcheck)
3. Применяются миграции Alembic (`alembic upgrade head`)
4. Загружаются тестовые данные (`python app/db/init_data.py`)
5. Запускается FastAPI сервер на порту 8000

## Остановка

```bash
# Остановить все сервисы
docker-compose down

# Остановить и удалить volumes (БД будет очищена!)
docker-compose down -v
```

## Пересборка после изменений в коде

```bash
# Пересобрать и перезапустить
docker-compose up -d --build
```

## Просмотр логов

```bash
# Все сервисы
docker-compose logs -f

# Только backend
docker-compose logs -f backend

# Только PostgreSQL
docker-compose logs -f postgres
```

## Доступ к БД

```bash
# Подключиться к PostgreSQL
docker-compose exec postgres psql -U filamenthub -d filamenthub
```

## Доступ к Redis

```bash
# Подключиться к Redis CLI
docker-compose exec redis redis-cli
```

## Переменные окружения

Все настройки в файле `.env` (создан из `env.example`):

- `DATABASE_URL` - строка подключения к PostgreSQL
- `REDIS_URL` - строка подключения к Redis  
- `SECRET_KEY` - секретный ключ для JWT токенов
- `DEBUG` - режим отладки (True/False)

## Troubleshooting

### Backend не запускается

1. Проверьте логи: `docker-compose logs backend`
2. Убедитесь что PostgreSQL и Redis запущены: `docker-compose ps`
3. Проверьте что `.env` файл существует и правильно настроен

### Ошибка подключения к БД

1. Проверьте что PostgreSQL контейнер работает: `docker-compose ps postgres`
2. Проверьте `DATABASE_URL` в `.env` файле
3. Убедитесь что миграции применены: `docker-compose exec backend alembic upgrade head`

### Порт 8000 уже занят

Измените порт в `docker-compose.yml`:
```yaml
ports:
  - "8001:8000"  # Внешний:Внутренний
```

Тогда API будет доступен на http://localhost:8001

## Разработка

При монтировании volumes (`- .:/app`) изменения в коде автоматически применяются благодаря `--reload` флагу uvicorn.

Для применения изменений в зависимостях нужно пересобрать:
```bash
docker-compose up -d --build
```

