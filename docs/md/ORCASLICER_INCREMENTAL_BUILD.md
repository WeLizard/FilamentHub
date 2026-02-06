# OrcaSlicer - Инкрементальная сборка (только изменённые файлы)

> **Путь:** `docs/OrcaSlicer/`  
> **Цель:** Пересобрать только изменённые файлы (быстрее полной сборки)

---

## 🚀 Способ 1: Visual Studio Solution (самый простой)

### 1. Открыть Solution в Visual Studio

```powershell
# Открыть solution
start C:\Users\Engineer\Downloads\FilamentHub\docs\OrcaSlicer\build\OrcaSlicer.sln
```

**Или вручную:**
1. Откройте Visual Studio 2022
2. File → Open → Project/Solution
3. Выберите `C:\Users\Engineer\Downloads\FilamentHub\docs\OrcaSlicer\build\OrcaSlicer.sln`

### 2. Собрать проект

**В Visual Studio:**
- `Build → Build Solution` (Ctrl+Shift+B)
- Или `Build → Build libslic3r_gui` (только GUI библиотека)

**Что происходит:**
- ✅ Visual Studio автоматически отслеживает изменения
- ✅ Пересобираются только изменённые `.cpp` файлы
- ✅ Остальные файлы не пересобираются (быстрее!)
- ⏱️ **Время:** ~1-5 минут (зависит от количества изменённых файлов)

---

## 🔧 Способ 2: MSBuild (из командной строки)

### 1. Загрузить переменные окружения VS

```powershell
& "C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat"
```

### 2. Собрать только проект `libslic3r_gui` (где FilamentHubPanel)

```powershell
cd C:\Users\Engineer\Downloads\FilamentHub\docs\OrcaSlicer\build

# Собрать только libslic3r_gui (инкрементально)
msbuild src\slic3r\libslic3r_gui.vcxproj /p:Configuration=Release /p:Platform=x64 /t:Build /m
```

**Что происходит:**
- ✅ MSBuild автоматически проверяет изменения
- ✅ Пересобираются только изменённые файлы
- ✅ Остальные файлы пропускаются
- ⏱️ **Время:** ~1-5 минут

### 3. Установить результат (после сборки)

```powershell
# Установить результат
cmake --build . --target install --config Release
```

---

## ⚡ Способ 3: CMake Build (самый быстрый для изменённых файлов)

### 1. Загрузить переменные окружения VS

```powershell
& "C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat"
```

### 2. Собрать через CMake (инкрементально)

```powershell
cd C:\Users\Engineer\Downloads\FilamentHub\docs\OrcaSlicer\build

# CMake автоматически пересобирает только изменённые файлы
cmake --build . --config Release --target libslic3r_gui -- -m
```

**Что происходит:**
- ✅ CMake отслеживает изменения через `.obj` файлы
- ✅ Пересобираются только изменённые `.cpp` файлы
- ✅ Остальные файлы пропускаются
- ⏱️ **Время:** ~1-5 минут

### 3. Установить результат

```powershell
# Установить результат
cmake --build . --target install --config Release
```

---

## 🎯 Способ 4: Собрать только FilamentHub файлы (если нужно)

### Если изменились только FilamentHubPanel.cpp или FilamentHubClient.cpp:

```powershell
cd C:\Users\Engineer\Downloads\FilamentHub\docs\OrcaSlicer\build

# Собрать только libslic3r_gui (где находятся FilamentHub файлы)
cmake --build . --config Release --target libslic3r_gui -- -m

# Установить результат
cmake --build . --target install --config Release
```

**Что происходит:**
- ✅ Пересобираются только FilamentHubPanel.cpp и FilamentHubClient.cpp
- ✅ Остальные файлы не пересобираются
- ⏱️ **Время:** ~30 секунд - 2 минуты

---

## 📊 Сравнение методов

| Метод | Время | Удобство | Автоматизация |
|-------|-------|----------|---------------|
| **Visual Studio** | ~1-5 мин | ⭐⭐⭐⭐⭐ | ✅ Автоматически |
| **MSBuild** | ~1-5 мин | ⭐⭐⭐⭐ | ✅ Автоматически |
| **CMake Build** | ~1-5 мин | ⭐⭐⭐ | ✅ Автоматически |
| **Полная сборка** | ~5-15 мин | ⭐⭐ | ❌ Всегда пересобирает всё |

---

## ✅ Проверка результата

После инкрементальной сборки:

```powershell
# Проверить время изменения exe файла
dir build\package\bin\orca-slicer.exe

# Запустить OrcaSlicer
build\package\bin\orca-slicer.exe
```

---

## 🔍 Как понять, что пересобралось

### В Visual Studio:
- **Output** окно показывает: `"Building..."` для изменённых файлов
- **Output** окно показывает: `"Skipping..."` для неизменённых файлов

### В MSBuild/CMake:
- В логах видно: `"Building..."` для изменённых файлов
- В логах видно: `"Up-to-date"` для неизменённых файлов

---

## 💡 Советы

1. **Используйте Visual Studio** - самый удобный способ для разработки
2. **Не удаляйте `.obj` файлы** - они нужны для инкрементальной сборки
3. **Если сборка "глючит"** - сделайте полную пересборку: `build_release_vs2022.bat slicer`
4. **Проверяйте логи** - если есть ошибки, они будут видны в Output окне

---

## 🚨 Если инкрементальная сборка не работает

### Принудительная пересборка всех файлов:

```powershell
# Очистить и пересобрать
cmake --build . --config Release --target libslic3r_gui --clean-first -- -m
```

### Или полная пересборка:

```batch
build_release_vs2022.bat slicer
```

---

**Готово!** 🚀

Инкрементальная сборка автоматически работает во всех методах выше - просто соберите проект, и пересоберутся только изменённые файлы.

