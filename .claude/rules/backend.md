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
- Пароли хешируются через `bcrypt` напрямую (passlib удалён).

## Alembic

- Production БД существует — миграции должны быть обратно-совместимыми.
- `ALTER TYPE ... ADD VALUE IF NOT EXISTS` для PostgreSQL enum.
- Не создавать пустых миграций.
- `env.py` использует `from app.models import *` — все модели должны быть в `__init__.py`.
- Revision ID — не длиннее 32 символов (ограничение `alembic_version.version_num`).

## Зависимости (pyproject.toml)

- `bcrypt~=5.0.0` — прямое использование, без passlib
- `PyJWT[crypto]~=2.9.0` — вместо python-jose
- `fastapi~=0.115.0`, `sqlalchemy~=2.0.35`, `asyncpg~=0.30.0`
- Все зависимости через `pyproject.toml`, НЕ через `requirements.txt`

## Структура

```
backend/app/
  api/v1/endpoints/    # REST endpoints
  core/                # config, security, utils
  models/              # SQLAlchemy models (24+)
  schemas/             # Pydantic schemas
  services/            # Бизнес-логика
```
