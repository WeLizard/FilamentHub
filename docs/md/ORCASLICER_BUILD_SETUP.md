# OrcaSlicer - Настройка окружения для сборки

> **Дата создания:** 2025-01-XX  
> **Платформа:** Windows  
> **Цель:** Установить все необходимые инструменты для сборки OrcaSlicer

---

## 🐳 Вариант 1: Docker + WSL2 (рекомендуется для Linux-сборки)

### Преимущества
- ✅ Изолированное окружение
- ✅ Не загрязняет систему
- ✅ Все зависимости уже настроены
- ✅ Быстрая пересборка

### Недостатки
- ❌ Работает только на Linux (или через WSL2 на Windows)
- ❌ Нужен WSL2 для Windows
- ❌ GUI требует X11 forwarding

### Требования

1. **Docker Desktop для Windows** или **Docker + WSL2**
2. **WSL2** (если на Windows)
   ```powershell
   # Проверить версию WSL
   wsl --version
   
   # Если не установлен, установить WSL2
   wsl --install
   ```

3. **Git**
   ```powershell
   winget install --id=Git.Git -e
   ```

### Установка через Docker (WSL2)

1. **Запустить WSL2:**
   ```powershell
   wsl
   ```

2. **Клонировать OrcaSlicer:**
   ```bash
   git clone https://github.com/SoftFever/OrcaSlicer
   cd OrcaSlicer
   ```

3. **Собрать Docker образ:**
   ```bash
   ./scripts/DockerBuild.sh
   ```
   
   ⏱️ **Время:** ~1-2 часа (первая сборка)

4. **Запустить OrcaSlicer:**
   ```bash
   ./scripts/DockerRun.sh
   ```

### Troubleshooting для Docker

**Если проблемы с X11 (GUI не работает):**

```bash
# В WSL2 перед запуском DockerRun.sh
export DISPLAY=$(cat /etc/resolv.conf | grep nameserver | awk '{print $2}'):0
xhost +local:docker
```

**Если проблемы с правами:**
```bash
# Запуск с вашим пользователем
docker run -u $(id -u):$(id -g) ...
```

---

## 🪟 Вариант 2: Локальная установка на Windows (для нативной сборки)

### Требования

1. **Visual Studio 2022** (или 2019)
   ```powershell
   winget install --id=Microsoft.VisualStudio.2022.Professional -e
   ```
   
   **Или Visual Studio Build Tools:**
   ```powershell
   winget install --id=Microsoft.VisualStudio.2022.BuildTools -e
   ```
   
   **Компоненты VS 2022:**
   - Desktop development with C++
   - CMake tools for Windows
   - Windows 10/11 SDK

2. **CMake версия 3.31.x** (строго!)
   ```powershell
   # Установить точную версию
   winget install --id=Kitware.CMake -v "3.31.6" -e
   ```
   
   **⚠️ КРИТИЧНО:** Проверьте версию после установки:
   ```powershell
   cmake --version
   # Должно быть: cmake version 3.31.x
   ```
   
   **Если версия неправильная:**
   - Проверьте PATH: `C:\Program Files\CMake\bin` должен быть **раньше** других CMake
   - Удалите старый CMake из PATH (например, из Strawberry Perl)

3. **Strawberry Perl**
   ```powershell
   winget install --id=StrawberryPerl.StrawberryPerl -e
   ```
   
   **⚠️ ВАЖНО:** После установки проверьте порядок PATH:
   - `C:\Program Files\CMake\bin` - **РАНЬШЕ**
   - `C:\Strawberry\c\bin` - **ПОЗЖЕ**
   
   **Если порядок неправильный:**
   - Откройте "Переменные среды" → "PATH"
   - Переместите CMake выше Strawberry Perl

4. **Git + Git LFS**
   ```powershell
   winget install --id=Git.Git -e
   winget install --id=GitHub.GitLFS -e
   ```

### Проверка установки

Создайте файл `check_tools.ps1`:

```powershell
Write-Host "=== Проверка инструментов для сборки OrcaSlicer ===" -ForegroundColor Green

# CMake
Write-Host "`nCMake:" -ForegroundColor Yellow
$cmakeVersion = cmake --version 2>&1 | Select-String "version"
if ($cmakeVersion -match "3\.31\.") {
    Write-Host "✅ $cmakeVersion" -ForegroundColor Green
} else {
    Write-Host "❌ $cmakeVersion (требуется 3.31.x)" -ForegroundColor Red
    Write-Host "   Проверьте PATH - CMake должен быть раньше Strawberry Perl" -ForegroundColor Yellow
}

# Git
Write-Host "`nGit:" -ForegroundColor Yellow
git --version | ForEach-Object { Write-Host "✅ $_" -ForegroundColor Green }

# Git LFS
Write-Host "`nGit LFS:" -ForegroundColor Yellow
git lfs version | ForEach-Object { Write-Host "✅ $_" -ForegroundColor Green }

# Visual Studio
Write-Host "`nVisual Studio:" -ForegroundColor Yellow
$vsPath = "C:\Program Files\Microsoft Visual Studio\2022"
if (Test-Path "$vsPath\Professional") {
    Write-Host "✅ Visual Studio 2022 Professional найдено" -ForegroundColor Green
} elseif (Test-Path "$vsPath\Community") {
    Write-Host "✅ Visual Studio 2022 Community найдено" -ForegroundColor Green
} elseif (Test-Path "$vsPath\BuildTools") {
    Write-Host "✅ Visual Studio 2022 Build Tools найдено" -ForegroundColor Green
} else {
    Write-Host "❌ Visual Studio 2022 не найдено" -ForegroundColor Red
}

