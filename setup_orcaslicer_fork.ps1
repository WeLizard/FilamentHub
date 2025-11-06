# Скрипт для настройки форка OrcaSlicer
# Выполняет: клонирование, применение правок, настройку upstream

param(
    [string]$GitHubUsername = "lizardjazz1"
)

$ErrorActionPreference = "Stop"

Write-Host "=== Настройка форка OrcaSlicer ===" -ForegroundColor Cyan
Write-Host ""

# Проверка форка
Write-Host "1. Проверка существования форка..." -ForegroundColor Yellow
$forkUrl = "https://github.com/$GitHubUsername/OrcaSlicer"
Write-Host "   Форк должен быть создан: $forkUrl" -ForegroundColor Gray
Write-Host ""

$confirm = Read-Host "Форк создан? (y/n)"
if ($confirm -ne "y" -and $confirm -ne "Y") {
    Write-Host "Создайте форк сначала:" -ForegroundColor Red
    Write-Host "1. Откройте: https://github.com/SoftFever/OrcaSlicer" -ForegroundColor Yellow
    Write-Host "2. Нажмите 'Fork'" -ForegroundColor Yellow
    Write-Host "3. Выберите аккаунт: $GitHubUsername" -ForegroundColor Yellow
    exit 1
}

# Переход в корень проекта
$projectRoot = "F:\FilamentHub"
Set-Location $projectRoot

# Удаление старой папки (если есть)
Write-Host "2. Очистка старой копии..." -ForegroundColor Yellow
if (Test-Path "docs\OrcaSlicer") {
    $remove = Read-Host "   Удалить существующую папку docs\OrcaSlicer? (y/n)"
    if ($remove -eq "y" -or $remove -eq "Y") {
        Remove-Item -Recurse -Force "docs\OrcaSlicer" -ErrorAction SilentlyContinue
        Write-Host "   ✓ Удалено" -ForegroundColor Green
    }
}

# Клонирование форка
Write-Host "3. Клонирование форка..." -ForegroundColor Yellow
if (-not (Test-Path "docs\OrcaSlicer")) {
    git clone "https://github.com/$GitHubUsername/OrcaSlicer.git" "docs\OrcaSlicer"
    Write-Host "   ✓ Клонировано" -ForegroundColor Green
} else {
    Write-Host "   ℹ Папка уже существует, пропускаю клонирование" -ForegroundColor Gray
}

Set-Location "docs\OrcaSlicer"

# Проверка remotes
Write-Host "4. Проверка remotes..." -ForegroundColor Yellow
$remotes = git remote -v
Write-Host $remotes

# Настройка upstream
Write-Host "5. Настройка upstream..." -ForegroundColor Yellow
if ($remotes -notmatch "upstream") {
    git remote add upstream https://github.com/SoftFever/OrcaSlicer.git
    Write-Host "   ✓ Upstream добавлен" -ForegroundColor Green
} else {
    Write-Host "   ℹ Upstream уже настроен" -ForegroundColor Gray
}

# Загрузка Git LFS
Write-Host "6. Загрузка Git LFS файлов..." -ForegroundColor Yellow
git lfs pull
Write-Host "   ✓ LFS файлы загружены" -ForegroundColor Green

# Применение правок из существующей копии
Write-Host "7. Применение правок из существующей копии..." -ForegroundColor Yellow

$sourceDir = "..\OrcaSlicer-main\OrcaSlicer-main"
if (Test-Path $sourceDir) {
    Write-Host "   Найдена существующая копия с правками" -ForegroundColor Gray
    
    # Сравнение CMakeLists.txt
    $targetCMake = "CMakeLists.txt"
    $sourceCMake = "$sourceDir\CMakeLists.txt"
    
    if (Test-Path $sourceCMake) {
        Write-Host "   Копирую правки в CMakeLists.txt..." -ForegroundColor Gray
        
        # Копируем файлы с правками
        Copy-Item $sourceCMake $targetCMake -Force
        Write-Host "   ✓ CMakeLists.txt обновлен" -ForegroundColor Green
    }
    
    # Сравнение src/libslic3r/CMakeLists.txt
    $targetLibCMake = "src\libslic3r\CMakeLists.txt"
    $sourceLibCMake = "$sourceDir\src\libslic3r\CMakeLists.txt"
    
    if (Test-Path $sourceLibCMake) {
        Write-Host "   Копирую правки в src/libslic3r/CMakeLists.txt..." -ForegroundColor Gray
        Copy-Item $sourceLibCMake $targetLibCMake -Force
        Write-Host "   ✓ src/libslic3r/CMakeLists.txt обновлен" -ForegroundColor Green
    }
} else {
    Write-Host "   ⚠ Существующая копия не найдена, правки нужно применить вручную" -ForegroundColor Yellow
}

# Проверка изменений
Write-Host "8. Проверка изменений..." -ForegroundColor Yellow
git status --short

# Создание ветки для разработки
Write-Host "9. Создание ветки для разработки..." -ForegroundColor Yellow
$branchName = "filamenthub-integration"
$currentBranch = git rev-parse --abbrev-ref HEAD
if ($currentBranch -ne $branchName) {
    git checkout -b $branchName
    Write-Host "   ✓ Ветка '$branchName' создана" -ForegroundColor Green
} else {
    Write-Host "   ℹ Уже на ветке '$branchName'" -ForegroundColor Gray
}

# Коммит правок (если есть изменения)
Write-Host "10. Коммит правок..." -ForegroundColor Yellow
$changes = git status --porcelain
if ($changes) {
    git add CMakeLists.txt src/libslic3r/CMakeLists.txt
    git commit -m "fix: исправления для сборки на Windows (OpenCV, OCCT DLL)"
    Write-Host "   ✓ Правки закоммичены" -ForegroundColor Green
} else {
    Write-Host "   ℹ Нет изменений для коммита" -ForegroundColor Gray
}

Write-Host ""
Write-Host "=== Настройка завершена! ===" -ForegroundColor Green
Write-Host ""
Write-Host "Следующие шаги:" -ForegroundColor Cyan
Write-Host "1. Запушить ветку: git push -u origin $branchName" -ForegroundColor Yellow
Write-Host "2. Проверить upstream: git fetch upstream" -ForegroundColor Yellow
Write-Host "3. Начать разработку интеграции FilamentHub" -ForegroundColor Yellow
Write-Host ""
