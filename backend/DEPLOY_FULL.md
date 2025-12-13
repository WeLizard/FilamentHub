# 🚀 Полная инструкция по развертыванию FilamentHub

## Подготовка

### 1. Требования на сервере

- Docker 20.10+
- Docker Compose 2.0+
- Минимум 2GB RAM
- Минимум 10GB свободного места
- Git (для клонирования репозитория)

### 2. Клонирование репозитория

```bash
git clone <repository-url>
cd FilamentHub/backend
```

### 3. Настройка переменных окружения

Создайте файл `.env.prod` на основе шаблона:

```bash
cp .env.prod.template .env.prod
nano .env.prod  # или используйте ваш любимый редактор
```

**КРИТИЧЕСКИ ВАЖНО:** Измените следующие значения:

#### Обязательные настройки:

1. **`POSTGRES_PASSWORD`** - надежный пароль для PostgreSQL
   ```env
   POSTGRES_PASSWORD=your_secure_database_password_here
   ```

2. **`SECRET_KEY`** - сгенерируйте случайную строку (минимум 32 символа)
   ```bash
   python3 -c "import secrets; print(secrets.token_urlsafe(32))"
   ```
   Или используйте:
   ```bash
   openssl rand -hex 32
   ```
   Затем вставьте в `.env.prod`:
   ```env
   SECRET_KEY=your_generated_secret_key_here
   ```

3. **`CORS_ORIGINS`** - укажите домены вашего фронтенда
   ```env
   CORS_ORIGINS=["https://yourdomain.com","https://www.yourdomain.com"]
   ```

4. **`DEBUG=False`** - обязательно для продакшена (уже установлено в шаблоне)

#### Опциональные настройки:

- `BACKEND_PORT` - порт для backend (по умолчанию: 8000)
- `FRONTEND_PORT` - порт для frontend (по умолчанию: 80)
- `DATABASE_POOL_SIZE` - размер пула соединений (по умолчанию: 10)
- `MAX_UPLOAD_SIZE_MB` - максимальный размер загружаемых файлов (по умолчанию: 50)

## Развертывание

### Вариант 1: Полная автоматическая развертка (рекомендуется)

```bash
# 1. Убедитесь что .env.prod настроен правильно
cat .env.prod | grep -E "POSTGRES_PASSWORD|SECRET_KEY|ADMIN_EMAIL|ADMIN_PASSWORD"

# 2. Остановите и удалите старые контейнеры и volumes (если есть)
docker-compose -f docker-compose.prod.yml down -v

# 3. Сборка и запуск всех сервисов
docker-compose -f docker-compose.prod.yml up -d --build

# 4. Проверка статуса (дождитесь пока все контейнеры станут healthy)
docker-compose -f docker-compose.prod.yml ps

# 5. Просмотр логов backend (проверьте что миграции применились)
docker-compose -f docker-compose.prod.yml logs -f backend
```

**Важно:** Дождитесь завершения миграций перед созданием админа. Проверьте логи:
```bash
docker-compose -f docker-compose.prod.yml logs backend | grep -E "Migration|upgrade|ERROR"
```

### Вариант 2: Пошаговое развертывание (для отладки)

```bash
# 1. Запуск PostgreSQL и Redis
docker-compose -f docker-compose.prod.yml up -d postgres redis

# 2. Ожидание готовности БД (проверка healthcheck)
docker-compose -f docker-compose.prod.yml ps postgres
# Дождитесь пока статус станет "healthy"

# 3. Запуск backend (применит миграции автоматически)
docker-compose -f docker-compose.prod.yml up -d --build backend

# 4. Проверка логов миграций
docker-compose -f docker-compose.prod.yml logs -f backend
# Дождитесь сообщения "✅ Migrations applied successfully!"

# 5. Запуск frontend
docker-compose -f docker-compose.prod.yml up -d --build frontend

# 6. Проверка всех сервисов
docker-compose -f docker-compose.prod.yml ps
```

