# OrcaSlicer - Быстрая инструкция по сборке

> **Путь:** `docs/OrcaSlicer/` (форк с изменениями FilamentHub)  
> **Ветка:** `filamenthub-integration`

---

## 🚀 Быстрая сборка (если зависимости уже собраны)

### 1. Открыть VS Command Prompt

**PowerShell:**
```powershell
# Загрузить переменные окружения VS
& "C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat"

# Перейти в проект (ВАЖНО: правильный путь!)
cd F:\FilamentHub\docs\OrcaSlicer
```

### 2. Пересобрать только OrcaSlicer (без зависимостей)

```batch
build_release_vs2022.bat slicer
```

⏱️ **Время:** ~5-15 минут (только изменения в коде)

**Что делает:**
- Собирает только OrcaSlicer с нашими изменениями (FilamentHubClient, FilamentHubPanel)
- Не пересобирает зависимости (OpenCV, OCCT и т.д.)
- Результат: `build\package\bin\orca-slicer.exe`

---

## 🆕 Первая сборка (если зависимости не собраны)

### 1. Открыть VS Command Prompt

```powershell
& "C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat"
cd F:\FilamentHub\docs\OrcaSlicer
```

### 2. Полная сборка (зависимости + OrcaSlicer)

```batch
build_release_vs2022.bat
```

⏱️ **Время:** ~1-2 часа
- ~30-60 мин: зависимости (`deps`)
- ~30-60 мин: сам OrcaSlicer

---

## ✅ Проверка результата

```batch
# Проверить наличие файла
dir build\package\bin\orca-slicer.exe

# Запустить OrcaSlicer
build\package\bin\orca-slicer.exe
```

**Что проверить:**
1. ✅ OrcaSlicer запускается
2. ✅ Есть tab "FilamentHub" в главном окне
3. ✅ Можно нажать "Test Connection" в FilamentHub tab

---

## 🔧 Параметры сборки

| Параметр | Описание | Время |
|----------|----------|-------|
| `build_release_vs2022.bat` | Полная сборка (deps + slicer) | ~1-2 часа |
| `build_release_vs2022.bat slicer` | Только OrcaSlicer | ~5-15 мин |
| `build_release_vs2022.bat deps` | Только зависимости | ~30-60 мин |
| `build_release_vs2022.bat debug` | Debug сборка | ~10-20 мин |

---

## ⚠️ Если что-то пошло не так

### Ошибка компиляции FilamentHubClient/FilamentHubPanel

**Решение:**
1. Проверьте, что файлы добавлены в `src/slic3r/CMakeLists.txt`
2. Проверьте include пути (FilamentHubPanel должен видеть FilamentHubClient)
3. Пересоберите: `build_release_vs2022.bat slicer`

### "CMake not found"

**Решение:**
1. Используйте VS Command Prompt (не обычный PowerShell)
2. Запустите `VsDevCmd.bat` вручную

### Ошибки линковки

**Решение:**
1. Убедитесь, что зависимости собраны (`deps\build\` существует)
2. Если нет - соберите зависимости: `build_release_vs2022.bat deps`

---

## 📂 Результат сборки

```
docs/OrcaSlicer/
├── build/
│   └── package/
│       └── bin/
│           └── orca-slicer.exe  ← Исполняемый файл
└── deps/
    └── build/                    ← Зависимости (если собирали)
```

---

**Готово к сборке!** 🚀

