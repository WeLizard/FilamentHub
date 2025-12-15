# Скрипт для проверки доступности портов 80 и 443 извне

param(
    [string]$IP = "185.237.236.5"
)

Write-Host "🔍 Проверка портов для $IP..." -ForegroundColor Cyan
Write-Host ""

# Проверка локально (что порты слушаются)
Write-Host "1. Проверка локально (порты слушаются):" -ForegroundColor Yellow
$port80Local = netstat -an | Select-String -Pattern ":80 " | Where-Object { $_ -match "LISTENING" }
$port443Local = netstat -an | Select-String -Pattern ":443 " | Where-Object { $_ -match "LISTENING" }

if ($port80Local) {
    Write-Host "   ✅ Порт 80 слушается локально" -ForegroundColor Green
    Write-Host "      $($port80Local.Line.Trim())" -ForegroundColor Gray
} else {
    Write-Host "   ⚠️  Порт 80 НЕ слушается локально" -ForegroundColor Yellow
}

if ($port443Local) {
    Write-Host "   ✅ Порт 443 слушается локально" -ForegroundColor Green
    Write-Host "      $($port443Local.Line.Trim())" -ForegroundColor Gray
} else {
    Write-Host "   ⚠️  Порт 443 НЕ слушается локально" -ForegroundColor Yellow
}

Write-Host ""

# Проверка извне (через Test-NetConnection)
Write-Host "2. Проверка извне (доступность из интернета):" -ForegroundColor Yellow
Write-Host "   (Это может занять несколько секунд...)" -ForegroundColor Gray

try {
    $port80Remote = Test-NetConnection -ComputerName $IP -Port 80 -WarningAction SilentlyContinue -InformationLevel Quiet
    if ($port80Remote) {
        Write-Host "   ✅ Порт 80 ОТКРЫТ извне" -ForegroundColor Green
    } else {
        Write-Host "   ❌ Порт 80 ЗАКРЫТ или недоступен извне" -ForegroundColor Red
    }
} catch {
    Write-Host "   ⚠️  Не удалось проверить порт 80: $_" -ForegroundColor Yellow
}

try {
    $port443Remote = Test-NetConnection -ComputerName $IP -Port 443 -WarningAction SilentlyContinue -InformationLevel Quiet
    if ($port443Remote) {
        Write-Host "   ✅ Порт 443 ОТКРЫТ извне" -ForegroundColor Green
    } else {
        Write-Host "   ❌ Порт 443 ЗАКРЫТ или недоступен извне" -ForegroundColor Red
    }
} catch {
    Write-Host "   ⚠️  Не удалось проверить порт 443: $_" -ForegroundColor Yellow
}

Write-Host ""

# Проверка Docker контейнеров
Write-Host "3. Проверка Docker контейнеров:" -ForegroundColor Yellow
$frontendContainer = docker ps --filter "name=frontend" --format "{{.Names}}: {{.Ports}}" 2>$null
if ($frontendContainer) {
    Write-Host "   $frontendContainer" -ForegroundColor Cyan
    if ($frontendContainer -match "0\.0\.0\.0:80" -or $frontendContainer -match ":80->") {
        Write-Host "   ✅ Порт 80 проброшен в Docker" -ForegroundColor Green
    }
    if ($frontendContainer -match "0\.0\.0\.0:443" -or $frontendContainer -match ":443->") {
        Write-Host "   ✅ Порт 443 проброшен в Docker" -ForegroundColor Green
    }
} else {
    Write-Host "   ⚠️  Frontend контейнер не запущен" -ForegroundColor Yellow
}

Write-Host ""

# Рекомендации
Write-Host "📝 Рекомендации:" -ForegroundColor Cyan
Write-Host "   • Для более точной проверки используй онлайн-сервисы:" -ForegroundColor Gray
Write-Host "     https://www.portchecker.co/ (введи IP: $IP, порты: 80, 443)" -ForegroundColor Gray
Write-Host "     https://canyouseeme.org/" -ForegroundColor Gray
Write-Host ""
Write-Host "   • Или просто открой в браузере:" -ForegroundColor Gray
Write-Host "     http://$IP" -ForegroundColor Cyan
Write-Host "     http://filamenthub.ru" -ForegroundColor Cyan

