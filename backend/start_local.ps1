# Скрипт для запуска БЕЗ Docker (с локальным PostgreSQL)
# Убедитесь что PostgreSQL установлен и запущен!

Write-Host "🚀 FilamentHub Backend - Local PostgreSQL Setup" -ForegroundColor Cyan
Write-Host ""

# Проверка PostgreSQL
Write-Host "🐘 Проверка PostgreSQL..." -ForegroundColor Yellow
try {
    $pgService = Get-Service | Where-Object { $_.Name -like "*postgresql*" }
    if ($pgService) {
        Write-Host "✅ PostgreSQL найден: $($pgService.Name)" -ForegroundColor Green
        if ($pgService.Status -eq "Running") {
            Write-Host "✅ PostgreSQL запущен" -ForegroundColor Green
        } else {
            Write-Host "⚠️ PostgreSQL не запущен, пытаюсь запустить..." -ForegroundColor Yellow
            Start-Service $pgService.Name
            Start-Sleep -Seconds 3
            Write-Host "✅ PostgreSQL запущен" -ForegroundColor Green
        }
    } else {
        Write-Host "⚠️ PostgreSQL сервис не найден" -ForegroundColor Yellow
        Write-Host "Убедитесь что PostgreSQL установлен и запущен вручную" -ForegroundColor Yellow
    }
} catch {
    Write-Host "⚠️ Не удалось проверить PostgreSQL" -ForegroundColor Yellow
    Write-Host "Продолжаем, но убедитесь что PostgreSQL доступен на localhost:5432" -ForegroundColor Yellow
}

# Проверка .env
Write-Host ""
Write-Host "📝 Проверка .env файла..." -ForegroundColor Yellow
if (Test-Path .env) {
    Write-Host "✅ .env файл найден" -ForegroundColor Green
} else {
    Write-Host "❌ .env файл не найден!" -ForegroundColor Red
    Write-Host "Создаю из шаблона..." -ForegroundColor Yellow
    Copy-Item env.example .env
    Write-Host "✅ .env создан, проверьте DATABASE_URL" -ForegroundColor Green
    exit 1
}

# Создание таблиц
Write-Host ""
Write-Host "📊 Создание таблиц в БД..." -ForegroundColor Yellow
.\venv\Scripts\python.exe -m alembic upgrade head

if ($LASTEXITCODE -ne 0) {
    Write-Host "⚠️ Alembic не сработал, попробуйте создать таблицы вручную через create_tables.sql" -ForegroundColor Yellow
    Write-Host "Или используйте pgAdmin для выполнения SQL скрипта" -ForegroundColor Yellow
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


