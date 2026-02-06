# 📊 Полный анализ мест хранения данных в FilamentHub

## ✅ Данные в Docker Volumes (сохраняются при обновлениях)

### 1. База данных PostgreSQL
- **Volume:** `postgres_data`
- **Путь в контейнере:** `/var/lib/postgresql/data`
- **Содержимое:**
  - Все таблицы (users, brands, filaments, presets, printers, brand_requests, etc.)
  - Миграции Alembic (таблица `alembic_version`)
  - История миграций (таблица `alembic_migration_history`)
- **Критичность:** 🔴 КРИТИЧНО
- **Статус:** ✅ Настроено правильно

### 2. Кэш Redis
- **Volume:** `redis_data`
- **Путь в контейнере:** `/data`
- **Содержимое:**
  - Кэш сессий
  - Rate limiting данные
  - Временные данные
- **Критичность:** 🟡 СРЕДНЯЯ (можно пересоздать)
- **Статус:** ✅ Настроено правильно

### 3. Загруженные файлы (Uploads)
- **Volume:** `uploads_data`
- **Путь в контейнере:** `/app/uploads`
- **Содержимое:**
  - `brand_requests/{request_id}/` - файлы подтверждения для заявок на бренд
  - `printer_requests/{request_id}/` - файлы подтверждения для заявок на принтер
  - `database_dumps/` - бэкапы базы данных (.sql, .dump, .tar)
  - `qr_codes/` - изображения QR-кодов для печати на этикетках (.png, размеры: 300, 600, 1200px)
- **Критичность:** 🔴 КРИТИЧНО
- **Статус:** ✅ Настроено правильно

### 4. Дистрибутивы (Distributions)
- **Volume:** `distributions_data`
- **Путь в контейнере:** `/app/distributions`
- **Содержимое:**
  - `orcaslicer/` - сборки OrcaSlicer FilamentHub Edition (.exe, .dmg, .AppImage, .zip)
- **Критичность:** 🟡 СРЕДНЯЯ (можно пересобрать, но долго)
- **Статус:** ✅ Настроено правильно

## 📁 Bind Mounts (на хосте, не критично или должны быть на хосте)

### 1. Логи приложения
- **Путь:** `./backend/logs:/app/logs`
- **Содержимое:**
  - `all_services.log`
  - `backend_full.log`
  - Другие логи
- **Критичность:** 🟢 НИЗКАЯ (можно удалять)
- **Статус:** ✅ Правильно (логи не критичны)

### 2. SSL сертификаты
- **Путь:** `./certbot/conf:/etc/letsencrypt`
- **Путь:** `./certbot/www:/var/www/certbot`
- **Содержимое:**
  - Let's Encrypt сертификаты
  - Временные файлы для валидации
- **Критичность:** 🟡 СРЕДНЯЯ (можно перевыпустить, но нужно на хосте для certbot)
- **Статус:** ✅ Правильно (certbot должен иметь доступ на хосте)

## 💾 Данные, которые НЕ хранятся на диске

**Все критичные данные теперь хранятся в volumes!** ✅

QR-коды теперь сохраняются на диск в `uploads/qr_codes/` при создании материала (см. раздел "Загруженные файлы" выше).

## 📋 Структура данных в volumes

### `uploads_data` volume:
```
/app/uploads/
├── brand_requests/
│   ├── 1/
│   │   ├── {uuid}.pdf
│   │   └── {uuid}.jpg
│   └── 2/
│       └── {uuid}.docx
├── printer_requests/
│   └── 1/
│       └── {uuid}.pdf
├── database_dumps/
│   ├── filamenthub_backup_20251106_211559.sql
│   ├── filamenthub_backup_20251106_091054.dump
│   └── ...
└── qr_codes/
    ├── FH-001-300.png  (веб)
    ├── FH-001-600.png  (стандартная печать)
    ├── FH-001-1200.png (высокое качество)
    └── ...
```

### `distributions_data` volume:
```
/app/distributions/
└── orcaslicer/
    ├── OrcaSlicer-FilamentHub-2.0.0-fh-win64.exe
    ├── OrcaSlicer-FilamentHub-2.0.0-fh-win64-portable.zip
    ├── OrcaSlicer-FilamentHub-2.0.0-fh-macos-arm64.dmg
    └── OrcaSlicer-FilamentHub-2.0.0-fh-linux-x64.AppImage
```

## ✅ Итоговая проверка

### Все критичные данные в volumes:
- ✅ База данных PostgreSQL → `postgres_data`
- ✅ Загруженные файлы → `uploads_data`
- ✅ Бэкапы БД → `uploads_data` (внутри uploads)
- ✅ QR-коды → `uploads_data` (внутри uploads/qr_codes/)
- ✅ Дистрибутивы → `distributions_data`

### Не критичные данные (bind mounts):
- ✅ Логи → `./backend/logs` (можно удалять)
- ✅ SSL сертификаты → `./certbot/conf` (нужны на хосте для certbot)

### Данные в памяти (не хранятся):
- ✅ Нет критичных данных в памяти - все сохраняется на диск

## 🔍 Проверка конфигурации

Текущая конфигурация `docker-compose.yml`:

```yaml
volumes:
  # Базы данных
  postgres_data:        # ✅ PostgreSQL
  redis_data:          # ✅ Redis
  # Пользовательские данные
  uploads_data:         # ✅ Uploads + database_dumps
  distributions_data:   # ✅ OrcaSlicer builds
```

**Вывод:** ✅ Все критичные данные правильно настроены в volumes!

## 🚨 Что НЕ нужно в volumes

1. **Код приложения** - в Docker образе
2. **Миграции Alembic** - в Docker образе (код)
3. **Конфигурация** - в Docker образе или env переменных
4. **Временные файлы** - в памяти или /tmp

## 📝 Рекомендации

1. ✅ **Текущая конфигурация правильная** - все критичные данные в volumes
2. ✅ **Логи можно оставить на хосте** - не критичны
3. ✅ **SSL сертификаты правильно на хосте** - нужны для certbot
4. ✅ **Database dumps внутри uploads** - автоматически в volume
5. ✅ **QR-коды теперь сохраняются** - в `uploads/qr_codes/` для печати на этикетках

## 🔄 При обновлении системы

Все данные сохранятся, потому что:
- ✅ База данных в `postgres_data` volume
- ✅ Файлы в `uploads_data` volume
- ✅ Дистрибутивы в `distributions_data` volume
- ✅ Redis кэш в `redis_data` volume (можно пересоздать)

**Процесс обновления безопасен:**
```bash
docker-compose down      # Останавливает контейнеры, volumes остаются
git pull                 # Обновляет код
docker-compose build     # Пересобирает образы
docker-compose up -d     # Запускает с теми же volumes
```

**Данные не потеряются!** ✅

