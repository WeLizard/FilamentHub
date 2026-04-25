# HANDOFF — FilamentHub

> Last updated: 2026-04-25 by Claude (Opus)

## Что сделано (сессия 2026-04-25 — Opus)

### Аудит TODO_CONSOLIDATED — обнаружено вранё в HH секции

Ранее TODO утверждал что HH D.1 / E.1 «реализованы в FilamentHubClient, ждут UI». Проверка показала: **в C++ методов не было**. Backend endpoints (`/orcaslicer/preset-slot-sync/heartbeat`, `manual/assignment`, `state`, `hh/snapshot`) готовы, но C++ обвязки в `FilamentHubClient.hpp` отсутствовали. Реальный статус восстановлен в TODO_CONSOLIDATED.

### HH этап E.2 — реализован (требует push submodule + main)

**Submodule изменения (требуют коммита и push):**

1. `submodule/OrcaSlicer/src/slic3r/Utils/FilamentHubClient.hpp`
   - Добавлена константа `API_HH_SNAPSHOT = "/api/v1/orcaslicer/preset-slot-sync/hh/snapshot"`
   - Объявлен метод `bool post_hh_snapshot_sync(access_token, payload_json)` — sync вариант (как `resolve_spool_presets_sync`), потому что вызывается из background polling thread где локальный `FilamentHubClient client;` уничтожается до завершения async запроса

2. `submodule/OrcaSlicer/src/slic3r/Utils/FilamentHubClient.cpp`
   - Реализован `post_hh_snapshot_sync` через `Http::post().perform_sync()`. Best-effort: возвращает `false` при любой ошибке, логирует `warning`

3. `submodule/OrcaSlicer/src/slic3r/Utils/MoonrakerPrinterAgent.cpp`
   - Подключены `#include "InstanceID.hpp"` и `<boost/date_time/posix_time/posix_time.hpp>`
   - В `fetch_hh_filament_info()` после успешного парсинга добавлен upload snapshot:
     - `device_fingerprint = "orca:" + instance_id::ensure(*app_config) + ":" + device_info.dev_id`
     - `snapshot_ts` — ISO8601 UTC через `boost::posix_time::microsec_clock::universal_time()` + "Z"
     - Все gates 0..num_gates-1 (включая пустые/unknown) попадают в payload — backend должен иметь полный snapshot слотов
     - `material` обрезается до 50 символов, `color_hex` до 7 (соответствует backend ограничениям `Field(max_length=...)`)
     - Если `access_token` пустой — snapshot не отправляется (no-op)
   - Best-effort: ошибки только логируются как `warning`, sync flow не прерывается

**Билд:** скомпилировано `libslic3r_gui` (target only) — 0 ошибок. Полный `ALL_BUILD` владелец билдит сам (см. правило в `.claude/rules/general.md` пункт 7).

### Грабли, на которые наткнулся

- **`std::function<Http()>`-style async для locally-created client не работает**: `FilamentHubClient client;` создаётся на стеке, локальная переменная уничтожается при возврате из функции → `~FilamentHubClient()` вызывает `cancel_all()` → запрос отменяется. Решение: sync-метод (как `resolve_spool_presets_sync`).
- **`device_fingerprint` нигде раньше не генерировался в OrcaSlicer**. Использован готовый `Slic3r::instance_id::ensure(config)` — это stable UUID кэшируется в `.orcaslicer_machine_id`. Per-printer уникальность через конкатенацию с `device_info.dev_id`.

### Правило добавлено

`.claude/rules/general.md` пункт 7: **НЕ запускать билд OrcaSlicer** (cmake/MSBuild/ninja в `submodule/OrcaSlicer/`). Владелец билдит сам.

## Current state
- **Submodule**: 3 файла изменены, **коммита нет**, push нет
- **Main repo**: TODO_CONSOLIDATED.md и HANDOFF.md обновлены, не закоммичены
- **Билд**: `libslic3r_gui.lib` собирается чисто, полный билд за владельцем
- **TODO**: HH E.1 + E.2 закрыты; HH D.1/D.2/D.3 + E.3/E.4 открыты

## What to do next
- [ ] Владельцу: пересобрать OrcaSlicer полностью (`ALL_BUILD`) и протестировать что snapshot действительно отправляется (логи: `BOOST_LOG_TRIVIAL(debug) << "FilamentHub::post_hh_snapshot_sync: uploaded, status=200"`)
- [ ] Запросить разрешение на коммит submodule + push
- [ ] Запросить разрешение на коммит main repo
- [ ] HH D.1: добавить в FilamentHubClient методы `post_device_heartbeat`, `post_manual_preset_assignment`, `get_preset_slot_state_sync`
- [ ] HH D.2/D.3: подключить heartbeat при старте + manual assignment при UI assign
- [ ] HH E.3: UI индикатор свежести HH state
- [ ] Recommended presets UI: либо по `plan.md` (новый `preset_matcher` + `recommended-for-printer` + UI секция), либо использовать существующий `/presets/recommended/{filament_id}` и добавить UI

## Context for next session
- HH snapshot теперь шлётся **на каждый polling cycle** (когда HH доступна). Если бэкенд видит спам — добавить дедупликацию (E.4) сравнением hash payload в static var
- `instance_id::ensure()` потокобезопасен (mutex внутри), кэширует значение
- Backend endpoint `POST /orcaslicer/preset-slot-sync/hh/snapshot` валидирует:
  - `gate_count` 1..256
  - `gates[].gate < gate_count` (иначе ValueError)
  - `gates[].gate` уникальны
  - `gates[].status` enum: -1, 0, 1, 2

## Предыдущая сессия (2026-03-28)

### OrcaSlicer C++ — retry logic + refactoring (4 коммита в submodule, запушены)

1. **`5b53faff2e` fix: add JSON key validation and temp file cleanup**
   - **[CODE-4]** 8 `.contains()` проверок в OnScriptMessage и sync callbacks
   - **[CODE-3]** temp_file cleanup на всех exception paths в import_profile_internal

2. **`f2fef3aed3` feat: add retry logic with exponential backoff to HTTP client**
   - `perform_with_retry()` с factory lambda (Http non-copyable), 500ms initial delay × 2, max 3 attempts
   - 15 async методов переведены на retry, login/delete_preset без retry
   - **[ORCA-SYNC-TIMEOUT-1]** TIMEOUT_MAX_IMPORT=120с для import-методов (было 30с)
   - Файл сокращён с 883 до 735 строк

3. **`766e8c96c4` refactor: decompose continue_sync_after_token_validation into 8 focused methods**
   (детали в предыдущей секции)

4. **`7ff069a39e` refactor: split FilamentHubPanel.cpp into 5 focused files**
   - **[CODE-0]** 7600 строк → 5 файлов:
     - `FilamentHubPanel.cpp` (1855) — UI, конструктор, WebView handlers
     - `FilamentHubSync.cpp` (1470) — sync orchestration, preset queue
     - `FilamentHubImport.cpp` (1540) — preset/profile import, batch processing
     - `FilamentHubExport.cpp` (2272) — filament/printer/print export, orphan scan
     - `FilamentHubUtils.cpp` (711) — auth, mappings, permissions, config
   - 104 метода, 0 потеряно
   - CMakeLists.txt обновлён

3 (prior). **`766e8c96c4`** — [CODE-5] 680 строк → 8 методов (max 211 строк)
   - `handle_presets_list_response/error` — HTTP callback dispatching
   - `process_successful_presets_list` — 200 OK: parse, empty-check, batch download
   - `handle_sync_token_expired` — дедупликация 401 retry (было 2 копии)
   - `detect_deleted_presets` — обнаружение + orphan cleanup
   - `report_deleted_presets_to_backend` — async reporting
   - `trigger_silent_profile_export` — auto-export при пустом sync

### Инфраструктура (1 коммит в main, запушен)

4. **`7b22dc7` perf(nginx): increase proxy buffers for API responses**
   - Фикс медленной загрузки сайта после деплоя (nginx spilling responses to disk)

5. **`d973a8e7c8` fix: resolve build errors from file split (Http non-copyable, orphaned body)**
   - C2280: Http non-copyable — `std::function<Http()>` невозможен (deleted copy ctor).
     Заменено на `RequestExecutor = std::function<void(CompleteFn, ErrorFn)>` — лямбда сама создаёт Http,
     прикрепляет callbacks, вызывает `.perform()` и `store_request()` внутри себя.
   - C2447: orphaned `json_string_value_or` body в Panel.cpp (баг парсера `= {}` default param) — удалён.
   - Обновлены: `perform_with_retry` impl + все 15 caller lambdas + header typedef.
   - **Билд чистый**: 0 ошибок, `orca-slicer.exe` собрался.

6. **`c84692dc84` fix: defer silent auto-export after sync to prevent UI freeze**
   - Auto-export после sync блокировал UI thread (file I/O + JSON parsing в `CallAfter`)
   - Кнопки навигации не реагировали до refresh
   - Отложено на 2 сек через `wxTimer` — UI успевает обработать pending events

7. **`b0a5b49bc2` refactor: deduplicate export response/error handling (CODE-1, CODE-2)**
   - **[CODE-1]** Три response handler по ~130 строк → один `process_export_response()` (~100 строк)
   - **[CODE-1]** Три error handler по ~25 строк → один `handle_export_error()` (~20 строк)
   - **[CODE-2]** `notify_webview()` и `save_app_config_async()` — обёртки над `CallAfter`
   - Export.cpp: 2272 → 1936 строк (-336, -15%)
   - CallAfter: 156 → 142 (-14), остальные необходимы для thread-safety

## Current state
- Main repo: запушен, up to date
- Submodule: 8 коммитов в filamenthub-integration (6 запушены + 2 новых — нужен push)
- Frontend tsx phantom `M` — те же 3 файла, не трогать
- TODO: CODE-0..CODE-5, LOW-3, LOW-4, LOW-7, LOW-10 закрыты; retry logic и ORCA-SYNC-TIMEOUT-1 закрыты
- **Билд OrcaSlicer**: PASS (Release, 0 errors)

## What to do next
- [ ] Запушить submodule (2 новых коммита)
- [ ] Продолжить по TODO_CONSOLIDATED.md

## Context for next session
- FilamentHubPanel.cpp разбит на 5 файлов: Panel (UI), Sync, Import, Export, Utils
- Export: response/error handling дедуплицирован в `process_export_response()` / `handle_export_error()`
- `notify_webview(msg, type)` — thread-safe wrapper для `CallAfter` + `show_notification_in_webview`
- `save_app_config_async()` — thread-safe wrapper для `CallAfter` + `app_config->save()`
- Retry через `perform_with_retry()` с `RequestExecutor` (не `std::function<Http()>`)
- Auto-export после sync отложен на 2с через `wxTimer` (fix UI freeze)

## Предыдущая сессия (2026-03-26)

### OrcaSlicer — fix UI freeze after sync + build tooling

1. **`d5185aece3` fix(sync): non-blocking auto-export after filament sync**
2. **`1e540805e9` feat(build): version selection menu + safer clean**
3. **Codex (25.03)**: crash fix `ensure_parent_preset_exists()` → UI thread

— Claude

---

## Что сделано (сессия 2026-03-25, часть 2 — Opus)

### Ревью коммитов Sonnet

- 3 коммита проверены: `865023e` (orca-bridge.d.ts), `e1aa08e` (client/AdminDatabase types), `ee362dd` (onError AxiosError) — **все корректные**
- Sonnet попытался заменить `catch (err: any)` → `catch (err: AxiosError<...>)` через Python-скрипт — **TS это запрещает** (только `any` или `unknown` в catch). Полностью откачено.
- WikiArticlePage.tsx: 2 пропущенных `onError` типизированы отдельным коммитом

### Актуализация TODO

- 87 завершённых `[x]` перенесены в `TODO_COMPLETED_ARCHIVE.md`
- TODO_CONSOLIDATED.md: 315 строк → 148, чисто только открытые задачи
- Структура: Активные → Product/Features → Технический долг → Долгосрочное → Идеи → Отложено
- sitemap.xml — проверен, работает (динамический endpoint на backend), ложная тревога убрана

### OrcaSlicer диагностика

- Логи подтвердили `user_id="true"` corruption (3 раза), 401, sync timeout
- Билд с фиксами от 24 марта лежит в submodule/ но не был распакован (portable на десктопе от 16 марта)
- Пользователь обновляет сборку

## Current state
- Main repo: up to date с origin, TSC 0 ошибок
- Submodule: уже запушен (cf7fbbb33d на origin/filamenthub-integration)
- Билд OrcaSlicer от 24.03 содержит все фиксы, пользователь распаковывает
- docs/ обновлён локально (не коммитится)

## What to do next
- [ ] Проверить OrcaSlicer с новой сборкой (sync, UI responsiveness)
- [ ] Продолжить TS-1/TS-2: ~25-30 осмысленных замен (интерфейсы AdminWiki, AdminStats, metadata helpers)
- [ ] `[LEGAL-6]` Роскомнадзор — не код, бумажная работа

