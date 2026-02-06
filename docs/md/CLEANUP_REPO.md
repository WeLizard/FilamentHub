# Анализ "хлама" в репозитории

## 🚨 Критические проблемы (нужно удалить из Git)

### 1. Пользовательские настройки OrcaSlicer (842 файла!)
**Путь:** `docs/OrcaSlicer_user_presets/`

**Проблема:** В Git закоммичено 842 файла пользовательских настроек OrcaSlicer:
- Конфиги OrcaSlicer (`OrcaSlicer.conf*`)
- Логи (`log/*.log.*`)
- Плагины (`.dll` файлы)
- Пользовательские пресеты
- Бэкапы

**Решение:**
```bash
# Удалить из Git, но оставить локально
git rm -r --cached docs/OrcaSlicer_user_presets/
git commit -m "chore: удалить пользовательские настройки OrcaSlicer из репозитория"

# Добавить в .gitignore
echo "docs/OrcaSlicer_user_presets/" >> .gitignore
```

### 2. Бэкапы базы данных (7 файлов)
**Путь:** `backend/uploads/database_dumps/`

**Проблема:** SQL дампы базы данных закоммичены в Git:
- `filamenthub_backup_*.sql`
- `*.dump`

**Решение:**
```bash
# Удалить из Git (но оставить локально для восстановления)
git rm --cached backend/uploads/database_dumps/*.sql
git rm --cached backend/uploads/database_dumps/*.dump
git commit -m "chore: удалить SQL дампы из репозитория"

# В .gitignore уже есть: backend/database_dumps/
# Нужно добавить: backend/uploads/database_dumps/
```

## ⚠️ Потенциальные проблемы

### 3. Большие файлы в docs/OrcaSlicer/build/
**Путь:** `docs/OrcaSlicer/build/`

**Статус:** ✅ Уже в .gitignore (`build/`)
**Но:** Файлы могут быть локально - их размер может быть большой

### 4. Референсные репозитории (уже в .gitignore)
- ✅ `docs/Spoolman-master/` - в .gitignore
- ✅ `docs/spoolman2slicer-main/` - в .gitignore

## ✅ Правильно настроено

- ✅ `backend/distributions/orcaslicer/` - в .gitignore (сборки OrcaSlicer)
- ✅ `*.log` - в .gitignore
- ✅ `.env` файлы - в .gitignore
- ✅ `__pycache__/` - в .gitignore
- ✅ `node_modules/` - в .gitignore

## 📊 Статистика репозитория

- **Всего объектов:** 9,017
- **Размер без упаковки:** 178.19 MiB
- **Размер упакованный:** 2.53 MiB ✅ (хорошо сжимается)

## 🎯 Рекомендации

1. **Срочно:** Удалить `docs/OrcaSlicer_user_presets/` из Git
2. **Важно:** Удалить SQL дампы из `backend/uploads/database_dumps/`
3. **Добавить в .gitignore:** `docs/OrcaSlicer_user_presets/`
4. **Проверить:** Нет ли еще больших файлов которые не должны быть в Git

## 🔧 Скрипт для очистки

```bash
# 1. Удалить пользовательские настройки OrcaSlicer
git rm -r --cached docs/OrcaSlicer_user_presets/

# 2. Удалить SQL дампы
git rm --cached backend/uploads/database_dumps/*.sql
git rm --cached backend/uploads/database_dumps/*.dump

# 3. Обновить .gitignore
echo "" >> .gitignore
echo "# OrcaSlicer user presets (should not be in repo)" >> .gitignore
echo "docs/OrcaSlicer_user_presets/" >> .gitignore
echo "backend/uploads/database_dumps/" >> .gitignore

# 4. Закоммитить
git add .gitignore
git commit -m "chore: удалить лишние файлы из репозитория (user presets, DB dumps)"
```

