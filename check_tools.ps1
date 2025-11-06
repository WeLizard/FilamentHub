Write-Host "=== Проверка инструментов для сборки OrcaSlicer ===" -ForegroundColor Green

# CMake
Write-Host "`nCMake:" -ForegroundColor Yellow
try {
    $cmakeVersion = cmake --version 2>&1 | Select-String "version"
    if ($cmakeVersion -match "3\.31\.") {
        Write-Host "✅ $cmakeVersion" -ForegroundColor Green
    } else {
        Write-Host "❌ $cmakeVersion (требуется 3.31.x)" -ForegroundColor Red
        Write-Host "   Проверьте PATH - CMake должен быть раньше Strawberry Perl" -ForegroundColor Yellow
    }
} catch {
    Write-Host "❌ CMake не найден" -ForegroundColor Red
}

# Git
Write-Host "`nGit:" -ForegroundColor Yellow
try {
    git --version | ForEach-Object { Write-Host "✅ $_" -ForegroundColor Green }
} catch {
    Write-Host "❌ Git не найден" -ForegroundColor Red
}

# Git LFS
Write-Host "`nGit LFS:" -ForegroundColor Yellow
try {
    git lfs version 2>&1 | ForEach-Object { Write-Host "✅ $_" -ForegroundColor Green }
} catch {
    Write-Host "⚠️  Git LFS не найден (может быть не установлен)" -ForegroundColor Yellow
}

# Visual Studio
Write-Host "`nVisual Studio:" -ForegroundColor Yellow
$vs2022Paths = @(
    "C:\Program Files\Microsoft Visual Studio\2022\Professional",
    "C:\Program Files\Microsoft Visual Studio\2022\Community",
    "C:\Program Files\Microsoft Visual Studio\2022\BuildTools"
)
$vsFound = $false
foreach ($path in $vs2022Paths) {
    if (Test-Path $path) {
        $vsName = Split-Path $path -Leaf
        Write-Host "✅ Visual Studio 2022 $vsName найдено" -ForegroundColor Green
        $vsFound = $true
        break
    }
}
if (-not $vsFound) {
    Write-Host "❌ Visual Studio 2022 не найдено" -ForegroundColor Red
    Write-Host "   Установите через: winget install --id=Microsoft.VisualStudio.2022.Professional -e" -ForegroundColor Yellow
}

# Strawberry Perl
Write-Host "`nStrawberry Perl:" -ForegroundColor Yellow
try {
    $perlVersion = perl --version 2>&1 | Select-String "This is"
    if ($perlVersion) {
        Write-Host "✅ $perlVersion" -ForegroundColor Green
    } else {
        Write-Host "⚠️  Perl найден, но версия не определена" -ForegroundColor Yellow
    }
} catch {
    Write-Host "⚠️  Perl не найден в PATH" -ForegroundColor Yellow
}

# Проверка порядка PATH
Write-Host "`n=== Проверка порядка PATH ===" -ForegroundColor Green
$pathEntries = $env:PATH -split ';' | Where-Object { 
    $_ -and ($_ -match "CMake|Strawberry|Program Files\\CMake|Strawberry\\c\\bin")
} | Select-Object -First 10

$cmakePos = -1
$strawberryPos = -1
for ($i = 0; $i -lt $pathEntries.Length; $i++) {
    if ($pathEntries[$i] -match "Program Files\\CMake") {
        $cmakePos = $i
        Write-Host "[$i] $($pathEntries[$i])" -ForegroundColor Green
    } elseif ($pathEntries[$i] -match "Strawberry\\c\\bin") {
        $strawberryPos = $i
        Write-Host "[$i] $($pathEntries[$i])" -ForegroundColor Cyan
    } elseif ($pathEntries[$i] -match "CMake|Strawberry") {
        Write-Host "[$i] $($pathEntries[$i])" -ForegroundColor Gray
    }
}

if ($cmakePos -ge 0 -and $strawberryPos -ge 0 -and $cmakePos -gt $strawberryPos) {
    Write-Host "`n⚠️  ВНИМАНИЕ: Strawberry Perl идет РАНЬШЕ CMake в PATH!" -ForegroundColor Red
    Write-Host "   Это может вызвать проблемы. Переместите CMake выше в PATH." -ForegroundColor Yellow
} elseif ($cmakePos -ge 0 -and $strawberryPos -ge 0) {
    Write-Host "`n✅ Порядок PATH правильный (CMake раньше Strawberry Perl)" -ForegroundColor Green
}

Write-Host "`n=== Проверка завершена! ===" -ForegroundColor Green


