# FilamentHub

FilamentHub — платформа для управления материалами и настройками 3D-печати с интеграцией в OrcaSlicer.

## Навигация по проекту

Вся подробная документация, архитектурные заметки, инструкции и планы развития были переорганизованы и собраны в единой "Карте Проекта".

**➡️ [Перейти к Карте Проекта](./docs/INDEX.md)**

---

## Быстрый старт (с использованием Docker)

Это рекомендуемый способ для запуска приложения. Он автоматически настраивает и запускает все необходимые сервисы (веб-сервер, API, базу данных) в изолированных контейнерах.

### Предварительные требования

*   **Docker:** Убедитесь, что на вашем компьютере установлен [Docker Desktop](https://www.docker.com/products/docker-desktop/) (для Windows/macOS) или Docker Engine (для Linux). Он включает в себя `docker` и `docker-compose`.

### Запуск приложения

1.  **Создайте файл `.env`:**
    Скопируйте файл `.env.template` в новый файл с именем `.env`.
    ```bash
    cp .env.template .env
    ```
    *Важно: Обязательно сгенерируйте новый `SECRET_KEY`.*

2.  **Запустите приложение:**
    *   **Для Windows (PowerShell):**
        ```powershell
        ./scripts/start.ps1 -Command up
        ```
    *   **Для Linux/macOS (Bash):**
        ```bash
        ./scripts/start.sh up
        ```

### Остановка приложения

*   **Для Windows (PowerShell):**
    ```powershell
    ./scripts/start.ps1 -Command down
    ```
*   **Для Linux/macOS (Bash):**
    ```bash
    ./scripts/start.sh down
    ```
