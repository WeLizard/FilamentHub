# HANDOFF — FilamentHub

> Last updated: 2026-03-10 23:30 by Claude

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
