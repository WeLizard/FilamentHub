# OrcaSlicer - Инструкция по сборке (Windows)

> **Статус:** Готов к сборке  
> **Путь:** `docs/OrcaSlicer-main/OrcaSlicer-main/`  
> **Дата:** 2025-01-XX

---

## ✅ Предварительные проверки

### 1. Инструменты установлены ✅

Запустите проверку:
```powershell
cd F:\FilamentHub
.\check_tools.ps1
```

**Должно быть:**
- ✅ CMake 3.31.6
- ✅ Visual Studio 2022
- ✅ Git + Git LFS
- ✅ Strawberry Perl
- ✅ Порядок PATH правильный

### 2. Git LFS файлы загружены

```powershell
cd docs\OrcaSlicer-main\OrcaSlicer-main
git lfs pull
```

**Проверка:**
```powershell
git lfs ls-files | Measure-Object -Line
# Должно быть > 0 файлов
```

---

## 🚀 Сборка OrcaSlicer

### Шаг 1: Открыть VS Command Prompt

**Вариант A: Через меню Start**
1. Найдите **"x64 Native Tools Command Prompt for VS 2022"**
2. Откройте его

**Вариант B: Через PowerShell**
```powershell
# Загрузить переменные окружения VS
& "C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat"

# Перейти в проект
cd F:\FilamentHub\docs\OrcaSlicer-main\OrcaSlicer-main
```

### Шаг 2: Первая сборка (полная)

**Сборка зависимостей + OrcaSlicer:**
```batch
build_release_vs2022.bat
```

⏱️ **Время:** ~1-2 часа (первая сборка)
- ~30-60 мин: зависимости (`deps`)
- ~30-60 мин: сам OrcaSlicer

**Что делает скрипт:**
1. Собирает зависимости в `deps\build\`
2. Собирает OrcaSlicer в `build\`
3. Устанавливает бинарники в `build\package\`

### Шаг 3: Проверка результата

```batch
# Проверить наличие исполняемого файла
dir build\package\bin\orca-slicer.exe

# Запустить (если собран)
build\package\bin\orca-slicer.exe
```

---

## 🔧 Параметры сборки

### Только зависимости

```batch
build_release_vs2022.bat deps
```

**Когда использовать:**
- Первая сборка (нужны зависимости)
- Обновление зависимостей

### Только OrcaSlicer (без зависимостей)

```batch
build_release_vs2022.bat slicer
```

**Когда использовать:**
- Зависимости уже собраны
- Изменяли только код OrcaSlicer
- Быстрая пересборка

### Debug сборка

```batch
build_release_vs2022.bat debug
```

**Результат:**
- Папка: `build-dbg\` (вместо `build\`)
- Тип: Debug
- Размер: больше, медленнее, но с отладочной информацией

### Release с debug info

```batch
build_release_vs2022.bat debuginfo
```

**Результат:**
- Папка: `build-dbginfo\`
- Тип: RelWithDebInfo
- Оптимизированный, но с символами для отладки

---

## ⚠️ Частые проблемы

### Проблема 1: "CMake not found"

**Решение:**
1. Используйте **VS Command Prompt** (не обычный PowerShell)
2. Или запустите `VsDevCmd.bat` в PowerShell

### Проблема 2: "CMake version mismatch" (нужна 3.31.x)

**Решение:**
```powershell
# Проверить версию
cmake --version

# Если не 3.31.x, проверьте PATH
$env:PATH -split ';' | Where-Object { $_ -match "CMake" }
```

### Проблема 3: "Missing LFS files"

**Решение:**
```powershell
git lfs pull
```

### Проблема 4: Ошибки компиляции зависимостей

**Решение:**
1. Убедитесь, что Visual Studio 2022 установлен полностью
2. Компонент: "Desktop development with C++"
3. Windows SDK: последняя версия
4. Попробуйте пересобрать: `build_release_vs2022.bat`

---

## 📂 Структура после сборки

```
OrcaSlicer-main/
├── deps/
│   └── build/              # Собранные зависимости
│       └── OrcaSlicer_dep/
│           ├── bin/        # Библиотеки (dll)
│           ├── include/    # Заголовки
│           └── lib/        # .lib файлы
├── build/                   # Release сборка
│   ├── package/
│   │   └── bin/
│   │       └── orca-slicer.exe  # ← Исполняемый файл
│   └── ...                 # Промежуточные файлы
└── build-dbg/              # Debug сборка (если собрали debug)
```

---

## 🔄 Пересборка после изменений

### Быстрая пересборка (только OrcaSlicer)

```batch
build_release_vs2022.bat slicer
```

⏱️ **Время:** ~5-10 минут

### Полная пересборка

```batch
# Удалить старые сборки (опционально)
rmdir /s /q build deps\build

# Пересобрать
build_release_vs2022.bat
```

---

## 🧪 Тестирование

После сборки можно запустить:

```batch
build\package\bin\orca-slicer.exe
```

**Проверка:**
- ✅ Приложение запускается
- ✅ GUI отображается
- ✅ Нет ошибок при старте

---

## 📚 Дополнительная информация

- **Полная документация:** `doc/developer-reference/How-to-build.md`
- **Изучение интеграции:** `docs/ORCASLICER_INTEGRATION.md`
- **Настройка инструментов:** `docs/ORCASLICER_BUILD_SETUP.md`

---

**Готово к сборке!** 🚀


