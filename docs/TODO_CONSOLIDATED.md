# TODO — FilamentHub (Консолидированный)

> **Дата:** 22 февраля 2026 (аудит кодовой базы)
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

## P2 — СРЕДНИЙ ПРИОРИТЕТ

### UX и баги

- [x] ~~Создание филамента: ошибка прав при создании для нового бренда~~ — неверифицированные бренды теперь доступны любому авторизованному юзеру
- [ ] **Перевод ошибок:** Сообщения об ошибках, такие как "Not enough permissions..." и "Brand with this slug already exists", должны быть переведены на язык пользователя.

---

## Общий статус проекта

```
Backend API          [███████████████████░]  95%
Frontend Web UI      [██████████████████░░]  85%
OrcaSlicer C++       [██████████████████░░]  87%
Безопасность         [████████████████████]  98%  ← P0 закрыты (SEC-1/2/3 + EXPORT-1)
Вендор-бандлы        [░░░░░░░░░░░░░░░░░░░░]   0%
Публичный запуск     [░░░░░░░░░░░░░░░░░░░░]   0%
```

---

## P0 — КРИТИЧЕСКИЕ (блокируют релиз)

### Секреты

- [x] **Сменить production-секреты** `[INFRA-1]` — выполняется вручную владельцем

### XSS в OrcaSlicer C++

- [x] ~~XSS: инъекция токена в JS без экранирования~~ `[SEC-1]` — заменено на `JSON.parse()` + `nlohmann::json`
- [x] ~~XSS: unsafe конкатенация JSON в JS~~ `[SEC-2]` — обёрнуто в `JSON.parse()` (response + notification)
- [x] ~~XSS: navigate_without_reload без экранирования~~ `[SEC-3]` — добавлена regex валидация path + `JSON.parse()`

### Пресеты не попадают в "FilamentHub presets"

- [x] ~~`fhub_source` не парсится Config.cpp~~ `[EXPORT-1]` — добавлен парсинг `fhub_source`/`fhub_id` в `key_values`

### Закрытые P0

- [x] ~~XSS: инъекция токена~~ `[SEC-1]` — `JSON.parse()` вместо `'%s'`
- [x] ~~XSS: unsafe конкатенация JSON~~ `[SEC-2]` — `JSON.parse()` для response/notification
- [x] ~~XSS: navigate path injection~~ `[SEC-3]` — regex валидация + `JSON.parse()`
- [x] ~~fhub_source не парсится~~ `[EXPORT-1]` — добавлен в `key_values` в `Config.cpp`
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

- [x] ~~`m_is_syncing` — plain bool, не atomic~~ `[RACE-1]` — теперь `std::atomic<bool>`
- [x] ~~`m_pending_actions_count` без atomic~~ `[RACE-2]` — переименован в `m_active_syncs`, уже `std::atomic<int>`
- [x] ~~`m_is_logged_in` без защиты~~ `[RACE-3]` — переменная не существует; login state через AppConfig/токен
- [x] ~~`m_presets_data` — shared vector без мьютекса~~ `[RACE-4]` — переименован в `m_preset_import_queue` + `m_preset_queue_mutex`

### Стабильность C++

- [x] ~~Blocking wait 30 сек в UI потоке~~ `[CRASH-1]` — таймаут снижен до 10s, добавлен комментарий о вызове из background thread
- [x] ~~Null pointer в dynamic_cast~~ `[CRASH-2]` — добавлена проверка результата `dynamic_cast` перед разыменованием
- [x] ~~WebView может быть null~~ `[CRASH-3]` — добавлены null-check в `Show()` и `OnLoaded()`

### OrcaSlicer баги

### Закрытые P1

- [x] ~~m_is_syncing plain bool~~ `[RACE-1]` — переведён на `std::atomic<bool>`
- [x] ~~m_pending_actions_count без atomic~~ `[RACE-2]` — `m_active_syncs` уже `std::atomic<int>`
- [x] ~~m_is_logged_in без защиты~~ `[RACE-3]` — переменная удалена
- [x] ~~m_presets_data без мьютекса~~ `[RACE-4]` — `m_preset_import_queue` + `m_preset_queue_mutex`
- [x] ~~get_my_presets пустой массив~~ — endpoint уже возвращает сохранённые пресеты с `sync=True`
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