## Проверка работы

### 1. Health Check

```bash
curl http://localhost:8000/health
```

Должен вернуть:
```json
{"status": "ok"}
```

### 2. API Docs

Откройте в браузере:
- Swagger UI: `http://your-server:8000/api/v1/docs`
- ReDoc: `http://your-server:8000/api/v1/redoc`

### 3. Проверка миграций

```bash
# Текущая версия миграции
docker-compose -f docker-compose.prod.yml exec backend alembic current

# Все доступные миграции (head)
docker-compose -f docker-compose.prod.yml exec backend alembic heads

# История миграций
docker-compose -f docker-compose.prod.yml exec backend alembic history | head -20
```

**Важно:** 
- Текущая версия должна совпадать с head. 
- Если миграции не применились, проверьте логи: `docker-compose -f docker-compose.prod.yml logs backend | grep -i error`
- Если есть ошибки миграций, они будут в логах при старте контейнера

### 4. Проверка структуры БД

```bash
# Подключение к PostgreSQL
docker-compose -f docker-compose.prod.yml exec postgres psql -U filamenthub -d filamenthub

# Проверка таблиц
\dt

# Проверка структуры таблицы users
\d users

# Выход
\q
```

## Создание администратора

**ВАЖНО:** Администратор НЕ создается автоматически при развертывании. Его нужно создать вручную после успешного применения всех миграций.

### Способ 1: Через скрипт (рекомендуется)

```bash
# Установите переменные окружения
export ADMIN_EMAIL=admin@yourdomain.com
export ADMIN_USERNAME=admin
export ADMIN_PASSWORD=your_secure_password

# Запустите скрипт
docker-compose -f docker-compose.prod.yml exec backend python create_admin_direct.py
```

Или напрямую:

```bash
docker-compose -f docker-compose.prod.yml exec -e ADMIN_EMAIL=admin@yourdomain.com -e ADMIN_USERNAME=admin -e ADMIN_PASSWORD=your_password backend python create_admin_direct.py
```

### Способ 2: Через прямой SQL

```bash
# Подключение к PostgreSQL
docker-compose -f docker-compose.prod.yml exec postgres psql -U filamenthub -d filamenthub
```

Затем выполните SQL (замените значения):

```sql
-- Создайте хэш пароля (используйте Python или другой способ)
-- Пример: python3 -c "from app.core.security import get_password_hash; print(get_password_hash('your_password'))"

INSERT INTO users (
    email, username, password_hash, role, 
    active, email_verified, created_at, updated_at
) VALUES (
    'admin@yourdomain.com',
    'admin',
    '$2b$12$...',  -- Вставьте реальный хэш пароля
    'admin'::userrole,
    true,
    true,
    now(),
    now()
)
ON CONFLICT (email) DO NOTHING;
```

### Способ 3: Через админ панель (после первого входа)

Если у вас уже есть другой админ, можно создать нового через админ панель.

## Первый вход

1. Откройте фронтенд: `http://your-server` (или `http://localhost` для локального тестирования)
2. Нажмите "Войти"
3. Введите данные администратора:
   - Email: `admin@yourdomain.com` (или тот, что вы указали)
   - Password: ваш пароль
4. После входа перейдите в админ панель (если доступна)

## Устранение проблем

### Проблема: Миграции не применяются

**Симптомы:**
- В логах ошибки типа "column does not exist"
- API возвращает 500 ошибки

**Решение:**
1. Проверьте логи: `docker-compose -f docker-compose.prod.yml logs backend`
2. Если миграции не все применены, зайдите в админ панель → Database → Migrations
3. Примените недостающие миграции вручную

### Проблема: Админ не может войти

**Симптомы:**
- "Invalid credentials" при попытке входа
- Админ не создан в БД

**Решение:**
1. Проверьте, создан ли админ:
   ```bash
   docker-compose -f docker-compose.prod.yml exec postgres psql -U filamenthub -d filamenthub -c "SELECT email, username, role FROM users WHERE role = 'admin';"
   ```
