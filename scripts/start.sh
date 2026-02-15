#!/bin/bash

# .SYNOPSIS
# Скрипт для управления Docker-контейнерами приложения FilamentHub.
#
# .DESCRIPTION
# Этот скрипт упрощает запуск, остановку и управление всем стеком приложения FilamentHub,
# используя Docker Compose. Он предоставляет простые команды для общих операций.
#
# .PARAMETER Command
# Команда для выполнения. Допустимые значения:
# - up: Собрать (при необходимости) и запустить все сервисы в фоновом режиме.
# - down: Остановить все сервисы.
# - clean: Остановить все сервисы и УДАЛИТЬ все данные (включая базу данных).
# - logs: Показать логи всех запущенных сервисов.
# - ps: Показать статус запущенных контейнеров.
#
# .EXAMPLE
# # Запустить приложение
# ./start.sh up
#
# .EXAMPLE
# # Остановить приложение и удалить все данные
# ./start.sh clean
#
# .EXAMPLE
# # Посмотреть логи
# ./start.sh logs

# Функция для вывода сообщений
log() {
    local message="$1"
    local color="$2"
    case "$color" in
        "red")      echo -e "[\e[31m$(date '+%H:%M:%S')\e[0m] $message" ;;
        "green")    echo -e "[\e[32m$(date '+%H:%M:%S')\e[0m] $message" ;;
        "yellow")   echo -e "[\e[33m$(date '+%H:%M:%S')\e[0m] $message" ;;
        "cyan")     echo -e "[\e[36m$(date '+%H:%M:%S')\e[0m] $message" ;;
        *)          echo -e "[$(date '+%H:%M:%S')] $message" ;;
    esac
}

# Проверяем, передан ли аргумент
if [ -z "$1" ]; then
    log "Использование: ./start.sh [up|down|clean|logs|ps]" "yellow"
    exit 1
fi

COMMAND="$1"

# Проверяем наличие docker-compose
if ! command -v docker-compose &> /dev/null; then
    log "Команда 'docker-compose' не найдена. Убедитесь, что Docker Desktop установлен и запущен." "red"
    exit 1
fi

# Переходим в директорию, где находится скрипт
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
pushd "$SCRIPT_DIR" &> /dev/null

case "$COMMAND" in
    "up")
        log "Проверяем наличие файла .env..." "cyan"
        if [ ! -f ".env" ]; then
            log "Файл .env не найден. Копирую .env.template в .env..." "yellow"
            cp ".env.template" ".env"
            log "Файл .env успешно создан. Пожалуйста, проверьте его и при необходимости измените, особенно SECRET_KEY." "green"
        else
            log "Файл .env найден." "green"
        fi

        log "Запуск сборки и подъема всех сервисов в фоновом режиме..." "cyan"
        docker-compose up --build -d
        log "Приложение запущено. Веб-интерфейс должен быть доступен по адресу http://localhost" "green"
        ;;
    "down")
        log "Остановка всех сервисов..." "cyan"
        docker-compose down
        log "Все сервисы остановлены." "green"
        ;;
    "clean")
        log "ВНИМАНИЕ! Эта команда остановит все сервисы и удалит ВСЕ ДАННЫЕ, включая базу данных." "yellow"
        read -p "Вы уверены, что хотите продолжить? (y/n): " -n 1 -r CONFIRMATION
        echo # Переход на новую строку
        if [[ "$CONFIRMATION" =~ ^[Yy]$ ]]; then
            log "Остановка сервисов и удаление томов данных..." "red"
            docker-compose down -v
            log "Все сервисы и данные были удалены." "green"
        else
            log "Операция отменена." "yellow"
        fi
        ;;
    "logs")
        log "Вывод логов всех сервисов. Нажмите Ctrl+C для выхода." "cyan"
        docker-compose logs -f
        ;;
    "ps")
        log "Статус запущенных контейнеров:" "cyan"
        docker-compose ps
        ;;
    *)
        log "Неизвестная команда: $COMMAND" "red"
        log "Использование: ./start.sh [up|down|clean|logs|ps]" "yellow"
        ;;
esac

popd &> /dev/null