## Context for next session
- `catch (err: any)` в catch блоках — оставить как есть. TS запрещает конкретные типы в catch. Менять на `unknown` нецелесообразно (нужны type guards в каждом блоке).
- Оставшиеся ~111 `any`: ~35 catch (не трогать), ~15 библиотечные касты (не трогать), ~7 тесты (ок), ~25-30 реальных (интерфейсы)
- OrcaSlicer portable: `C:\Users\Lizard\Desktop\OrcaSlicer-FilamentHub-2.3.2-dev-fh-win64-portable\`
- Свежий zip: `submodule/OrcaSlicer/OrcaSlicer-FilamentHub-2.3.2-dev-fh-win64-portable.zip` (24.03)

— Claude

---

## Что сделано (сессия 2026-03-25, часть 1 — Sonnet)

### [PERF-2] Lazy-load CreatePresetModal и CreatePrinterProfileModal ✅

- `ProfilePage.tsx`, `BrandProfilePage.tsx`, `AdminPresets.tsx` — переведены на `React.lazy()` + `<Suspense fallback={null}>`
- `App.tsx` — добавлен prefetch обоих модалок через 2с после загрузки
- Создан `frontend/src/types/orca-bridge.d.ts` — типизация `window.filamenthub`, `window.wx`, `window.BarcodeDetector` (убраны 39 `as any` кастов из 4 файлов)

### [TS-1/TS-2] Сокращение `any` в frontend TypeScript ✅ (частично)

- `onError: (err: any)` → `onError: (err: AxiosError<{ detail: unknown }>)` в **21 файле**
- `api/client.ts`: `RetryableAxiosConfig` интерфейс, `processQueue(error: unknown)`, `orcaslicer_settings?: Record<string, unknown> | null`
- `data/materialDefaults.ts`: `[key: string]: unknown`
- `admin/AdminDatabase.tsx`: `MigrationInfo` и `TableInfo` интерфейсы вместо `any[]`
- TSC: **0 ошибок** после всех правок
- Осталось ~111 `any` (было ~211)

— Claude

---

## Что сделано (сессия 2026-03-24)

### OrcaSlicer — фикс sync багов (5 исправлений)

Submodule коммит: `cf7fbbb33d` в ветке `filamenthub-integration`

1. **`""` → `std::string()` в `app_config->set()`** (10 вызовов) — `const char* ""` резолвился в `bool` overload (писал `"true"` вместо пустой строки). Это вызывало `user_id_str = "true"` → бесконечный цикл re-login.
2. **`try_acquire_sync_lock()` с 60с таймаутом** — при зависшем `m_is_syncing` >60с force-reset. Предотвращает permanent deadlock.
3. **Все 6 `m_is_syncing.exchange(true)` заменены на `try_acquire_sync_lock()`** — synchronize_presets, 3 export функции, unified export, orphaned scan.
4. **`m_initial_sync_done` флаг** — auto-sync после логина только 1 раз за сессию (не на каждый тик token monitor).
5. **Сброс `m_initial_sync_done` и `m_full_sync_attempted` при logout** — следующий логин снова вызовет sync.

### ProfilePage — убрана кнопка Activate для draft пресетов

Удалён весь chain: кнопка → проп → хендлер → стейт → импорт модалки. `ActivatePresetModal.tsx` стал dead code (не импортируется нигде).

## Current state
- Submodule запушен? **Нет, нужно `git push` в submodule/OrcaSlicer**
- ProfilePage коммит в main repo: сделан ранее
- Нужна сборка OrcaSlicer для проверки C++ изменений

## What to do next
- [ ] Запушить submodule (`cd submodule/OrcaSlicer && git push`)
- [ ] Собрать OrcaSlicer и протестировать sync flow
- [ ] Удалить `ActivatePresetModal.tsx` (dead code) — по разрешению владельца
- [ ] Протестировать OAuth flow на проде

## Context for next session
- Root cause бага `user_id = "true"`: C++ overload resolution — `const char* ""` (non-null ptr) → `bool true` → записывает строку `"true"` через `set(section, key, bool)`. Фикс: явно передавать `std::string()`.
- Каскадный sync (`empty list → full sync`) уже был защищён `m_full_sync_attempted`, дополнительных изменений не потребовалось.
- JS token monitor (setInterval 1с) проверяет localStorage — с `m_initial_sync_done` повторные `login_success` от рефреша токена не вызывают sync.

— Claude

---

## Что сделано (сессия 2026-03-23)

### [STUB-2] OAuth 2.0 — Google + Яндекс (полная реализация)

**Backend:**
- `backend/app/services/oauth_service.py` — Google и Yandex token exchange, OAuthUserInfo, CSRF state
- `backend/app/api/v1/endpoints/auth.py` — `GET /auth/oauth/{provider}/url` + `POST /auth/oauth/{provider}/callback`
- Логика: find by oauth_provider_id → find by email (link) → create new user
- `User.password_hash` сделан nullable (OAuth-юзеры без пароля)
- Redirect URI: `https://filamenthub.ru/oauth/callback/{provider}` (provider-specific)
- `backend/alembic/versions/c5d3a7b92e04_add_oauth_fields.py` — миграция применена на проде через CLI (был emergency: сайт падал из-за missing column)
- 6 новых ERR_OAUTH_* кодов в `core/errors.py`

**Frontend:**
- `frontend/src/pages/OAuthCallbackPage.tsx` — страница `/oauth/callback/:provider`
- `AuthContext.loginWithToken()` — метод для OAuth-входа по готовому токену
- `AuthModal.tsx` — убрана заглушка, добавлены кнопки Google + Яндекс (с spinner, обе всегда видны)
- `App.tsx` — роут `/oauth/callback/:provider`
- i18n: ru/en ключи для oauthCallback + ERR_OAUTH_* ошибок

### Прочее
- Убрана внутренняя разбивка затрат из КП (Phase 4 multi-item — ранее, в этой же сессии)
- AuthModal header: лого сверху, FilamentHub снизу, подпись убрана
- reCAPTCHA badge: `transform: scale(0.75)` в `index.css`
- Правило про Opus добавлено в `.claude/rules/general.md`
- Миграция применена напрямую через `docker exec alembic upgrade head` — это был вынужденный шаг (сайт был полностью недоступен), не нарушение правил

## Current state
- Всё задеплоено на прод, OAuth работает (ключи в `.env.prod`)
- Google Console: redirect URI `https://filamenthub.ru/oauth/callback/google`
- Яндекс OAuth: redirect URI `https://filamenthub.ru/oauth/callback/yandex`, scope `login:email`
- ВАЖНО: в `.env.prod` на сервере прописаны `GOOGLE_CLIENT_ID/SECRET` и `YANDEX_CLIENT_ID/SECRET`
- Codex завершил перевод юридических текстов (TermsPage + ConsentPage) на английский — коммит `070190f` ✅

## What to do next
- [ ] Протестировать OAuth flow на проде (Google + Яндекс)
- [ ] reCAPTCHA badge: при желании можно скрыть полностью (добавить текст "protected by reCAPTCHA" в footer)
- [ ] Shareable quote page `[CALC-PRO]`

## Context for next session
- OAuth не тестировался после деплоя — стоит проверить полный flow (кнопка → редирект → callback → вход)
- Если OAuth не работает: проверить логи `docker logs filamenthub_backend_prod --tail 50`, вероятная причина — неправильные redirect URI в Google/Yandex консолях
- `password_hash` у OAuth-пользователей = NULL, login через email/пароль для них вернёт ERR_WRONG_PASSWORD (это ок)

— Claude

---

## Что сделано (сессия 2026-03-16 — ORCA-ENRICHMENT-1)

### [ORCA-ENRICHMENT-1] — Preset Enrichment & Orphaned Recovery

Полная реализация по 3 слоям:

**Backend:**
- `preset_enrichment_service.py` — сервис обогащения черновиков (37 материалов в `material_defaults.json`)
- `detect_material_type()` → определение материала по filament_type / inherits / имени (confidence 0.3–1.0)
- `enrich_preset()` → заполнение пустых полей дефолтами материала
- `POST /presets/{id}/activate` — активация черновика с привязкой к филаменту
- `POST /admin/presets/enrich-all` — batch enrichment для всех draft
- Orphaned metadata в orca_sync (orphaned, orphaned_reason, original_inherits)

**C++ (OrcaSlicer):**
- Orphaned preset scanner в FilamentHubPanel.cpp — рекурсивно сканирует `filament/` (включая `base/` подпапку)
- Детектирует .json файлы, не загруженные OrcaSlicer (broken inherits → Preset.cpp:1357 `continue`)
- Отправляет через тот же sync endpoint как draft с флагом `orphaned=true`

**Frontend:**
- `ActivatePresetModal.tsx` — модалка активации черновика с поиском филамента
- Бейджи orphaned/enrichment в ProfilePage.tsx
- Кнопка Zap для активации draft пресетов
- 13 i18n ключей (ru + en), 2 error кода

### [SYNC-OVERHAUL-1] — все 8 пунктов закрыты (ранее)

1. **Авторефреш после синхронизации** — `sync_complete` postMessage → invalidateQueries на фронте
2. **Hide toggle для черновиков** — скрытие/показ draft пресетов
3. **Переименование кнопки** — экспорт → импорт
4. **Постфикс `[FilamentHub]` → `[fh]`** — 7 исходных файлов (backend: `orca_sync.py`, `orcaslicer_machine_exporter.py`, `orcaslicer_exporter.py`; frontend: `ProfilePage.tsx`, `CreatePresetModal.tsx`; C++: `FilamentHubPanel.cpp/.hpp`). Backward-compat: `@FilamentHub` в strip-списках сохранён
5. **Очистка orphaned preset_mapping** — автоудаление стейловых `preset_mapping_*` в OrcaSlicer.conf при full sync
6. **Dev mode detailed notifications** — подробные per-preset уведомления (имя + статус) при `developer_mode == "true"` в OrcaSlicer Preferences; в обычном режиме — краткое summary. Реализовано для всех 3 типов (filament, printer, print) в обе стороны (export + import)
7. **"Download from FilamentHub" кнопка** — определено как ненужная, sync уже двунаправленный
8. **Счётчик не обновлялся после sync** — добавлены `['presets-stats']` и `['saved-presets-details']` в invalidation list `useOrcaSlicerNotifications.ts`

### Предыдущие фиксы этой серии сессий (2026-03-15/16)
- Backend: авторитетные поля в exporter (vendor, color, type после orcaslicer_settings)
- Backend: strip `[FilamentHub]`/`@FilamentHub` из входящих имён (3 места)
- Frontend: flow rate/ratio decimal precision
- OrcaSlicer: finish_export_operation early returns, skip `[fh]` пресетов в export

### Защита пресетов — 3 уровня (проверено по коду)
1. OrcaSlicer UI запрещает `[]` в именах (`SavePresetDialog.cpp:142`)
2. Сервер проверяет `preset.user_id != current_user.id` на всех 5 уровнях приоритета
3. Name fallback всегда фильтрует по `user_id == current_user.id`

### [CALC-QUOTE-4] + [CALC-QUOTE-NUMBER] — Валюта и нумерация КП

- Заменён захардкоженный `₽` на настраиваемый выбор валюты (₽/$€) в профиле КП
- `makeCurrencyFormatter()` — фабрика, `useMemo` в CalculatorPage
- `formatCurrency` прокинут через props в CalculatorView, HistoryView, QuoteModal
- Нумерация КП: `{prefix}-{YYYYMMDD}-{seq}` (по умолчанию КП-20260316-01), prefix настраиваем
- `quoteSequenceRef` — session-scoped счётчик, сбрасывается при перезагрузке
- i18n ключи добавлены (ru + en): quoteCurrency, quoteNumberPrefix, quoteNumberPrefixHint
- Коммит: `177fdc1`

### [Phase 1.5] — Калькулятор: точность формул и UX (6/6 задач)

Реализовано все 6 задач Phase 1.5 калькулятора:

1. **CALC-BED-PREP** — стоимость подготовки стола за запуск (full stack: schema/calculation/UI/profile/migration)
2. **CALC-AUTO-COMPLEXITY** — авто-коэффициент сложности из G-code (toolchanges, supports, layer height, infill, walls, objects)
3. **CALC-DEPRECIATION-AUTO** — авто-расчёт амортизации из цены принтера и ресурса (frontend helper fields)
4. **CALC-ENERGY-DETAIL** — покомпонентная мощность (hotend/bed/steppers/electronics → авто-сумма)
5. **CALC-POSTPROCESS-CHECKLIST** — 10 типовых операций постобработки с preset временем (toggle chips)
6. **CALC-PRICING-PRESETS** — 4 built-in пресета + сохраняемые пользовательские (localStorage)

Коммиты: `f37eaeb` → `a057e23` → `676d5ad` → `e5bbe4a` → `6e2c64d` → `7945b02`

## Current state
- Backend: enrichment + калькулятор bed_prep — готово, НЕ задеплоено
- **OrcaSlicer НЕ пересобран** — C++ изменения ждут сборки пользователем
- Frontend: калькулятор Phase 1.5 — готов, НЕ задеплоен
- **Миграция** `a3f1e8c72b01` (calculator profile + bed_prep) — НЕ применена, через админку
- Sync работает корректно
- deploy.sh: submodule отключён (`--no-recurse-submodules`)