2. Если админа нет - создайте его через скрипт (см. выше)
3. Если админ есть, но не может войти - проверьте пароль или создайте нового

### Проблема: Backend не запускается

**Симптомы:**
- Контейнер постоянно перезапускается
- Ошибки подключения к PostgreSQL

**Решение:**
1. Проверьте `.env.prod` - все ли переменные установлены
2. Проверьте логи: `docker-compose -f docker-compose.prod.yml logs backend`
3. Проверьте, что PostgreSQL запущен: `docker-compose -f docker-compose.prod.yml ps postgres`
4. Проверьте пароль PostgreSQL в `.env.prod`

### Проблема: Frontend показывает "Ошибка загрузки материалов"

**Симптомы:**
- Фронтенд загружается, но API не отвечает
- 502 Bad Gateway в консоли браузера

**Решение:**
1. Проверьте, что backend запущен: `docker-compose -f docker-compose.prod.yml ps backend`
2. Проверьте логи backend: `docker-compose -f docker-compose.prod.yml logs backend`
3. Проверьте API напрямую: `curl http://localhost:8000/api/v1/filaments/`
4. Если API не отвечает - проверьте миграции (см. выше)

## Обновление

### Обновление кода

```bash
# Остановить контейнеры
docker-compose -f docker-compose.prod.yml down

# Обновить код
git pull

# Пересобрать и запустить
docker-compose -f docker-compose.prod.yml up -d --build
```

### Применение новых миграций

Новые миграции применяются автоматически при запуске backend через `docker-entrypoint.sh`.

Если что-то пошло не так:
1. Зайдите в админ панель → Database → Migrations
2. Примените недостающие миграции вручную

## Резервное копирование

### Экспорт БД

```bash
docker-compose -f docker-compose.prod.yml exec postgres pg_dump -U filamenthub filamenthub > backup_$(date +%Y%m%d_%H%M%S).sql
```

### Восстановление БД

```bash
docker-compose -f docker-compose.prod.yml exec -T postgres psql -U filamenthub -d filamenthub < backup_20250101_120000.sql
```

## Безопасность

### После развертывания:

1. ✅ Смените пароль администратора
2. ✅ Убедитесь, что `DEBUG=False` в `.env.prod`
3. ✅ Убедитесь, что `SECRET_KEY` уникальный и сложный
4. ✅ Настройте firewall (откройте только нужные порты)
5. ✅ Настройте SSL/TLS для фронтенда (через reverse proxy)
6. ✅ Регулярно обновляйте Docker образы
7. ✅ Делайте резервные копии БД

## Мониторинг

### Просмотр логов

```bash
# Все сервисы
docker-compose -f docker-compose.prod.yml logs -f

# Только backend
docker-compose -f docker-compose.prod.yml logs -f backend

# Последние 100 строк
docker-compose -f docker-compose.prod.yml logs --tail 100 backend
```

### Статистика контейнеров

```bash
docker-compose -f docker-compose.prod.yml ps
docker stats
```

## Остановка

```bash
# Остановить контейнеры (данные сохраняются)
docker-compose -f docker-compose.prod.yml stop

# Остановить и удалить контейнеры (данные сохраняются)
docker-compose -f docker-compose.prod.yml down

# Остановить и удалить всё, включая данные (ОСТОРОЖНО!)
docker-compose -f docker-compose.prod.yml down -v
```

## Дополнительная информация

- **Документация API:** `http://your-server:8000/api/v1/docs`
- **Админ панель:** `http://your-server/admin` (после входа как админ)
- **GitHub репозиторий:** [ссылка на репозиторий]

## Поддержка

При возникновении проблем:
1. Проверьте логи: `docker-compose -f docker-compose.prod.yml logs`
2. Проверьте статус контейнеров: `docker-compose -f docker-compose.prod.yml ps`
3. Проверьте документацию выше
4. Создайте issue в репозитории

