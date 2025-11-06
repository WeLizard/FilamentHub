# OrcaSlicer - Резюме установки инструментов

> **Статус:** ✅ Инструменты установлены  
> **Дата:** 2025-01-XX  
> **Платформа:** Windows

---

## ✅ Установленные инструменты

### 1. CMake 3.31.6 ✅
```powershell
winget install --id=Kitware.CMake -v "3.31.6" -e
```
**Статус:** Установлено  
**Путь:** `C:\Program Files\CMake\bin\`  
**Проверка:**
```powershell
cmake --version
# Должно быть: cmake version 3.31.6
```

### 2. Strawberry Perl ✅
```powershell
winget install --id=StrawberryPerl.StrawberryPerl -e
```
**Статус:** Установлено  
**Путь:** `C:\Strawberry\perl\bin\`  
**Проверка:**
```powershell
perl --version
```

### 3. Visual Studio 2022 ✅
**Статус:** Уже установлен (Community)  
**Путь:** `C:\Program Files\Microsoft Visual Studio\2022\Community`

### 4. Git + Git LFS ✅
**Статус:** Уже установлены  
- Git: 2.45.2
- Git LFS: 3.5.1

---

## ⚠️ Важно: Порядок PATH

**КРИТИЧНО:** CMake должен быть **РАНЬШЕ** в PATH, чем Strawberry Perl.

### Текущий порядок должен быть:

```
C:\Program Files\CMake\bin          ← Должно быть РАНЬШЕ
...
C:\Strawberry\c\bin                 ← Должно быть ПОЗЖЕ
```

### Проверка порядка:

```powershell
# Проверить порядок
$env:PATH -split ';' | Where-Object { $_ -match "CMake|Strawberry" }
```

### Если порядок неправильный:

1. Откройте **"Переменные среды"** (Win + R → `sysdm.cpl` → Advanced → Environment Variables)
2. Найдите переменную **PATH**
3. Переместите `C:\Program Files\CMake\bin` **выше** `C:\Strawberry\c\bin`
4. Перезапустите терминал

**Или через PowerShell (требует прав администратора):**

```powershell
# Получить текущий PATH
$machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine") -split ';'
$userPath = [Environment]::GetEnvironmentVariable("Path", "User") -split ';'

# Убрать CMake и Strawberry из PATH
$newMachinePath = $machinePath | Where-Object { $_ -notmatch "CMake|Strawberry" }
$newUserPath = $userPath | Where-Object { $_ -notmatch "CMake|Strawberry" }

# Добавить в правильном порядке
$cmakePath = "C:\Program Files\CMake\bin"
$strawberryPath = $machinePath | Where-Object { $_ -match "Strawberry\\c\\bin" } | Select-Object -First 1

# Обновить PATH (СНАЧАЛА CMake, ПОТОМ Strawberry)
$finalPath = @($cmakePath) + $newMachinePath
if ($strawberryPath) {
    $finalPath += $strawberryPath
}
$finalPath += $newUserPath

# Установить (требует прав администратора!)
[Environment]::SetEnvironmentVariable("Path", ($finalPath -join ';'), "Machine")
```

---

## 🧪 Проверка установки

Запустите скрипт проверки:

```powershell
.\check_tools.ps1
```

**Ожидаемый результат:**
```
✅ CMake: cmake version 3.31.6
✅ Git: git version 2.45.2.windows.1
✅ Git LFS: git-lfs/3.5.1
✅ Visual Studio 2022 Community найдено
✅ Strawberry Perl: This is perl 5, version ...
✅ Порядок PATH правильный (CMake раньше Strawberry Perl)
```

---

## 🚀 Следующий шаг: Сборка OrcaSlicer

После проверки всех инструментов:

1. **Перезапустите терминал** (чтобы применить изменения PATH)

2. **Откройте VS Command Prompt:**
   - Найдите "x64 Native Tools Command Prompt for VS 2022"
   - Или запустите:
   ```powershell
   & "C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat"
   ```

3. **Клонируйте OrcaSlicer:**
   ```powershell
   git clone https://github.com/SoftFever/OrcaSlicer
   cd OrcaSlicer
   git lfs pull
   ```

4. **Соберите:**
   ```batch
   build_release_vs2022.bat
   ```

---

## 📚 Документация

- **Полная инструкция:** `docs/ORCASLICER_BUILD_SETUP.md`
- **Изучение интеграции:** `docs/ORCASLICER_INTEGRATION.md`
- **Проверка инструментов:** `check_tools.ps1`

---

**Готово к сборке!** ✅