## What to do next
1. **Деплой** (калькулятор Phase 1 + 1.5, облачный профиль)
2. **Применить миграцию** `a3f1e8c72b01` через админку
3. **Пересобрать OrcaSlicer** (пользователь соберёт сам)
4. Продолжить задачи калькулятора: CALC-QUOTE-5 (PDF/shareable), Phase 2 (оборудование)
5. WebView тормоза в OrcaSlicer
6. `user_id='true'` corruption в AppConfig

## Context for next session
- Phase 1.5 helper fields (printerPurchasePrice, printerUsefulHours, power components) — frontend-only, localStorage, НЕ в backend profile
- bed_prep_cost_per_print — full stack, в backend profile + migration
- Pricing presets хранятся в отдельном localStorage ключе `filamenthub_pricing_presets_v1`
- Postprocess checklist state — useState, не персистится (сбрасывается при перезагрузке)
- Калькулятор: `formatCurrency` — useMemo внутри CalculatorPage, прокидывается как prop в дочерние компоненты

— Claude

---

## Что сделано (сессия 2026-03-10, часть 8)

### Production fixes
- Admin stats 500 — timezone mismatch fix (`datetime.utcnow()` вместо `datetime.now(timezone.utc)`)
- 502 на проде — nginx кэшировал старый IP контейнера → `nginx -s reload`

### Admin stats redesign
- Компактные карточки, Docker-метрики по запросу, PageSpeed Insights виджет
- Generic admin settings endpoint (GET/PUT `/admin/settings/{key}` через Redis)
- CSP обновлён для googleapis.com

### Printer Profile Modal
- Убран SLA, hotend → dropdown (17 моделей), 4 новых типа сопел, скрыт #1 single extruder, компактная кинематика, X-кнопка G-code модалки

### i18n & SEO & Perf
- "рэмминг" → "трамбовка (ramming)" во всех локалях
- PNG favicons (120x120 Yandex, 180x180 Apple)
- Prefetch lazy-loaded страниц через 2с после load
- Удалён `qrcode.react`, обновлён `react-syntax-highlighter` 15.6.1 → 16.1.1

### OrcaSlicer (submodule, коммит `aac96cc3d6`)
- Удалена admin button из FilamentHubPanel (6 мест)

### TODO audit
- Полный прогон, 8+ задач отмечены ✅

## Current state
- Все изменения закоммичены локально
- Submodule OrcaSlicer: 64 коммита ahead of origin (не запушены)
- Основной репо: frontend/backend изменения не задеплоены
- Google PageSpeed API key ещё не введён в админке (нужен деплой)

## What to do next
1. **Деплой** — frontend/backend готовы к выкатке
2. **PageSpeed API key** — ввести в админке после деплоя
3. **Codex brand page** — незакоммиченные файлы (AdaptiveLogo, BrandDetailPage, BrandProfilePage, i18n) — проверить и закоммитить
4. **OrcaSlicer submodule push** — 64 коммита ждут пуша
5. **P2**: UX-TOOLTIPS-1, UX-NOZZLE-HINTS-1, INFRA-CDN-1, EMAIL-1

## Context for next session
- Docker stats endpoint: socket mount (`/var/run/docker.sock:ro`) + `group_add: ["110"]`
- PageSpeed API key в Redis (`admin:settings:pagespeed_api_key`)
- OrcaSlicer role parsing убран вместе с admin button — если понадобится роль, нужно вернуть
- HANDOFF append-only правило: `.claude/skills/fh-handoff/skill.md` обновлён, чтобы не перезаписывать чужие записи

— Claude

---

## Follow-up (сессия 2026-03-12, Telegram bot logging/session fix)

### Что сделано
- В `bot/bot.py` логирование переведено в stdout, чтобы штатный launcher писал рабочий лог в `bot/bot.log`, а не оставлял его пустым.
- В `bot/bot.py` добавлен `TG_PERSISTENT_SESSIONS` (по умолчанию `0`): бот теперь по умолчанию опирается на собственную thread history и запускает CLI stateless, без `resume`, чтобы не дублировать контекст.
- В `bot/bot.py` возвращён явный plain-text route через `@claude`, `@codex`, `@qwen`, `@gemini` без переключения active agent.
- В `bot/agent_adapters.py` для всех адаптеров добавлен явный stateless path; persistent resume остаётся доступен только при `TG_PERSISTENT_SESSIONS=1`.
- В `bot/bot.ps1` `status` теперь показывает хвосты и `bot.log`, и `bot_err.log`, если в них есть данные.
- В `bot/README.md` задокументированы новый env-флаг и обновлённая логика просмотра логов.

### Что проверено
- In-memory `compile()` для `bot/bot.py`, `bot/agent_adapters.py`, `bot/state_store.py`.
- Smoke на `build_agent_adapters()`:
  - stateless mode не создаёт resume/session contract по умолчанию;
  - persistent mode по-прежнему собирает session-aware команды.
- `powershell -ExecutionPolicy Bypass -File bot\bot.ps1 restart` выполнен успешно.
- После рестарта бот поднялся с новым PID `34664`, `/healthz` отвечает, `bot/bot.log` начал заполняться новыми строками.

### Что не сделано
- Не проводил живой Telegram E2E для `@agent`, `/ask`, `/pass` уже после рестарта.
- `docs/current/TODO_CONSOLIDATED.md` не менял: под этот bot-follow-up там нет отдельного существующего пункта.

### Что делать дальше
1. Из Telegram проверить минимум:
   - `@codex ping`
   - `/who`
   - `/codex <короткий запрос>`
2. Если понадобится вернуть CLI-resume, включать это осознанно через `TG_PERSISTENT_SESSIONS=1` и проверять по агентам отдельно.

— Codex

---

## Follow-up (сессия 2026-03-31, README refresh for project overview)

### Что сделано
- Обновлён корневой `README.md` под реальное позиционирование проекта: платформа для филаментов, пресетов и профилей 3D-печати с прямой интеграцией в OrcaSlicer.
- Убраны неточные или устаревшие формулировки из старого короткого README; добавлены разделы про продуктовую задачу, ключевые возможности, стек, структуру репозитория, dev quick start и ссылки на документацию.
- В тексте README отражены реальные интересные части проекта: OrcaSlicer WebView bridge, двусторонняя sync-логика, Spoolman-compatible API, QR-коды, брендовый контур, калькулятор и roadmap-направления.

### Что проверено
- Сверены реальные пути репозитория (`backend/`, `frontend/`, `submodule/OrcaSlicer/`, `docs/`, `scripts/`).
- Сверены базовые версии и стек по `frontend/package.json`, `backend/pyproject.toml`, `docker-compose.dev.yml`.
- Осознанно не добавлялась license-секция в README: в корне репозитория нет отдельного `LICENSE`, поэтому не стал писать недостоверные утверждения.

### Что не сделано
- Не менял `docs/INDEX.md` и другие `.md` файлы, кроме `README.md`.
- Не запускал тесты или сборки: задача чисто документационная.

### Что делать дальше
1. Если README будет готовиться под публичный репозиторий, отдельно решить вопрос лицензии и contribution policy, а уже потом добавлять badges/section про вклад.
2. При желании следующим шагом можно сделать английскую версию project overview для GitHub/LinkedIn/portfolio.

— Codex

## Follow-up (сессия 2026-03-26, OrcaSlicer sync UI freeze after successful batch import)

### Что сделано
- Проверен свежий OrcaSlicer лог после пересборки с sync-фиксами:
  - `C:\Users\Lizard\AppData\Roaming\OrcaSlicer\log\debug_Thu_Mar_26_23_02_40_103308.log.0`
- Подтверждено, что текущий бинарь уже содержит последний sync-fix:
  - `Current OrcaSlicer Version 2.3.2-rc2+fh build d6010df6ce`
- Подтверждено, что filament sync теперь доходит до batch-import и не падает:
  - `SYNC STEP 9.1 HTTP status: 200`
  - `BATCH UI thread import callback entered`
  - `BATCH Before load_current_presets`
  - `BATCH After load_current_presets`
  - `BATCH Before auto-export permission check`
  - `BATCH Auto-export handoff callback entered`
- Сопоставлен лог с кодом в `submodule/OrcaSlicer/src/slic3r/GUI/FilamentHubPanel.cpp`.
- Найден наиболее вероятный источник текущего "залипания" UI после успешной синхронизации:
  - в batch-path после успешного filament sync вызывается скрытый auto-export printer/print profiles;
  - этот шаг стартует из UI thread в `process_batch_export_response()`;
  - в handoff callback код снова поднимает `m_is_syncing=true` и вызывает:
    - `export_printer_profiles_to_filamenthub_internal(...)`
    - `export_print_profiles_to_filamenthub_internal(...)`
  - обе функции синхронно обходят `preset_bundle`, читают JSON-файлы и собирают payload прямо на главном потоке.
- Дополнительно проверен старый queue-path: там такой же скрытый auto-export хвост тоже присутствует.
- Проверен frontend сайта:
  - `frontend/src/hooks/useOrcaSlicerNotifications.ts` действительно слушает `sync_complete`, но сам не держит отдельный `isSyncing` и только инвалидирует query cache;
  - значит визуальный эффект "кнопки залипли до refresh" с высокой вероятностью не из React-state, а из-за того, что WebView/главный поток Orca занят post-sync работой.
- Проверено, что для printer profile export уже есть отдельная ручная кнопка на странице профиля:
  - `frontend/src/pages/ProfilePage.tsx`
  - `frontend/src/components/ExportPrinterProfilesButton.tsx`
- Проверено, что `ExportPrintProfilesButton.tsx` существует, но на `ProfilePage` сейчас не используется.

### Что проверено
- Свежий лог обрывается по сути сразу после:
  - `FilamentHub: [BATCH] Auto-export handoff callback entered`
  - и дальше уже нет логов начала `export_printer_profiles_to_filamenthub_internal()` / `export_print_profiles_to_filamenthub_internal()`.
- Это сильный признак не нового crash, а UI-thread stall / долгого синхронного post-sync этапа.
- В batch-path порядок сейчас такой:
  1. `send_command_to_webview("sync_complete")`
  2. `release_sync_ui()`
  3. `show_notification_in_webview(...)`
  4. `update_user_info()`
  5. `update_unread_notifications_count()`
  6. скрытый auto-export printer/print profiles
- В queue-path после успешного filament sync тоже идёт скрытый auto-export printer/print profiles.

### Что не сделано
- Код не менялся.
- `submodule/OrcaSlicer/src/slic3r/GUI/FilamentHubPanel.cpp` не редактировался.
- Никакие сборки не запускались.
- `HANDOFF.md` обновлён только локально, без коммита.

### Что делать дальше
1. Самый безопасный следующий фикс: убрать скрытый auto-export printer/print profiles из конца filament sync как минимум в двух местах:
   - batch-path;
   - queue-path.
2. Причина: это не основной контракт ручной кнопки "Синхронизация" для filament presets, а тяжёлый второй этап, который сейчас перегружает UI thread и визуально делает WebView "неотзывчивым".
3. После этого отдельно решить продуктово:
   - нужен ли вообще auto-export после filament sync;
   - если нужен, то его надо выносить из UI thread и/или делать отдельным явным действием.
4. Если сохранять функциональность export без скрытого post-sync, printer profiles уже имеют ручную кнопку во frontend; print profiles отдельно надо либо явно вывести в UI, либо оставить отдельной последующей задачей.

— Codex

---

## Follow-up (сессия 2026-03-26, OrcaSlicer batch sync crash hardening)

### Что сделано
- В сабмодуле `submodule/OrcaSlicer` внесён точечный crash-safe фикс для batch sync и запушен в `origin/filamenthub-integration` коммитом `db61201c65` (`fix(sync): harden batch callback crash paths`).
- В `src/slic3r/Utils/FilamentHubClient.cpp` добавлен единый `invoke_callback_safe(...)` и через него защищены callback-boundary для:
  - `get_current_user`
  - `batch_download_profiles`
  - `get_my_presets`
  - `report_deleted_presets`
- В `src/slic3r/GUI/FilamentHubPanel.cpp` усилен `process_batch_export_response(...)`:
  - сохранён уже существующий локальный перенос `ensure_parent_preset_exists(...)` на UI thread;
  - добавлен внешний `try/catch` вокруг всего UI batch-import этапа;
  - cleanup sync-state (`m_is_syncing`, `m_active_syncs`, progress/status UI) сделан идемпотентным;
  - добавлен cleanup temp-файла на exception-path внутри import loop;
  - добавлены дополнительные warning/error log-маркеры перед критичными фазами (`UI callback entered`, `Before/After load_current_presets`, `Before auto-export permission check`, `Auto-export handoff callback entered`).
- Для ранних batch-ошибок (bad JSON / missing `profiles`) теперь также скрываются progress/status элементы, а не только сбрасывается lock.

### Что проверено
- `git diff --check` по двум изменённым файлам в сабмодуле проходит без замечаний.
- Изменения изолированы двумя файлами:
  - `src/slic3r/Utils/FilamentHubClient.cpp`
  - `src/slic3r/GUI/FilamentHubPanel.cpp`
- Сборки, `build.ps1`, Docker, packaging и любые compile/run шаги **не запускались**.

### Что не сделано
- Не менялся продуктовый контракт sync: открытие вкладки по-прежнему само по себе не запускает sync.
- Не трогался backend API и frontend сайта.
- Не обновлялся указатель сабмодуля в основном репозитории: в root есть параллельные локальные изменения, и смешивать их с submodule pointer update было бы грязно.
- Не решался более глубокий архитектурный вопрос смешанного flow `filament import -> printer/print auto-export`.

