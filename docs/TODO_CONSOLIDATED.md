# TODO — FilamentHub (Консолидированный)

> **Дата:** 15 февраля 2026
> **Источники:** `TODO.md`, `TODO_Main.md`, `ROADMAP.md`, `docs/PENDING_TASKS.md`, `docs/OrcaSlicer/TODO.md`, `plan.md`, `найденное/*`
>
> Оригиналы НЕ удалены — этот файл является единой точкой входа.

---

## Навигация по оригинальным файлам

| Файл | Что содержит |
|------|-------------|
| [`TODO.md`](TODO.md) | Аудит безопасности P0–P3 (50 пунктов) |
| [`TODO_Main.md`](TODO_Main.md) | Прогресс MVP по фазам, все endpoints |
| [`ROADMAP.md`](ROADMAP.md) | Стратегический план, фазы 0–8, монетизация |
| [`PENDING_TASKS.md`](PENDING_TASKS.md) | Нерешённые задачи, Issues, вендор-бандлы |
| [`OrcaSlicer/TODO.md`](OrcaSlicer/TODO.md) | Профили OrcaSlicer: filament/print/printer/bundles |
| [`plan.md`](plan.md) | План: рекомендованные пресеты для принтера |

---

## Общий статус проекта

```
Backend API          [███████████████████░]  95%
Frontend Web UI      [██████████████████░░]  85%
OrcaSlicer C++       [██████████████████░░]  87%
Безопасность         [██████████████████░░]  90%  ← аудит проведён, P0 закрыты
Вендор-бандлы        [░░░░░░░░░░░░░░░░░░░░]   0%
Публичный запуск     [░░░░░░░░░░░░░░░░░░░░]   0%
```

---

## P0 — КРИТИЧЕСКИЕ (блокируют релиз)

### Секреты

- [ ] **Сменить production-секреты** `[INFRA-1]`
  - `.env.prod`: `ADMIN_PASSWORD=admin123`, реальный `SECRET_KEY`, `POSTGRES_PASSWORD`
  - Сменить все три значения на сервере

### XSS в OrcaSlicer C++

- [ ] **XSS: инъекция токена в JS без экранирования** `[SEC-1]`
  - `FilamentHubPanel.cpp:655-673` — `wxString::Format('%s')`
  - Решение: `JSON.parse()` вместо строковой подстановки

- [ ] **XSS: unsafe конкатенация JSON в JS** `[SEC-2]`
  - `FilamentHubPanel.cpp:1710-1715, 1748-1751`

- [ ] **XSS: navigate_without_reload без экранирования** `[SEC-3]`
  - `FilamentHubPanel.cpp:3444-3462`
  - Решение: валидировать path — только `/[a-zA-Z0-9/_-]+/`

### Пресеты не попадают в "FilamentHub presets"

- [ ] **`fhub_source` не парсится Config.cpp** `[EXPORT-1]`
  - `Config.cpp:905` — `load_from_json()` не кладёт `fhub_source` в `key_values`
  - Добавить обработку `fhub_source`/`fhub_id` перед `else` веткой

### Закрытые P0

- [x] ~~Заменить `python-jose` на `PyJWT`~~ `[CVE-1, INFRA-13]`
- [x] ~~Обновить `python-multipart` ≥ 0.0.22~~ `[CVE-2]`
- [x] ~~Обновить `bcrypt` ≥ 5.0.0~~ `[CVE-3]`
- [x] ~~Fallback `"fdm_filament_common"` → импорт отклоняется~~ `[EXPORT-2]`
- [x] ~~Нет проверки прав по fhub_id из .info~~ `[SYNC-1]`
- [x] ~~SQL LIKE injection~~ `[SYNC-3]`
- [x] ~~Капча — reCAPTCHA v3~~ `[SEC-7]`
- [x] ~~Path Traversal в file_service.py~~ `[SEC-8]`
- [x] ~~DoS через большие файлы~~ `[BACKEND-9]`
- [x] ~~Обновить vite ≥ 7.1.11~~ `[CVE-4]`
- [x] ~~Обновить axios ≥ 1.13.5~~ `[CVE-5]`
- [x] ~~Обновить react ≥ 19.2.3~~ `[CVE-6]`

