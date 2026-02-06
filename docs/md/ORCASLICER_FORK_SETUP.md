# OrcaSlicer - Настройка форка для разработки

> **Аккаунт:** lizardjazz1  
> **Цель:** Создать форк OrcaSlicer для разработки интеграции FilamentHub

---

## 🎯 План действий

1. **Форкнуть репозиторий на GitHub**
2. **Клонировать форк локально**
3. **Применить существующие правки (OpenCV, OCCT)**
4. **Настроить upstream для синхронизации**
5. **Создать ветку для разработки FilamentHub**

---

## Шаг 1: Форкнуть репозиторий

### Вариант A: Через веб-интерфейс GitHub

1. Откройте: https://github.com/SoftFever/OrcaSlicer
2. Нажмите кнопку **"Fork"** (справа вверху)
3. Выберите аккаунт **lizardjazz1**
4. Дождитесь создания форка

**Результат:** Будет создан репозиторий `https://github.com/lizardjazz1/OrcaSlicer`

### Вариант B: Через GitHub CLI (если установлен)

```powershell
gh repo fork SoftFever/OrcaSlicer --owner lizardjazz1
```

---

## Шаг 2: Клонировать форк локально

```powershell
# Перейти в родительскую директорию FilamentHub
cd F:\FilamentHub

# Удалить старую папку (если нужно)
Remove-Item -Recurse -Force docs\OrcaSlicer-main -ErrorAction SilentlyContinue

# Клонировать форк
git clone https://github.com/lizardjazz1/OrcaSlicer.git docs\OrcaSlicer

# Перейти в директорию
cd docs\OrcaSlicer
```

---

## Шаг 3: Настроить upstream remote

```powershell
# Добавить upstream (оригинальный репозиторий SoftFever)
git remote add upstream https://github.com/SoftFever/OrcaSlicer.git

# Проверить remotes
git remote -v

# Должно быть:
# origin     https://github.com/lizardjazz1/OrcaSlicer.git (fetch)
# origin     https://github.com/lizardjazz1/OrcaSlicer.git (push)
# upstream   https://github.com/SoftFever/OrcaSlicer.git (fetch)
# upstream   https://github.com/SoftFever/OrcaSlicer.git (push)
```

---

## Шаг 4: Загрузить Git LFS файлы

```powershell
# Установить Git LFS (если еще не установлен)
# git lfs install

# Загрузить LFS файлы
git lfs pull
```

---

## Шаг 5: Применить существующие правки

### 5.1 Исправление OpenCV в CMakeLists.txt (корневой)

**Файл:** `CMakeLists.txt`  
**Строки:** ~278-299

Добавить после строки `set(PREFIX_PATH_CHECK ${CMAKE_PREFIX_PATH}):`

```cmake
# Исправление для OpenCV: явно устанавливаем RUNTIME и ARCH для Windows
# OpenCVConfig.cmake может не правильно определить MSVC_VERSION
if(WIN32 AND MSVC)
    if(NOT DEFINED OpenCV_RUNTIME)
        if(MSVC_VERSION MATCHES "^193[0-9]$")
            set(OpenCV_RUNTIME vc17 CACHE STRING "OpenCV runtime version" FORCE)
        elseif(MSVC_VERSION MATCHES "^192[0-9]$")
            set(OpenCV_RUNTIME vc16 CACHE STRING "OpenCV runtime version" FORCE)
        elseif(MSVC_VERSION MATCHES "^191[0-9]$")
            set(OpenCV_RUNTIME vc15 CACHE STRING "OpenCV runtime version" FORCE)
        elseif(MSVC_VERSION EQUAL 1900)
            set(OpenCV_RUNTIME vc14 CACHE STRING "OpenCV runtime version" FORCE)
        endif()
    endif()
    if(NOT DEFINED OpenCV_ARCH)
        if(CMAKE_SYSTEM_PROCESSOR MATCHES "amd64.*|x86_64.*|AMD64.*" OR CMAKE_GENERATOR_PLATFORM STREQUAL "x64")
            set(OpenCV_ARCH x64 CACHE STRING "OpenCV architecture" FORCE)
        else()
            set(OpenCV_ARCH x86 CACHE STRING "OpenCV architecture" FORCE)
        endif()
    endif()
endif()
```

### 5.2 Исправление OCCT DLL в CMakeLists.txt (корневой)

**Файл:** `CMakeLists.txt`  
**Функция:** `orcaslicer_copy_dlls` (около строки 803)

Найти секцию копирования DLL и добавить перед ней:

```cmake
    # Определяем путь к DLL файлам OCCT (они могут быть в bin/occt/, win64/vc14/bin/, win64/vc17/bin/)
    set(_occt_dll_path "")
    
    # Список возможных путей (в порядке приоритета)
    set(_occt_candidate_paths
        "${CMAKE_PREFIX_PATH}/bin/occt"
        "${CMAKE_PREFIX_PATH}/win64/vc17/bin"
        "${CMAKE_PREFIX_PATH}/win64/vc16/bin"
        "${CMAKE_PREFIX_PATH}/win64/vc15/bin"
        "${CMAKE_PREFIX_PATH}/win64/vc14/bin"
    )
    
    # Находим первый существующий путь
    foreach(_path IN LISTS _occt_candidate_paths)
        if(EXISTS "${_path}/TKBO.dll")
            set(_occt_dll_path "${_path}")
            message(STATUS "Found OCCT DLLs at: ${_occt_dll_path}")
            break()
        endif()
    endforeach()
    
    # Копируем DLL файлы OCCT только если они существуют
    if(_occt_dll_path AND EXISTS "${_occt_dll_path}/TKBO.dll")
        file(COPY ${_occt_dll_path}/TKBO.dll
                ${_occt_dll_path}/TKBRep.dll
                ${_occt_dll_path}/TKCAF.dll
                # ... остальные DLL ...
                DESTINATION ${_out_dir})
    endif()
```

### 5.3 Исправление OpenCV в src/libslic3r/CMakeLists.txt

**Файл:** `src/libslic3r/CMakeLists.txt`  
**После:** `find_package(CGAL REQUIRED)`

Добавить:

```cmake
# Исправление для OpenCV: явно устанавливаем RUNTIME и ARCH, так как MSVC_VERSION может не определяться в OpenCVConfig.cmake
if(NOT DEFINED OpenCV_RUNTIME)
    if(MSVC_VERSION MATCHES "^193[0-9]$")
        set(OpenCV_RUNTIME vc17)
    elseif(MSVC_VERSION MATCHES "^192[0-9]$")
        set(OpenCV_RUNTIME vc16)
    elseif(MSVC_VERSION MATCHES "^191[0-9]$")
        set(OpenCV_RUNTIME vc15)
    elseif(MSVC_VERSION EQUAL 1900)
        set(OpenCV_RUNTIME vc14)
    endif()
endif()
if(NOT DEFINED OpenCV_ARCH)
    if(CMAKE_SYSTEM_PROCESSOR MATCHES "amd64.*|x86_64.*|AMD64.*")
        set(OpenCV_ARCH x64)
    else()
        set(OpenCV_ARCH x86)
    endif()
endif()

# Устанавливаем OpenCV_DIR явно, если он не задан пользователем
# ... (полный код из существующего файла)
```

---

## Шаг 6: Создать ветку для разработки

```powershell
# Создать и переключиться на ветку для FilamentHub интеграции
git checkout -b filamenthub-integration

# Закоммитить правки
git add CMakeLists.txt src/libslic3r/CMakeLists.txt
git commit -m "fix: исправления для сборки на Windows (OpenCV, OCCT DLL)"

# Запушить в форк
git push -u origin filamenthub-integration
```

---

## Шаг 7: Проверка структуры

После выполнения всех шагов структура должна быть:

```
F:\FilamentHub\
├── docs\
│   └── OrcaSlicer\          ← Клонированный форк (git repo)
│       ├── .git\            ← Git репозиторий
│       ├── CMakeLists.txt   ← С правками
│       ├── src\
│       │   └── libslic3r\
│       │       └── CMakeLists.txt  ← С правками
│       └── ...
```

---

## 🔄 Синхронизация с upstream (периодически)

```powershell
# Получить обновления от SoftFever
git fetch upstream

# Просмотреть что изменилось
git log HEAD..upstream/main --oneline

# Влить обновления в текущую ветку
git merge upstream/main

# Разрешить конфликты (если есть)
# ... редактировать файлы ...

# Закоммитить
git add .
git commit -m "merge: синхронизация с upstream"

# Запушить в форк
git push origin filamenthub-integration
```

---

## 📝 Следующие шаги

1. ✅ Форк создан
2. ✅ Правки применены
3. ✅ Upstream настроен
4. ⏳ Начать разработку интеграции FilamentHub:
   - Авторизация в OrcaSlicer
   - Таб "FilamentHub" в UI
   - Синхронизация профилей

---

## 🔗 Полезные ссылки

- **Ваш форк:** https://github.com/lizardjazz1/OrcaSlicer
- **Оригинал (upstream):** https://github.com/SoftFever/OrcaSlicer
- **Документация OrcaSlicer:** `docs/OrcaSlicer/CLAUDE.md`
- **План интеграции:** `docs/ORCASLICER_INTEGRATION.md`

---

**Готово! Теперь можно начинать разработку интеграции.** ✅