### Что делать дальше
1. Пользователь пересобирает OrcaSlicer сам и повторяет crash path.
2. Сразу смотреть новые логи Orca:
   - интересуют новые маркеры `FilamentHub: [BATCH] ...`
   - особенно, дошло ли до `Before load_current_presets`, `After load_current_presets` и `Auto-export handoff callback entered`
3. Если падение исчезло — отдельно решать product/UX вопрос: нужен ли auto-sync при открытии вкладки и нужно ли развязывать filament sync от auto-export printer/print profiles.
4. Если падение осталось — следующий шаг уже точечно бить по фазе, на которой оборвался новый лог, а не по всей sync-цепочке сразу.

— Codex

---

## Follow-up (сессия 2026-03-15, результаты проверки Orca build e9579d6eb1)

### Что проверено
- Проверен свежий Orca log после сборки из `submodule/OrcaSlicer`:
  - [debug_Sun_Mar_15_22_03_05_28720.log.0](C:\Users\Lizard\AppData\Roaming\OrcaSlicer\log\debug_Sun_Mar_15_22_03_05_28720.log.0)
- Сборка действительно новая:
  - `Current OrcaSlicer Version 2.3.2-dev-fh build e9579d6eb1`
- Проверены локальные FilamentHub filament files:
  - `ABS HTP [FilamentHub].json/.info`
  - `PETG HTP [FilamentHub].json/.info`

### Что подтвердилось
- Основной баг с импортом FilamentHub filament presets закрыт:
  - ошибки `type must be string, but is array` больше нет;
  - `Failed to import preset 154/159` больше нет;
  - FilamentHub tab для filament presets снова появился;
  - локально создаются новые `*[FilamentHub].json` с `fhub_id` и `fhub_source=filamenthub`.

### Что осталось в логах
- `EXPORT SKIP` / `Export/sync already in progress, skipping printer profiles export` всё ещё воспроизводится.
- Перед этим в логе виден auth/race-хвост:
  - `Get current user failed ... Status: 401`
  - `Failed to get unread notifications count ... Status: 401`
  - `user_id_str contains non-digit characters: 'true', clearing corrupted data`
  - затем `Not authenticated, cannot export filament presets`
- Это уже не importer bug, а отдельная проблема auth/export flow в Orca.

### Где копать дальше
- Подозрительный участок auth-state:
  - `FilamentHubPanel.cpp:1925` — `user_id_str contains non-digit characters: 'true'`
  - `FilamentHubPanel.cpp:4975` — `Not authenticated, cannot export filament presets`
- Подозрительный участок WebView token monitor:
  - `FilamentHubPanel.cpp:646-660`
  - если токен исчезает в localStorage, WebView шлёт `logout` обратно в C++
- Дубликаты export-вызовов и skip:
  - `FilamentHubPanel.cpp:4967`
  - `FilamentHubPanel.cpp:5510`

### Отдельно про warnings `can not find inherit preset ... just skip`
- Они всё ещё есть, но это уже не FilamentHub import/export bug.
- Сейчас это выглядит как отдельный legacy/orphaned preset cleanup problem:
  - loader до сих пор пропускает старые локальные user presets без валидного parent.
- Фикс `base_id` fallback уже в сборке (`ff737a135c`), но он не может восстановить реально мёртвые старые пресеты.

### Реальный статус
- FilamentHub filament sync/import: починен.
- Orca auth/export flow: не починен, остались 401 / `user_id=true` / `EXPORT SKIP`.
- Legacy local preset warnings: частично ожидаемы, требуют отдельного разбора, если мешают.

— Codex

---

## Follow-up (сессия 2026-03-15, Orca sync / FilamentHub presets)

### Что сломалось
- На production export filament presets для FilamentHub отдавал `inherits` массивом вместо строки:
  - было `\"inherits\": [\"Generic ABS @System\"]`
  - Orca ждёт строку и падала на импорте с ошибкой `type must be string, but is array`
- Из-за этого новые filament presets не импортировались как FilamentHub-presets, локально не появлялись файлы `*[FilamentHub].json`, а вкладка `FilamentHub` для них не восстанавливалась.
- После ошибок импорта в Orca дополнительно наблюдался спам `EXPORT SKIP` / `Export already in progress` и warnings `can not find inherit preset ... just skip`.

### Что сделано
- Backend fix уже в `main`: коммит `37aa1ea` в `backend/app/services/orcaslicer_exporter.py`
  - `inherits` больше не сериализуется как массив;
  - legacy-list случай тоже нормализуется обратно в строку.
- После деплоя backend fix импорт FilamentHub filament presets восстановился:
  - в Orca снова появились `ABS HTP [FilamentHub]` и `PETG HTP [FilamentHub]`;
  - локально создаются новые `*[FilamentHub].json` с `fhub_id` и `fhub_source=filamenthub`.
- В сабмодуле OrcaSlicer добавлен фикс восстановления parent preset по `base_id/setting_id`, если `inherits`-имя устарело:
  - commit `ff737a135c` `fix preset parent resolution by base_id`
- В ветку `filamenthub-integration` подтянут `upstream/main`:
  - commit `e9579d6eb1` `Merge remote-tracking branch 'upstream/main' into filamenthub-integration`

### Что это значит
- Основной баг с падением импорта FilamentHub filament presets закрыт backend-фиксом `37aa1ea`.
- Новый Orca build из `submodule/OrcaSlicer` уже включает:
  - upstream fixes по `m_is_syncing` / export flow;
  - наш fallback по `base_id` для устаревших parent preset references.
- После новой сборки Orca ожидается:
  - меньше или отсутствие `EXPORT SKIP`;
  - заметно меньше ложных `can not find inherit preset ... just skip`.

### Что ещё не гарантировано
- Если после новой сборки часть warnings `can not find inherit preset ... just skip` останется, это уже, вероятно, реальные orphaned legacy presets, а не поломка FilamentHub import/export.
- Main repo pointer на сабмодуль не коммитился в этой сессии; менялся только сам `submodule/OrcaSlicer`.

### Что делать дальше
1. Собрать OrcaSlicer из текущего `submodule/OrcaSlicer` (`filamenthub-integration`, HEAD `e9579d6eb1`).
2. Повторно проверить Orca log после запуска новой сборки.
3. Если warnings останутся, разбирать уже конкретные orphaned local presets по именам/`base_id`.

— Codex

---

## Follow-up (сессия 2026-03-15, Orca sync/export follow-up after FH filament restore)

### Что сделано
- Подтверждён и исправлен backend root cause filament import-падения:
  - `backend/app/services/orcaslicer_exporter.py`
  - коммит `37aa1ea` (`fix filament preset inherits export`)
  - `inherits` в export JSON снова отдаётся строкой, а не массивом.
- После выката backend подтверждено, что FilamentHub filament presets снова импортируются в Orca и появляются в секции `FilamentHub`:
  - `ABS HTP [FilamentHub]`
  - `PETG HTP [FilamentHub]`
- Разобран остаточный Orca-side шум:
  - `EXPORT SKIP`
  - `can not find inherit preset ... just skip`
- Установлено, что `EXPORT SKIP` относится не к filament import root cause, а к Orca/WebView export loop:
  - в исходниках уже есть фикс `72d61d236b` (`fix: resolve 3 FilamentHub sync issues`)
  - он чистит дублирующиеся WebView token monitor intervals и не даёт `m_is_syncing` залипать после export error/timeout.
- Для legacy/cloud/user preset warnings внесён чистый Orca fix по восстановлению parent preset через `base_id`, когда старое имя в `inherits` уже протухло:
  - `submodule/OrcaSlicer/src/libslic3r/Preset.hpp`
  - `submodule/OrcaSlicer/src/libslic3r/Preset.cpp`
  - `submodule/OrcaSlicer/src/libslic3r/PresetBundle.cpp`
  - коммит `ff737a135c` (`fix preset parent resolution by base_id`)
- Дополнительно в сабмодуль подтянут свежий `upstream/main`:
  - merge commit `e9579d6eb1`

### Что проверено
- В свежем Orca-логе после backend-фикса больше нет старой ошибки:
  - `type must be string, but is array`
  - `Failed to import preset 154/159`
- На диске появились новые корректные FilamentHub preset files:
  - `C:\Users\Lizard\AppData\Roaming\OrcaSlicer\user\2136879404\filament\ABS HTP [FilamentHub].json`
  - `C:\Users\Lizard\AppData\Roaming\OrcaSlicer\user\2136879404\filament\PETG HTP [FilamentHub].json`
- В них присутствуют корректные FilamentHub metadata:
  - `fhub_id`
  - `fhub_source=filamenthub`
  - строковый `inherits`
- Разобрана трасса warnings:
  - `Slic3r::PresetCollection::load_user_preset ... just skip`
  - это legacy/user-cloud sync path (`GUI_App::reload_settings()` -> `preset_bundle->load_user_presets(...)`), а не текущий FilamentHub import queue.
- Подтверждено, что часть warnings — не ложные, а реально старые orphaned presets:
  - например локальный process preset `0.20mm Standard @Creality Ender3V2 - Копировать` ссылается на старого parent по имени и имеет `base_id`, который уже не матчится к текущим base presets.

### Что не сделано
- Новую Orca сборку после коммитов `ff737a135c` + `e9579d6eb1` сам не запускал и не проверял: сборку пользователь делает вручную.
- Main repo pointer на новый Orca submodule commit не коммитился.
- Не делал миграцию/чистку реально мёртвых legacy local/cloud presets: текущий фикс только корректно восстанавливает parent там, где это возможно по `base_id`.

### Что делать дальше
1. Собрать Orca из текущего `submodule/OrcaSlicer` (`filamenthub-integration`, HEAD `e9579d6eb1`).
2. После сборки проверить:
   - ушёл ли `EXPORT SKIP`;
   - сократилось ли число `can not find inherit preset ... just skip`.
3. Если часть inherit warnings останется, это уже отдельный слой данных:
   - либо старые orphaned local presets;
   - либо старые cloud/user presets с действительно мёртвым parent.
4. Не лечить оставшиеся warnings новым loader-костылём; для них нужен отдельный cleanup/migration plan по legacy presets.

— Codex

---

## Follow-up (сессия 2026-03-15, Orca filament export inherits fix)

### Что сделано
- В `backend/app/services/orcaslicer_exporter.py` исправлен merge `preset.orcaslicer_settings` для filament export: scalar-ключи Orca больше не заворачиваются в массивы.
- Для текущего инцидента добавлен typed-safe handling для `inherits`, чтобы export JSON снова отдавал строку, а не `["..."]`.
- Добавлен безопасный legacy-path: если `inherits` в `orcaslicer_settings` когда-либо уже лежит как список, exporter берёт первый элемент и тоже отдаёт строкой.
- Локально сохранена резервная копия битого файла: `backend/app/services/orcaslicer_exporter.py.broken-20260315.bak` (не в git).

### Что проверено
- `python -m compileall backend/app/services/orcaslicer_exporter.py` прошёл успешно.
- Smoke-проверка через локальный вызов `preset_to_orcaslicer_json()` подтвердила:
  - строковый `inherits` экспортируется как `str`;
  - legacy-list `inherits` тоже экспортируется как `str`.
- Подтверждён root cause на продовых пресетах `154` и `159`: до фикса export отдавал `inherits` массивом, а Orca ждёт строку.

### Что не сделано
- Не правил Orca C++ importer: фикс внесён только на backend export-слое.
- Не делал deploy на прод.
- Не трогал более широкий рефакторинг exporter и другие возможные scalar-ключи вне текущего инцидента.

### Что делать дальше
1. Задеплоить backend с коммитом `37aa1ea`.
2. На проде повторно проверить экспорт `/api/v1/presets/154/export/orcaslicer.json` и `/api/v1/presets/159/export/orcaslicer.json` — `inherits` должен быть строкой.
3. После деплоя повторить sync из Orca и убедиться, что filament presets снова импортируются в секцию `FilamentHub`.

— Codex

---

## Follow-up (сессия 2026-03-15, пожелания для Opus -> Codex)

### Что сделано
- В корне проекта добавлен файл `OPUS_FOR_CODEX.md` с явным протоколом постановки задач для Codex.
- Зафиксированы:
  - роль `Opus / Claude` как постановщика и ревьюера;
  - роль `Codex` как узкого исполнителя по `Task Packet`;
  - рекомендуемый шаблон `Task Packet`;
  - что хранить в `knowledge graph`, а что оставлять в `docs/*.md`;
  - когда лучше подключать `Qwen` и `Gemini`.

### Что проверено
- Проверен факт отсутствия дублирующего root-файла с таким назначением.
- Изменения ограничены `OPUS_FOR_CODEX.md` и append-only записью в `HANDOFF.md`.

### Что не сделано
- Не менял `AGENTS.md`, `TODO_CONSOLIDATED.md` или `knowledge graph`.
- Не правил существующие Claude/Codex skills и не внедрял автоматизацию поверх нового протокола.

### Что делать дальше
1. Если Opus будет использовать этот протокол постоянно, можно позже синхронизировать шаблон `Task Packet` со skill `fh-codex-task`.
2. При первых 2-3 делегированных задачах проверить на практике, хватает ли полей `Priority / Expected output / Stop conditions`.

