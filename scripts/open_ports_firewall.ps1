# Скрипт для открытия портов 80 и 443 в файрволе Windows

Write-Host "🔓 Открытие портов 80 и 443 в файрволе Windows..." -ForegroundColor Cyan
Write-Host ""

# Проверяем существующие правила
$rule80 = netsh advfirewall firewall show rule name="FilamentHub HTTP (Port 80)" 2>$null
$rule443 = netsh advfirewall firewall show rule name="FilamentHub HTTPS (Port 443)" 2>$null

if ($rule80) {
    Write-Host "⚠️  Правило для порта 80 уже существует" -ForegroundColor Yellow
} else {
    Write-Host "Создаю правило для порта 80..." -ForegroundColor Yellow
    netsh advfirewall firewall add rule name="FilamentHub HTTP (Port 80)" dir=in action=allow protocol=TCP localport=80
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ Порт 80 открыт" -ForegroundColor Green
    } else {
        Write-Host "❌ Ошибка при открытии порта 80" -ForegroundColor Red
    }
}

if ($rule443) {
    Write-Host "⚠️  Правило для порта 443 уже существует" -ForegroundColor Yellow
} else {
    Write-Host "Создаю правило для порта 443..." -ForegroundColor Yellow
    netsh advfirewall firewall add rule name="FilamentHub HTTPS (Port 443)" dir=in action=allow protocol=TCP localport=443
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ Порт 443 открыт" -ForegroundColor Green
    } else {
        Write-Host "❌ Ошибка при открытии порта 443" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "📝 Проверь правила:" -ForegroundColor Cyan
Write-Host "   netsh advfirewall firewall show rule name=\"FilamentHub HTTP\""
Write-Host "   netsh advfirewall firewall show rule name=\"FilamentHub HTTPS\""

