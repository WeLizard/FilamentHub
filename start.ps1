<#
.SYNOPSIS
Скрипт для управления Docker-контейнерами приложения FilamentHub.

.DESCRIPTION
Этот скрипт упрощает запуск, остановку и управление всем стеком приложения FilamentHub,
используя Docker Compose. Он предоставляет простые команды для общих операций.

.PARAMETER Command
Команда для выполнения. Допустимые значения:
- up: Собрать (при необходимости) и запустить все сервисы в фоновом режиме.
- down: Остановить все сервисы.
- clean: Остановить все сервисы и УДАЛИТЬ все данные (включая базу данных).
- logs: Показать логи всех запущенных сервисов.
- ps: Показать статус запущенных контейнеров.

.EXAMPLE
# Запустить приложение
./start.ps1 -Command up

.EXAMPLE
# Остановить приложение и удалить все данные
./start.ps1 -Command clean

.EXAMPLE
# Посмотреть логи
./start.ps1 -Command logs
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, HelpMessage = "Команда для выполнения (up, down, clean, logs, ps)")]
    [ValidateSet('up', 'down', 'clean', 'logs', 'ps')]
    [string]$Command
)

# Проверяем, существует ли docker-compose
$dockerComposePath = Get-Command docker-compose -ErrorAction SilentlyContinue
if (-not $dockerComposePath) {
    Write-Error "Команда 'docker-compose' не найдена. Убедитесь, что Docker Desktop установлен и запущен."
    exit 1
}

# Функция для вывода сообщений
function Write-Log {
    param(
        [string]$Message,
        [string]$Color = "White"
    )
    Write-Host "[$([datetime]::now.ToString('HH:mm:ss'))] $Message" -ForegroundColor $Color
}

# Переходим в директорию, где находится скрипт
Push-Location (Split-Path -Path $MyInvocation.MyCommand.Definition -Parent)

try {
    switch ($Command) {
        "up" {
            Write-Log "Проверяем наличие файла .env..." -Color "Cyan"
            if (-not (Test-Path ".env")) {
                Write-Log "Файл .env не найден. Копирую .env.template в .env..." -Color "Yellow"
                Copy-Item -Path ".env.template" -Destination ".env"
                Write-Log "Файл .env успешно создан. Пожалуйста, проверьте его и при необходимости измените, особенно SECRET_KEY." -Color "Green"
            } else {
                Write-Log "Файл .env найден." -Color "Green"
            }

            Write-Log "Запуск сборки и подъема всех сервисов в фоновом режиме..." -Color "Cyan"
            docker-compose up --build -d
            Write-Log "Приложение запущено. Веб-интерфейс должен быть доступен по адресу http://localhost" -Color "Green"
        }
        "down" {
            Write-Log "Остановка всех сервисов..." -Color "Cyan"
            docker-compose down
            Write-Log "Все сервисы остановлены." -Color "Green"
        }
        "clean" {
            Write-Log "ВНИМАНИЕ! Эта команда остановит все сервисы и удалит ВСЕ ДАННЫЕ, включая базу данных." -Color "Yellow"
            $confirmation = Read-Host "Вы уверены, что хотите продолжить? (y/n)"
            if ($confirmation -eq 'y') {
                Write-Log "Остановка сервисов и удаление томов данных..." -Color "Red"
                docker-compose down -v
                Write-Log "Все сервисы и данные были удалены." -Color "Green"
            } else {
                Write-Log "Операция отменена." -Color "Yellow"
            }
        }
        "logs" {
            Write-Log "Вывод логов всех сервисов. Нажмите Ctrl+C для выхода." -Color "Cyan"
            docker-compose logs -f
        }
        "ps" {
            Write-Log "Статус запущенных контейнеров:" -Color "Cyan"
            docker-compose ps
        }
    }
}
catch {
    Write-Error "Произошла ошибка при выполнении команды '$Command': $_"
}
finally {
    Pop-Location
}