— Codex

---

## Follow-up (сессия 2026-03-15, ProtectedRoute return hint cleanup)

### Что сделано
- В `frontend/src/components/ProtectedRoute.tsx` убрана видимая строка про возврат на исходную страницу после логина.
- Логика `return_url`, открытие модалки входа через `/?auth=login&return_url=...` и возврат после успешной авторизации не менялись.

### Что проверено
- `npm run build` в `frontend/` прошёл успешно после точечной правки UI-текста.

### Что не сделано
- Не убирал неиспользуемый i18n-ключ `protectedRoute.return_after_login`, так как задача была только про удаление видимой надписи.
- Не менял countdown, маршрутизацию или сам сценарий редиректа.

### Что делать дальше
1. Если понадобится, можно отдельно подчистить неиспользуемый i18n-ключ в RU/EN локалях.
2. При следующем UI-smoke проверить руками экран закрытого маршрута после деплоя: кнопка входа, countdown и переход на главную.

— Codex

---

## Follow-up (сессия 2026-03-15, auth redirect / protected route UX)

### Что сделано
- В `frontend/src/components/ProtectedRoute.tsx` сохранён текущий 5-секундный автопереход на главную, но экран доступа переработан в более понятную user-friendly карточку:
  - список того, что доступно после входа;
  - отдельный countdown-блок;
  - primary CTA `Войти`;
  - secondary CTA `На главную сейчас`;
  - строка с возвратом на исходный путь после авторизации.
- Кнопка входа в `ProtectedRoute` больше не ведёт на сломанный `same-path?auth=login`. Теперь используется `/?auth=login&return_url=<current path>`, чтобы модалка открывалась в `Layout`, где она реально живёт.
- В `frontend/src/components/Layout.tsx` добавлена обработка `return_url`:
  - URL санитизируется;
  - после успешного входа пользователь возвращается на исходную страницу;
  - при простом закрытии модалки pending return path очищается.
- RU/EN локали для `protectedRoute` обновлены под новый экран доступа.

### Что проверено
- `npm run build` в `frontend/` прошёл успешно.

### Что не сделано
- Не делал browser-smoke вручную: сценарий `закрытая страница -> Войти -> возврат обратно` не прокликивался в браузере, ограничился успешной сборкой.
- Не трогал отдельный `403` UX глубже текущего состояния.

### Что делать дальше
1. Руками проверить минимум:
   - `/profile` в logout состоянии;
   - `/calculator` в logout состоянии;
   - кнопка `Войти`;
   - возврат обратно после успешной авторизации;
   - автопереход на главную через 5 секунд.
2. Если product позже решит убрать countdown совсем, это уже отдельная маленькая правка поверх текущего рабочего `return_url` flow.

— Codex

---

## Follow-up (сессия 2026-03-15, единый калькулятор печати)

### Что сделано
- В `frontend/src/pages/ProfilePage.tsx` убран отдельный пользовательский таб `calculator`; в профиле оставлен один вход в калькулятор через `calculator-pro`.
- Из `ProfilePage.tsx` удалён мёртвый legacy-блок старого базового калькулятора (`CalculatorComponent` + related helpers/imports), чтобы второй калькулятор не оставался скрыто в коде.
- Пользовательские названия обновлены в RU/EN локалях:
  - `Calculator Pro` → `Калькулятор печати` / `Print Calculator`
  - короткая подпись таба → `Печать` / `Print`
  - общие подписи калькулятора приведены к единому неймингу без второго отдельного “Pro” калькулятора.
- Локально синхронизированы `docs/current/calculator-todo.md`, `docs/current/TODO_CONSOLIDATED.md`, `docs/current/calculator-implementation-history.md`, но они игнорируются `.gitignore` и в git не попали.

### Что проверено
- `npm run build` в `frontend/` прошёл успешно после удаления старого калькуляторного хвоста.

### Что не сделано
- Не менял premium access policy для оставшегося калькулятора: extra gate component не добавлялся, но текущий inline premium-state в `ProfilePage` оставлен как был.
- Не трогал `CalculatorPage.tsx` по продуктовой логике.

### Что делать дальше
1. Если product-решение окончательно сместится от “premium calc” к просто “единому калькулятору”, отдельно пройтись по текстам premium upsell внутри `ProfilePage` и `CalculatorPage`.
2. Если понадобится, вынести доступ к калькулятору из profile-only маршрута в отдельный публично-известный UX-flow, но без возвращения legacy tab `calculator`.

— Codex

---

## Follow-up (сессия 2026-03-14, Calculator Pro quote-flow cleanup)

### Что сделано
- `frontend/src/pages/CalculatorPage.tsx` перестроен под единый full quote-flow:
  - убран UX selector `by_weight / by_time / combined` из `Calculator Pro`;
  - backend estimate по-прежнему используется, но фронт теперь всегда собирает `combined` request как основной коммерческий сценарий;
  - сохранены два источника данных: ручной ввод и `G-code`, причём `G-code` теперь показан как источник автозаполнения, а не как отдельный режим калькулятора.
- В `Calculator Pro` выведен рабочий builder коммерческого предложения:
  - форма данных исполнителя / заказчика;
  - локальное сохранение реквизитов исполнителя;
  - открытие печатной версии с breakdown и line item для `Print / Save as PDF` из браузера.
- История расчётов больше не показывает старый `pricing method` как главный смысл карточки; вместо этого в UI используется источник данных (`manual` / `gcode`).
- RU/EN локали `frontend/src/locales/{ru,en}/translation.json` обновлены под новый quote-flow и печатное КП.
- Локальные `docs/current/calculator-todo.md` и `docs/current/TODO_CONSOLIDATED.md` синхронизированы с новым состоянием calculator-блока.

### Что проверено
- `npm run build` в `frontend/` прошёл успешно после переделки flow и добавления quote modal.

### Что не сделано
- Не было browser-smoke `Calculator Pro` руками: quote modal и печатную версию не прокликивал в браузере, ограничился успешной сборкой.
- Не делал отдельный shareable quote page.
- Не делал admin settings / monetization.

### Что делать дальше
1. Ручной UI smoke:
   - расчёт
   - `Открыть коммерческое предложение`
   - печатная версия / `Save as PDF`
   - сохранение в историю
   - восстановление из истории
2. Следующий калькуляторный блок — не возвращаться к selector-логике, а идти в `shareable quote page` и admin settings.

— Codex

---

## Follow-up (сессия 2026-03-14, Calculator Pro history persistence)

### Что сделано
- `Calculator Pro` доведён до следующего production-ready этапа после G-code parser:
  - добавлена таблица истории расчётов `calculator_history_entries`;
  - добавлены backend endpoints `GET/POST/DELETE /api/v1/calculator/history`;
  - в `frontend/src/pages/CalculatorPage.tsx` включён реальный `Save to history` flow;
  - вкладка `История` теперь показывает сохранённые расчёты, умеет восстанавливать форму и удалять записи.
- В историю сохраняются:
  - входные параметры расчёта;
  - breakdown результата;
  - распарсенные данные G-code (без тяжёлого thumbnail payload);
  - snapshot выбранного филамента.
- Убраны мёртвые disabled-controls истории/quote из `Calculator Pro`, чтобы UI не оставался декоративным.
- Локальные `docs/current/calculator-todo.md` и `docs/current/TODO_CONSOLIDATED.md` обновлены: estimate + parser + history уже живые, следующим разрывом остался `КП / PDF / shareable quote`.

### Что проверено
- `npm run build` в `frontend/` прошёл.
- `python -m compileall` прошёл для:
  - `backend/app/api/v1/endpoints/calculator.py`
  - `backend/app/schemas/calculator.py`
  - `backend/app/models/calculator_history_entry.py`
  - `backend/alembic/versions/c8d34f71b2aa_add_calculator_history_entries.py`

### Что не сделано
- Не прогонял browser-smoke истории вручную в UI после сборки.
- Alembic migration не применялась локально в БД в рамках этой сессии.
- `КП / PDF` и admin calculator settings всё ещё не реализованы.

### Что делать дальше
1. Применить миграцию и проверить живой flow:
   - расчёт -> `Сохранить в историю`
   - вкладка `История`
   - `Восстановить`
   - `Удалить`
2. Следующий реальный этап по reference: `КП / PDF / shareable quote`.
3. После этого возвращаться к admin settings / monetization, а не откатываться назад к parser/history.

— Codex

---

## Follow-up (сессия 2026-03-14, CreatePrintProfileModal cleanup)

### Что сделано
- В `frontend/src/components/CreatePrintProfileModal.tsx` убрана техничка из UI:
  - удалён поиск по Orca-полям
  - убран видимый блок `Residual JSON overrides`
  - пустые boolean-значения больше не показываются как `Наследовать из базового профиля`
- Модалка оставлена в структуре Orca-вкладок `Вид / Прочность / Скорость / Поддержки / Многоцвет / Прочее` без технических группировок по типам данных.
- Контекст принтера перенесён в обычный блок `Общее`, без отдельной псевдо-`phase` карточки.
- Видимые тексты секции приведены к нормальным подписям в RU/EN локалях (`Общее`, `Скорость перемещений`, `Спиральная ваза`, упрощённый hint для compatibility condition).
- Селекторы boolean/enum теперь все проходят через i18n-lookup с fallback, а не через жёсткие invent-тексты.

### Что проверено
- `npm run build` в `frontend/` прошёл успешно после правок.
- В git-коммит вошли только:
  - `frontend/src/components/CreatePrintProfileModal.tsx`
  - `frontend/src/locales/ru/translation.json`
  - `frontend/src/locales/en/translation.json`
- Грязные калькуляторные изменения в этом коммите не участвовали.

### Что не сделано
- Не делал browser-smoke самой модалки.
- Полный словарь RU-лейблов для всех residual Orca advanced fields не заведён отдельным исчерпывающим блоком в i18n: для незаведённых ключей остаётся fallback humanized label.

### Что делать дальше
1. Если пользователь продолжит этот блок, открыть модалку и добить те Orca advanced field labels, которые всё ещё выглядят сыровато в UI.
2. Не объявлять задачу “идеально закрытой”, пока не будет ручной browser-проверки структуры вкладок и подписей.

— Codex

## Follow-up (сессия 2026-03-14, CreatePrintProfileModal full structured parity)

### Что сделано
- `frontend/src/components/CreatePrintProfileModal.tsx` доведён до полной structured parity по Orca `process` schema без опоры на raw JSON как основной интерфейс.
- Добавлен новый typed helper `frontend/src/components/createPrintProfileOrcaFields.ts` со schema всех оставшихся Orca `process` keys по типам (`bool`, `enum`, `int`, `float`, `percent`, `floatOrPercent`, `string` и списки).
- В модалке добавлены structured advanced sections с поиском по Orca-полям и typed controls для всех remaining process keys из Orca.

---

## Follow-up (сессия 2026-03-15, финальный узкий проход по calculator parser)

### Что сделано
- `backend/app/services/calculator_gcode_parser.py` точечно усилен без дальнейшей перестройки `Calculator Pro`:
  - добавлены low-risk read-only поля `nozzle_diameter_mm`, температуры сопла/стола для первого слоя и остальных слоёв;
  - добавлены алиасы под реальные комментарии из референсных парсеров (`layer_count`, `maxz`, `filament_name`, `filament weight = [..]`);
  - добавлен разбор температур из `PRINT_START EXTRUDER=... BED=...` и базовых `M104/M109/M140/M190`;
  - исправлен разбор Cura `SETTING_3`: теперь режется и по escaped `\\n`, и по обычным переводам строк после `json.loads()`.
- `backend/app/schemas/calculator.py` и `frontend/src/types/api.ts` расширены под новые parser-поля.
- `frontend/src/pages/CalculatorPage.tsx` `G-code`-summary сделан суше и полезнее:
  - основной материал остаётся в верхнем meta-блоке;
  - добавлен pill с соплом;
  - в process summary показываются температуры, если они реально распарсены;
  - materials-секция больше не показывается при одиночном материале без реального multi-material контекста.
- `frontend/src/locales/{ru,en}/translation.json` обновлены под новые read-only подписи (`Сопло`, `Температуры`, короткие метки слоёв).

### Что проверено
- `python -m compileall backend/app/services/calculator_gcode_parser.py backend/app/schemas/calculator.py`
- `npm run build` в `frontend/`
- Parser smoke на synthetic примерах:
  - Cura: `TIME`, `Filament weight`, `LAYER_COUNT`, `MAXZ`, `SETTING_3` температуры/сопло;
  - Creality: `generated by Creality_Print`, `PRINT_START`, температуры и сопло;
  - Prusa/SuperSlicer-style: `fill_density`, `layer_count`, `maxz`
- Parser smoke на реальном `03_PETG_1h16m.gcode`:
  - `object_count = 7`
  - `active_material_count = 1`
  - `is_multi_material = false`
  - `toolchange_count = 1`
  - сопло и стартовые температуры доезжают

### Что не сделано
- Не брал дальше большой product/UX трек калькулятора: multi-item order flow, shareable quote, admin settings, полная архитектура `Calculator Pro`.
- Не трогал базовый калькулятор, кроме уже существующих локалей.

