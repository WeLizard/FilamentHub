# FHAgents Telegram Bot

Telegram-бот вокруг FilamentHub для multi-agent работы в одном Telegram чате: `claude`, `codex`, `qwen`, `gemini`, GitHub issues и project docs.

Отдельный backlog по самому боту:
- `bot/TODO.md`
- `bot/telegram-bot-todo.md`
- `bot/HANDOFF.md`

## Что уже умеет

- thread-scoped state: у каждого Telegram thread свой `active_agent`
- persistent sessions по агентам внутри thread
- явное переключение `/use <agent>`
- явный вызов `/claude`, `/codex`, `@claude`, `@codex`
- параллельные запуски `/ask codex,claude <prompt>`
- видимый handoff `/pass <agent> [prompt]`
- webhook `/hook`, GitHub webhook `/github`, health check `/healthz`

Ограничение текущего среза:
- `claude` и `codex` используют persistent session refs
- `qwen` и `gemini` пока stateless, пока не зафиксирован их session contract

## Архитектура

```text
Telegram thread
  -> bot.py transport/router
  -> state_store.py (thread state + agent sessions)
  -> agent_adapters.py (claude/codex/qwen/gemini)
  -> CLI agent processes
```

Основные файлы:
- `bot/bot.py` — Telegram transport, routing, webhook server
- `bot/agent_adapters.py` — adapters и сборка команд для CLI-агентов
- `bot/state_store.py` — persistent JSON store для thread/session state
- `bot/bot.ps1` — локальный Windows launcher

## Команды

### Agent routing

| Команда | Действие |
|---------|----------|
| `/use <agent>` | Выбрать активного агента в текущем thread |
| `/claude <prompt>` | Отправить prompt в Claude и сделать его active |
| `/qwen <prompt>` | Отправить prompt в Qwen и сделать его active |
| `/gemini <prompt>` | Отправить prompt в Gemini и сделать его active |
| `/codex <prompt>` | Отправить prompt в Codex и сделать его active |
| `@claude ...` | Явный route в Claude без переключения active agent |
| `@codex ...` | Явный route в Codex без переключения active agent |

### Multi-agent

| Команда | Действие |
|---------|----------|
| `/ask codex,claude <prompt>` | Один prompt нескольким агентам параллельно |
| `/pass <agent> [prompt]` | Передать last output активного агента другому агенту |

### Sessions / runs

| Команда | Действие |
|---------|----------|
| `/status` | Статус текущего thread |
| `/sessions` | Алиас для `/status` |
| `/who` | Все активные run'ы по боту |
| `/new [agent|all]` | Сбросить session в текущем thread |
| `/kill [agent|run_id|all]` | Остановить run'ы в текущем thread |

### Project / docs

| Команда | Действие |
|---------|----------|
| `/task <текст>` | Создать GitHub Issue |
| `/issue <текст>` | Алиас для создания GitHub Issue |
| `/docs` | Показать корневой `HANDOFF.md` |
| `/todo` | Показать `docs/current/TODO_CONSOLIDATED.md` |
| `/botdocs` | Показать `bot/HANDOFF.md` |
| `/bottodo` | Показать `bot/TODO.md` |

## Webhook API

### `POST /hook`

Входящий event от локальных хуков агента.

Пример payload:

```json
{
  "agent": "claude",
  "event": "commit",
  "text": "fix: printer profile export"
}
```

Если задан `HOOK_SECRET`, нужно передавать заголовок:

```text
X-FH-Hook-Secret: <secret>
```

### `POST /github`

GitHub webhook relay для `push`, `issues`, `issue_comment`.

Если задан `GITHUB_WEBHOOK_SECRET`, проверяется `X-Hub-Signature-256`.

### `GET /healthz`

Возвращает JSON вида:

```json
{
  "status": "ok",
  "active_runs": 0,
  "available_agents": ["claude", "codex"]
}
```

## Запуск

### Windows launcher

```powershell
powershell -ExecutionPolicy Bypass -File bot\bot.ps1
powershell -ExecutionPolicy Bypass -File bot\bot.ps1 start
```

### Локально

```powershell
cd bot
pip install -r requirements.txt
$env:BOT_TOKEN="..."
$env:CHAT_ID="..."
$env:REPO_PATH="F:/FilamentHub"
python bot.py
```

### Docker

```powershell
docker compose -f docker-compose.dev.yml up tg-bot -d
docker logs filamenthub_tg_bot --tail 50
```

## Переменные окружения

| Переменная | Описание |
|------------|----------|
| `BOT_TOKEN` | Токен Telegram-бота |
| `CHAT_ID` | ID чата/группы для сервисных сообщений |
| `GITHUB_TOKEN` | GitHub PAT для issue API |
| `GITHUB_REPO` | `owner/repo`, по умолчанию `WeLizard/FilamentHub` |
| `REPO_PATH` | Путь к репо, по умолчанию `/repo` |
| `WEBHOOK_PORT` | Порт webhook сервера, по умолчанию `8090` |
| `HOOK_SECRET` | Секрет для `POST /hook` |
| `GITHUB_WEBHOOK_SECRET` | Секрет проверки GitHub webhook signature |
| `CLAUDE_CMD` | Путь к `claude` CLI |
| `CODEX_CMD` | Путь к `codex` CLI |
| `QWEN_CMD` | Путь к `qwen` CLI |
| `GEMINI_CMD` | Путь к `gemini` CLI |
| `TG_RESULTS_ONLY` | Для `codex` брать только final message |
| `TG_SHOW_STATUS` | Показывать промежуточный статус запуска |

Для `bot.ps1` допускаются legacy env names:
- `TG_BOT_TOKEN` -> `BOT_TOKEN`
- `TG_CHAT_ID` -> `CHAT_ID`

## Runtime files

Бот пишет runtime state в локальные файлы внутри `bot/`:
- `state.json`
- `bot.pid`
- `bot.log`
- `bot_err.log`

Они не должны попадать в git.
