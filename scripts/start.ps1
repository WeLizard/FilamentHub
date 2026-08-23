<#
.SYNOPSIS
Скрипт для управления локальным dev-окружением FilamentHub.

.DESCRIPTION
Все команды явно используют docker-compose.dev.yml и не затрагивают
production-compose.

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

# Проверяем, существует ли docker
$dockerPath = Get-Command docker -ErrorAction SilentlyContinue
if (-not $dockerPath) {
    throw "Команда 'docker' не найдена. Убедитесь, что Docker Desktop установлен и запущен."
}

# Функция для вывода сообщений
function Write-Log {
    param(
        [string]$Message,
        [string]$Color = "White"
    )
    Write-Host "[$([datetime]::now.ToString('HH:mm:ss'))] $Message" -ForegroundColor $Color
}

$projectRoot = Split-Path -Path $PSScriptRoot -Parent
$composeArguments = @('compose', '-f', 'docker-compose.dev.yml')

function Invoke-DevCompose {
    param([Parameter(Mandatory)][string[]]$Arguments)

    & docker @composeArguments @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Compose завершился с ошибкой ($LASTEXITCODE)."
    }
}

Push-Location $projectRoot

try {
    switch ($Command) {
        "up" {
            Write-Log "Сборка и запуск local dev в фоновом режиме..." -Color "Cyan"
            Invoke-DevCompose @('up', '--build', '-d')
            Write-Log "Local dev запущен: frontend http://127.0.0.1:3000, backend http://127.0.0.1:8001" -Color "Green"
        }
        "down" {
            Write-Log "Остановка local dev..." -Color "Cyan"
            Invoke-DevCompose @('down')
            Write-Log "Local dev остановлен." -Color "Green"
        }
        "clean" {
            Write-Log "ВНИМАНИЕ! Эта команда остановит все сервисы и удалит ВСЕ ДАННЫЕ, включая базу данных." -Color "Yellow"
            $confirmation = Read-Host "Вы уверены, что хотите продолжить? (y/n)"
            if ($confirmation -eq 'y') {
                Write-Log "Остановка сервисов и удаление томов данных..." -Color "Red"
                Invoke-DevCompose @('down', '-v')
                Write-Log "Local dev и его Docker volumes удалены." -Color "Green"
            } else {
                Write-Log "Операция отменена." -Color "Yellow"
            }
        }
        "logs" {
            Write-Log "Логи local dev. Нажмите Ctrl+C для выхода." -Color "Cyan"
            Invoke-DevCompose @('logs', '-f')
        }
        "ps" {
            Write-Log "Статус local dev контейнеров:" -Color "Cyan"
            Invoke-DevCompose @('ps')
        }
    }
}
catch {
    throw "Ошибка local dev команды '$Command': $($_.Exception.Message)"
}
finally {
    Pop-Location
}