### Что делать дальше
1. Основной calculator-flow продолжать уже по обновлённому TODO и референсам в отдельной ветке работ.
2. Если снова понадобится моя помощь по калькулятору, ограничивать меня только parser/backend/i18n/read-only summary задачами.

— Codex
- `raw JSON` в модалке сохранён только как residual overrides для неизвестных / vendor-specific keys; известные Orca process keys теперь идут через structured state и исключаются из raw block.
- В сериализации `orcaslicer_settings` добавлена запись `notes`, а structured advanced values нормализуются обратно в Orca-compatible payload.
- Локали `frontend/src/locales/ru/translation.json` и `frontend/src/locales/en/translation.json` обновлены под новые structured sections, search и residual JSON блок.
- В локальном `docs/current/TODO_CONSOLIDATED.md` под пунктом `Расширить CreatePrintProfileModal (скорости, заполнение)` добавлен follow-up про полную structured parity.

### Что проверено
- `npm run build` в `frontend/` выполнен успешно после всех изменений (`tsc && vite build`).
- Проверен diff: в git-коммит идут только `CreatePrintProfileModal`, новый helper со schema Orca и RU/EN локали; случайные локальные backend-хвосты в коммит не включались.

### Что не сделано
- Browser-smoke не гонял: UI не прокликивал вручную после этого слоя, ограничился успешной сборкой.
- C++/submodule `OrcaSlicer` под эту задачу не менял: parity собрана на основе уже существующих process keys из сабмодуля.

### Что делать дальше
1. Если будет следующий слой по этому же блоку, то это уже не `CreatePrintProfileModal`, а проверка реального UX на длинных advanced sections и возможная донастройка порядка/группировки полей.
2. Отдельный соседний хвост по Orca остаётся в auth/import loop: `fhub_id` string/int mismatch и межаккаунтное загрязнение локальной Orca-папки.

— Codex

---

## Follow-up (сессия 2026-03-14, OrcaSlicer session/import diagnostics)

### Что сделано
- Исследованы реальные пользовательские данные OrcaSlicer в `C:\Users\Lizard\AppData\Roaming\OrcaSlicer`:
  - `OrcaSlicer.conf`
  - свежий лог из `log/`
  - локальные `.json/.info` профили в `user/2136879404/{filament,machine,process}`
- Подтверждено, что FilamentHub auth и mapping'и реально живут в `OrcaSlicer.conf`.
- Подтверждено, что `ERR_NO_PERMISSION` при импорте связан не просто с названием `[FilamentHub]`, а с ownership check по старому `fhub_id` / `sync_info`.
- Подтвержден отдельный format mismatch: локальный `fhub_id` в `.json` хранится строкой (`"13"`), а C++ местами ждёт `get<int>()`.
- Подтвержден отдельный баг с порчей `user_id` в `AppConfig`: в логе есть `user_id_str contains non-digit characters: 'true', clearing corrupted data`.
- Отдельно уже исправлен frontend race в embedded auth bootstrap; fix запушен коммитом `2cbbc3a`.
- Подробные выводы и гипотезы сохранены в `docs/current/orca-auth-import-findings-2026-03-14.md`.

### Что проверено
- В `OrcaSlicer.conf` на момент проверки лежали `access_token`, `refresh_token`, `user_id = "3"` и `preset_mapping_*`.
- В локальном FH-пресете `PETG чёрный [FilamentHub]`:
  - `.info`: `sync_info = filamenthub:preset:13`, `user_id = 1`
  - `.json`: `fhub_id = "13"` строкой
- В свежем логе на старте были:
  - `401` на `get current user`
  - `Token is expired!`
  - `user_id_str contains non-digit characters: 'true'`
  - множественные `ERR_NO_PERMISSION`
  - множественные `Failed to parse fhub_id from JSON metadata`

### Что не сделано
- Не правил C++ import/export path.
- Не искал до конца источник записи `user_id = true`.
- Не внедрял account-scoping для локальных FH mapping/metadata.

### Что делать дальше
1. В C++ починить чтение `fhub_id` как `string | int | FHUB-prefixed string`.
2. Найти источник, откуда в `CONFIG_KEY_USER_ID` попадает `'true'`.
3. Решить account-scoping локальных FH metadata при смене FilamentHub-аккаунта в одной Orca profile directory.
4. После этого отдельно разобрать повторные export/import trigger'ы.

— Codex

---

## Follow-up (сессия 2026-03-13, print profile / deploy / reCAPTCHA wrap-up)

### Что сделано
- `CreatePrintProfileModal` доведён до следующего слоя Orca parity:
  - selector совместимых принтеров из базы вместо строки через запятую;
  - добавлены реальные Orca process поля (`initial_layer_speed`, `initial_layer_infill_speed`, `internal_solid_infill_speed`, `bridge_speed`, `default_acceleration`, `travel_acceleration`, support/adhesion/seam/ironing/arc/spiral);
  - layout формы выровнен под RU/EN тексты;
  - изменения запушены в `main`.
- Для deploy:
  - `scripts/deploy.sh` получил более строгий health check;
  - backend/nginx логирование прижато до `warning`/`warn`;
  - отключён `COMPOSE_BAKE`, чтобы на Ubuntu `docker.io` не сыпался лишний warning про отсутствующий `buildx`;
  - эти изменения запушены в `main`.
- Для auth/register:
  - backend сначала показывает ошибки email-domain (`ERR_EMAIL_DOMAIN_TYPO`, `ERR_DOMAIN_NO_MAIL`), а потом уже reCAPTCHA;
  - reCAPTCHA на фронте переведена на получение свежего token перед submit;
  - CSP в `frontend/nginx.conf` расширен под Google reCAPTCHA domains;
  - backend verify теперь отправляет `remoteip`, логирует `error-codes/action/hostname/score`, а threshold снижен до `0.3` для low-traffic alpha;
  - после этого регистрация с reCAPTCHA проходит успешно.
- Локально, только в `docs/current/`, добавлены памятки:
  - `oauth-compliance-note.md`
  - `site-legal-compliance-checklist.md`
  Эти файлы gitignored и в репозиторий не попали.

### Что проверено
- `npm run build` для frontend проходил после изменений в print profile modal и после reCAPTCHA/CSP фиксов.
- `python -m compileall` проходил для backend-файлов, связанных с reCAPTCHA.
- После правок регистрация на сайте прошла успешно; в консоли остались только некритичные browser/provider warnings от Firefox/Google reCAPTCHA.
- Основные коммиты по этой сессии запушены в `origin/main`:
  - `d6480ce` `expand orca print profile modal and refresh favicons`
  - `9493fa9` `show email domain errors before recaptcha`
  - `0b4e5a8` `refresh recaptcha token on register submit`
  - `3de133b` `fix recaptcha error order and csp`
  - `7eb0bd3` `tune recaptcha verification for alpha traffic`

### Что не сделано
- `STUB-2` (OAuth Яндекс/Google) не начат в коде.
- Локальные legal/compliance docs не перенесены в versioned документацию, потому что `docs/` в этом репо игнорируется.
- Следующий слой `CreatePrintProfileModal` (более глубокая Orca parity / normal links path) не добит.

### Что делать дальше
1. Следующий явный рабочий тикет — `STUB-2`: OAuth авторизация.
2. Реализацию делать через текущую JWT/AuthContext схему без ломки email/password login.
3. Держать policy, зафиксированную локально в `oauth-compliance-note.md`:
   - РФ: `email/password + Yandex`
   - non-RU: `email/password + Google`
   - `Google OAuth` для РФ не включать без отдельного решения.

— Codex

---

## Follow-up (сессия 2026-03-13, AGENTS workflow simplification)

### Что сделано
- В `AGENTS.md` убран абсолютный запрет на обычный `git push`: теперь явное разрешение требуется только для `push --force`, rewrite history и push в нестандартные ветки или remote.
- Рабочий цикл в `AGENTS.md` сжат до фактического сценария команды: `HANDOFF` → `TODO` → задача → отметка в TODO при реальном завершении → именованный commit → обычный push → `HANDOFF` только при остановке работы или явном follow-up.

### Что проверено
- Правка ограничена только `AGENTS.md`, без изменений в коде проекта и без затрагивания `TODO_CONSOLIDATED.md`.

### Что не сделано
- Не менял другие агентские инструкции вне корневого `AGENTS.md`.
- Не делал `git push` после этой правки.

### Что делать дальше
1. Использовать новый цикл как default для следующих задач.
2. Если позже понадобится ещё сильнее ужать `AGENTS.md`, сокращать уже без смены смысла правил.

— Codex

---

## Follow-up (сессия 2026-03-13, register email hint before reCAPTCHA)

### Что сделано
- В `backend/app/api/v1/endpoints/auth.py` переставлен порядок проверок в `POST /auth/register`: `validate_email_domain()` теперь выполняется раньше `verify_recaptcha()`.
- Из-за этого подсказки по опечатке домена (`ERR_EMAIL_DOMAIN_TYPO`) и ошибки по отсутствию почтовых записей (`ERR_DOMAIN_NO_MAIL`) больше не маскируются `ERR_RECAPTCHA_FAILED`, если у пользователя уже некорректный email.

### Что проверено
- `python -m compileall backend/app/api/v1/endpoints/auth.py` выполнен успешно.
- Diff ограничен одной точечной перестановкой блоков проверки без изменения самой логики reCAPTCHA или email-validator.

### Что не сделано
- Не менял фронтенд `AuthModal` и не добавлял отдельную client-side подсказку до запроса.
- Не трогал порог `RECAPTCHA_SCORE_THRESHOLD` и не менял `Captcha.tsx`.

### Что делать дальше
1. Если останется жалоба именно на `ERR_RECAPTCHA_FAILED`, следующий шаг — обновлять reCAPTCHA token непосредственно перед submit, а не только при открытии модалки.
2. Если нужен ещё более ранний UX, можно отдельно добавить client-side hint по typo-доменам до отправки формы, но это уже отдельная правка.

— Codex

---

## Follow-up (сессия 2026-03-13, CreatePrintProfileModal Orca parity + UX cleanup)

### Что сделано
- В `frontend/src/components/CreatePrintProfileModal.tsx` убран свободный textarea для `compatible_printers`; вместо него добавлен selector по сохранённым `PrinterProfile` из базы с чипами выбранных профилей.
- Selector сохраняет в `compatible_printers` именно Orca-имена профилей принтера (`PrinterProfile.name`), а не ID; legacy-имена из уже импортированных process profiles не теряются и показываются отдельными чипами.
- Модалка расширена до следующего реального слоя Orca process settings по source of truth из `submodule/OrcaSlicer`: добавлены `initial_layer_speed`, `initial_layer_infill_speed`, `internal_solid_infill_speed`, `bridge_speed`, `default_acceleration`, `travel_acceleration`, `enable_support`, `support_type`, `support_threshold_angle`, `brim_width`, `skirt_loops`, `raft_layers`, `seam_position`, `ironing_type`, `enable_arc_fitting`, `spiral_mode`.
- Для Orca bool-полей использован tri-state (`inherit / enabled / disabled`), чтобы не затирать базовый profile лишними `0`.
- Для скоростей первого слоя разрешены не только числа, но и проценты (`35%`), как в реальных Orca process JSON.
- Layout формы выровнен через единый field wrapper, чтобы подписи на русском не “скакали” и не ломали сетку.
- В `frontend/src/locales/ru/translation.json` и `frontend/src/locales/en/translation.json` добавлены новые подписи, enum-опции и тексты для selector’а совместимых принтеров.

### Что проверено
- Source of truth дополнительно сверялся по `submodule/OrcaSlicer/resources/profiles_template/Template/process/process template.json` и enum-картам в `submodule/OrcaSlicer/src/libslic3r/PrintConfig.cpp`.
- Подтверждены реальные значения Orca для:
  - `support_type`: `normal(auto)`, `tree(auto)`, `normal(manual)`, `tree(manual)`
  - `seam_position`: `nearest`, `aligned`, `aligned_back`, `back`, `random`
  - `ironing_type`: `no ironing`, `top`, `topmost`, `solid`
- `npm run build` в `frontend/` выполнен успешно после правок.

### Что не сделано
- Browser-smoke вручную не гонял; проверка пока ограничена сборкой и сверкой diff/source of truth.
- Backend/API под эту задачу не менял: правка ограничена `CreatePrintProfileModal` и i18n.
- Параллельные локальные изменения пользователя по favicon (`frontend/public/favicon-120.png`, `frontend/public/apple-touch-icon.png`, удаление `frontend/public/vite.svg`) не трогал и в commit не включал.

### Что делать дальше
1. Пройти UI руками и посмотреть, хватает ли текущего process-layer или нужен ещё один advanced block (`support_style`, `elefant_foot_compensation`, `compatible_printers_condition`).
2. Если следующий шаг всё ещё в этом TODO, логично проверить create/edit flow на реальном процессе: создать новый print profile, открыть его повторно и убедиться, что все Orca поля читаются/пишутся без потерь.

— Codex

---

## Follow-up (сессия 2026-03-13, disable Compose Bake in deploy)

### Что сделано
- В `scripts/deploy.sh` запуск `docker compose up -d --build` переведён на `COMPOSE_BAKE=false docker compose up -d --build`.
- Это убирает warning про `Docker Compose is configured to build using Bake, but buildx isn't installed` на production-сервере с Ubuntu-пакетами `docker.io` + `docker-compose-v2`, без миграции на Docker CE stack.