---

## P1 — ВЫСОКИЙ ПРИОРИТЕТ (до релиза)

### Race conditions в C++

- [ ] **`m_is_syncing` — plain bool, не atomic** `[RACE-1]`
- [ ] **`m_pending_actions_count` без atomic** `[RACE-2]`
- [ ] **`m_is_logged_in` без защиты** `[RACE-3]`
- [ ] **`m_presets_data` — shared vector без мьютекса** `[RACE-4]`

### Стабильность C++

- [ ] **Blocking wait 30 сек в UI потоке** `[CRASH-1]`
  - `FilamentHubPanel.cpp:2200-2223` — `cv.wait_for(lock, 30s)`

- [ ] **Null pointer в dynamic_cast** `[CRASH-2]`
  - `FilamentHubPanel.cpp:85-90`

- [ ] **WebView может быть null** `[CRASH-3]`
  - `FilamentHubPanel.cpp:366, 3464`

### OrcaSlicer баги

- [ ] **403 для printer/print profiles** — настройки `allow_*_import` = false по умолчанию
- [ ] **get_my_presets возвращает пустой массив** — после экспорта должны появиться

### Закрытые P1

- [x] ~~commit внутри цикла~~ `[SYNC-2]`
- [x] ~~Race condition при создании принтера/бренда~~ `[SYNC-6]`
- [x] ~~Enum `preset_locally_deleted` не в PostgreSQL~~ `[ALEMBIC-6]`
- [x] ~~env.py — только 6 из 24 моделей~~ `[ALEMBIC-3]`
- [x] ~~Два несовместимых генератора .info~~ `[EXPORT-3]`
- [x] ~~`filament_cost` занижена в 10 раз~~ `[EXPORT-4]`
- [x] ~~Двойной prefix `/orcaslicer/orcaslicer/`~~ `[SYNC-4]`
- [x] ~~OR вместо AND в поиске~~ `[SYNC-9]`
- [x] ~~Дублирование endpoints~~ `[CONTRACT-1,2,3]`
- [x] ~~~140 строк дублированного обновления~~ `[SYNC-5]`
- [x] ~~CORS без production домена~~ `[INFRA-2]`
- [x] ~~Stack trace в API-ответах~~ `[SYNC-8]`
- [x] ~~except Exception: pass~~ `[BACKEND-1]`
- [x] ~~undefined base_upload_dir~~ `[BACKEND-10]`
- [x] ~~Uploads без авторизации~~ `[INFRA-8]`
- [x] ~~Экспорт пресетов без auth~~ `[EXPORT-7]`
- [x] ~~react-router-dom ≥ 7.9.6~~ `[CVE-7]`
- [x] ~~uvicorn ≥ 0.40.0~~ `[CVE-8]`
- [x] ~~mermaid → latest~~ `[CVE-9]`
- [x] ~~Загрузка ВСЕХ филаментов в память~~ `[SYNC-7]`
- [x] ~~flow_ratio эвристика~~ `[EXPORT-5]`

---

## P2 — СРЕДНИЙ ПРИОРИТЕТ

### Инфраструктура

- [ ] CI/CD пайплайн `.github/workflows/ci.yml` `[INFRA-5]`
- [ ] Rate limiter → Redis backend `[INFRA-6]`
- [ ] Redis с паролем `[INFRA-11]`
- [ ] Токены в localStorage → httpOnly cookies `[INFRA-7]`
- [ ] Тестовый фреймворк для фронтенда (vitest) `[INFRA-3]`
- [ ] Тесты: Admin API, Sync, Reviews, QR, auth flows `[INFRA-4]`

### Alembic

- [ ] `drop_constraint(None)` — невозможный downgrade `[ALEMBIC-4]`
- [ ] Потеря данных при downgrade e01bc3b29297 `[ALEMBIC-5]`

### Валидация

- [ ] Валидация не блокирует экспорт → HTTP 422 `[EXPORT-6]`
- [ ] Усилить валидацию пароля (цифры + буквы + спецсимволы)

### UX

