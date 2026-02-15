# CLAUDE.md — Правила работы с Claude Code

> Этот файл читается автоматически при запуске Claude Code в директории проекта.

---

## Проект

**FilamentHub** — платформа для управления материалами и настройками 3D-печати с интеграцией в OrcaSlicer.

**Стек:**
- Backend: Python 3.11+, FastAPI, SQLAlchemy 2.0, PostgreSQL 15, Redis 7, Alembic
- Frontend: React 19, TypeScript, Vite, TailwindCSS, TanStack Query, react-i18next
- OrcaSlicer: C++17, wxWidgets, CMake (форк lizardjazz1/OrcaSlicer)
- Инфра: Docker Compose (dev + prod), Nginx

**Порты:**
- Frontend dev: `http://localhost:3000`
- Backend API: `http://localhost:8000`
- Swagger: `http://localhost:8000/api/v1/docs` (только при `DEBUG=True`)

---

## Абсолютные запреты

1. **НЕ удалять файлы** без явного разрешения владельца. Никогда. Это включает `rm`, `del`, `unlink`, "cleanup", "refactor", "remove dead code". Спроси сначала.

2. **НЕ использовать `git checkout`, `git reset --hard`, `git clean`, `git restore`, `rm`**. Никогда. Эти команды уже привели к потере 47 файлов. Единственный допустимый вариант — если владелец явно напишет конкретную команду.

3. **НЕ делать `git push`** без явного разрешения.

4. **НЕ создавать заглушки, стабы, хаки, TODO-комментарии** вместо реального кода. Код должен быть production-ready.

5. **НЕ менять версию Python, базовые зависимости или структуру проекта** без обсуждения.

6. **НЕ трогать `.env.prod`** — production секреты управляются вручную.

---

## Правила работы

### Код

- Исправления делаются **in place** — в существующих файлах, а не в новых.
- Перед изменением файла — **всегда прочитать его** целиком или релевантную часть.
- Не добавлять docstrings, комментарии или type annotations к коду, который не менялся.
- Не добавлять "улучшения" за пределами запрошенной задачи.
- Сообщения об ошибках в API — на русском языке (кроме технических полей).
- Backend логирование — `logger.warning(exc_info=True)` вместо `except: pass`.

### Git

- **Каждая важная правка коммитится сразу после внесения.** Не накапливать изменения — коммитить по мере завершения логического блока (фикс, фича, рефакторинг).
- Не использовать `--amend` если не попросили.
- Не использовать `git add .` или `git add -A` — добавлять файлы поимённо.
- Формат коммита:
  ```
  тип: краткое описание

  Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
  ```

### Безопасность

- Все LIKE-запросы используют `like_pattern()` из `app/core/utils.py`.
- Пути к файлам проверяются через `.resolve()` + проверка префикса.
- `str(e)` НИКОГДА не попадает в HTTP detail — только в логи.
- Новые эндпоинты с данными пользователя — всегда через `Depends(get_current_active_user)`.

### Alembic

- Production БД существует — миграции должны быть обратно-совместимыми.
- `ALTER TYPE ... ADD VALUE IF NOT EXISTS` для PostgreSQL enum.
- Не создавать пустых миграций.

---

## Структура проекта

```
FilamentHub/
  backend/
    app/
      api/v1/endpoints/    # REST endpoints
      core/                # config, security, utils, i18n (мёртвый)
      models/              # SQLAlchemy models (24+)
      schemas/             # Pydantic schemas
      services/            # Бизнес-логика
    alembic/               # Миграции (45+)
    tests/
  frontend/
    src/
      api/client.ts        # API клиент (20 модулей)
      components/          # React компоненты (48+)
      contexts/            # AuthContext
      pages/               # 12 страниц
      locales/             # i18n (ru, en)
  docs/
    OrcaSlicer/            # Форк, C++ код, CLAUDE.md для Orca
    PENDING_TASKS.md       # Нерешённые задачи + вендор-бандлы
  TODO.md                  # Аудит безопасности P0-P3
  TODO_Main.md             # Прогресс MVP по фазам
  TODO_CONSOLIDATED.md     # Единая точка входа (этот проект)
  ROADMAP.md               # Стратегический план
  plan.md                  # План: рекомендованные пресеты
  найденное/               # Референс: утерянные фиксы (только для чтения)
```

---

## Ключевые файлы для навигации

| Задача | Где искать |
|--------|-----------|
| Аудит безопасности | `TODO.md` |
| Все задачи (единый вход) | `TODO_CONSOLIDATED.md` |
| Прогресс MVP | `TODO_Main.md` |
| OrcaSlicer профили | `docs/OrcaSlicer/TODO.md` |
| Вендор-бандлы | `docs/PENDING_TASKS.md` → раздел в конце |
| Рекомендации пресетов | `plan.md` |
| Потерянные фиксы (справка) | `найденное/` |

---

## Docker (разработка)

```bash
# Запуск dev-окружения
docker compose -f docker-compose.dev.yml up -d

# Backend монтируется через volume: ./backend:/app
# Frontend: npm run dev (localhost:3000)

# Production
docker compose up -d --build
```

---

## Тестирование

```bash
# Backend тесты
cd backend && python -m pytest tests/ -v

# Frontend (vitest не настроен — в планах)
```

---

## Язык

- Код, переменные, комментарии в коде — **английский**
- Документация, TODO, ROADMAP — **русский**
- Сообщения об ошибках в API для пользователей — **русский**
- Логирование — **английский**
- Git commit messages — **английский**
