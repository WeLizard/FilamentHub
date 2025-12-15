# Workflow работы с OrcaSlicer FilamentHub Edition

## 🎯 Цель
Регулярно получать обновления из оригинального OrcaSlicer, сохраняя наши изменения FilamentHub.

## 🔒 Безопасность: Защита от случайного push в upstream

**ВНИМАНИЕ:** Upstream настроен так, что **НЕВОЗМОЖНО случайно отправить изменения в оригинальный репозиторий**.

### Текущая настройка:
- ✅ `origin` → твой форк (`lizardjazz1/OrcaSlicer`) - сюда можно пушить
- ✅ `upstream` → оригинал (`SoftFever/OrcaSlicer`) - **только чтение** (fetch), push **заблокирован**

### Что это значит:
- `git push` → всегда идет только в `origin` (твой форк) ✅
- `git push upstream` → заблокировано (Git выдаст ошибку) ✅
- `git fetch upstream` → работает нормально (только скачивание) ✅

**Вывод:** Твои изменения FilamentHub **никогда не попадут** в оригинальный OrcaSlicer случайно!

## 📋 Регулярный процесс обновления

### Шаг 1: Получить обновления из upstream

```bash
cd docs/OrcaSlicer

# Получить последние изменения из оригинального репозитория
git fetch upstream

# Посмотреть что изменилось (опционально)
git log HEAD..upstream/main --oneline
```

### Шаг 2: Слить изменения (MERGE)

```bash
# Убедиться что мы на нашей ветке
git checkout filamenthub-integration

# Влить изменения из upstream/main
git merge upstream/main
```

**Что происходит:**
- Git автоматически объединяет изменения
- Если нет конфликтов → merge коммит создается автоматически
- Если есть конфликты → Git попросит разрешить их вручную

### Шаг 3: Разрешить конфликты (если есть)

Если Git сообщает о конфликтах:

```bash
# Посмотреть список конфликтных файлов
git status

# Открыть файл с конфликтом и найти маркеры:
# <<<<<<< HEAD
# твои изменения
# =======
# изменения из upstream
# >>>>>>> upstream/main

# Редактировать файл, оставив нужные изменения
# Удалить маркеры <<<<<<<, =======, >>>>>>>

# После разрешения всех конфликтов:
git add .
git commit -m "Merge upstream/main - разрешены конфликты"
```

**Важно:** Обычно конфликты возникают только если:
- Upstream изменил те же файлы, что и мы
- Изменились файлы, в которые мы встроили FilamentHub

### Шаг 4: Проверить что наши изменения на месте

```bash
# Убедиться что FilamentHub файлы есть
ls src/slic3r/GUI/FilamentHubPanel.*
ls src/slic3r/Utils/FilamentHubClient.*

# Проверить что MainFrame содержит наши изменения
grep -r "FilamentHub" src/slic3r/GUI/MainFrame.*
```

### Шаг 5: Протестировать компиляцию

```bash
# Быстрая проверка что все компилируется (если нужно)
# (можно пропустить, если уверен)
```

### Шаг 6: Закоммитить и запушить

```bash
# Если merge прошел без конфликтов, коммит уже создан
# Если были конфликты, уже закоммитили на шаге 3

# Запушить в наш форк (origin - это твой форк, безопасно!)
git push origin filamenthub-integration

# ВАЖНО: git push (без указания remote) тоже идет в origin по умолчанию
# НО если хочешь быть на 100% уверен - всегда указывай origin явно
```

### Шаг 7: Обновить submodule в основном репозитории

```bash
cd ../..  # Вернуться в корень FilamentHub

# Обновить ссылку на submodule
git add docs/OrcaSlicer
git commit -m "chore: обновлен OrcaSlicer submodule до последней версии"
git push
```

## 🔄 Когда делать обновления?

**Рекомендуется:**
- После важных релизов OrcaSlicer (когда выходит новая версия)
- Раз в месяц (чтобы получать багфиксы и небольшие улучшения)
- Перед важными изменениями FilamentHub (чтобы работать на свежей базе)

**Не стоит:**
- Обновляться слишком часто (каждый день) - много работы с конфликтами
- Обновляться перед дедлайном - могут быть непредвиденные проблемы

## ⚠️ Что делать если что-то пошло не так?

### Откатить merge (если еще не запушили)

```bash
git merge --abort  # Отменить merge
```

### Откатить последний merge коммит

```bash
git reset --hard HEAD~1  # ОСТОРОЖНО: удалит merge коммит
```

### Создать бэкап перед merge

```bash
# Создать резервную ветку
git branch filamenthub-integration-backup

# Теперь можно спокойно делать merge
# Если что-то пойдет не так, можно вернуться:
git reset --hard filamenthub-integration-backup
```

## 📊 Текущее состояние

- ✅ Upstream настроен: `https://github.com/SoftFever/OrcaSlicer.git`
- ✅ Ветка интеграции: `filamenthub-integration`
- ✅ Последний merge: `568a463ce0` (v2.0.0-fh)

## 🎓 Полезные команды

```bash
# Посмотреть разницу между нашими и upstream изменениями
git diff upstream/main...HEAD

# Посмотреть только наши файлы (FilamentHub)
git diff upstream/main...HEAD --name-only | grep -i filamenthub

# Посмотреть историю merge'ов
git log --merges --oneline

# Проверить насколько мы отстаем от upstream
git rev-list --left-right --count upstream/main...HEAD
```

## 🔒 Проверка безопасности

Если хочешь убедиться что push в upstream заблокирован:

```bash
# Проверить настройки remote
git remote -v

# Должно быть:
# origin   https://github.com/lizardjazz1/OrcaSlicer.git (fetch)
# origin   https://github.com/lizardjazz1/OrcaSlicer.git (push)
# upstream https://github.com/SoftFever/OrcaSlicer.git (fetch)
# upstream no_push (push)  ← ВОТ ЭТО ЗАЩИТА!

# Попробовать запушить в upstream (должна быть ошибка)
git push upstream main
# Результат: error: remote 'upstream' does not support pushing
```

## 🔗 Ссылки

- **Upstream (оригинал, только чтение):** https://github.com/SoftFever/OrcaSlicer
- **Наш форк (можно пушить):** https://github.com/lizardjazz1/OrcaSlicer
- **Ветка:** `filamenthub-integration`