- [ ] WikiPage — поиск не показывает результаты `[UX-2]`
- [ ] BrandDetailPage — рейтинг-заглушка `[UX-3]`
- [ ] ViewPresetModal — нет полей экструдеров `[UX-4]`
- [ ] Issue 2: белый экран при Ctrl+Shift+R → loading screen

### Email

- [ ] **Email-сервис (SMTP)** `[EMAIL-1]`
  - Верификация email, сброс пароля, уведомления
  - Сейчас токены логируются в `debug` — убрать после реализации
  - SMTP config в `.env`, шаблоны писем, очередь отправки

### Закрытые P2

- [x] ~~N+1 запросы для deleted presets~~ `[SYNC-10]`
- [x] ~~SELECT DISTINCT на каждый вызов~~ `[SYNC-11]`
- [x] ~~`if not value` ложно для 0.0~~ `[SYNC-12]`
- [x] ~~Двойной commit~~ `[SYNC-15]`
- [x] ~~Границы слов в matcher'е~~ `[SYNC-17]`
- [x] ~~AttributeError при filament=None~~ `[SYNC-18]`
- [x] ~~Lazy loading → MissingGreenlet~~ `[SYNC-19]`
- [x] ~~commit после ошибки без rollback~~ `[SYNC-20]`
- [x] ~~Race condition в QR-коде~~ `[BACKEND-5]`
- [x] ~~innerHTML / dangerouslySetInnerHTML~~ `[SEC-4..6]`
- [x] ~~account_deletion deactivate бесполезен~~ `[BACKEND-8]`
- [x] ~~49 мест с alert()/confirm()~~ `[UX-1]`
- [x] ~~Notifications.tsx — postMessage без проверки~~ `[UX-5]`
- [x] ~~TableOfContents — stale closure~~ `[UX-6]`
- [x] ~~N+1 запросы при загрузке пресетов~~ `[PERF-1]`
- [x] ~~Логирование конфиденциальных данных~~ `[CODE-7]`
- [x] ~~Неконсистентный язык ошибок~~ `[BACKEND-7]`
- [x] ~~Дублирование формулы в calculator.py~~ `[BACKEND-12]`
- [x] ~~Заполнители в юридических документах~~ `[LEGAL-1]`
- [x] ~~Nginx client_max_body_size~~ `[INFRA-9]`
- [x] ~~Content-Security-Policy~~ `[INFRA-10]`
- [x] ~~JWT double-decode~~ `[INFRA-12]`
- [x] ~~Hardcoded fallback пароль~~ `[INFRA-14]`
- [x] ~~run.py — reload=True в production~~ `[BACKEND-4]`
- [x] ~~can_edit_wiki в БД, но не в модели~~ `[ALEMBIC-8]`

---

## P3 — НИЗКИЙ ПРИОРИТЕТ

### Заглушки

- [ ] `get_all_mapped_preset_ids()` — всегда пустой вектор `[STUB-1]`
- [ ] Google OAuth кнопка — заглушка `[STUB-2]`
- [ ] История печати — `userHistory = []` `[STUB-3]`
- [ ] Spoolman интеграция — `status="TODO"` `[BACKEND-6]`

### Код backend

- [ ] Двойная docstring, проглоченные exceptions, дубли импортов `[SYNC-21..25]`
- [ ] Пустая миграция 5752bb11b46d `[ALEMBIC-9]`
- [ ] Orphan таблица bad_words `[ALEMBIC-10]`
- [ ] Нестандартные revision ID `[ALEMBIC-11]`
- [ ] Admin endpoints не используются из frontend `[CONTRACT-5]`
- [ ] 8 пустых классов в schemas `[CODE-6]`

### Код C++

- [ ] Огромные callback лямбды (438 строк) `[CODE-1]`
- [ ] 136 вызовов CallAfter без контроля `[CODE-2]`
- [ ] Temp-файлы не удаляются при исключениях `[CODE-3]`
- [ ] JSON parsing без проверки ключей `[CODE-4]`
- [ ] `_ensure_printer_id()` — 278 строк `[CODE-5]`
- [ ] Мёртвый код `m_notifications_button/badge` `[LOW-2]`
- [ ] Хардкод таймаутов `[LOW-3]`
- [ ] Хардкод API endpoints `[LOW-4]`
- [ ] Хардкод постфикса `[FilamentHub]` `[LOW-5]`
- [ ] `sync_call_counter` переполнение `[LOW-6]`
- [ ] 200+ BOOST_LOG_TRIVIAL на info `[LOW-7]`
- [ ] Unused variable `e` `[LOW-8]`
- [ ] Include guards `__` зарезервированы `[LOW-9]`
- [ ] Переменные не в member initializer list `[LOW-10]`

