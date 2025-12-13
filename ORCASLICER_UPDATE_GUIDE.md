# Инструкция по обновлению OrcaSlicer с интеграцией FilamentHub

## Текущее состояние

- **Submodule:** `docs/OrcaSlicer`
- **Ветка:** `filamenthub-integration`
- **Upstream:** `https://github.com/SoftFever/OrcaSlicer.git`
- **Последний тег upstream:** `v2.3.1`

## Шаги обновления

### 1. Обновление до последней версии upstream

```bash
cd docs/OrcaSlicer

# Добавить upstream если еще не добавлен
git remote add upstream https://github.com/SoftFever/OrcaSlicer.git

# Получить последние изменения
git fetch upstream

# Переключиться на нашу ветку интеграции
git checkout filamenthub-integration

# Слить изменения из upstream/main
git merge upstream/main

# Разрешить конфликты если есть
# После разрешения:
git add .
git commit -m "Merge upstream/main into filamenthub-integration"
```

### 2. Применение изменений FilamentHub

Наши изменения находятся в:
- `src/slic3r/GUI/FilamentHubPanel.cpp` - основная панель интеграции
- `src/slic3r/GUI/FilamentHubPanel.hpp` - заголовочный файл
- Возможно другие файлы для интеграции

После слияния нужно:
1. Проверить что наши изменения не потеряны
2. Применить их к новой версии если нужно
3. Протестировать компиляцию

### 3. Сборка для Windows

```bash
cd docs/OrcaSlicer

# Создать директорию для сборки
mkdir build
cd build

# Настроить CMake
cmake .. -DCMAKE_BUILD_TYPE=Release

# Собрать (может занять много времени)
cmake --build . --config Release --parallel

# Результат будет в build/src/Release/orca-slicer.exe
```

### 4. Создание установщика

После успешной сборки нужно:
1. Собрать установщик (используя скрипты в `scripts/`)
2. Загрузить файлы на сервер или в хранилище
3. Обновить ссылки в API

### 5. Обновление API с реальными ссылками

После сборки и загрузки файлов обновить `backend/app/api/v1/endpoints/downloads.py`:
- Установить `download_url` для доступных сборок
- Установить `available: true` для готовых сборок
- Добавить `checksum` (SHA256) для проверки целостности

## Текущий статус

- ✅ API эндпоинт создан и работает
- ✅ Фронтенд обновлен для использования API
- ⏳ OrcaSlicer submodule нужно обновить
- ⏳ Сборка еще не выполнена
- ⏳ Файлы еще не загружены

## Следующие шаги

1. Обновить submodule OrcaSlicer до последней версии
2. Применить изменения FilamentHub интеграции
3. Собрать для Windows
4. Загрузить файлы
5. Обновить API с реальными ссылками

