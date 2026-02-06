# Настройка MCP для доступа к базе данных FilamentHub

## Текущие параметры подключения

Из `docker-compose.yml` и `env.example`:

- **Host:** localhost (или 127.0.0.1)
- **Port:** 5432
- **Database:** filamenthub
- **User:** filamenthub
- **Password:** filamenthub_dev_password

**Connection String:**
```
postgresql://filamenthub:filamenthub_dev_password@localhost:5432/filamenthub
```

## Настройка MCP в Cursor

### Вариант 1: Через настройки Cursor (рекомендуется)

1. Откройте Cursor
2. Перейдите в настройки (Settings)
3. Найдите раздел "MCP Servers" или "Model Context Protocol"
4. Добавьте новый MCP сервер для PostgreSQL

### Вариант 2: Через конфигурационный файл

Файл конфигурации обычно находится в:
- **Windows:** `%APPDATA%\Cursor\User\globalStorage\mcp.json`
- **macOS:** `~/Library/Application Support/Cursor/User/globalStorage/mcp.json`
- **Linux:** `~/.config/Cursor/User/globalStorage/mcp.json`

Добавьте следующую конфигурацию:

```json
{
  "mcpServers": {
    "database-main": {
      "command": "npx",
      "args": [
        "-y",
        "@modelcontextprotocol/server-postgres"
      ],
      "env": {
        "POSTGRES_CONNECTION_STRING": "postgresql://filamenthub:filamenthub_dev_password@localhost:5432/filamenthub"
      }
    }
  }
}
```

Или используя отдельные переменные:

```json
{
  "mcpServers": {
    "database-main": {
      "command": "npx",
      "args": [
        "-y",
        "@modelcontextprotocol/server-postgres"
      ],
      "env": {
        "POSTGRES_HOST": "localhost",
        "POSTGRES_PORT": "5432",
        "POSTGRES_DB": "filamenthub",
        "POSTGRES_USER": "filamenthub",
        "POSTGRES_PASSWORD": "filamenthub_dev_password"
      }
    }
  }
}
```

### Вариант 3: Использование готового MCP сервера

Если у вас уже есть MCP сервер для PostgreSQL, просто обновите строку подключения:

```json
{
  "mcpServers": {
    "database-main": {
      "env": {
        "POSTGRES_CONNECTION_STRING": "postgresql://filamenthub:filamenthub_dev_password@localhost:5432/filamenthub"
      }
    }
  }
}
```

## Проверка подключения

После настройки MCP должен иметь доступ к следующим таблицам:

- `users` - пользователи
- `brands` - производители
- `filaments` - материалы
- `presets` - пресеты настроек
- `printers` - принтеры

## Доступные инструменты MCP

После настройки вы сможете использовать:

- `mcp_database-main_read_query` - выполнение SELECT запросов
- `mcp_database-main_write_query` - выполнение INSERT/UPDATE/DELETE
- `mcp_database-main_create_table` - создание таблиц
- `mcp_database-main_alter_table` - изменение схемы
- `mcp_database-main_drop_table` - удаление таблиц
- `mcp_database-main_list_tables` - список таблиц
- `mcp_database-main_describe_table` - описание таблицы
- `mcp_database-main_export_query` - экспорт результатов

## Безопасность

⚠️ **Важно:** Не коммитьте пароли в git! Используйте `.env` файлы и не добавляйте их в репозиторий.

Для продакшена:
- Используйте более сложные пароли
- Настройте SSL соединение
- Ограничьте доступ по IP
- Используйте переменные окружения из secure vault