### Код frontend

- [ ] TypeScript `noUnusedLocals: false` `[INFRA-19]`
- [ ] 60+ использований `any` `[TS-1]`
- [ ] Unsafe `as any` casts `[TS-2]`
- [ ] `qrcode.react` — inactive `[CVE-11]`
- [x] ~~`passlib` 1.7.4 — не поддерживается~~ `[CVE-12]` → заменён на прямой bcrypt 5.x
- [ ] `react-syntax-highlighter` ≥ 16.1.0 `[CVE-10]`
- [ ] Admin role check только на frontend `[FRONTEND-1]`

### Закрытые P3

- [x] ~~32 console.log в production~~ `[LOW-1]`
- [x] ~~OpenAPI docs в production~~ `[INFRA-15]`
- [x] ~~Frontend Dockerfile без health check~~ `[INFRA-16]`
- [x] ~~Dev Dockerfile: COPY до pip install~~ `[INFRA-17]`
- [x] ~~CORS allow_methods/headers = ["*"]~~ `[INFRA-18]`
- [x] ~~requirements.txt — артефакт~~ `[INFRA-20]`

---

## Фичи — Backend / Frontend

### Ближайшие (MVP)

- [ ] **"Галочка на пресете" → sync в OrcaSlicer** (~200-300 строк)
  - `get_my_presets` должен отдавать сохранённые чужие с `sync_enabled=true`
  - Frontend: кнопка "Добавить в OrcaSlicer"
  - Источник: `docs/PENDING_TASKS.md`

- [ ] **Рекомендованные пресеты для принтера** (plan.md)
  - `preset_matcher.py` — сервис скоринга
  - `GET /api/v1/presets/recommended-for-printer`
  - Секция "Рекомендовано для {Printer}" в каталоге

- [ ] **Двусторонняя синхронизация OrcaSlicer → FilamentHub**
  - `POST /api/v1/orcaslicer/filaments/import`
  - C++ экспорт всех 3 типов профилей
  - Кнопка "Экспортировать в FilamentHub"
  - Подробно: `docs/md/ORCASLICER_BIDIRECTIONAL_SYNC_IMPLEMENTATION.md`

### Фичи (post-MVP)

- [ ] Переименовать "История" → "Активность"
- [ ] Топ-10 популярных на главной (закомментировано в CatalogPage)
- [ ] Расширить CreatePrintProfileModal (скорости, заполнение)
- [ ] Retry logic в FilamentHubClient
- [ ] "Мои принтеры" — generic вместо конкретных моделей `[TODO-12]`
- [ ] Комбинации профилей (принтер + филамент + process) `[TODO-13]`
- [ ] Smart Matching & Filtering System `[TODO-14]`
- [ ] Dark/Light режимы
- [ ] Мобильная адаптация (responsive)
- [ ] PWA поддержка
- [ ] SEO оптимизация

### UI-система компонентов (рефакторинг)

- [ ] Создать библиотеку базовых UI компонентов (`components/ui/`)
  - Modal, Dropdown, Button, Card, Input, Badge, Toast
- [ ] Система дизайн-токенов (`styles/tokens.ts`)
- [ ] Рефакторинг существующих компонентов
- [ ] Документация (Storybook)

---

## OrcaSlicer — профили и бандлы

> Подробно: [`docs/OrcaSlicer/TODO.md`](docs/OrcaSlicer/TODO.md)

### Filament Profiles ✅
- [x] Backend экспорт в JSON
- [x] C++ импорт + синхронизация
- [x] UI секция "FilamentHub presets"
- [ ] Тесты экспорта

### Print/Process Profiles ✅ Backend / 🔲 C++ sync
- [x] Backend API + модели + экспорт + валидация
- [ ] C++ sync print profiles в FilamentHubPanel.cpp
- [ ] C++ API метод в FilamentHubClient.cpp

