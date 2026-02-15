---
paths:
  - "**/*"
---

# Общие правила

## Абсолютные запреты

1. **НЕ удалять файлы** без явного разрешения владельца. Никогда. Это включает `rm`, `del`, `unlink`, "cleanup", "refactor", "remove dead code". Спроси сначала.
2. **НЕ использовать `git checkout`, `git reset --hard`, `git clean`, `git restore`, `rm`**. Никогда. Эти команды уже привели к потере 47 файлов. Единственный допустимый вариант — если владелец явно напишет конкретную команду.
3. **НЕ делать `git push`** без явного разрешения.
4. **НЕ создавать заглушки, стабы, хаки, TODO-комментарии** вместо реального кода. Код должен быть production-ready.
5. **НЕ менять версию Python, базовые зависимости или структуру проекта** без обсуждения.
6. **НЕ трогать `.env.prod`** — production секреты управляются вручную.

## Рабочий цикл (обязательный)

После завершения каждой задачи (фикс, фича, рефакторинг):

1. **Код** — написать/исправить
2. **Отметить в `docs/TODO_CONSOLIDATED.md`** — поставить `[x]` или обновить статус
3. **Обновить `docs/ROADMAP.md`** — если задача влияет на прогресс фаз
4. **Коммит** — сразу, не накапливая (`git add` поимённо → `git commit`)
5. **Пуш** — по разрешению владельца

Никогда не откладывать коммиты. Потеря наработок недопустима.

## Git

- **Каждая важная правка коммитится сразу после внесения.** Не накапливать изменения — коммитить по мере завершения логического блока (фикс, фича, рефакторинг).
- Не использовать `--amend` если не попросили.
- Не использовать `git add .` или `git add -A` — добавлять файлы поимённо.
- Формат коммита:
  ```
  тип: краткое описание

  Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
  ```

## Код

- Исправления делаются **in place** — в существующих файлах, а не в новых.
- Перед изменением файла — **всегда прочитать его** целиком или релевантную часть.
- Не добавлять docstrings, комментарии или type annotations к коду, который не менялся.
- Не добавлять "улучшения" за пределами запрошенной задачи.

## Язык

- Код, переменные, комментарии в коде — **английский**
- Документация, TODO, ROADMAP — **русский**
- Сообщения об ошибках в API для пользователей — **русский**
- Логирование — **английский**
- Git commit messages — **английский**

## Проект

**FilamentHub** — платформа для управления материалами и настройками 3D-печати с интеграцией в OrcaSlicer.

**Стек:**
- Backend: Python 3.11+, FastAPI, SQLAlchemy 2.0, PostgreSQL 15, Redis 7, Alembic
- Frontend: React 19, TypeScript, Vite, TailwindCSS, TanStack Query, react-i18next
- OrcaSlicer: C++17, wxWidgets, CMake (форк lizardjazz1/OrcaSlicer)
- Инфра: Docker Compose (dev + prod), Nginx

## Структура проекта

```
FilamentHub/
  backend/
    app/
      api/v1/endpoints/    # REST endpoints
      core/                # config, security, utils
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
    TODO_CONSOLIDATED.md   # Единая точка входа по задачам
    TODO.md                # Аудит безопасности P0-P3
    TODO_Main.md           # Прогресс MVP по фазам
    ROADMAP.md             # Стратегический план
    plan.md                # План: рекомендованные пресеты
    PENDING_TASKS.md       # Нерешённые задачи + вендор-бандлы
    OrcaSlicer/            # Форк, C++ код (submodule)
  scripts/                 # Скрипты запуска и деплоя
```

## Ключевые файлы для навигации

| Задача | Где искать |
|--------|-----------|
| Все задачи (единый вход) | `docs/TODO_CONSOLIDATED.md` |
| Аудит безопасности | `docs/TODO.md` |
| Прогресс MVP | `docs/TODO_Main.md` |
| Стратегический план | `docs/ROADMAP.md` |
| OrcaSlicer профили | `docs/OrcaSlicer/TODO.md` |
| Вендор-бандлы | `docs/PENDING_TASKS.md` |
| Рекомендации пресетов | `docs/plan.md` |
| Деплой | `docs/DEPLOY.md`, `docs/DEPLOYMENT.md` |
| Скрипты | `scripts/` |

## Docker

```bash
# Dev (Windows + Docker Desktop):
docker compose -f docker-compose.dev.yml up -d
# Frontend dev: http://localhost:3000
# Backend API: http://localhost:8001
# Swagger: http://localhost:8001/api/v1/docs

# Production (Linux, deploy.sh):
# НЕ ТРОГАТЬ — деплоится через GitHub + bash scripts/deploy.sh
# Frontend: http://localhost (nginx)
# Backend API: http://localhost:8000
```

## Тестирование

```bash
# Backend тесты (внутри контейнера):
docker exec filamenthub_backend_dev python -m pytest tests/ -v

# Frontend (vitest не настроен — в планах)
```
