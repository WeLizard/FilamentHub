# Деплой FilamentHub на сервер
# Использование: .\deploy-server.ps1

Write-Host ""
Write-Host "🚀 FilamentHub - Deploy to Server" -ForegroundColor Cyan
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor DarkGray
Write-Host ""

# Проверяем есть ли незакоммиченные изменения
$status = git status --porcelain
if ($status) {
    Write-Host "⚠️  Есть незакоммиченные изменения:" -ForegroundColor Yellow
    git status --short
    Write-Host ""
    $confirm = Read-Host "Закоммитить и запушить? (y/n)"
    if ($confirm -eq 'y' -or $confirm -eq 'Y') {
        $message = Read-Host "Введи commit message"
        if (-not $message) { $message = "Update" }
        git add -A
        git commit -m $message
        git push origin main
    } else {
        Write-Host "❌ Деплой отменён" -ForegroundColor Red
        exit 1
    }
}

Write-Host "📤 Деплою на сервер..." -ForegroundColor Green
ssh lizard@192.168.0.33 "cd ~/FilamentHub && bash scripts/deploy.sh"

Write-Host ""
Write-Host "✅ Готово!" -ForegroundColor Green

