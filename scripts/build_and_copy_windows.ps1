# Скрипт для сборки Windows версии и копирования в distributions

$ErrorActionPreference = "Stop"

$OrcaSlicerDir = Join-Path $PSScriptRoot "..\docs\OrcaSlicer"
$DistributionsDir = Join-Path $PSScriptRoot "..\backend\distributions\orcaslicer"
$Version = "2.0.0-fh"

Write-Host "🔨 Сборка OrcaSlicer для Windows..." -ForegroundColor Cyan
Write-Host "Директория: $OrcaSlicerDir"
Write-Host ""

# Переходим в директорию OrcaSlicer
Push-Location $OrcaSlicerDir

try {
    # Сборка
    Write-Host "Запускаю сборку..." -ForegroundColor Yellow
    & .\build_release_vs2022.bat slicer
    
    if ($LASTEXITCODE -ne 0) {
        throw "Сборка завершилась с ошибкой (код: $LASTEXITCODE)"
    }
    
    Write-Host "✅ Сборка завершена успешно!" -ForegroundColor Green
    Write-Host ""
    
    # Проверяем результаты
    $Installer = Get-Item "build\OrcaSlicer_Windows_Installer_*.exe" -ErrorAction SilentlyContinue
    $BuildDir = Get-Item "build\OrcaSlicer" -ErrorAction SilentlyContinue
    
    if (-not $Installer) {
        throw "Установщик не найден после сборки"
    }
    
    if (-not $BuildDir) {
        throw "Папка build\OrcaSlicer не найдена"
    }
    
    # Создаем папку distributions
    New-Item -ItemType Directory -Force -Path $DistributionsDir | Out-Null
    
    # Копируем установщик
    $InstallerDest = Join-Path $DistributionsDir "OrcaSlicer-FilamentHub-${Version}-win64.exe"
    Copy-Item $Installer.FullName $InstallerDest -Force
    Write-Host "✅ Скопирован установщик: $InstallerDest" -ForegroundColor Green
    Write-Host "   Размер: $([math]::Round($Installer.Length/1MB, 2)) MB"
    
    # Создаем portable ZIP
    $ZipDest = Join-Path $DistributionsDir "OrcaSlicer-FilamentHub-${Version}-win64-portable.zip"
    Write-Host ""
    Write-Host "Создаю portable ZIP..." -ForegroundColor Yellow
    
    # Удаляем старый ZIP если есть
    if (Test-Path $ZipDest) {
        Remove-Item $ZipDest -Force
    }
    
    # Создаем ZIP из содержимого папки OrcaSlicer
    Compress-Archive -Path "$($BuildDir.FullName)\*" -DestinationPath $ZipDest -Force
    $ZipSize = (Get-Item $ZipDest).Length
    Write-Host "✅ Создан portable ZIP: $ZipDest" -ForegroundColor Green
    Write-Host "   Размер: $([math]::Round($ZipSize/1MB, 2)) MB"
    
    Write-Host ""
    Write-Host "🎉 Готово! Файлы скопированы в:" -ForegroundColor Green
    Write-Host "   $DistributionsDir" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Файлы будут доступны через:" -ForegroundColor Yellow
    Write-Host "   - API: /api/v1/downloads/orcaslicer"
    Write-Host "   - Прямая ссылка: http://filamenthub.ru/distributions/orcaslicer/{filename}"
    
} catch {
    Write-Host "❌ Ошибка: $_" -ForegroundColor Red
    exit 1
} finally {
    Pop-Location
}

