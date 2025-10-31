# Quick start script for FilamentHub Backend
# PowerShell script для быстрого запуска

Write-Host "🚀 FilamentHub Backend - Quick Start" -ForegroundColor Cyan
Write-Host ""

# Проверка Docker
Write-Host "📦 Проверка Docker..." -ForegroundColor Yellow
try {
    docker --version | Out-Null
    Write-Host "✅ Docker установлен" -ForegroundColor Green
} catch {
    Write-Host "❌ Docker не найден! Установите Docker Desktop" -ForegroundColor Red
    exit 1
}

# Запуск Docker Compose
Write-Host ""
Write-Host "🐘 Запуск PostgreSQL и Redis..." -ForegroundColor Yellow
docker-compose up -d

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Ошибка запуска Docker Compose!" -ForegroundColor Red
    Write-Host "Проверьте что Docker Desktop запущен" -ForegroundColor Yellow
    exit 1
}

Write-Host "✅ Контейнеры запущены" -ForegroundColor Green

# Ждем пока PostgreSQL запустится
Write-Host ""
Write-Host "⏳ Ожидание запуска PostgreSQL (15 секунд)..." -ForegroundColor Yellow
Start-Sleep -Seconds 15

# Проверка подключения
Write-Host ""
Write-Host "🔌 Проверка подключения к БД..." -ForegroundColor Yellow
$env:PGPASSWORD = "filamenthub_dev_password"
try {
    docker-compose exec -T postgres psql -U filamenthub -d filamenthub -c "SELECT 1;" | Out-Null
    Write-Host "✅ PostgreSQL готов" -ForegroundColor Green
} catch {
    Write-Host "⚠️ PostgreSQL еще загружается, продолжаем..." -ForegroundColor Yellow
}

# Создание таблиц через Alembic
Write-Host ""
Write-Host "📊 Создание таблиц в БД..." -ForegroundColor Yellow
.\venv\Scripts\python.exe -m alembic upgrade head

if ($LASTEXITCODE -ne 0) {
    Write-Host "⚠️ Alembic не сработал, используем SQL скрипт..." -ForegroundColor Yellow
    Write-Host "Выполните вручную: docker-compose exec postgres psql -U filamenthub -d filamenthub -f /tmp/create_tables.sql"
}

# Загрузка тестовых данных
Write-Host ""
Write-Host "📥 Загрузка тестовых данных..." -ForegroundColor Yellow
.\venv\Scripts\python.exe app\db\init_data.py

# Запуск приложения
Write-Host ""
Write-Host "🚀 Запуск приложения..." -ForegroundColor Yellow
Write-Host ""
Write-Host "✨ Приложение запущено!" -ForegroundColor Green
Write-Host ""
Write-Host "Откройте в браузере:" -ForegroundColor Cyan
Write-Host "  Frontend: http://localhost:8000/static/index.html" -ForegroundColor White
Write-Host "  API Docs: http://localhost:8000/api/v1/docs" -ForegroundColor White
Write-Host ""
Write-Host "Нажмите Ctrl+C чтобы остановить" -ForegroundColor Yellow
Write-Host ""

.\venv\Scripts\python.exe run.py