### Printer/Machine Profiles ✅ Backend / 🔲 C++ проверить
- [x] Backend API + экспорт + валидация
- [ ] C++ sync проверить
- [ ] C++ API метод проверить

### Bundles (Фаза 4) 🔲
- [ ] Backend: модель Bundle, API, экспорт ZIP
- [ ] Frontend: каталог бандлов, визард создания
- [ ] C++ : import bundle, UI

---

## Вендор-бандлы (стратегическая задача)

> Подробно: [`docs/PENDING_TASKS.md`](docs/PENDING_TASKS.md) → раздел "Анализ системы вендор-бандлов"
> Гайд: `docs/VENDOR_BUNDLE_SYSTEM_GUIDE.md`

### Фаза 0: "Галочка на пресете" (~200-300 строк) ← БЛИЖАЙШАЯ
- [ ] `get_my_presets` → + сохранённые чужие с `sync_enabled=true`
- [ ] Frontend: кнопка "Добавить в OrcaSlicer" в каталоге

### Фаза A: Клиентская часть (~1300 строк)
- [ ] Каталог бандлов в WebView
- [ ] C++ скачивание + распаковка ZIP
- [ ] `load_vendor_configs_from_json()` → профили в UI
- [ ] `installed.json` — трекинг установленных
- [ ] Backend: API `GET /profiles/bundle/{slug}.zip`

### Фаза B: Серверная часть (~1850 строк)
- [ ] Модель `CommunityVendor` + CRUD API
- [ ] ZIP-импорт, валидатор профилей, модерация

### Фаза C: Веб-редактор (~1250 строк)
- [ ] Визард: принтер → варианты → филаменты → печать → предпросмотр

---

## Публичный запуск (Фаза 4)

### Бета-тестирование
- [ ] Пригласить 20-30 бета-тестеров
- [ ] Собрать обратную связь
- [ ] Исправить критические баги

### Документация
- [ ] Руководство пользователя
- [ ] Руководство для производителей
- [ ] Инструкция по установке плагина
- [ ] FAQ

### Инфраструктура запуска
- [ ] Production сервер (VPS)
- [ ] Домен + SSL
- [ ] Мониторинг (Grafana, Prometheus)
- [ ] Логирование (Sentry)
- [ ] Бэкапы БД
- [ ] CI/CD (GitHub Actions)
- [ ] Сборка бинарников OrcaSlicer для Windows

### Маркетинг
- [ ] Соцсети (VK, Telegram)
- [ ] Пост на Habr
- [ ] Связь с @SoftFever

---

## Post-MVP фазы

### Фаза 5: Spoolman Integration
- [ ] Импорт/экспорт катушек
- [ ] Двусторонняя синхронизация остатков
- [ ] Свой Inventory Tracker (вариант Б)

### Фаза 6: G-code калькулятор
- [ ] Портировать парсеры из PHP (6 слайсеров)
- [ ] Полный Cost Calculator с парсингом
- [ ] Региональные тарифы

### Фаза 7: Сообщество
- [ ] Рейтинги и отзывы на пресеты
- [ ] Профили с достижениями
- [ ] Система reputation (karma)
- [ ] Аналитика для производителей (платная)

### Фаза 8: Расширение
- [ ] QR-код → Deep link → авто-импорт в OrcaSlicer
- [ ] Маркетплейс (ссылки на Ozon/WB)
- [ ] Плагины для SuperSlicer, Bambu Studio, PrusaSlicer
- [ ] AI-ассистент для подбора настроек

---

## i18n — состояние

### Frontend (react-i18next) — ОСТАВИТЬ
- Файлы: `frontend/src/i18n.ts`, `frontend/src/locales/`
- Статус: используется, работает

### Backend (fastapi-i18n) — УДАЛИТЬ
- Файлы: `backend/app/core/i18n.py`, `backend/app/locales/`
- Статус: мёртвый код, добавлен Gemini, не используется нигде
- Действие: удалить файлы (с разрешения владельца)

---

*Источники: Claude Opus аудит (7 фаз), Gemini CVE-анализ, tracing потока экспорта/импорта, docs/PENDING_TASKS.md аудит (10 фев 2026)*
