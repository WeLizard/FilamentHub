# План коммитов для FilamentHub

## Коммит 1: feat(backend): добавить rate limiting и refresh tokens
**Файлы:**
- `backend/app/core/security.py` - добавлены функции для refresh tokens
- `backend/app/core/limiter.py` - новый модуль для rate limiting
- `backend/app/api/v1/endpoints/auth.py` - rate limiting + refresh endpoint
- `backend/app/main.py` - настройка slowapi middleware
- `backend/app/schemas/user.py` - добавлены RefreshTokenRequest/Response
- `backend/pyproject.toml` - добавлен slowapi

**Описание:**
- Реализован rate limiting для auth endpoints (3 регистрации/мин, 5 логинов/мин)
- Добавлена поддержка refresh tokens
- Создан endpoint `/api/v1/auth/refresh` для обновления токенов
- Исправлен циклический импорт через создание отдельного модуля limiter

## Коммит 2: feat(frontend): поддержка refresh tokens и улучшения auth
**Файлы:**
- `frontend/src/api/client.ts` - автоматическое обновление токенов через interceptor
- `frontend/src/contexts/AuthContext.tsx` - сохранение refresh tokens
- `frontend/src/types/api.ts` - типы для refresh tokens
- `frontend/src/utils/auth.ts` - утилиты для работы с refresh tokens
- `frontend/src/components/AuthModal.tsx` - улучшения UI (переключалка методов входа)
- `frontend/src/components/ProtectedRoute.tsx` - улучшенное сообщение о необходимости авторизации
- `frontend/vite.config.ts` - настройка host для IPv4/IPv6

**Описание:**
- Реализовано автоматическое обновление токенов при 401 ошибке
- Добавлена очередь запросов для предотвращения множественных refresh
- Улучшен UI авторизации (переключалка Email/Google для входа)
- Исправлена проблема с подключением к frontend (IPv6 → IPv4)

## Коммит 3: feat(frontend): добавлены модали для создания материалов и пресетов
**Файлы:**
- `frontend/src/components/CreateFilamentModal.tsx` - новый компонент
- `frontend/src/components/CreatePresetModal.tsx` - новый компонент
- `frontend/src/pages/ProfilePage.tsx` - интеграция модалей
- `frontend/src/pages/CatalogPage.tsx` - рефакторинг
- `frontend/src/components/Layout.tsx` - мелкие улучшения

**Описание:**
- Созданы модальные окна для управления материалами и пресетами
- Добавлена интеграция с API для создания/редактирования
- Улучшен UX на странице профиля

## Коммит 4: fix(backend): исправления моделей и миграций
**Файлы:**
- `backend/alembic/versions/0b9a467f6918_add_user_model.py` - исправлена миграция
- `backend/alembic/versions/d1b87bd1b8f7_fix_user_role_enum.py` - новая миграция для исправления ENUM
- `backend/app/models/user.py` - исправления модели User
- `backend/app/models/preset.py` - мелкие исправления

**Описание:**
- Исправлена проблема с типом ENUM для user.role
- Добавлена миграция для существующих баз данных
- Улучшена обработка ошибок регистрации

## Коммит 5: test(backend): добавлены тесты для API endpoints
**Файлы:**
- `backend/tests/test_filaments.py` - тесты для filaments API
- `backend/tests/test_presets.py` - тесты для presets API
- `backend/tests/test_printers.py` - тесты для printers API
- `backend/tests/test_calculator.py` - тесты для calculator API
- `backend/tests/test_spoolman.py` - тесты для spoolman stub
- `backend/tests/conftest.py` - исправления fixtures

**Описание:**
- Добавлены комплексные тесты для всех основных endpoints
- Исправлены проблемы с async testing
- Coverage увеличен до 58%+

## Коммит 6: chore: обновление инфраструктуры и документации
**Файлы:**
- `backend/Dockerfile` - обновления
- `backend/docker-compose.yml` - настройки
- `backend/app/db/init_data.py` - улучшения инициализации
- `.gitignore` - добавлены исключения для MCP config и screenshots
- `TODO.md` - обновлен прогресс (75% Backend, обновлены секции Security)
- `ROADMAP.md` - обновлен статус задач

**Описание:**
- Обновлена документация с текущим прогрессом
- Улучшена инициализация данных
- Добавлены исключения в .gitignore

## Коммит 7: chore: удаление временных файлов
**Файлы:**
- `.playwright-mcp/*.png` - удалены временные screenshots

**Описание:**
- Очистка репозитория от временных файлов

