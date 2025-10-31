# 🚀 Инструкция по запуску FilamentHub

## ✅ Что уже готово:
- ✅ Все зависимости установлены
- ✅ .env файл создан и настроен
- ✅ Код готов к запуску

## ⚠️ Что нужно сделать:

### Вариант 1: Docker Compose (рекомендуется)

**1. Запустите Docker Desktop**

**2. Запустите PostgreSQL и Redis:**
```bash
cd backend
docker-compose up -d
```

**3. Подождите 10-15 секунд** пока PostgreSQL запустится

**4. Создайте таблицы в БД:**

**Вариант A: Через SQL скрипт (проще):**
```bash
# Подключитесь к PostgreSQL
docker-compose exec postgres psql -U filamenthub -d filamenthub -f /tmp/create_tables.sql

# Или скопируйте скрипт и выполните вручную:
docker-compose exec postgres psql -U filamenthub -d filamenthub
# Затем в psql выполните команды из create_tables.sql
```

**Вариант B: Через Alembic (правильно):**
```bash
# После запуска PostgreSQL:
.\venv\Scripts\python.exe -m alembic upgrade head
```

**5. Загрузите тестовые данные:**
```bash
.\venv\Scripts\python.exe app\db\init_data.py
```

**6. Запустите приложение:**
```bash
.\venv\Scripts\python.exe run.py
```

**7. Откройте в браузере:**
- Frontend: http://localhost:8000/static/index.html
- API Docs: http://localhost:8000/api/v1/docs

---

### Вариант 2: Локальный PostgreSQL

**1. Убедитесь что PostgreSQL установлен и запущен**

**2. Создайте базу данных:**
```sql
CREATE DATABASE filamenthub;
CREATE USER filamenthub WITH PASSWORD 'filamenthub_dev_password';
GRANT ALL PRIVILEGES ON DATABASE filamenthub TO filamenthub;
```

**3. Создайте таблицы:**
```bash
# Подключитесь к PostgreSQL и выполните:
psql -U filamenthub -d filamenthub -f create_tables.sql

# Или через pgAdmin / DBeaver выполните SQL из create_tables.sql
```

**4. Загрузите тестовые данные:**
```bash
.\venv\Scripts\python.exe app\db\init_data.py
```

**5. Запустите приложение:**
```bash
.\venv\Scripts\python.exe run.py
```

---

## 🐛 Проблемы?

### Docker не запускается (Virtualization support not detected)

**Быстрое решение:** Используйте PostgreSQL БЕЗ Docker!

См. подробные инструкции:
- `SETUP_WITHOUT_DOCKER.md` - установка PostgreSQL локально
- `fix_docker_virtualization.md` - как исправить Docker

### Ошибка подключения к PostgreSQL
- Убедитесь что PostgreSQL запущен (`docker-compose ps`)
- Проверьте DATABASE_URL в .env файле
- Подождите 10-15 секунд после `docker-compose up`

### Ошибка "database does not exist"
- Создайте базу: `CREATE DATABASE filamenthub;`
- Или используйте Docker Compose (база создается автоматически)

### Ошибка импорта модулей
- Убедитесь что venv активирован
- Проверьте: `.\venv\Scripts\python.exe -c "import app; print('OK')"`

---

## 📝 Быстрая команда (если Docker запущен):

```powershell
cd backend
docker-compose up -d
Start-Sleep -Seconds 15
.\venv\Scripts\python.exe -m alembic upgrade head
.\venv\Scripts\python.exe app\db\init_data.py
.\venv\Scripts\python.exe run.py
```

---

**После запуска откройте:** http://localhost:8000/static/index.html 🎉

