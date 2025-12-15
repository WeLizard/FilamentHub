# 📦 Инструкция по обновлению FilamentHub

## 🚀 Быстрое обновление (1 команда!)

### На сервере просто запусти:

```bash
cd ~/FilamentHub && bash scripts/deploy.sh
```

**Всё!** Работает без дополнительных настроек прав доступа.

**Всё!** Скрипт сам:
- Обновит код из Git (`git pull`)
- Пересоберёт контейнеры (если изменились Dockerfile/docker-compose.yml)
- Перезапустит контейнеры **БЕЗ удаления volumes** (база данных сохранится!)

---

## 📝 Что делает скрипт deploy.sh

1. `git pull` - получает изменения из GitHub
2. Проверяет изменения в Docker файлах
3. Если нужно - пересобирает контейнеры (`docker-compose build`)
4. Перезапускает контейнеры (`docker-compose up -d`)
5. **Volumes НЕ удаляются** - база данных остаётся целой!

---

## 🔧 Ручное обновление (если скрипт не работает)

```bash
cd ~/FilamentHub
git pull origin main
docker-compose build  # если изменились Dockerfile/docker-compose.yml
docker-compose up -d  # перезапуск БЕЗ удаления volumes
```

---

## 📦 Обновление OrcaSlicer билдов

Просто скопируй файлы через Samba в:
```
\\192.168.0.33\FullDisk\home\lizard\FilamentHub\backend\distributions\orcaslicer\
```

Файлы:
- `OrcaSlicer-FilamentHub-2.0.0-fh-win64.exe`
- `OrcaSlicer-FilamentHub-2.0.0-fh-win64-portable.zip`
- `OrcaSlicer-FilamentHub-2.0.0-fh-linux-x64.AppImage`

**Перезапуск не нужен** - файлы доступны сразу через volume.

---

## ⚠️ Важные замечания

1. **База данных НЕ удаляется** - скрипт использует `docker-compose up -d` без флага `-v`, volumes сохраняются

2. **Если что-то пошло не так:**
   ```bash
   # Проверь логи
   docker-compose logs -f
   
   # Проверь статус
   docker-compose ps
   ```

3. **Откат изменений:**
   ```bash
   cd ~/FilamentHub
   git reset --hard HEAD~1
   docker-compose up -d
   ```

---

## 📋 Чеклист перед обновлением

- [ ] Изменения запушены в GitHub
- [ ] На сервере есть доступ к Git репозиторию

---

## 🔍 Проверка после обновления

```bash
# Проверь что контейнеры запущены
docker-compose ps

# Проверь логи на ошибки
docker-compose logs --tail=50 backend

# Проверь сайт
curl -I https://filamenthub.ru
```

---

## 💡 Советы

- **Всегда используй `./scripts/deploy.sh`** - он всё сделает сам и безопасно
- **База данных сохраняется** - volumes не удаляются при обновлении
- **Для билдов OrcaSlicer:** Просто копируй файлы, перезапуск не нужен

