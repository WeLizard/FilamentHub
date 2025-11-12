# Setup OrcaSlicer as Git Submodule
# Этот скрипт мигрирует существующий OrcaSlicer репозиторий в Git Submodule

param(
    [switch]$Force,
    [switch]$SkipCommit
)

$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "OrcaSlicer Git Submodule Setup" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Проверка, что мы в корне FilamentHub
if (-not (Test-Path ".git")) {
    Write-Host "❌ Ошибка: Этот скрипт должен быть запущен из корня FilamentHub репозитория" -ForegroundColor Red
    exit 1
}

$OrcaSlicerPath = "docs\OrcaSlicer"
$GitModulesPath = ".gitmodules"
$OrcaSlicerRepo = "https://github.com/lizardjazz1/OrcaSlicer.git"
$OrcaSlicerBranch = "filamenthub-integration"

Write-Host "1. Проверка текущего состояния..." -ForegroundColor Yellow

# Проверка, существует ли OrcaSlicer
if (Test-Path $OrcaSlicerPath) {
    Write-Host "   ✓ Найдена папка $OrcaSlicerPath" -ForegroundColor Green
    
    # Проверка, является ли это Git репозиторием
    if (Test-Path "$OrcaSlicerPath\.git") {
        Write-Host "   ✓ Это Git репозиторий" -ForegroundColor Green
        
        # Проверка статуса
        Push-Location $OrcaSlicerPath
        $status = git status --short
        Pop-Location
        
        if ($status) {
            Write-Host "   ⚠️ Обнаружены незакоммиченные изменения:" -ForegroundColor Yellow
            Write-Host $status -ForegroundColor Gray
            Write-Host ""
            Write-Host "   ❗ ВАЖНО: Сначала закоммитьте и запушьте все изменения в OrcaSlicer репозиторий!" -ForegroundColor Red
            Write-Host ""
            $response = Read-Host "   Продолжить? (y/N)"
            if ($response -ne "y" -and $response -ne "Y") {
                Write-Host "   Прервано пользователем" -ForegroundColor Yellow
                exit 0
            }
        }
    } else {
        Write-Host "   ❌ Это не Git репозиторий!" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "   ℹ️ Папка $OrcaSlicerPath не найдена" -ForegroundColor Gray
}

# Проверка, является ли уже submodule
if (Test-Path $GitModulesPath) {
    $isSubmodule = Select-String -Path $GitModulesPath -Pattern "docs/OrcaSlicer" -Quiet
    if ($isSubmodule) {
        Write-Host "   ℹ️ OrcaSlicer уже настроен как submodule" -ForegroundColor Gray
        Write-Host "   Используйте 'git submodule update --remote docs/OrcaSlicer' для обновления" -ForegroundColor Gray
        exit 0
    }
}

Write-Host ""
Write-Host "2. Проверка .gitignore..." -ForegroundColor Yellow

# Проверка .gitignore
$gitignorePath = ".gitignore"
if (Test-Path $gitignorePath) {
    $gitignoreContent = Get-Content $gitignorePath -Raw
    if ($gitignoreContent -match "docs/OrcaSlicer") {
        Write-Host "   ⚠️ Найдено 'docs/OrcaSlicer' в .gitignore" -ForegroundColor Yellow
        Write-Host "   Это нужно будет удалить после настройки submodule" -ForegroundColor Gray
    }
}

Write-Host ""
Write-Host "3. Сохранение текущих изменений в OrcaSlicer..." -ForegroundColor Yellow

if (Test-Path $OrcaSlicerPath) {
    Push-Location $OrcaSlicerPath
    
    # Проверка текущей ветки
    $currentBranch = git branch --show-current
    Write-Host "   Текущая ветка: $currentBranch" -ForegroundColor Gray
    
    if ($currentBranch -ne $OrcaSlicerBranch) {
        Write-Host "   ⚠️ Текущая ветка ($currentBranch) не совпадает с целевой ($OrcaSlicerBranch)" -ForegroundColor Yellow
        $response = Read-Host "   Переключиться на ветку $OrcaSlicerBranch? (y/N)"
        if ($response -eq "y" -or $response -eq "Y") {
            git checkout $OrcaSlicerBranch
            Write-Host "   ✓ Переключено на ветку $OrcaSlicerBranch" -ForegroundColor Green
        }
    }
    
    # Проверка статуса
    $status = git status --short
    if ($status -and -not $SkipCommit) {
        Write-Host "   ⚠️ Обнаружены незакоммиченные изменения:" -ForegroundColor Yellow
        Write-Host $status -ForegroundColor Gray
        Write-Host ""
        Write-Host "   ❗ Рекомендуется закоммитить изменения перед миграцией на submodule" -ForegroundColor Red
        Write-Host ""
        $response = Read-Host "   Закоммитить изменения сейчас? (y/N)"
        if ($response -eq "y" -or $response -eq "Y") {
            git add -A
            $commitMessage = Read-Host "   Введите сообщение коммита (или нажмите Enter для стандартного)"
            if (-not $commitMessage) {
                $commitMessage = "Update FilamentHub integration"
            }
            git commit -m $commitMessage
            Write-Host "   ✓ Изменения закоммичены" -ForegroundColor Green
            
            # Пуш изменений
            $response = Read-Host "   Запушить изменения в origin? (y/N)"
            if ($response -eq "y" -or $response -eq "Y") {
                git push origin $OrcaSlicerBranch
                Write-Host "   ✓ Изменения запушены" -ForegroundColor Green
            }
        }
    }
    
    Pop-Location
}

Write-Host ""
Write-Host "4. Удаление OrcaSlicer из FilamentHub индекса..." -ForegroundColor Yellow

# Удаление из Git индекса (если отслеживается)
$trackedFiles = git ls-files $OrcaSlicerPath 2>$null
if ($trackedFiles) {
    Write-Host "   Найдено отслеживаемых файлов: $($trackedFiles.Count)" -ForegroundColor Gray
    if ($Force -or (Read-Host "   Удалить из Git индекса? (y/N)") -eq "y") {
        git rm -r --cached $OrcaSlicerPath
        Write-Host "   ✓ Удалено из Git индекса" -ForegroundColor Green
    }
} else {
    Write-Host "   ℹ️ OrcaSlicer не отслеживается в Git индексе" -ForegroundColor Gray
}

Write-Host ""
Write-Host "5. Удаление физической папки..." -ForegroundColor Yellow

if (Test-Path $OrcaSlicerPath) {
    if ($Force -or (Read-Host "   Удалить папку $OrcaSlicerPath? (y/N)") -eq "y") {
        Remove-Item -Recurse -Force $OrcaSlicerPath
        Write-Host "   ✓ Папка удалена" -ForegroundColor Green
    } else {
        Write-Host "   ⚠️ Папка не удалена, submodule не может быть добавлен" -ForegroundColor Yellow
        exit 1
    }
}

Write-Host ""
Write-Host "6. Добавление OrcaSlicer как Git Submodule..." -ForegroundColor Yellow

try {
    git submodule add -b $OrcaSlicerBranch $OrcaSlicerRepo $OrcaSlicerPath
    Write-Host "   ✓ Submodule добавлен" -ForegroundColor Green
} catch {
    Write-Host "   ❌ Ошибка при добавлении submodule: $_" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "7. Инициализация submodule..." -ForegroundColor Yellow

try {
    git submodule init
    Write-Host "   ✓ Submodule инициализирован" -ForegroundColor Green
} catch {
    Write-Host "   ❌ Ошибка при инициализации submodule: $_" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "8. Обновление submodule..." -ForegroundColor Yellow

try {
    git submodule update
    Write-Host "   ✓ Submodule обновлен" -ForegroundColor Green
} catch {
    Write-Host "   ❌ Ошибка при обновлении submodule: $_" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "9. Обновление .gitignore..." -ForegroundColor Yellow

if (Test-Path $gitignorePath) {
    $gitignoreContent = Get-Content $gitignorePath -Raw
    if ($gitignoreContent -match "docs/OrcaSlicer") {
        Write-Host "   ⚠️ Найдено 'docs/OrcaSlicer' в .gitignore" -ForegroundColor Yellow
        Write-Host "   ❗ Нужно удалить эту строку из .gitignore вручную" -ForegroundColor Red
        Write-Host "   Откройте .gitignore и удалите строку с 'docs/OrcaSlicer'" -ForegroundColor Gray
    } else {
        Write-Host "   ✓ 'docs/OrcaSlicer' не найдено в .gitignore" -ForegroundColor Green
    }
}

Write-Host ""
Write-Host "10. Проверка настройки..." -ForegroundColor Yellow

# Проверка .gitmodules
if (Test-Path $GitModulesPath) {
    Write-Host "   ✓ Файл .gitmodules создан" -ForegroundColor Green
    $gitmodulesContent = Get-Content $GitModulesPath -Raw
    if ($gitmodulesContent -match $OrcaSlicerPath) {
        Write-Host "   ✓ OrcaSlicer найден в .gitmodules" -ForegroundColor Green
    }
} else {
    Write-Host "   ❌ Файл .gitmodules не найден!" -ForegroundColor Red
    exit 1
}

# Проверка статуса submodule
$submoduleStatus = git submodule status
Write-Host "   Статус submodule:" -ForegroundColor Gray
Write-Host $submoduleStatus -ForegroundColor Gray

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "✅ Настройка завершена!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Следующие шаги:" -ForegroundColor Yellow
Write-Host "1. Удалите 'docs/OrcaSlicer' из .gitignore (если есть)" -ForegroundColor Gray
Write-Host "2. Добавьте изменения в Git:" -ForegroundColor Gray
Write-Host "   git add .gitmodules $OrcaSlicerPath .gitignore" -ForegroundColor White
Write-Host "3. Закоммитьте изменения:" -ForegroundColor Gray
Write-Host "   git commit -m 'Add OrcaSlicer as Git submodule'" -ForegroundColor White
Write-Host "4. Запушьте изменения:" -ForegroundColor Gray
Write-Host "   git push origin main" -ForegroundColor White
Write-Host ""
Write-Host "Для работы с OrcaSlicer:" -ForegroundColor Yellow
Write-Host "  cd $OrcaSlicerPath" -ForegroundColor White
Write-Host "  # Работайте как обычно (коммиты, пуши в форк OrcaSlicer)" -ForegroundColor Gray
Write-Host ""
Write-Host "Для обновления версии OrcaSlicer в FilamentHub:" -ForegroundColor Yellow
Write-Host "  git submodule update --remote $OrcaSlicerPath" -ForegroundColor White
Write-Host "  git add $OrcaSlicerPath" -ForegroundColor White
Write-Host "  git commit -m 'Update OrcaSlicer submodule'" -ForegroundColor White
Write-Host "  git push origin main" -ForegroundColor White
Write-Host ""

