---
paths:
  - "backend/**/*"
---

# Backend правила (Python / FastAPI)

## Безопасность

- Все LIKE-запросы используют `like_pattern()` из `app/core/utils.py`.
- Пути к файлам проверяются через `.resolve()` + проверка префикса.
- `str(e)` НИКОГДА не попадает в HTTP detail — только в логи.
- Новые эндпоинты с данными пользователя — всегда через `Depends(get_current_active_user)`.
- Backend логирование — `logger.warning(exc_info=True)` вместо `except: pass`.

## Alembic

- Production БД существует — миграции должны быть обратно-совместимыми.
- `ALTER TYPE ... ADD VALUE IF NOT EXISTS` для PostgreSQL enum.
- Не создавать пустых миграций.
- `env.py` использует `from app.models import *` — все модели должны быть в `__init__.py`.

## Структура

```
backend/app/
  api/v1/endpoints/    # REST endpoints
  core/                # config, security, utils
  models/              # SQLAlchemy models (24+)
  schemas/             # Pydantic schemas
  services/            # Бизнес-логика
```

## Docker

```bash
# Dev (с volume mount):
docker compose -f docker-compose.dev.yml up -d

# Production:
docker compose up -d --build
```

- Frontend dev: http://localhost:3000
- Backend API: http://localhost:8000
- Swagger: http://localhost:8000/api/v1/docs (только при DEBUG=True)
