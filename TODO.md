# TODO — FilamentHub

> Консолидация всех открытых задач.
> Подробный аудит (описания, файлы, строки): [`docs/PENDING_TASKS.md`](docs/PENDING_TASKS.md)
> Общий план проекта и прогресс MVP: [`TODO_Main.md`](TODO_Main.md)

---

## P0 — КРИТИЧЕСКИЕ

### Секреты и аутентификация

- [ ] **Сменить production-секреты** `[INFRA-1]`
  - `backend/.env.prod`: `ADMIN_PASSWORD=admin123`, реальный `SECRET_KEY`, `POSTGRES_PASSWORD`
  - Сменить все три значения на сервере

- [x] ~~**Заменить `python-jose` на `PyJWT`**~~ `[CVE-1, INFRA-13]`
- [x] ~~**Обновить `python-multipart` ≥ 0.0.22**~~ `[CVE-2]`
- [x] ~~**Обновить `bcrypt` ≥ 5.0.0**~~ `[CVE-3]`

### XSS в OrcaSlicer C++

- [ ] **XSS: инъекция токена в JS без экранирования** `[SEC-1]`
  - `FilamentHubPanel.cpp:655-673` — `wxString::Format('%s')`
  - Решение: `JSON.parse()` вместо строковой подстановки

- [ ] **XSS: unsafe конкатенация JSON в JS** `[SEC-2]`
  - `FilamentHubPanel.cpp:1710-1715, 1748-1751`

- [ ] **XSS: navigate_without_reload без экранирования** `[SEC-3]`
  - `FilamentHubPanel.cpp:3444-3462` — path в `wxString::Format("navigate('%s')")`
  - Решение: валидировать path — только `/[a-zA-Z0-9/_-]+/`

### Пресеты НЕ попадают в секцию "FilamentHub presets"

- [ ] **`fhub_source` не парсится Config.cpp** `[EXPORT-1]`
  - `Config.cpp:905` — `load_from_json()` не кладёт `fhub_source` в `key_values`
  - Добавить обработку `fhub_source`/`fhub_id` перед `else` веткой

- [x] ~~**Fallback `"fdm_filament_common"` → импорт молча отклоняется**~~ `[EXPORT-2]`

### Перезапись чужих данных

- [x] ~~**Нет проверки прав по fhub_id из .info**~~ `[SYNC-1]`
- [x] ~~**SQL LIKE injection — неэкранированные `%` и `_`**~~ `[SYNC-3]`

### Другие уязвимости

- [x] ~~**Капча — визуальная заглушка без защиты**~~ `[SEC-7]`
  - Заменена на reCAPTCHA v3 с серверной верификацией через Google API
  - Backend: `utils.py:verify_recaptcha()`, проверка в `/auth/register`
  - Frontend: невидимый виджет `Recaptcha` в `Captcha.tsx`

- [x] ~~**Path Traversal в file_service.py**~~ `[SEC-8]`
- [x] ~~**DoS через большие файлы**~~ `[BACKEND-9]`

### CVE фронтенда

- [x] ~~**Обновить `vite` ≥ 7.1.11**~~ `[CVE-4]`
- [x] ~~**Обновить `axios` ≥ 1.13.5**~~ `[CVE-5]`
- [x] ~~**Обновить `react` ≥ 19.2.3**~~ `[CVE-6]`

---

## P1 — ВЫСОКИЙ ПРИОРИТЕТ (до релиза)

### Данные и атомарность

- [x] ~~**commit внутри цикла нарушает атомарность**~~ `[SYNC-2]`
- [x] ~~**Race condition при создании принтера/бренда**~~ `[SYNC-6]`
- [x] ~~**Enum `preset_locally_deleted` не в PostgreSQL**~~ `[ALEMBIC-6]`
- [x] ~~**env.py — только 6 из 24 моделей**~~ `[ALEMBIC-3]`

### Экспорт пресетов

- [x] ~~**Два несовместимых генератора .info**~~ `[EXPORT-3]`
- [x] ~~**`filament_cost` — цена занижена в 10 раз**~~ `[EXPORT-4]`
- [x] ~~**Двойной prefix `/orcaslicer/orcaslicer/`**~~ `[SYNC-4]`
- [x] ~~**OR вместо AND в поиске manufacturer+model**~~ `[SYNC-9]`

