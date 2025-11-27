# OrcaSlicer Git Submodule - Краткая инструкция

> **Цель:** Быстрая справка по работе с OrcaSlicer как Git Submodule

---

## 🚀 Быстрый старт

### Настройка (один раз)

```powershell
# Запустить скрипт настройки
.\setup_orcaslicer_submodule.ps1

# Или вручную:
# 1. Сохранить изменения в OrcaSlicer (коммит + push)
# 2. Удалить из FilamentHub: git rm -r --cached docs/OrcaSlicer
# 3. Удалить физически: Remove-Item -Recurse -Force docs/OrcaSlicer
# 4. Добавить как submodule: git submodule add -b filamenthub-integration https://github.com/lizardjazz1/OrcaSlicer.git docs/OrcaSlicer
# 5. Инициализировать: git submodule init && git submodule update
```

### Клонирование FilamentHub с OrcaSlicer

```powershell
# Клонировать с submodule
git clone --recurse-submodules https://github.com/lizardjazz1/FilamentHub.git

# Или после клонирования
git clone https://github.com/lizardjazz1/FilamentHub.git
cd FilamentHub
git submodule update --init --recursive
```

---

## 💻 Повседневная работа

### Работа с OrcaSlicer

```powershell
# 1. Перейти в OrcaSlicer
cd docs/OrcaSlicer

# 2. Работать как обычно
git status
git add .
git commit -m "Your changes"
git push origin filamenthub-integration

# 3. Вернуться в FilamentHub
cd ../..

# 4. Обновить версию OrcaSlicer в FilamentHub
git add docs/OrcaSlicer
git commit -m "Update OrcaSlicer submodule"
git push origin main
```

### Обновление OrcaSlicer до последней версии

```powershell
# Из корня FilamentHub
git submodule update --remote docs/OrcaSlicer
git add docs/OrcaSlicer
git commit -m "Update OrcaSlicer submodule to latest"
git push origin main
```

---

## 🔍 Полезные команды

### Проверка статуса

```powershell
# Статус submodule
git submodule status

# Статус всех изменений
git status

# Статус изменений в OrcaSlicer
cd docs/OrcaSlicer
git status
cd ../..
```

### Обновление submodule

```powershell
# Обновить до последней версии ветки
git submodule update --remote docs/OrcaSlicer

# Обновить до конкретного коммита
cd docs/OrcaSlicer
git checkout <commit-hash>
cd ../..
git add docs/OrcaSlicer
git commit -m "Update OrcaSlicer to specific commit"
```

### Синхронизация с upstream (SoftFever)

```powershell
# Перейти в OrcaSlicer
cd docs/OrcaSlicer

# Получить последние изменения из upstream
git fetch upstream

# Слить изменения (если нужно)
git merge upstream/main

# Запушить в форк
git push origin filamenthub-integration

# Вернуться в FilamentHub
cd ../..

# Обновить версию в FilamentHub
git add docs/OrcaSlicer
git commit -m "Update OrcaSlicer submodule"
git push origin main
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

## 🐛 Решение проблем

### Submodule не инициализирован

```powershell
git submodule update --init --recursive
```

### Submodule показывает "modified" при `git status`

```powershell
# Это нормально, если вы сделали изменения в OrcaSlicer
# Закоммитьте изменения в OrcaSlicer, затем обновите submodule в FilamentHub
cd docs/OrcaSlicer
git add .
git commit -m "Your changes"
git push origin filamenthub-integration
cd ../..
git add docs/OrcaSlicer
git commit -m "Update OrcaSlicer submodule"
```

### Submodule показывает неправильную ветку

```powershell
cd docs/OrcaSlicer
git checkout filamenthub-integration
git pull origin filamenthub-integration
cd ../..
git add docs/OrcaSlicer
git commit -m "Fix OrcaSlicer submodule branch"
```

---

## 📚 Дополнительная информация

- Полная инструкция: `docs/ORCASLICER_SUBMODULE_SETUP.md`
- Git Submodules Documentation: https://git-scm.com/book/en/v2/Git-Tools-Submodules