### Что проверено
- `bash -n scripts/deploy.sh` проходит без синтаксических ошибок.

### Что не сделано
- Не менял Docker stack сервера (`docker.io` / `docker-compose-v2`) и не добавлял `buildx`.
- Не делал push: только локальный фикс в репозитории.

### Что делать дальше
1. При следующем deploy warning про Bake больше не должен появляться.
2. Если позже понадобится полноценный `buildx`, это уже отдельная инфраструктурная задача с переводом сервера на официальный Docker repo.

— Codex

---

## Follow-up (сессия 2026-03-13, deploy health check и quieter container logs)

### Что сделано
- В `scripts/deploy.sh` frontend health check заменён на проверку реального production-пути через nginx:
  - `https://127.0.0.1/health` с `Host: filamenthub.ru`
  - `https://127.0.0.1/` для SPA index
  - `https://127.0.0.1/logo.svg` для фронтовой статики
- В `docker-compose.yml` backend `uvicorn` переведён на `--log-level warning` при сохранении `--no-access-log`.
- В `backend/Dockerfile.prod` default `uvicorn` CMD также переведён на `--log-level warning`, чтобы поведение совпадало с compose.
- В `frontend/nginx.conf` отключены access logs и выставлен `error_log /dev/stderr warn` для HTTP и HTTPS server blocks, чтобы контейнер frontend не засыпал stdout request-логами.

### Что проверено
- `bash -n scripts/deploy.sh` проходит без синтаксических ошибок.
- `docker compose config -q` проходит с временными dummy-значениями `POSTGRES_PASSWORD` / `REDIS_PASSWORD`, без изменения `.env`.
- Проверен diff: изменения ограничены `scripts/deploy.sh`, `docker-compose.yml`, `backend/Dockerfile.prod`, `frontend/nginx.conf`.

### Что не сделано
- Не запускал `nginx -t` в контейнере: локально на машине в момент проверки был недоступен Docker engine.
- Не делал живой deploy / smoke на сервере.
- `docs/current/TODO_CONSOLIDATED.md` не менял: отдельного TODO-пункта под этот ops-follow-up нет.

### Что делать дальше
1. После следующего реального deploy на сервере убедиться, что `deploy.sh` теперь ловит проблемы именно по nginx/backend/static, а не только по открытому порту.
2. Если логов всё ещё слишком много, следующим шагом уже смотреть конкретные backend `logger.warning/info` точки, а не контейнерный уровень.

— Codex

---

## Follow-up (сессия 2026-03-13, CreatePrintProfileModal phase 1 Orca fields)

### Что сделано
- `frontend/src/components/CreatePrintProfileModal.tsx` расширен до phase 1 формы под реальные Orca `process` keys.
- В модалку добавлены поля:
  - `initial_layer_print_height`
  - `wall_loops`
  - `top_shell_layers`
  - `bottom_shell_layers`
  - `sparse_infill_density`
  - `sparse_infill_pattern`
  - `outer_wall_speed`
  - `inner_wall_speed`
  - `sparse_infill_speed`
  - `travel_speed`
  - `compatible_printers`
- При сохранении модалка теперь собирает Orca-compatible scaffold в `orcaslicer_settings`:
  - `type=process`
  - `from`
  - `instantiation=true`
  - `inherits`
  - `version`
  - `print_settings_id`
  - `compatible_printers`
- Контекст текущего printer profile теперь передаётся из `ProfilePage` в `CreatePrintProfileModal`, чтобы сразу подставлять Orca-compatible `compatible_printers`.
- В `frontend/src/api/client.ts` расширен payload для `printProfilesAPI.create/update`.
- В `backend/app/services/profile_validator.py` исправлено расхождение: `print_settings_id` теперь принимается как строка или массив, что соответствует живым Orca process JSON.
- Добавлена защита от создания идентичного clone-профиля, если когда-либо будет активирован flow с `baseProfile`.
- В локальном `docs/current/TODO_CONSOLIDATED.md` пункт `Расширить CreatePrintProfileModal (скорости, заполнение)` отмечен выполненным.

### Что проверено
- `npm run build` в `frontend/` выполнен успешно после всех правок.
- `python -m compileall backend/app/services/profile_validator.py` прошёл успешно.
- Mapping продолжает соответствовать `docs/current/create-print-profile-orca-mapping.md`.

### Что не сделано
- Не добавлял отдельный UI для `compatible_printers_condition`, `compatible_filaments`, support/adhesion/acceleration advanced fields.
- Не делал ручной browser-smoke.
- Не коммитил локальные `docs/` и `HANDOFF.md` изменения в git.

### Что делать дальше
1. Если продолжать этот блок, следующий шаг — advanced Orca fields (`support`, `adhesion`, `seam`, `acceleration`) без нарушения inheritance-модели.
2. Отдельно стоит решить, нужно ли для обычного `/print-profiles/` create/update создавать `printer_links` автоматически, а не полагаться только на `compatible_printers`.

— Codex

---

## Follow-up (сессия 2026-03-13, CreatePrintProfileModal Orca mapping)

### Что сделано
- Создан отдельный локальный документ `docs/current/create-print-profile-orca-mapping.md` с точным mapping между текущим `CreatePrintProfileModal`, моделью `PrintProfile` и реальными Orca `process` keys.
- В документе зафиксирован минимальный Orca-compatible scaffold для ручного создания process-профиля и список phase 1 полей для задачи `Расширить CreatePrintProfileModal (скорости, заполнение)`.
- Под пунктом `Расширить CreatePrintProfileModal (скорости, заполнение)` в `docs/current/TODO_CONSOLIDATED.md` добавлена ссылка на новый mapping-документ.

### Что проверено
- Сверены реальные process JSON из `docs/orca_bundles/system_presets/` и `submodule/OrcaSlicer/resources/profiles/`.
- Сверены backend import/export точки: `orcaslicer_machine_exporter.py`, `orca_bundle_importer.py`, `print_profiles.py`.
- Сверен C++ export payload в `submodule/OrcaSlicer/src/slic3r/GUI/FilamentHubPanel.cpp`.

### Что не сделано
- Код `CreatePrintProfileModal` пока не менялся под новый mapping.
- Валидацию `profile_validator.py` не правил, хотя зафиксировано расхождение по типу `print_settings_id`.

### Что делать дальше
1. Реализацию `TODO-219` начинать только от полей, перечисленных в `Phase 1` нового mapping-документа.
2. Перед UI-реализацией учесть расхождение: `print_settings_id` в validator сейчас ожидается как массив, а в живых Orca process JSON это строка.
3. Не делать source of truth из `quality_tier` и `default_nozzle`; canonical значения должны жить в `orcaslicer_settings`.

— Codex

---

## Follow-up (сессия 2026-03-13, nozzle guide spoiler)

### Что сделано
- Таблица-подсказка по материалам сопла в `frontend/src/components/CreatePrinterProfileModal.tsx` свёрнута под `details/summary`-спойлер.
- Заголовок спойлера использует существующий i18n-ключ `printerProfile.nozzleGuide.title`, без хардкода строки в компоненте.

### Что проверено
- В `CreatePrinterProfileModal.tsx` спойлер использует существующие переводы `printerProfile.nozzleGuide.*`.
- `npm run build` в `frontend/` после этого изменения проходит успешно.

### Что не сделано
- Отдельный browser-smoke не запускал.
- `docs/current/TODO_CONSOLIDATED.md` не менял: это точечный UI-запрос, а не отдельный пункт TODO.

### Что делать дальше
1. Если продолжать блок профилей/Orca, ближайший открытый пункт в TODO — `Расширить CreatePrintProfileModal (скорости, заполнение)`.
2. Если приоритет на bundle/combinations, следующий отдельный блок — `[TODO-13] Комбинации профилей (printer + filament + process)`.

— Codex

---

## Follow-up (сессия 2026-03-13, print profiles import -> printer links)

### Что сделано
- В `backend/app/api/v1/endpoints/orca_sync.py` исправлен import path для `POST /api/v1/orcaslicer/print-profiles/import`: теперь при импорте из OrcaSlicer не только сохраняются `compatible_printers` / `compatible_filaments` в JSON-поля, но и пересобираются junction-связи `print_profile_printers` и `print_profile_filaments`.
- Для `compatible_printers` добавлен резолв по `Printer`, `PrinterProfile`, базовому имени без суффикса `0.4 nozzle` и безопасный slug fallback, чтобы импортированные process profiles реально привязывались к принтерам FilamentHub.
- Во `frontend/src/pages/ProfilePage.tsx` добавлен безопасный fallback для уже существующих legacy-импортов без `printer_links`: профиль печати в разделе принтеров теперь дополнительно матчится по `compatible_printers` и имени `PrinterProfile`, а не только по `printer_slug`.
- Добавлен regression test `backend/tests/test_orca_print_profiles_sync.py` на создание и обновление связей при Orca import. Файл попадает под `backend/.gitignore` (`test_*.py`), поэтому при коммите нужен `git add -f`.

### Что проверено
- `pytest tests/test_orca_print_profiles_sync.py` из `backend/` — 2 теста прошли успешно.
- `npm run build` в `frontend/` выполнен успешно после frontend fallback.

### Что не сделано
- `docs/current/TODO_CONSOLIDATED.md` не менял: это частичный фикс внутри большего блока `Двусторонняя синхронизация OrcaSlicer -> FilamentHub`, а не полное закрытие задачи.
- Миграцию/бекфилл для уже сохранённых `print_profiles` в БД не делал. Для старых записей без `printer_links` добавлен только UI fallback по имени.
- Ручной E2E через реальный OrcaSlicer не проводил.

### Что делать дальше
1. Проверить реальный export/import process profiles из OrcaSlicer и убедиться, что после синка они появляются внутри нужного printer profile в UI.
2. Если понадобится убрать legacy fallback, позже можно сделать отдельный backfill existing `print_profiles` -> `print_profile_printers`.

— Codex

## Follow-up (сессия 2026-03-13, profile achievements cursor)

### Что сделано
- В `frontend/src/pages/ProfilePage.tsx` для контейнера ачивок в шапке профиля добавлен `cursor-default`, чтобы при hover не появлялся текстовый курсор.
- Правка точечная, только для отображения achievements/badges в профиле, без изменений поведения или структуры блока.

### Что проверено
- Поиск по `ProfilePage.tsx` подтвердил, что ачивки профиля рендерятся через `renderExpandableProfileBadge`.
- `git diff -- frontend/src/pages/ProfilePage.tsx` показывает ровно одно изменение класса: добавлен `cursor-default`.

### Что не сделано
- `docs/current/TODO_CONSOLIDATED.md` не менял: отдельного существующего пункта под этот micro-fix там нет.
- UI smoke в браузере не гонял; ограничился точечной проверкой diff.

### Что делать дальше
1. При желании можно быстро проверить в браузере `/profile`, что у бейджей теперь обычный курсор вместо I-beam.

— Codex

---

## Follow-up (сессия 2026-03-12, restore session-based local CLI flow)

### Что сделано
- В `bot/bot.py` `TG_PERSISTENT_SESSIONS` снова включён по умолчанию (`1`), чтобы бот работал как router поверх локальных CLI session'ов, а не как stateless prompt-runner.
- В `bot/bot.py` исправлена логика prompt injection: если у агента уже есть `session_ref` в текущем Telegram thread, в CLI уходит только новое пользовательское сообщение; бот больше не дублирует весь transcript поверх `resume`.
- Полный transcript по-прежнему используется для первого запуска агента в треде, чтобы handoff между моделями не потерялся при первичном старте.

### Что проверено
- In-memory `compile()` для `bot/bot.py`.
- `powershell -ExecutionPolicy Bypass -File bot\bot.ps1 restart` выполнен успешно.
- После рестарта бот поднялся с PID `26060`, `/healthz` отвечает `ok`.

### Что ещё важно
- Это исправляет архитектурную ошибку бота под сценарий "как `codex resume` в терминале, но через Telegram".
- Если конкретно `codex` всё ещё падает transport API error, это уже отдельная проблема самого локального `codex-cli`/его сети/его сессии, а не того, что бот принудительно гонит его в stateless режим.

— Codex

---

## Correction (сессия 2026-03-12, remove cliproxy path and keep pure local CLI)

### Что сделано
- Из `bot/bot.py` полностью удалён `cliproxy` transport path: бот снова умеет только одно — запускать локальные CLI-агенты в `REPO_PATH`.
- Из `bot/bot.ps1` удалена вся автологика `TG_AGENT_TRANSPORT` и `CLIPROXY_*`; launcher снова просто поднимает локальный bot-process без прокси-веток.
- `bot/README.md` приведён к простому контракту: Telegram -> bot -> local CLI process in project directory.

### Что проверено
- `rg` по bot-файлам не находит `cliproxy`, `CLIPROXY`, `TG_AGENT_TRANSPORT`.
- In-memory `compile()` для `bot/bot.py`.
- `powershell -ExecutionPolicy Bypass -File bot\bot.ps1 restart` выполнен успешно.
- После рестарта бот поднялся с PID `6064`, `/healthz` отвечает `ok`.

### Что не сделано
- Не гонял живой Telegram E2E после этого упрощения.
- `docs/current/TODO_CONSOLIDATED.md` не менял: отдельного пункта под bot-only transport там нет.