### Дубликаты

- [x] ~~**Дублирование endpoints в printer_requests.py**~~ `[CONTRACT-1,2]`
- [x] ~~**Дублирование кода в brands.py**~~ `[CONTRACT-3]`
- [x] ~~**~140 строк дублированного обновления пресета**~~ `[SYNC-5]`

### Безопасность инфраструктуры

- [x] ~~**CORS без production домена**~~ `[INFRA-2]`
- [x] ~~**Stack trace в API-ответах**~~ `[SYNC-8]`
- [x] ~~**except Exception: pass — проглоченные ошибки**~~ `[BACKEND-1]`
- [x] ~~**undefined base_upload_dir в cleanup**~~ `[BACKEND-10]`

- [x] ~~**Uploads без авторизации**~~ `[INFRA-8]`
  - Убран StaticFiles mount, добавлен endpoint с Bearer/query token auth

- [x] ~~**Экспорт пресетов без auth**~~ `[EXPORT-7]`
  - Добавлен `get_current_active_user` в export .json и .info

### CVE

- [x] ~~**`react-router-dom` ≥ 7.9.6**~~ `[CVE-7]`
- [x] ~~**`uvicorn` ≥ 0.40.0**~~ `[CVE-8]`
- [x] ~~**`mermaid` → latest**~~ `[CVE-9]` — уже на ^11.12.2 (latest)

### Race conditions C++

- [ ] **`m_is_syncing` — plain bool, не atomic** `[RACE-1]`
- [ ] **`m_pending_actions_count` без atomic** `[RACE-2]`
- [ ] **`m_is_logged_in` без защиты** `[RACE-3]`
- [ ] **`m_presets_data` — shared vector без мьютекса** `[RACE-4]`

### Производительность

- [x] ~~**Загрузка ВСЕХ филаментов в память**~~ `[SYNC-7]`
  - Заменено на точечный SQL-запрос с `LOWER(TRIM(...))` вместо загрузки всей таблицы

### Экспорт

- [x] ~~**flow_ratio: эвристика ломает значения 1.0–2.0**~~ `[EXPORT-5]`
  - БД хранит проценты (50–150), OrcaSlicer — множитель (0.5–1.5). Убрана эвристика, всегда `*100` / `/100`

### Стабильность C++

- [ ] **Blocking wait 30 сек в UI потоке** `[CRASH-1]`
  - `FilamentHubPanel.cpp:2200-2223` — `cv.wait_for(lock, 30s)` при удалении пресета

- [ ] **Null pointer в dynamic_cast** `[CRASH-2]`
  - `FilamentHubPanel.cpp:85-90` — `dynamic_cast<ConfigOptionString*>(opt)->value` без проверки

- [ ] **WebView может быть null** `[CRASH-3]`
  - `FilamentHubPanel.cpp:366, 3464` — `LoadUrl`/`RunScript` без проверки `m_browser`

---

## P2 — СРЕДНИЙ ПРИОРИТЕТ

### Инфраструктура

- [ ] CI/CD пайплайн `.github/workflows/ci.yml` `[INFRA-5]`
- [ ] Rate limiter → Redis backend `[INFRA-6]`
- [x] ~~Nginx `client_max_body_size 50m`~~ `[INFRA-9]`
- [x] ~~Content-Security-Policy~~ `[INFRA-10]`
- [ ] Redis с паролем `[INFRA-11]`
- [x] ~~Убрать диагностический JWT double-decode~~ `[INFRA-12]`
- [x] ~~Убрать hardcoded fallback пароль в docker-compose~~ `[INFRA-14]`
- [x] ~~`run.py` — `reload=True` в production~~ `[BACKEND-4]`

### Тесты

- [ ] Тестовый фреймворк для фронтенда (vitest) `[INFRA-3]`
- [ ] Тесты: Admin API, Sync, Reviews, QR, auth flows `[INFRA-4]`

### Alembic

- [ ] `drop_constraint(None)` — невозможный downgrade `[ALEMBIC-4]`
- [ ] Потеря данных при downgrade e01bc3b29297 `[ALEMBIC-5]`
- [x] ~~`can_edit_wiki` в БД, но не в модели~~ `[ALEMBIC-8]` — добавлено в User model

### Sync orchestrator

