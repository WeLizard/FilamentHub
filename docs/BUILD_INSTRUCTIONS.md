# Инструкция по сборке OrcaSlicer

## ✅ Статус компиляции

**Компиляция успешна!** ✅
- `libslic3r_gui` успешно скомпилирован
- Изменения в `FilamentHubPanel.cpp` и `FilamentHubClient.cpp` применены
- Новый `OrcaSlicer.dll` находится в `build\src\Release\OrcaSlicer.dll`

**Установка не удалась** ❌
- Ошибка: `Permission denied` при копировании `OrcaSlicer.dll`
- Причина: Файл заблокирован (OrcaSlicer запущен)

---

## 🔧 Что делать

### Вариант 1: Закрыть OrcaSlicer и установить

1. **Закрыть OrcaSlicer** (если запущен)
2. **Запустить установку:**
   ```bash
   cd docs\OrcaSlicer\build
   cmake --build . --target install --config Release
   ```
3. **Перезапустить OrcaSlicer** из `build\OrcaSlicer\orca-slicer.exe`

### Вариант 2: Скопировать DLL вручную

1. **Закрыть OrcaSlicer** (если запущен)
2. **Скопировать DLL:**
   ```powershell
   Copy-Item "docs\OrcaSlicer\build\src\Release\OrcaSlicer.dll" -Destination "docs\OrcaSlicer\build\OrcaSlicer\OrcaSlicer.dll" -Force
   ```
3. **Перезапустить OrcaSlicer** из `build\OrcaSlicer\orca-slicer.exe`

### Вариант 3: Использовать скомпилированный DLL напрямую

1. **Закрыть OrcaSlicer** (если запущен)
2. **Скопировать DLL в директорию установки OrcaSlicer** (если OrcaSlicer установлен)
3. **Или запустить OrcaSlicer из `build\src\Release\orca-slicer.exe`** (но там могут не хватать ресурсов)

---

## 📋 Пошаговая инструкция

### 1. Закрыть OrcaSlicer

```powershell
# Проверить, запущен ли OrcaSlicer
Get-Process -Name "orca-slicer","OrcaSlicer" -ErrorAction SilentlyContinue

# Если процесс найден, закрыть его
Stop-Process -Name "orca-slicer","OrcaSlicer" -Force -ErrorAction SilentlyContinue
```

### 2. Установить скомпилированные файлы

```powershell
cd docs\OrcaSlicer\build
cmake --build . --target install --config Release
```

### 3. Проверить результат

```powershell
# Проверить, что DLL обновлён
Get-Item "docs\OrcaSlicer\build\OrcaSlicer\OrcaSlicer.dll" | Select-Object LastWriteTime, Length
```

### 4. Запустить OrcaSlicer

```powershell
# Запустить OrcaSlicer из директории установки
Start-Process "docs\OrcaSlicer\build\OrcaSlicer\orca-slicer.exe"
```

---

## 🎯 Быстрая проверка изменений

### Проверка, что изменения применены:

1. **Проверить, что новый DLL создан:**
   ```powershell
   Get-Item "docs\OrcaSlicer\build\src\Release\OrcaSlicer.dll" | Select-Object LastWriteTime, Length
   ```

2. **Проверить, что DLL содержит новые функции:**
   - Открыть OrcaSlicer
   - Перейти на вкладку "FilamentHub"
   - Проверить логи: должны появиться записи `[info] FilamentHub: ========== FilamentHubPanel::init() CALLED ==========`

3. **Проверить синхронизацию:**
   - Нажать кнопку "Synchronize"
   - Проверить логи: должны появиться записи `[error] FilamentHub: ========== SYNC BUTTON CLICKED (ERROR LEVEL FOR VISIBILITY) ==========`

---

## ⚠️ Важно

1. **Всегда закрывать OrcaSlicer перед установкой** - иначе файл будет заблокирован
2. **Использовать `build\OrcaSlicer\orca-slicer.exe`** - это финальная версия с ресурсами
3. **Проверять логи после запуска** - должны появиться записи о FilamentHub

---

## 🔍 Диагностика проблем

### Проблема: "Permission denied" при установке
**Решение:** Закрыть OrcaSlicer перед установкой

### Проблема: DLL не обновляется
**Решение:** 
1. Закрыть OrcaSlicer
2. Удалить старый DLL вручную
3. Установить новый DLL

### Проблема: Логи не появляются
**Решение:**
1. Проверить, что новый DLL установлен
2. Проверить настройки логирования BOOST_LOG_TRIVIAL
3. Проверить, что логи пишутся в правильный файл

---

## 📝 Резюме

**Текущий статус:**
- ✅ Компиляция успешна
- ❌ Установка не удалась (файл заблокирован)
- ✅ Новый DLL готов в `build\src\Release\OrcaSlicer.dll`

**Следующие шаги:**
1. Закрыть OrcaSlicer (если запущен)
2. Установить DLL (скопировать в `build\OrcaSlicer\OrcaSlicer.dll`)
3. Запустить OrcaSlicer и проверить логи

