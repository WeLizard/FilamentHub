# Telegram Bot TODO

> Подробный backlog для bot-обвязки
> Обновлено: 10 марта 2026
> Статус: в работе, базовый thread-scoped рефактор уже внедрён

---

## Зачем это нужно

Текущий `bot/bot.py` работает как glue-script вокруг CLI-агентов:
- состояние сессий хранится в памяти процесса
- routing завязан на один `active_agent`
- команды агентов собираются вручную
- parallel/multi-agent сценарии почти не оформлены как системная модель
- inter-agent handoff не прозрачен для пользователя

Для бота нужен не просто Telegram launcher, а небольшой диспетчер сессий:
- можно обращаться к разным агентам в одном Telegram topic
- можно держать отдельные persistent sessions по агентам
- можно звать нескольких агентов параллельно
- можно передавать контекст между агентами, но это должно быть видно в чате

---

## Обязательные требования

### 1. Thread-scoped state

Единица контекста:
- `telegram chat + topic` для форумов
- `telegram chat` для DM/обычных чатов

В каждом таком контексте нужно хранить:
- `active_agent`
- `session_id` или эквивалент для каждого агента
- список активных run'ов
- последние сообщения/результаты для адресации и handoff

Ключевая модель:
- `telegram:{chat_id}:{topic_id_or_dm}:{agent}`

### 2. Несколько агентов одновременно

Бот должен поддерживать:
- явный вызов конкретного агента: `@codex`, `@claude`, `@gemini`
- переключение активного агента в текущем треде: `/use codex`
- параллельный вызов нескольких агентов: `/ask codex,claude <prompt>`
- отдельные независимые сессии агентов в рамках одного и того же треда

### 3. Видимый inter-agent handoff

Если один агент передаёт задачу другому, это должно быть видно пользователю:
- событие в чате: `Codex -> Claude`
- краткий контекст передачи
- отдельный ответ получателя в том же треде

Никакой скрытой внутренней переписки без внешнего следа.

### 4. Persistent sessions

Нельзя держать всё только в RAM.

Нужен persistent store:
- JSON как минимальный старт
- либо SQLite, если JSON начнёт мешать параллельности

В store хранить:
- thread bindings
- active agent per thread
- agent session keys/ids
- run metadata
- optional audit trail

### 5. Secure transport

Нужно закрыть текущие дыры:
- webhook secret
- hook secret / signature policy
- health endpoint
- нормальная диагностика старта и статуса

---

## Минимальный UX-контракт

### Базовые команды

- `/use <agent>`
  - переключить активного агента в текущем треде
- `/status`
  - показать active agent, открытые сессии, занятые run'ы
- `/ask <agent1,agent2,...> <prompt>`
  - отправить один prompt нескольким агентам параллельно
- `/pass <agent> <prompt>`
  - передать текущий контекст выбранному агенту с явным логом handoff
- `/new [agent]`
  - сбросить session только для одного агента или для текущего активного
- `/kill [agent|run_id]`
  - остановить конкретный run

### Message routing

- сообщение без префикса идёт в `active_agent`
- `@codex ...` идёт в `codex`, не меняя `active_agent`, если не оговорено отдельно
- `@claude @codex ...` трактуется как multi-agent invocation только через явный `/ask`, без магии

---

## Архитектура минимального production-ready решения

### Слой 1. Telegram transport

Отвечает за:
- parsing команд и mentions
- вычисление thread key
- отправку сообщений/статусов/ошибок
- visible event log

### Слой 2. Session store

Отвечает за:
- `thread -> active_agent`
- `thread + agent -> session`
- `run_id -> process metadata`
- persistent read/write

### Слой 3. Agent adapters

Отдельный адаптер на каждого агента:
- `codex`
- `claude`
- `gemini`
- возможно `qwen`, если останется в use

У каждого адаптера должен быть единый контракт:
- `start(prompt, context)`
- `resume(prompt, session_ref, context)`
- `cancel(run_ref)`
- `status(run_ref)`
- `extract_final_output(raw_output)`

Нельзя продолжать расширять giant `if/elif` внутри одного `build_cmd()`.

### Слой 4. Run manager

Отвечает за:
- запуск процессов
- tracking параллельных run'ов
- timeouts / cancellation
- stream/finish events
- публикацию agent lifecycle events в чат

---

## Что брать из OpenClaw, а что не брать

Полезно взять как ориентир:
- thread-scoped Telegram routing
- persistent session state
- Windows spawn resolution для `.cmd/.bat` wrappers
- secure webhook secret + health endpoint

Не надо тащить целиком:
- весь ACP runtime
- всю их plugin/command ecosystem
- весь их transport stack

Для бота нужен упрощённый вариант:
- lightweight dispatcher
- adapters над CLI
- минимальный persistent store
- явная observability в Telegram

---

## Этапы

### Этап 1. State model и routing

- [x] Убрать глобальный `active_agent`
- [x] Ввести `thread_key`
- [x] Ввести persistent thread state
- [x] Ввести `thread + agent -> session_ref`

### Этап 2. Agent adapters

- [x] Вынести `codex` adapter из `build_cmd`
- [x] Вынести `claude` adapter
- [x] Вынести `gemini` adapter
- [x] Вынести общую модель adapter contract

Примечание:
- `qwen` и `gemini` сейчас работают как stateless adapters, пока не подтверждён их явный session-id contract

### Этап 3. Multi-agent UX

- [x] Реализовать `/use`
- [x] Реализовать `/status`
- [x] Реализовать `/ask`
- [x] Реализовать `/pass`
- [x] Поддержать `@agent` routing

### Этап 4. Visible handoff и observability

- [x] Логировать handoff-события в чат
- [x] Показывать start / running / done / failed
- [ ] Нормализовать вывод агентов без ad-hoc мусора

### Этап 5. Security и operations

- [x] Добавить секрет для `/hook`
- [x] Добавить проверку GitHub webhook signature
- [x] Добавить health endpoint
- [x] Привести `bot.ps1` / launcher к модели одного источника статуса

### Этап 6. Cleanup legacy glue

- [x] Удалить зависимость от RAM-only `agent_has_session`
- [x] Убрать giant `build_cmd` как точку расширения
- [x] Убрать скрытую ad-hoc логику `@agent` injection без event trail

---

## Не делать без отдельного решения

- Не тащить весь OpenClaw ACP внутрь бота
- Не вводить скрытую “внутреннюю беседу” агентов без логирования в чат
- Не завязывать архитектуру только на один агент
- Не хранить source of truth по сессиям только в оперативной памяти

---

## Критерий готовности

Можно считать задачу закрытой, когда:
- в одном Telegram topic можно независимо работать минимум с `codex` и `claude`
- можно явно переключаться между агентами
- можно запускать хотя бы 2 агента параллельно
- можно делать handoff между агентами с видимым trail в чате
- перезапуск бота не теряет agent-thread bindings
- webhook/hook защищены минимум секретом