- [x] ~~N+1 запросы для deleted presets~~ `[SYNC-10]` — batch DELETE с `.in_()`
- [x] ~~SELECT DISTINCT manufacturer на каждый вызов~~ `[SYNC-11]` — кэш на уровне batch
- [x] ~~`if not value` ложно для 0.0 → `is None`~~ `[SYNC-12]`
- [x] ~~Лимит на батч printer/print profiles~~ `[SYNC-13]` — max_length=50 на все SyncRequest
- [x] ~~Фильтр active при поиске пресетов~~ `[SYNC-14]` — не баг, осознанно ищем все (включая неактивные) чтобы избежать дублей
- [x] ~~Двойной commit в handle_deleted_preset_action~~ `[SYNC-15]`
- [x] ~~Границы слов в matcher'е материалов~~ `[SYNC-17]` — проверено: `\b` + `[^A-Z]` корректно разделяют
- [x] ~~AttributeError при filament=None~~ `[SYNC-18]`
- [x] ~~Lazy loading → MissingGreenlet~~ `[SYNC-19]` — selectinload(Filament.brand)
- [x] ~~commit после ошибки без rollback~~ `[SYNC-20]`

### Валидация

- [ ] Валидация не блокирует экспорт → HTTP 422 `[EXPORT-6]`
- [x] ~~Race condition в QR-коде при создании филамента~~ `[BACKEND-5]` — обработка IntegrityError

### Безопасность

- [ ] Токены в localStorage → httpOnly cookies `[INFRA-7]`
- [x] ~~innerHTML / dangerouslySetInnerHTML без санитизации~~ `[SEC-4..6]` — заменено на createElement/textContent
- [x] ~~`account_deletion.py` — deactivate перед delete бесполезен~~ `[BACKEND-8]`

### UX

- [x] ~~49 мест с `alert()`/`confirm()` вместо toast~~ `[UX-1]`
- [ ] WikiPage — поиск не показывает результаты `[UX-2]`
- [ ] BrandDetailPage — рейтинг-заглушка `[UX-3]`
- [ ] ViewPresetModal — нет полей экструдеров `[UX-4]`
- [x] ~~Notifications.tsx — postMessage без проверки OrcaSlicer~~ `[UX-5]` — добавлена проверка event.origin
- [x] ~~TableOfContents — stale closure в useEffect~~ `[UX-6]`

### Качество кода

- [x] ~~N+1 запросы при загрузке пресетов~~ `[PERF-1]` — проверено: selectinload используется везде
- [x] ~~Логирование конфиденциальных данных (JWT exp, API URLs)~~ `[CODE-7]` — токены понижены до debug
- [x] ~~Неконсистентный язык ошибок (рус/англ)~~ `[BACKEND-7]`
- [x] ~~Дублирование формулы в calculator.py~~ `[BACKEND-12]` — вынесено вычисление, убраны дубли

### Юридическое

- [x] ~~Заполнители в юридических документах~~ `[LEGAL-1]`
  - Заменены `[адрес электронной почты]` → `support@filamenthub.ru`
  - Добавлен раздел 8 «Синхронизация и передача настроек печати» в Пользовательское соглашение
  - В Согласие на обработку ПД добавлены настройки печати как обрабатываемые данные
  - `[адрес ИП Кузьмин И.И.]` — оставлен для заполнения вручную

---

## P3 — НИЗКИЙ ПРИОРИТЕТ

### Заглушки

- [ ] `get_all_mapped_preset_ids()` — всегда пустой вектор `[STUB-1]`
- [ ] Google OAuth кнопка — заглушка `[STUB-2]`
- [ ] История печати — `userHistory = []` `[STUB-3]`
- [ ] Spoolman интеграция — `status="TODO"` `[BACKEND-6]`
- [ ] Email-сервис (SMTP) — верификация email, сброс пароля, уведомления `[EMAIL-1]`
  - Сейчас токены логируются в `debug` — убрать после реализации
  - SMTP config в `.env`, шаблоны писем, очередь отправки

### Код backend

