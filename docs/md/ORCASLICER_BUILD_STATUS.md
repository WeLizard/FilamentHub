# OrcaSlicer - Статус сборки

> **Дата запуска:** 2025-01-XX  
> **Путь:** `docs/OrcaSlicer-main/OrcaSlicer-main/`

---

## 🚀 Сборка запущена

Сборка выполняется в фоновом режиме через:
```batch
build_release_vs2022.bat
```

**Ожидаемое время:** ~1-2 часа (первая сборка)

---

## 📊 Этапы сборки

### 1. Зависимости (deps)
- **Папка:** `deps\build\`
- **Время:** ~30-60 минут
- **Что собирается:**
  - Boost
  - CGAL
  - wxWidgets
  - OpenCV
  - И другие зависимости

### 2. OrcaSlicer
- **Папка:** `build\`
- **Время:** ~30-60 минут
- **Что собирается:**
  - Основной код OrcaSlicer
  - GUI компоненты
  - Slicing алгоритмы

### 3. Установка (install)
- **Папка:** `build\package\bin\`
- **Результат:** `orca-slicer.exe`

---

## 🔍 Проверка прогресса

### Проверить процесс сборки:

```powershell
# Проверить процессы
Get-Process -Name cmake,msbuild -ErrorAction SilentlyContinue

# Проверить папки сборки
Test-Path "deps\build"
Test-Path "build"

# Посмотреть файлы в deps\build (если есть)
Get-ChildItem "deps\build" | Select-Object -First 5
```

### Проверить логи:

Сборка выводит логи в консоль. Если запускали через PowerShell, проверьте вывод процесса.

---

## ⚠️ Если сборка зависла или ошибка

### Проблема 1: CMake не запускается

**Проверка:**
```powershell
cmake --version
# Должно быть: cmake version 3.31.6
```

**Решение:**
- Используйте "x64 Native Tools Command Prompt for VS 2022"
- Или запустите `VsDevCmd.bat` перед сборкой

### Проблема 2: Ошибки компиляции зависимостей

**Решение:**
1. Убедитесь, что Visual Studio 2022 установлен полностью
2. Компонент: "Desktop development with C++"
3. Попробуйте пересобрать: `build_release_vs2022.bat`

### Проблема 3: Нехватка памяти

**Решение:**
- Закройте другие программы
- Используйте меньше параллельных потоков (изменить скрипт)

---

## ✅ Когда сборка завершится

После успешной сборки проверьте:

```powershell
# Исполняемый файл должен быть здесь:
Test-Path "build\package\bin\orca-slicer.exe"

# Размер должен быть > 10 MB
(Get-Item "build\package\bin\orca-slicer.exe").Length
```

**Запуск:**
```batch
build\package\bin\orca-slicer.exe
```

---

## 📚 Дополнительная информация

- **Полная инструкция:** `docs/ORCASLICER_BUILD_INSTRUCTIONS.md`
- **Быстрый старт:** `docs/ORCASLICER_QUICK_START.md`
- **Установка инструментов:** `docs/ORCASLICER_BUILD_SETUP.md`

---

**Сборка запущена. Ожидайте завершения (~1-2 часа).** ⏳