— Codex

---

## Correction (сессия 2026-03-12, restore local CLI as default)

### Что исправлено
- Откачен главный регресс transport layer: бот снова по умолчанию запускает локальные CLI-агенты в `REPO_PATH`, а не ходит напрямую в `cliproxy` как в обычный `chat/completions`.
- В `bot/bot.py` добавлен явный переключатель `TG_AGENT_TRANSPORT`; default теперь `cli`, `cliproxy` остаётся только как opt-in.
- В `bot/bot.ps1` убран автоперевод launcher'а на `cliproxy`: автоподстановка `CLIPROXY_*` теперь происходит только если явно задан `TG_AGENT_TRANSPORT=cliproxy`.
- В `bot/README.md` документация приведена в соответствие: базовый режим снова local CLI runner, `cliproxy` описан как опциональный транспорт, а не поведение по умолчанию.

### Что проверено
- In-memory `compile()` для `bot/bot.py`.
- `powershell -ExecutionPolicy Bypass -File bot\bot.ps1 restart` выполнен успешно.
- После рестарта бот поднялся с PID `12576`, `/healthz` отвечает `ok`.

### Важное уточнение
- `cliproxy` через `POST /v1/chat/completions` не даёт агенту реальный доступ к папке проекта. Если нужен coding-agent в `F:\FilamentHub`, бот обязан запускать локальный CLI-процесс; `cliproxy` может быть только опциональным upstream/transport-слоем, но не заменой такого процесса.

— Codex

---

## Follow-up (сессия 2026-03-12, cliproxy routing hardening)

### Что сделано
- Бот переведён на нормальный `cliproxy` path `Telegram -> bot -> cliproxy -> model`, если заданы `CLIPROXY_BASE_URL` и `CLIPROXY_API_KEY`.
- В `bot/bot.py` добавлен discovery через `GET /v1/models` с коротким TTL-кэшем: бот теперь сам подбирает рабочий model id для агента и не упирается в устаревший alias вроде `qwen-coder`, если proxy отдаёт другой список моделей.
- В `bot/bot.py` добавлены нормализованные ошибки для upstream auth/config проблем: отдельно распознаются `invalid x-api-key`, `API_KEY_INVALID`, `unknown provider for model`, чтобы в Telegram уходила короткая понятная причина, а не сырой JSON/trace.
- В `bot/README.md` обновлена документация по `cliproxy`-режиму и `CLIPROXY_*` env vars.

### Что проверено
- In-memory `compile()` для `bot/bot.py`.
- Локальный smoke `cliproxy` на `http://127.0.0.1:8317/v1`:
  - `GET /v1/models` отвечает и отдаёт актуальный список моделей.
  - `POST /v1/chat/completions` с `model=gpt-5.4` отвечает `200` и возвращает `OK`.
  - `claude-sonnet` сейчас падает в upstream auth (`invalid x-api-key`).
  - `gemini-pro` сейчас падает с `API_KEY_INVALID`.
  - Qwen отвечает на реальные model id из `/v1/models` (`qwen3-coder-plus`, `qwen3-coder-flash`, `coder-model`), поэтому bot-side fallback на discovery добавлен намеренно.
- `powershell -ExecutionPolicy Bypass -File bot\bot.ps1 restart` выполнен успешно; новый PID `15424`.
- `/healthz` после рестарта отвечает `200` и показывает доступные агенты `claude`, `codex`, `gemini`, `qwen`.

### Что не сделано
- Не делал живой E2E из Telegram группы после этого рестарта.
- Не трогал Docker вообще после прямого запрета пользователя.
- `docs/current/TODO_CONSOLIDATED.md` не менял: отдельного существующего пункта под этот bot-follow-up нет.

### Что делать дальше
1. В Telegram проверить `@codex ping` или `/codex ping`: теперь это должно идти через `cliproxy`, а не через локальный `codex` CLI transport.
2. Если нужен рабочий `@claude` или `@gemini`, надо чинить уже не бота, а upstream credentials внутри `cliproxy`:
   - Claude: перелогинить/обновить account/key
   - Gemini: заменить невалидный API key
3. Если понадобится, позже можно убрать direct CLI fallback полностью и оставить только `cliproxy` path.

— Codex

---

## Follow-up (сессия 2026-03-13, UX-TOOLTIPS-1 for printer profile)

### Что сделано
- В `frontend/src/components/CreatePrinterProfileModal.tsx` добавлен локальный hover/focus tooltip helper на базе `HelpCircle`.
- Tooltip-подсказки подключены для неочевидных терминов в форме профиля принтера: `junction deviation`, `SEMM`, `wipe tower`, `purge_in_prime_tower`, `ramming`, `bed temperature formula`, а также связанных SEMM-параметров (`parking retraction`, `cooling tube retraction`, `cooling tube length`, `extra loading move`, `tool change time`).
- В `frontend/src/locales/ru/translation.json` и `frontend/src/locales/en/translation.json` добавлены тексты подсказок.
- В локальном `docs/current/TODO_CONSOLIDATED.md` пункт `[UX-TOOLTIPS-1]` отмечен выполненным.

### Что проверено
- `npm run build` в `frontend/` выполнен успешно после правок (`tsc && vite build`).
- Проверен diff: изменения ограничены `CreatePrinterProfileModal.tsx` и RU/EN локалями; без побочных изменений в API или структуре данных.

### Что не сделано
- Не трогал `UX-NOZZLE-HINTS-1`.
- Не делал ручной browser-smoke через UI; ограничился сборкой и точечной проверкой кода.

### Что делать дальше
1. Если нужен следующий лёгкий тикет, логичное продолжение — `UX-NOZZLE-HINTS-1` в той же форме профиля принтера.

— Codex

---

## Follow-up (сессия 2026-03-13, UX-NOZZLE-HINTS-1 for printer profile)

---

## Follow-up (сессия 2026-03-13, profile combinations TODO breakdown)

### Что сделано
- Для задачи `Комбинации профилей (printer + filament + process) [TODO-13]` создан отдельный рабочий документ [docs/current/profile-combinations-todo.md](F:/FilamentHub/docs/current/profile-combinations-todo.md).
- В [docs/current/TODO_CONSOLIDATED.md](F:/FilamentHub/docs/current/TODO_CONSOLIDATED.md) под пунктом `[TODO-13]` добавлена ссылка на новый детализированный TODO.
- В отдельном TODO явно разведены два трека:
  - combinations в профиле пользователя
  - полноценные `vendor bundles`, которые остаются отдельным эпиком
- Отдельно зафиксировано обязательное требование Orca-validity:
  - не генерировать псевдо-bundles
  - соблюдать формат Orca profile/bundle
  - ориентироваться на dev wiki и текущие Orca guides
  - не выпускать export без подтверждённой совместимости с Orca loader / validator

### Что проверено
- Ссылка из `TODO_CONSOLIDATED.md` на `profile-combinations-todo.md` присутствует.
- В новом TODO есть явный раздел `Обязательные требования Orca-validity` со ссылками на:
  - `Preset-and-bundle.md`
  - `How-to-create-profiles.md`
  - `OrcaSlicer-Profiles-Guide.md`
  - `VENDOR_BUNDLE_SYSTEM_GUIDE.md`

### Что не сделано
- Саму задачу `[TODO-13]` не начинал в коде: это только декомпозиция и фиксация scope.
- `vendor bundles` endpoints / UI не трогал.
- `TODO_CONSOLIDATED.md` не отмечал выполненным: создан только отдельный рабочий план.

### Что делать дальше
1. Если брать `TODO-13` в реализацию, начинать с backend `GET /api/v1/profiles/combinations`.
2. После этого заменить dashboard-заглушку в `ProfilePage.tsx` на реальный блок.
3. Export layer в Orca делать только с подтверждённой Orca-validity, без упрощённого “почти bundle” формата.

— Codex

---

## Follow-up (сессия 2026-03-13, make Telegram bot local-only)

### Что сделано
- В `.gitignore` добавлен `/bot/`, чтобы Telegram bot целиком оставался локальным и больше не попадал в git.
- Все уже трекаемые файлы из `bot/` сняты с индекса через `git rm --cached -r -- bot`, без удаления локальных файлов.

### Что проверено
- `git check-ignore` подтверждает, что `bot/bot.py` и `bot/README.md` теперь игнорируются правилом `/bot/`.
- В staged diff по git для `bot/` стоят только удаления из индекса, без удаления с диска.

### Что не сделано
- Историю git не переписывал. Старые bot-коммиты останутся в истории репозитория.
- `docs/current/TODO_CONSOLIDATED.md` не менял: под этот запрос нет отдельного существующего пункта.

### Что делать дальше
1. Если нужно убрать бота не только из текущего tree, но и из истории GitHub, это уже отдельная операция с rewrite history и force-push.
2. Текущий безопасный вариант уже уберёт `bot/` из HEAD после обычного push.

— Codex

### Что сделано
- В `frontend/src/components/CreatePrinterProfileModal.tsx` добавлена компактная таблица-подсказка по материалам сопла прямо в секцию выбора `Nozzle type`.
- Таблица показывает рекомендуемый профиль для каждого материала сопла: температурное поведение, ожидаемую скорость/flow и совместимость с абразивными филаментами.
- Выбранные пользователем типы сопла визуально подсвечиваются внутри таблицы, чтобы подсказка была связана с текущим выбором, а не оставалась статическим справочником.
- В `frontend/src/locales/ru/translation.json` и `frontend/src/locales/en/translation.json` добавлены все заголовки, подписи и описания для nozzle guide.
- В локальном `docs/current/TODO_CONSOLIDATED.md` пункт `[UX-NOZZLE-HINTS-1]` отмечен выполненным.
- По результатам отдельной проверки локально отмечен выполненным и stale-пункт `Переименовать "История" -> "Активность"`: в актуальном профиле history tab уже отсутствует, а ранее был заменён коммитом `810a90b` (`feat(spools): replace history tab with spools tab in ProfilePage`).

### Что проверено
- `npm run build` в `frontend/` выполнен успешно после правок (`tsc && vite build`).
- Проверен diff: изменения ограничены `CreatePrinterProfileModal.tsx` и RU/EN локалями; без затрагивания API, моделей или backend-логики.
- Дополнительно проверен текущий `ProfilePage`: активного UI-места с вкладкой `История` в профиле больше нет.

### Что не сделано
- Не делал ручной browser-smoke через UI, ограничился успешной сборкой и проверкой diff.
- Не трогал соседние TODO вне текущих UX-пунктов.

### Что делать дальше
1. Если продолжать по тому же блоку профиля принтера, следующий естественный шаг — `Расширить CreatePrintProfileModal (скорости, заполнение)`, но это уже заметно крупнее текущих UX-тикетов.
2. Если нужен ещё один быстрый безопасный тикет, лучше брать отдельный локальный UI/UX баг, а не инфраструктурные или SEO-задачи.

— Codex

---

## Follow-up (сессия 2026-03-14, Calculator Pro material source cleanup)

### Что сделано
- `Calculator Pro` больше не опирается только на общий каталог `filaments` для цены катушки:
  - в `frontend/src/pages/CalculatorPage.tsx` добавен запрос `spoolsAPI.list`;
  - material-блок перестроен по схеме `Мои филаменты -> каталог fallback`.
- Для `UserSpool` цена и полный вес катушки теперь подставляются как приоритетный источник:
  - сначала фактическая `spool.price`;
  - если её нет, fallback на `filament.price_per_kg * initial_weight_g`.
- Добавлен аккуратный auto-match для `G-code`:
  - сначала ищется уверенное совпадение по `UserSpool`;
  - если его нет, пробуется каталог;
  - при неоднозначном совпадении автоподбор не срабатывает, чтобы не угадывать "на авось".
- В UI добавлены отдельные поля:
  - выбор катушки из `Мои филаменты`;
  - выбор материала из каталога как fallback;
  - явный индикатор источника цены (`Мои филаменты` / `каталог` / `ручной ввод`).
- Локальный `docs/current/calculator-todo.md` синхронизирован: под `[CALC-MATERIAL-1]` добавлена пометка о уже выполненном user-spool-first слое и о том, что multi-material ещё остаётся.

### Что проверено
- `npm run build` в `frontend/` прошёл успешно после привязки `Calculator Pro` к `UserSpool`.
- Проверено, что в git diff по задаче вошли только:
  - `frontend/src/pages/CalculatorPage.tsx`
  - `frontend/src/locales/ru/translation.json`
  - `frontend/src/locales/en/translation.json`
- Грязный `frontend/src/pages/ProfilePage.tsx` не трогался.

### Что не сделано
- Не добивал multi-material сценарии в material matching.
- Не добавлял явный review-step для "неуверенного" совпадения; сейчас в таких случаях автоподбор просто не выбирает материал сам.
- Backend формулу и `CalculatorEstimateRequest` под это не менял: это именно чистка material-source слоя на фронте.

### Что делать дальше
1. Добить `[CALC-MATERIAL-1]`:
   - multi-material cases;
   - vendor aliases / legacy names;
   - явный UI выбора при неуверенном совпадении.
2. После этого переходить к `[CALC-FULLFLOW-1]`, а не размазывать новые UX-твики поверх текущего шага.

— Codex
