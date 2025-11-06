# OrcaSlicer - Быстрый старт для сборки

> **У вас уже есть клон OrcaSlicer в:** `docs/OrcaSlicer-main/OrcaSlicer-main/`  
> **Статус инструментов:** ✅ Все установлены

---

## ✅ Быстрая проверка готовности

```powershell
# Проверить инструменты
cd F:\FilamentHub
.\check_tools.ps1

# Перейти в OrcaSlicer
cd docs\OrcaSlicer-main\OrcaSlicer-main

# Проверить файлы сборки
Test-Path build_release_vs2022.bat  # Должно быть True
Test-Path CMakeLists.txt            # Должно быть True
```

---

## 🚀 Сборка (первый раз)

### Вариант 1: Через VS Command Prompt (рекомендуется)

1. **Откройте "x64 Native Tools Command Prompt for VS 2022"** (через Start Menu)

2. **Перейдите в проект:**
   ```batch
   cd F:\FilamentHub\docs\OrcaSlicer-main\OrcaSlicer-main
   ```

3. **Запустите сборку:**
   ```batch
   build_release_vs2022.bat
   ```

⏱️ **Время:** ~1-2 часа (первая сборка)

### Вариант 2: Через PowerShell

```powershell
# Загрузить VS окружение
& "C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat"

# Перейти в проект
cd F:\FilamentHub\docs\OrcaSlicer-main\OrcaSlicer-main

# Запустить сборку
.\build_release_vs2022.bat
```

---

## 📂 Результат сборки

После успешной сборки:

```
OrcaSlicer-main/
└── build/
    └── package/
        └── bin/
            └── orca-slicer.exe  ← Исполняемый файл
```

**Проверка:**
```batch
dir build\package\bin\orca-slicer.exe
```

**Запуск:**
```batch
build\package\bin\orca-slicer.exe
```

---

## 🔄 Параметры сборки

### Только зависимости (первый раз или после обновления)
```batch
build_release_vs2022.bat deps
```

### Только OrcaSlicer (быстрая пересборка)
```batch
build_release_vs2022.bat slicer
```

### Debug сборка
```batch
build_release_vs2022.bat debug
```

---

## ⚠️ Если что-то не работает

1. **CMake не найден:**
   - Используйте VS Command Prompt (не обычный PowerShell)
   - Или запустите `VsDevCmd.bat` в PowerShell

2. **CMake версия неправильная:**
   ```powershell
   cmake --version
   # Должно быть 3.31.6
   # Если нет - запустите: .\check_tools.ps1
   ```

3. **Ошибки компиляции:**
   - Убедитесь, что Visual Studio 2022 установлен полностью
   - Компонент: "Desktop development with C++"
   - Перезапустите сборку: `build_release_vs2022.bat`

---

## 📚 Подробная документация

- **Установка инструментов:** `docs/ORCASLICER_BUILD_SETUP.md`
- **Полная инструкция по сборке:** `docs/ORCASLICER_BUILD_INSTRUCTIONS.md`
- **Изучение интеграции:** `docs/ORCASLICER_INTEGRATION.md`

---

**Готово! Можно собирать.** 🚀


