# Telegram Bot TODO

> Отдельный backlog для bot-обвязки вокруг FilamentHub
> Не входит в основной `docs/current/TODO_CONSOLIDATED.md`
> Обновлено: 10 марта 2026

Подробная проработка:
- `bot/telegram-bot-todo.md`
- `bot/HANDOFF.md`

---

## Цель

Перевести текущий `bot/bot.py` из glue-script состояния в отдельный thread-scoped multi-agent dispatcher:
- несколько агентов в одном Telegram topic
- persistent sessions по агентам
- переключение между агентами
- параллельные вызовы
- видимый inter-agent handoff в чате

---

## Требования

- [x] Thread-scoped state вместо одного глобального `active_agent`
- [x] Persistent store для `thread -> active_agent` и `thread + agent -> session`
- [x] Явное переключение агента: `/use <agent>`
- [x] Явный вызов агента: `@codex`, `@claude`, `@gemini`
- [x] Параллельные вызовы: `/ask codex,claude <prompt>`
- [x] Видимый handoff: `/pass <agent> <prompt>` с event trail в чате
- [x] Нормальный `/status` по активным run'ам и сессиям
- [x] Agent adapters вместо giant `build_cmd()`
- [x] Secure webhook/hook: secret, signature policy, health endpoint
- [ ] Нормальный Windows spawn layer для `.cmd/.bat` wrappers

Ограничение текущего среза:
- `claude` и `codex` используют persistent session refs
- `qwen` и `gemini` пока работают как stateless adapters, пока не подтверждён их явный session contract

---

## Этапы

### Этап 1. State model

- [x] Ввести `thread_key`
- [x] Убрать RAM-only source of truth
- [x] Ввести persistent thread/session store

### Этап 2. Agent adapters

- [x] Вынести `codex` adapter
- [x] Вынести `claude` adapter
- [x] Вынести `gemini` adapter
- [x] Нормализовать контракт `start / resume / cancel / parse_result`

### Этап 3. Multi-agent UX

- [x] Реализовать `/use`
- [x] Реализовать `/ask`
- [x] Реализовать `/pass`
- [x] Реализовать `/status`
- [x] Поддержать `@agent` routing без скрытой магии

### Этап 4. Operations / security

- [x] Добавить webhook secret
- [x] Добавить GitHub webhook signature verification
- [x] Добавить health endpoint
- [ ] Привести launcher к одному источнику статуса

---

## Референс

- `OPENCLAW/wt-sync-main-clean`
- Полезные ориентиры:
  - thread-scoped Telegram routing
  - persistent session state
  - Windows spawn resolution
  - secure webhook mode