- [ ] Двойная docstring, проглоченные exceptions, дубли импортов `[SYNC-21..25]`
- [ ] Пустая миграция 5752bb11b46d `[ALEMBIC-9]`
- [ ] Orphan таблица bad_words `[ALEMBIC-10]`
- [ ] Нестандартные revision ID `[ALEMBIC-11]`
- [x] ~~OpenAPI docs в production~~ `[INFRA-15]`
- [x] ~~Frontend Dockerfile без health check~~ `[INFRA-16]`
- [x] ~~Dev Dockerfile: COPY до pip install~~ `[INFRA-17]`
- [x] ~~CORS allow_methods/headers = ["*"]~~ `[INFRA-18]` — ограничено до конкретных методов и заголовков
- [x] ~~requirements.txt — артефакт~~ `[INFRA-20]` — удалён
- [ ] Admin endpoints не используются из frontend `[CONTRACT-5]`
- [ ] 8 пустых классов в schemas (наследуют с `pass`) `[CODE-6]`

### Код C++

- [ ] Огромные callback лямбды (438 строк) `[CODE-1]`
- [ ] 136 вызовов CallAfter без контроля `[CODE-2]`
- [ ] Temp-файлы не удаляются при исключениях `[CODE-3]`
- [ ] JSON parsing без проверки ключей `[CODE-4]`
- [ ] `_ensure_printer_id()` — 278 строк монстр-функция `[CODE-5]`
- [ ] Мёртвый код `m_notifications_button/badge` `[LOW-2]`
- [ ] Хардкод таймаутов в FilamentHubClient `[LOW-3]`
- [ ] Хардкод API endpoints `[LOW-4]`
- [ ] Хардкод постфикса `[FilamentHub]` `[LOW-5]`
- [ ] `sync_call_counter` может переполниться `[LOW-6]`
- [ ] 200+ BOOST_LOG_TRIVIAL на info вместо debug `[LOW-7]`
- [ ] Unused variable `e` в CallAfter лямбде `[LOW-8]`
- [ ] Include guards `__` зарезервированы стандартом `[LOW-9]`
- [ ] Переменные не в member initializer list `[LOW-10]`

### Код frontend

- [x] ~~32 `console.log` в production~~ `[LOW-1]`
- [ ] TypeScript `noUnusedLocals: false` `[INFRA-19]`
- [ ] 60+ использований `any` в TypeScript `[TS-1]`
- [ ] Unsafe `as any` casts `[TS-2]`
- [ ] `qrcode.react` — inactive, рассмотреть замену `[CVE-11]`
- [ ] `passlib` 1.7.4 — не поддерживается `[CVE-12]`
- [ ] `react-syntax-highlighter` ≥ 16.1.0 `[CVE-10]`
- [ ] Admin role check только на frontend `[FRONTEND-1]`

### Фичи

- [ ] Переименовать "История" → "Активность"
- [ ] Топ-10 популярных на главной
- [ ] Расширить CreatePrintProfileModal
- [ ] Retry logic в FilamentHubClient
- [ ] "Мои принтеры" — generic вместо конкретных моделей `[TODO-12]`
- [ ] Комбинации профилей (принтер + филамент + process) `[TODO-13]`
- [ ] Smart Matching & Filtering System `[TODO-14]`
- [ ] Вендор-бандлы (Фазы A→C) — см. `PENDING_TASKS.md`

---

## OrcaSlicer C++ — баги

- [x] ~~Экспорт пропускал все новые пресеты~~ (убран `continue` по `fhub_id`)
- [x] ~~user_id = 'true' в AppConfig~~ (очистка невалидного user_id)
- [x] ~~Дублирование "Export started" текста~~
- [x] ~~74 русских перевода добавлены в .po файл~~
- [x] ~~Кракозябры в тостах WebView~~ (`wxString::FromUTF8()`)
- [x] ~~Спам "Printer profiles import is disabled"~~ (guard `m_is_syncing`)
- [x] ~~Зависание UI при синхронизации~~
- [x] ~~Синхронизация запускается дважды при открытии~~
- [x] ~~Типы материалов на сайте — только PLA~~

- [ ] **403 для printer/print profiles** — настройки `allow_*_import` = false по умолчанию
- [ ] **get_my_presets возвращает пустой массив** — после экспорта должны появиться

---

## Нужно проверить

- [ ] get_my_presets возвращает пустой массив `[TODO-10]`

---

*Источники: Claude Opus аудит (7 фаз), Gemini CVE-анализ, tracing потока экспорта/импорта пресетов*