# Strawberry Perl
Write-Host "`nStrawberry Perl:" -ForegroundColor Yellow
if (Get-Command perl -ErrorAction SilentlyContinue) {
    $perlVersion = perl --version 2>&1 | Select-String "This is"
    Write-Host "✅ $perlVersion" -ForegroundColor Green
} else {
    Write-Host "⚠️  Perl не найден в PATH" -ForegroundColor Yellow
}

Write-Host "`n=== Проверка порядка PATH ===" -ForegroundColor Green
$pathEntries = $env:PATH -split ';' | Where-Object { 
    $_ -match "CMake|Strawberry" 
}
foreach ($entry in $pathEntries) {
    Write-Host $entry -ForegroundColor Cyan
}

Write-Host "`n✅ Проверка завершена!" -ForegroundColor Green
```

Запустите:
```powershell
.\check_tools.ps1
```

### Настройка командного промпта

**Важно:** Для сборки нужно использовать правильный командный промпт:

1. Откройте **Start Menu**
2. Найдите **"x64 Native Tools Command Prompt for VS 2022"**
   - Или: `"Developer Command Prompt for VS 2022"`
3. Проверьте, что CMake доступен:
   ```batch
   cmake --version
   ```

**Альтернатива:** Используйте PowerShell с инициализацией VS:

```powershell
# Загрузить переменные окружения VS 2022
& "C:\Program Files\Microsoft Visual Studio\2022\Professional\Common7\Tools\VsDevCmd.bat"
# Или для Build Tools:
& "C:\Program Files\Microsoft Visual Studio\2022\BuildTools\Common7\Tools\VsDevCmd.bat"
```

---

## 🚀 Вариант 3: WSL2 + Локальная сборка (гибридный)

Можно использовать WSL2 для сборки Linux-версии, но это требует:

1. **WSL2 с Ubuntu/Debian**
2. **Установка зависимостей в WSL2:**
   ```bash
   # В WSL2
   sudo apt update
   sudo apt install -y build-essential cmake git libgtk-3-dev libwebkit2gtk-4.1-dev
   ```
3. **Сборка через build_linux.sh:**
   ```bash
   ./build_linux.sh -u  # Установка зависимостей
   ./build_linux.sh -dsti  # Сборка
   ```

---

## 📋 Рекомендации

### Для разработки FilamentHub интеграции:

**Рекомендуется: Вариант 2 (Локальная установка на Windows)**

**Почему:**
- ✅ Можно собирать нативный Windows-бинарник
- ✅ Легче отлаживать в Visual Studio
- ✅ Быстрее разработка (без Docker overhead)
- ✅ Прямой доступ к файлам проекта

**Когда использовать Docker:**
- Если нужна Linux-версия
- Если не хотите засорять систему
- Если нужна изоляция окружения

### Быстрый старт (Windows)

1. **Установить инструменты** (см. Вариант 2)
2. **Проверить установку** (`check_tools.ps1`)
3. **Клонировать OrcaSlicer:**
   ```powershell
   git clone https://github.com/SoftFever/OrcaSlicer
   cd OrcaSlicer
   git lfs pull
   ```
4. **Открыть VS Command Prompt** и собрать:
   ```batch
   build_release_vs2022.bat
   ```

---

## ⚠️ Частые проблемы

### Проблема 1: CMake версия неправильная

**Симптомы:**
```
CMake version 3.29 found, but 3.31.x required
```

**Решение:**
1. Проверьте порядок PATH
2. Удалите старый CMake из PATH
3. Установите CMake 3.31.6 напрямую

### Проблема 2: Strawberry Perl в PATH перед CMake

**Симптомы:**
```
CMake misbehaving (e.g., missing modules)
```

**Решение:**
1. Откройте "Переменные среды"
2. В "PATH" переместите `C:\Program Files\CMake\bin` выше `C:\Strawberry\c\bin`
3. Перезапустите терминал

### Проблема 3: Visual Studio не найден

**Симптомы:**
```
No CMAKE_CXX_COMPILER could be found
```

**Решение:**
1. Используйте **"x64 Native Tools Command Prompt for VS 2022"**
2. Или запустите `VsDevCmd.bat` в PowerShell

### Проблема 4: Git LFS файлы не загружены

**Симптомы:**
```
Missing files in deps/
```

**Решение:**
```powershell
git lfs pull
```

---

## 🔧 Дополнительные инструменты (опционально)

### Для отладки:

1. **Debugger Tools for Windows**
   - Входит в Visual Studio
   - Или отдельно: Windows SDK

2. **Process Monitor** (от Sysinternals)
   - Для мониторинга файловых операций
   - https://docs.microsoft.com/en-us/sysinternals/downloads/procmon

### Для анализа:

1. **Dependency Walker** (старая версия)
   - Для анализа DLL зависимостей

2. **CMake GUI** (опционально)
   ```powershell
   winget install --id=Kitware.CMake.GUI -e
   ```

---

## ✅ Чеклист готовности

- [ ] Visual Studio 2022 установлен
- [ ] CMake 3.31.x установлен и в PATH
- [ ] Git и Git LFS установлены
- [ ] Strawberry Perl установлен
- [ ] Порядок PATH правильный (CMake перед Perl)
- [ ] VS Command Prompt работает
- [ ] `cmake --version` показывает 3.31.x
- [ ] OrcaSlicer клонирован
- [ ] `git lfs pull` выполнен

**Готовы к сборке?** → Переходите к `ORCASLICER_INTEGRATION.md`

---

**Создано:** 2025-01-XX  
**Последнее обновление:** 2025-01-XX


