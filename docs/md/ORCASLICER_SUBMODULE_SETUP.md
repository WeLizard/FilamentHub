# OrcaSlicer - Настройка Git Submodule

> **Цель:** Интегрировать OrcaSlicer как Git Submodule в FilamentHub, чтобы при обновлении FilamentHub автоматически обновлялась версия OrcaSlicer.

---

## 🎯 Что такое Git Submodule?

**Git Submodule** - это способ встроить один Git репозиторий в другой как зависимость. Это позволяет:
- ✅ Хранить версию OrcaSlicer как часть FilamentHub
- ✅ При клонировании FilamentHub автоматически подтягивать правильную версию OrcaSlicer
- ✅ Работать с OrcaSlicer независимо (коммиты, пуши в отдельный репозиторий)
- ✅ При обновлении FilamentHub можно обновить версию OrcaSlicer одним коммитом

---

## 📋 Текущая ситуация

- ✅ Форк OrcaSlicer существует: `https://github.com/lizardjazz1/OrcaSlicer`
- ✅ Ветка разработки: `filamenthub-integration`
- ❌ `docs/OrcaSlicer` находится в `.gitignore` (но изменения отслеживаются)
- ❌ `docs/OrcaSlicer` не является Git Submodule

---

## 🔧 Шаг 1: Сохранить текущие изменения в OrcaSlicer

**ВАЖНО:** Сначала нужно закоммитить и запушить все изменения в OrcaSlicer репозиторий.

```powershell
# Перейти в OrcaSlicer
cd docs/OrcaSlicer

# Проверить статус
git status

# Добавить изменения
git add src/slic3r/GUI/FilamentHubPanel.cpp
git add src/slic3r/GUI/FilamentHubPanel.hpp
git add src/slic3r/Utils/FilamentHubClient.cpp
git add src/slic3r/Utils/FilamentHubClient.hpp
git add clean_build.ps1

# Закоммитить
git commit -m "Add notification badge and unread count API"

# Запушить в форк
git push origin filamenthub-integration
```

---

## 🔧 Шаг 2: Удалить OrcaSlicer из FilamentHub

**ВАЖНО:** Мы удаляем только отслеживание в FilamentHub, сам репозиторий останется.

```powershell
# Вернуться в корень FilamentHub
cd F:\FilamentHub

# Удалить из Git индекса (но оставить файлы)
git rm -r --cached docs/OrcaSlicer

# Удалить из .gitignore
# (нужно отредактировать .gitignore вручную)
```

---

## 🔧 Шаг 3: Добавить OrcaSlicer как Git Submodule

```powershell
# Удалить папку (если она существует)
Remove-Item -Recurse -Force docs/OrcaSlicer -ErrorAction SilentlyContinue

# Добавить как submodule
git submodule add -b filamenthub-integration https://github.com/lizardjazz1/OrcaSlicer.git docs/OrcaSlicer

# Инициализировать submodule
git submodule init

# Обновить submodule
git submodule update
```

---

## 🔧 Шаг 4: Обновить .gitignore

Убрать `docs/OrcaSlicer/` из `.gitignore`, так как теперь это submodule.

---

## 🔧 Шаг 5: Закоммитить изменения

```powershell
# Добавить .gitmodules и docs/OrcaSlicer
git add .gitmodules
git add docs/OrcaSlicer
git add .gitignore

# Закоммитить
git commit -m "Add OrcaSlicer as Git submodule"

# Запушить
git push origin main
```

---

## 🚀 Как работать с Submodule после настройки

### Клонирование FilamentHub с Submodule

```powershell
# Клонировать FilamentHub
git clone https://github.com/lizardjazz1/FilamentHub.git

# Клонировать submodule
git submodule update --init --recursive
```

Или одной командой:

```powershell
git clone --recurse-submodules https://github.com/lizardjazz1/FilamentHub.git
```

### Работа с OrcaSlicer

```powershell
# Перейти в OrcaSlicer
cd docs/OrcaSlicer

# Работать как обычно (коммиты, пуши в форк OrcaSlicer)
git status
git add .
git commit -m "Your changes"
git push origin filamenthub-integration

# Вернуться в FilamentHub
cd ../..

# Обновить версию OrcaSlicer в FilamentHub
git add docs/OrcaSlicer
git commit -m "Update OrcaSlicer submodule"
git push origin main
```

### Обновление Submodule до последней версии

```powershell
# Перейти в OrcaSlicer
cd docs/OrcaSlicer

# Получить последние изменения
git fetch origin
git checkout filamenthub-integration
git pull origin filamenthub-integration

# Вернуться в FilamentHub
cd ../..

# Обновить версию в FilamentHub
git add docs/OrcaSlicer
git commit -m "Update OrcaSlicer submodule to latest"
git push origin main
```

### Обновление Submodule из FilamentHub

```powershell
# Из корня FilamentHub
git submodule update --remote docs/OrcaSlicer

# Закоммитить обновление
git add docs/OrcaSlicer
git commit -m "Update OrcaSlicer submodule"
git push origin main
```

---

## 📝 Файл .gitmodules

После добавления submodule создастся файл `.gitmodules`:

```ini
[submodule "docs/OrcaSlicer"]
    path = docs/OrcaSlicer
    url = https://github.com/lizardjazz1/OrcaSlicer.git
    branch = filamenthub-integration
```

---

## ⚠️ Важные замечания

1. **Не коммитьте изменения в OrcaSlicer напрямую из FilamentHub**
   - Всегда работайте с OrcaSlicer из его собственного репозитория
   - Коммитьте и пушите изменения в форк OrcaSlicer
   - Затем обновляйте submodule в FilamentHub

2. **При клонировании FilamentHub не забудьте инициализировать submodule**
   ```powershell
   git submodule update --init --recursive
   ```

3. **При обновлении FilamentHub проверяйте версию OrcaSlicer**
   ```powershell
   git submodule status
   ```

---

## 🔄 Миграция существующего репозитория

Если у вас уже есть `docs/OrcaSlicer` в FilamentHub:

1. **Сохраните изменения в OrcaSlicer** (коммит + push)
2. **Удалите из FilamentHub** (`git rm -r --cached docs/OrcaSlicer`)
3. **Удалите физически** (`Remove-Item -Recurse -Force docs/OrcaSlicer`)
4. **Добавьте как submodule** (`git submodule add -b filamenthub-integration ...`)
5. **Закоммитьте изменения** в FilamentHub

---

## 📚 Дополнительные ресурсы

- [Git Submodules Documentation](https://git-scm.com/book/en/v2/Git-Tools-Submodules)
- [Git Submodule Tutorial](https://www.atlassian.com/git/tutorials/git-submodule)

---

## ✅ Проверка настройки

После настройки проверьте:

```powershell
# Проверить статус submodule
git submodule status

# Проверить файл .gitmodules
cat .gitmodules

# Проверить, что OrcaSlicer отслеживается
git ls-files docs/OrcaSlicer | Select-Object -First 5
```

Должно быть:
- ✅ Файл `.gitmodules` существует
- ✅ `docs/OrcaSlicer` отслеживается как submodule (160000 в `git ls-files`)
- ✅ Ветка `filamenthub-integration` используется в submodule