- [ ] Токены в localStorage → httpOnly cookies `[INFRA-7]`
- [ ] Тестовый фреймворк для фронтенда (vitest) `[INFRA-3]`
- [ ] Тесты: Admin API, Sync, Reviews, QR, auth flows `[INFRA-4]`

### Alembic

- [x] ~~`drop_constraint(None)` — невозможный downgrade~~ `[ALEMBIC-4]` — заменено на raw SQL с динамическим поиском FK
- [x] ~~Потеря данных при downgrade e01bc3b29297~~ `[ALEMBIC-5]` — тихий DELETE заменён на RuntimeError с подсчётом черновиков

### Валидация

- [x] ~~Валидация не блокирует экспорт → HTTP 422~~ `[EXPORT-6]` — добавлена проверка обязательных полей перед генерацией json/info
- [x] ~~Усилить валидацию пароля (цифры + буквы + спецсимволы)~~

### UX

- [x] Wiki вкладка в админ-панели: CRUD статей/категорий, синхронизация, экспорт в .md `[UX-6]`
- [x] ~~WikiPage — поиск не показывает результаты~~ `[UX-2]`
- [x] ~~BrandDetailPage — рейтинг-заглушка~~ `[UX-3]`
- [x] ~~ViewPresetModal — нет полей экструдеров~~ `[UX-4]` (уже реализовано)

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

- [x] ~~Двойная docstring, проглоченные exceptions, дубли импортов~~ `[SYNC-21..25]`
- [ ] Пустая миграция 5752bb11b46d `[ALEMBIC-9]`
- [ ] Orphan таблица bad_words `[ALEMBIC-10]`
- [ ] Нестандартные revision ID `[ALEMBIC-11]`
- [x] ~~Admin endpoints не используются из frontend~~ `[CONTRACT-5]` — все admin endpoints реализованы в   
    adminAPI (client.ts)
- [ ] 4 пустых класса в schemas `[CODE-6]` (`FilamentCategoryBase`, `PrintProfileBase`, `PrinterProfileBase`, `ProcessProfileBase`)

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
- [ ] 116+ использований `any` `[TS-1]`
- [ ] Unsafe `as any` casts `[TS-2]`
- [ ] `qrcode.react` — inactive `[CVE-11]`
- [x] ~~`passlib` 1.7.4 — не поддерживается~~ `[CVE-12]` → заменён на прямой bcrypt 5.x
- [ ] `react-syntax-highlighter` ≥ 16.1.0 `[CVE-10]`
- [x] ~~Admin role check только на frontend~~ `[FRONTEND-1]` — все admin endpoints используют              
    `Depends(get_current_admin_user)`

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

- [x] ~~Сохранённые чужие пресеты не попадают в OrcaSlicer~~ — **реализовано**
  - `GET /auth/my-presets` возвращает все пресеты с `sync=True` из `user_saved_presets` (свои + чужие)
  - Toggle sync: `PresetSyncToggle.tsx` + `PATCH /saved-presets/{id}/sync`
  - При создании пресета автоматически создаётся запись в `user_saved_presets`

- [ ] **Рекомендованные пресеты для принтера** (plan.md) — *частично реализовано*
  - [x] `preset_recommender.py` — сервис скоринга (существует)
  - [x] `GET /api/v1/presets/recommended-for-printer` — endpoint (существует)
  - [ ] Секция "Рекомендовано для {Printer}" в каталоге (UI не готов)
  - [ ] Тестирование и доработка алгоритма скоринга

- [ ] **Двусторонняя синхронизация OrcaSlicer → FilamentHub** — *частично реализовано*
  - [x] `POST /api/v1/orcaslicer/filaments/import` — endpoint импорта (существует)
  - [ ] C++ экспорт всех 3 типов профилей
  - [ ] Кнопка "Экспортировать в FilamentHub" в OrcaSlicer UI
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

### Print Profiles (зависит от Filament Profiles)

- [ ] Backend: CRUD, export
- [ ] C++: import, sync
- [ ] UI: ...

### Printer Profiles (зависит от Filament Profiles)

- [ ] Backend: ...
- [ ] C++: ...
- [ ] UI: ...

### Vendor Bundles

- [ ] `POST /api/v1/orcaslicer/vendor-bundles`
- [ ] UI для загрузки бандлов
