# Решение проблемы сборки OrcaSlicer

## ✅ Проверка: Все правки на месте!

Проверено:
- ✅ `src/slic3r/Utils/FilamentHubClient.hpp` - существует
- ✅ `src/slic3r/GUI/FilamentHubPanel.hpp` - существует
- ✅ Изменения в `CMakeLists.txt` (OpenCV, OCCT) - на месте
- ✅ Изменения в `MainFrame.hpp/cpp` - на месте
- ✅ Git коммиты показывают все изменения

**Вывод:** Все правки FilamentHub внесены правильно!

---

## ⚠️ Проблема: PowerShell требует `.\` перед скриптом

В PowerShell нужно использовать `.\` перед именем скрипта:

```powershell
# ❌ НЕПРАВИЛЬНО (не работает в PowerShell)
build_release_vs2022.bat deps

# ✅ ПРАВИЛЬНО (работает в PowerShell)
.\build_release_vs2022.bat deps
```

Или использовать **cmd.exe** (VS Command Prompt), там `.\` не нужен.

---

## 🚀 Правильная команда для сборки

### Вариант 1: PowerShell

```powershell
cd F:\FilamentHub\docs\OrcaSlicer

# Собрать зависимости (если еще не собраны)
.\build_release_vs2022.bat deps

# После сборки зависимостей - собрать OrcaSlicer
.\build_release_vs2022.bat slicer
```

### Вариант 2: cmd.exe (VS Command Prompt)

```batch
cd F:\FilamentHub\docs\OrcaSlicer

# Собрать зависимости
build_release_vs2022.bat deps

# Собрать OrcaSlicer
build_release_vs2022.bat slicer
```

---

## 📋 Полная последовательность

1. **Открыть VS Command Prompt** (или загрузить переменные VS в PowerShell)
2. **Перейти в проект:** `cd F:\FilamentHub\docs\OrcaSlicer`
3. **Собрать зависимости:** `.\build_release_vs2022.bat deps` (в PowerShell) или `build_release_vs2022.bat deps` (в cmd)
4. **Дождаться завершения** (~30-60 минут)
5. **Собрать OrcaSlicer:** `.\build_release_vs2022.bat slicer` (в PowerShell) или `build_release_vs2022.bat slicer` (в cmd)
6. **Дождаться завершения** (~5-15 минут)
7. **Запустить:** `build\package\bin\orca-slicer.exe`

---

**Все правки на месте! Просто используйте `.\` в PowerShell или переключитесь на cmd.exe.**

