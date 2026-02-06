# OrcaSlicer - Изучение для интеграции FilamentHub

> **Дата изучения:** 2025-01-XX  
> **Версия OrcaSlicer:** Последняя из `docs/OrcaSlicer-main/`  
> **Цель:** Понять структуру проекта и точки интеграции для FilamentHub

---

## 📋 Оглавление

1. [Общая информация](#общая-информация)
2. [Требования для сборки](#требования-для-сборки)
3. [Процесс сборки на Windows](#процесс-сборки-на-windows)
4. [Архитектура проекта](#архитектура-проекта)
5. [Структура GUI](#структура-gui)
6. [Профили материалов и принтеров](#профили-материалов-и-принтеров)
7. [Точки интеграции FilamentHub](#точки-интеграции-filamenthub)
8. [Ресурсы](#ресурсы)

---

## Общая информация

### Что такое OrcaSlicer?

**OrcaSlicer** — open-source слайсер для 3D-печати, форкнут из **Bambu Studio** (который форкнут из **PrusaSlicer**).

**Основные технологии:**
- **C++17** с поддержкой C++20
- **wxWidgets** для GUI (кроссплатформенный фреймворк)
- **CMake** для системы сборки (требуется 3.13-3.31.x на Windows)
- **OpenGL** для 3D визуализации
- **TBB** (Intel Threading Building Blocks) для параллелизации

**Лицензия:** GNU Affero General Public License v3 (AGPL-3.0)

### Официальные ссылки

- **Website:** https://www.orcaslicer.com/
- **GitHub:** https://github.com/SoftFever/OrcaSlicer
- **Discord:** https://discord.gg/P4VE9UY9gJ

---

## Требования для сборки

### Windows 64-bit

**Необходимые инструменты:**

1. **Visual Studio 2022** (или 2019)
   ```powershell
   winget install --id=Microsoft.VisualStudio.2022.Professional -e
   ```

2. **CMake версия 3.31.x** (строго!)
   ```powershell
   winget install --id=Kitware.CMake -v "3.31.6" -e
   ```
   ⚠️ **Важно:** Только версии 3.13-3.31.x поддерживаются на Windows. Проверьте: `cmake --version`

3. **Strawberry Perl**
   ```powershell
   winget install --id=StrawberryPerl.StrawberryPerl -e
   ```

4. **Git + Git LFS**
   ```powershell
   winget install --id=Git.Git -e
   winget install --id=GitHub.GitLFS -e
   ```

**Важные замечания:**
- Убедитесь, что CMake (из Program Files) идет **раньше** в PATH, чем Strawberry Perl
- Проверьте порядок: `C:\Program Files\CMake\bin` должен быть до `C:\Strawberry\c\bin`
- Если CMake не найден или версия неправильная, CMakeLists.txt выдаст FATAL_ERROR

---

## Процесс сборки на Windows

### Быстрый старт

1. **Клонировать репозиторий:**
   ```powershell
   git clone https://github.com/SoftFever/OrcaSlicer
   cd OrcaSlicer
   git lfs pull  # Загрузить большие файлы
   ```

2. **Открыть правильный командный промпт:**
   - **Для VS 2022:** `x64 Native Tools Command Prompt for VS 2022`
   - **Для VS 2019:** `x64 Native Tools Command Prompt for VS 2019`

3. **Запустить сборку:**
   ```batch
   build_release_vs2022.bat
   ```

### Варианты сборки

```batch
# Собрать всё (deps + slicer)
build_release_vs2022.bat

# Собрать только зависимости (долго, ~30-40 минут)
build_release_vs2022.bat deps

# Собрать только slicer (после deps)
build_release_vs2022.bat slicer

# Debug сборка
build_release_vs2022.bat debug

# Release с debug info
build_release_vs2022.bat debuginfo
```

### Процесс сборки

1. **Этап 1: Зависимости (deps)**
   - Запускается CMake для `deps/CMakeLists.txt`
   - Собираются библиотеки: Boost, wxWidgets, OpenGL, TBB, CGAL и др.
   - Результат: `deps/build/OrcaSlicer_dep/`
   - ⏱️ **Время:** 30-40 минут (первый раз)

2. **Этап 2: Основное приложение**
   - Запускается CMake для корневого `CMakeLists.txt`
   - Собираются: `libslic3r/` (core), `src/slic3r/` (GUI)
   - Результат: `build/src/Release/orca-slicer.exe`
   - ⏱️ **Время:** 10-20 минут

3. **Этап 3: Локализация**
   - Запускается `scripts/run_gettext.bat`
   - Генерируются переводы

4. **Этап 4: Install**
   - Копируются ресурсы и исполняемые файлы
   - Результат: `build/src/Release/`

### Результаты сборки

```
build/
├── OrcaSlicer.sln           # Visual Studio solution
└── src/
    └── Release/
        ├── orca-slicer.exe  # Исполняемый файл
        ├── resources/       # Ресурсы (профили, иконки)
        └── ...
```

### Открытие в Visual Studio

1. Откройте `build/OrcaSlicer.sln`
2. Выберите конфигурацию: `Release` (или `Debug`)
3. Нажмите **F5** или выберите **Local Windows Debugger**

---

## Архитектура проекта

### Структура директорий

```
OrcaSlicer/
├── src/
│   ├── libslic3r/          # 🎯 Core slicing engine (платформо-независимый)
│   │   ├── GCode/          # Генерация G-code
│   │   ├── Fill/           # Паттерны заполнения
│   │   ├── Support/         # Поддержки (tree, traditional)
│   │   ├── Geometry/        # Геометрия (Voronoi, medial axis)
│   │   ├── Format/          # I/O (3MF, AMF, STL, OBJ, STEP)
│   │   ├── SLA/             # SLA печать
│   │   └── Arachne/         # Продвинутая генерация стен
│   │
│   ├── slic3r/             # 🎨 GUI приложение
│   │   ├── GUI/             # GUI компоненты (wxWidgets)
│   │   ├── OrcaSlicer.cpp   # Точка входа
│   │   └── ...
│   │
│   └── dev-utils/           # Утилиты разработки
│
├── deps/                    # Конфигурации зависимостей
├── deps_src/                # Vendored библиотеки (не изменять!)
├── resources/               # 📦 Ресурсы приложения
│   ├── profiles/            # Профили принтеров и материалов
│   ├── printers/            # Конфигурации принтеров
│   ├── images/              # Иконки, логотипы
│   ├── calib/               # Калибровочные паттерны
│   └── handy_models/        # Тестовые модели
│
├── tests/                   # 🧪 Тесты (Catch2)
├── cmake/                   # CMake модули
├── scripts/                 # Скрипты автоматизации
└── doc/                     # Документация
```

### Ключевые компоненты

#### 1. Core Library (`libslic3r/`)

**Назначение:** Ядро слайсера, платформо-независимое

**Основные классы:**
- `Print` - оркестрация процесса слайсинга
- `PrintObject` - обработка объектов
- `Layer` - слой печати
- `GCode` - генерация G-code
- `Config` - конфигурация (PrintConfig.cpp определяет все настройки)

**Модули:**
- `GCode/` - генерация G-code, охлаждение, давление
- `Fill/` - паттерны заполнения (gyroid, honeycomb, lightning)
- `Support/` - генерация поддержек (tree, traditional)
- `Geometry/` - операции с геометрией, Voronoi диаграммы
- `Format/` - загрузка/сохранение 3MF, AMF, STL, OBJ, STEP
- `SLA/` - SLA-специфичная обработка
- `Arachne/` - продвинутая генерация стен с переменной шириной

#### 2. GUI Application (`src/slic3r/`)

**Назначение:** Пользовательский интерфейс (wxWidgets)

**Основные файлы:**
- `OrcaSlicer.cpp` - точка входа приложения
- `GUI_App.cpp` - главный класс приложения
- `MainFrame.cpp` - главное окно
- `Plater.cpp` - рабочая область (стол)
- `Tab.cpp` - вкладки настроек (Print, Filament, Printer)

**Поддиректория `GUI/`:**
- Сотни файлов .cpp/.hpp для UI компонентов
- Компоненты: диалоги, панели, виджеты
- Интеграция с libslic3r через события

---

## Структура GUI

### Основные GUI компоненты

#### Вкладки настроек (Tabs)

**Файлы:** `src/slic3r/GUI/Tab.cpp`, `Tab.hpp`

**Типы вкладок:**
1. **Print Settings** (`TabPrint`) - настройки печати
2. **Filament Settings** (`TabFilament`) - настройки материала
3. **Printer Settings** (`TabPrinter`) - настройки принтера

**Функциональность:**
- Загрузка/сохранение профилей
- Комбобоксы для выбора профилей
- Валидация настроек
- Отображение подсказок (hints)

#### Профили и комбобоксы

**Ключевые файлы:**
- `PresetComboBoxes.cpp/hpp` - комбобоксы для выбора профилей
- `PresetComboBoxes.cpp` - управление выбором профилей
- `FilamentPickerDialog.cpp/hpp` - диалог выбора материала
- `SavePresetDialog.cpp/hpp` - сохранение профилей
- `CreatePresetsDialog.cpp/hpp` - создание профилей

**Важно:** Профили хранятся в JSON формате в `resources/profiles/`

#### Рабочая область (Plater)

**Файлы:** `Plater.cpp/hpp`

**Функции:**
- Отображение 3D моделей
- Управление объектами на столе
- Слайсинг и превью
- Интеграция с GCodeViewer

#### Главное окно (MainFrame)

**Файлы:** `MainFrame.cpp/hpp`

**Структура:**
- Меню бар
- Панели инструментов
- Рабочая область (Plater)
- Боковая панель с настройками (Tabs)
- Статус бар

### Профили материалов

**Где хранятся:**
- `resources/profiles/` - папка с профилями по производителям
- Формат: JSON файлы
- Структура: `[manufacturer].json` или `[manufacturer]/[material].json`

**Пример структуры:**
```
resources/profiles/
├── BambuStudio/
├── PrusaResearch/
├── Generic/
└── ...
```

**Как загружаются:**
- Через `PresetBundle` класс
- При старте приложения
- При выборе в комбобоксах

**Где редактируются:**
- Через вкладку `Filament` в GUI
- Через диалоги сохранения/создания профилей
- Прямое редактирование JSON (не рекомендуется)

---

## Профили материалов и принтеров

### Формат профилей

**Типы профилей:**
1. **Printer** - настройки принтера (размер стола, возможности)
2. **Filament** - настройки материала (температуры, скорость)
3. **Print** - настройки печати (слои, заполнение)

**Формат файла:**
- JSON
- Хранится в `resources/profiles/`
- Может быть системным или пользовательским

### Структура профиля материала

**Основные поля:**
```json
{
  "name": "PLA",
  "from": "System",
  "compatible_printers": ["*"],
  "settings": {
    "filament_temperature": [215, 220],
    "bed_temperature": [60, 60],
    "print_speed": 50,
    "retraction_length": 5,
    ...
  }
}
```

### Профили принтеров

**Хранятся:** `resources/printers/`

**Содержат:**
- Размер стола
- Максимальные скорости
- G-code шаблоны (start/end)
- Возможности (multi-extruder, etc.)

---

## Точки интеграции FilamentHub

### 🎯 Стратегия интеграции

**Вариант 1: Расширение существующих компонентов (рекомендуется)**

1. **Модификация `PresetComboBoxes`**
   - Добавить кнопку "FilamentHub" рядом с комбобоксом материалов
   - При клике открывать диалог FilamentHub

2. **Новый диалог `FilamentHubDialog`**
   - Поиск материалов по API
   - Просмотр профилей
   - Импорт профилей в локальные настройки

3. **HTTP клиент**
   - Использовать существующие библиотеки (CURL есть в deps)
   - Асинхронные запросы для неблокирующего UI

**Вариант 2: Новый Tab (более сложно)**

- Создать `TabFilamentHub` по аналогии с `TabFilament`
- Полная интеграция в интерфейс
- Требует больше изменений в архитектуре

### 🔍 Ключевые файлы для изучения

#### Для интеграции профилей:

1. **`src/slic3r/GUI/PresetComboBoxes.cpp`**
   - Как работают комбобоксы профилей
   - Как добавляются новые профили
   - Как обновляется UI

2. **`src/slic3r/GUI/Tab.cpp`**
   - Как вкладки управляют профилями
   - Как происходит загрузка/сохранение

3. **`src/libslic3r/PresetBundle.cpp`** (предположительно)
   - Управление набором профилей
   - Загрузка из файлов

4. **`src/slic3r/GUI/FilamentPickerDialog.cpp`**
   - Пример диалога выбора материала
   - Можно использовать как шаблон для FilamentHub диалога

#### Для HTTP запросов:

5. **Изучить использование CURL в проекте**
   - Найти примеры HTTP запросов (если есть)
   - Или использовать CURL напрямую из deps

#### Для UI компонентов:

6. **`src/slic3r/GUI/SavePresetDialog.cpp`**
   - Пример диалога для сохранения
   - Шаблон для создания диалогов

7. **`src/slic3r/GUI/MainFrame.cpp`**
   - Структура главного окна
   - Где добавлять новые элементы

### 📝 План интеграции (краткий)

**Фаза 1: Базовая интеграция**
1. Создать `FilamentHubDialog.cpp/hpp`
2. Добавить кнопку "FilamentHub" в `PresetComboBoxes`
3. Реализовать HTTP клиент (CURL) для запросов к API
4. Парсинг JSON ответов от FilamentHub API
5. Импорт профилей в локальный формат OrcaSlicer

**Фаза 2: Расширенная функциональность**
1. Кеширование профилей локально
2. Авторизация (API key)
3. Синхронизация профилей
4. Поиск и фильтрация

**Фаза 3: Полная интеграция**
1. Автоматическое обновление профилей
2. Интеграция с "Профиль прутка" dropdown
3. Пометка профилей как "FilamentHub (синхр.)"

---

## Ресурсы

### Документация OrcaSlicer

- **README.md** - общая информация
- **CLAUDE.md** - инструкции для AI (сборка, архитектура)
- **AGENTS.md** - руководящие принципы разработки
- **doc/developer-reference/How-to-build.md** - подробная инструкция по сборке
- **doc/developer-reference/How-to-create-profiles.md** - создание профилей

### Референсы

- **PrusaSlicer** - оригинальный слайсер
- **Bambu Studio** - прямой предок OrcaSlicer
- **SuperSlicer** - много фич заимствовано оттуда

### Полезные ссылки

- **Wiki OrcaSlicer:** https://github.com/SoftFever/OrcaSlicer/wiki
- **Discord:** https://discord.gg/P4VE9UY9gJ
- **Releases:** https://github.com/SoftFever/OrcaSlicer/releases

---

## ⚠️ Важные замечания

### Лицензия

OrcaSlicer использует **GNU AGPL-3.0**, что означает:
- Любые изменения должны быть под той же лицензией
- Если мы создаем форк/патч, он должен быть open-source
- Лучший вариант: **Pull Request** в основной репозиторий

### Совместимость

- **Не изменять** файлы в `deps_src/` - это vendored библиотеки
- **Тестировать** на всех платформах (Windows, macOS, Linux)
- **Следовать** coding style (см. `.clang-format`)

### Размер проекта

- **500k+ строк кода** - используйте поиск активно
- **Много зависимостей** - сборка занимает 40+ минут
- **Большой кодобаза** - изучайте постепенно

---

## 🚀 Следующие шаги

1. ✅ Изучить структуру проекта
2. ✅ Понять процесс сборки
3. ⏳ Собрать OrcaSlicer локально (без изменений)
4. ⏳ Изучить код `PresetComboBoxes` и `Tab`
5. ⏳ Изучить формат профилей JSON
6. ⏳ Создать Proof-of-Concept диалог FilamentHub
7. ⏳ Реализовать HTTP клиент для API
8. ⏳ Интегрировать импорт профилей

---

**Создано:** 2025-01-XX  
**Последнее обновление:** 2025-01-XX


