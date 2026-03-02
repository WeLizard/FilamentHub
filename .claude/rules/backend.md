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

## Ошибки (error codes i18n)

- Все HTTP-ошибки используют коды из `app/core/errors.py` (80+ констант `ERR_*`).
- Формат: `raise_error(status_code, ERR_CONSTANT)` или `raise_error(status_code, ERR_CONSTANT, params={...})`.
- Хелпер `raise_error()` формирует `detail={"code": "ERR_...", "params": {...}}`.
- **НЕ** использовать `detail="строка на русском"` — только коды.
- Текстовая валидация: `validate_text_field()` из `app/core/utils.py` → возвращает dict с `ERR_BAD_WORDS` / `ERR_REPEATED_CHARS` / `ERR_NO_LETTERS_OR_DIGITS`.
- Email валидация: `app/services/email_validator.py` → `ERR_EMAIL_DOMAIN_TYPO`, `ERR_DOMAIN_NO_MAIL`.
- Остаток: ~24 места в admin.py/wiki.py используют `detail=ERR_STRING` (строка вместо dict) — работает, но неконсистентно. См. `docs/plan_error_codes_i18n.md`.

## Alembic

- Production БД существует — миграции должны быть обратно-совместимыми.
- `ALTER TYPE ... ADD VALUE IF NOT EXISTS` для PostgreSQL enum.
- Не создавать пустых миграций.
- `env.py` использует `from app.models import *` — все модели должны быть в `__init__.py`.
- Revision ID — не длиннее 32 символов (ограничение `alembic_version.version_num`).
- **НИКОГДА не применять миграции вручную** через CLI (`alembic upgrade head`). Все миграции применяются только через админ-панель на фронтенде администратором.

## Зависимости (pyproject.toml)

- `bcrypt~=5.0.0` — прямое использование, без passlib
- `PyJWT[crypto]~=2.9.0` — вместо python-jose
- `fastapi~=0.115.0`, `sqlalchemy~=2.0.35`, `asyncpg~=0.30.0`
- Все зависимости через `pyproject.toml`, НЕ через `requirements.txt`

## Структура

```
backend/app/
  api/v1/endpoints/    # REST endpoints (21 файл)
  core/                # config, security, utils, errors, dependencies
  models/              # SQLAlchemy models (25)
  schemas/             # Pydantic schemas
  services/            # Бизнес-логика (25 сервисов)
```

## Ключевые сервисы

| Сервис | Назначение |
|--------|-----------|
| `orcaslicer_service.py` | Синхронизация пресетов OrcaSlicer ↔ FilamentHub |
| `orcaslicer_exporter.py` | Экспорт пресетов в формат OrcaSlicer JSON/.info |
| `preset_recommender.py` | Скоринг и рекомендации пресетов для принтера |
| `weighted_preset_service.py` | Взвешенные (агрегированные) пресеты |
| `email_validator.py` | Валидация email: домены, опечатки, MX/A check |
| `file_service.py` | Загрузка/хранение файлов с валидацией |
| `text_moderation.py` | Проверка текста на запрещённые слова |
| `sync_orchestrator.py` | Оркестрация синхронизации данных |
| `wiki_sync_service.py` | Синхронизация Wiki статей |
| `maintenance_service.py` | Режим обслуживания |
