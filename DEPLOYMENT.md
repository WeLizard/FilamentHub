# 🚀 Инструкция по развертыванию FilamentHub на новом сервере

## 📋 Подготовка

1. **Подключись к серверу по SSH:**
   ```bash
   ssh user@your-server-ip
   ```

2. **Установи необходимые зависимости:**
   ```bash
   # Обновление системы
   sudo apt update && sudo apt upgrade -y
   
   # Docker и Docker Compose
   curl -fsSL https://get.docker.com -o get-docker.sh
   sudo sh get-docker.sh
   sudo usermod -aG docker $USER
   
   # Docker Compose
   sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
   sudo chmod +x /usr/local/bin/docker-compose
   
   # Git
   sudo apt install git -y
   ```

3. **Выйди и зайди снова** (чтобы применились права Docker):
   ```bash
   exit
   # Подключись снова
   ```

---

## 🔧 Развертывание

### 1. Клонируй репозиторий:

```bash
git clone https://github.com/your-username/FilamentHub.git
cd FilamentHub
```

### 2. Настрой переменные окружения:

```bash
cp .env.example .env
nano .env
```

**Важные переменные:**
- `POSTGRES_PASSWORD` - надежный пароль для БД
- `SECRET_KEY` - сгенерируй новый секретный ключ
- `FRONTEND_PORT=80` - порт для HTTP (или другой)
- `BACKEND_PORT=8000` - порт для backend

### 3. Настрой DNS:

Убедись что DNS указывает на IP нового сервера:
```bash
nslookup filamenthub.ru
# Должен показать IP нового сервера
```

### 4. Настрой проброс портов на роутере:

Если сервер за роутером:
- `80 → внутренний_IP:80`
- `443 → внутренний_IP:443`

Если VPS - обычно порты уже открыты.

### 5. Открой порты в файрволе (если нужно):

```bash
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
# Порт 8000 НЕ нужен - backend доступен только через nginx (frontend)
sudo ufw enable
```

### 6. Запусти контейнеры:

```bash
docker-compose up -d
```

Проверь что все запустилось:
```bash
docker-compose ps
```

### 7. Выполни миграции БД:

```bash
docker-compose exec backend alembic upgrade head
```

---

## 🔒 Настройка SSL сертификата

### Вариант 1: Перенести существующий сертификат

Если сертификат был получен на старом сервере:

1. **Скопируй папку `certbot/conf/` на новый сервер:**
   ```bash
   # На старом сервере
   tar -czf certbot-conf.tar.gz certbot/conf/
   
   # Скопируй на новый сервер (через scp или другой способ)
   scp certbot-conf.tar.gz user@new-server:/path/to/FilamentHub/
   
   # На новом сервере
   cd FilamentHub
   tar -xzf certbot-conf.tar.gz
   ```

2. **Убедись что DNS указывает на новый IP**

3. **Перезапусти frontend:**
   ```bash
   docker-compose restart frontend
   ```

### Вариант 2: Получить новый сертификат (рекомендуется)

1. **Останови frontend:**
   ```bash
   docker-compose stop frontend
   ```

2. **Создай папки для certbot:**
   ```bash
   mkdir -p certbot/conf certbot/www
   ```

3. **Получи сертификат через DNS challenge:**
   ```bash
   docker run -it --rm \
     -v "$(pwd)/certbot/conf:/etc/letsencrypt" \
     certbot/certbot certonly \
     --manual \
     --preferred-challenges dns \
     --email your-email@example.com \
     --agree-tos \
     -d filamenthub.ru \
     -d www.filamenthub.ru
   ```

4. **Certbot покажет TXT записи** - добавь их в DNS панели:
   - `_acme-challenge.filamenthub.ru` → значение 1
   - `_acme-challenge.www.filamenthub.ru` → значение 2

5. **Подожди 1-2 минуты** и проверь:
   ```bash
   dig TXT _acme-challenge.filamenthub.ru
   ```

6. **Нажми Enter** в терминале certbot для продолжения

7. **Запусти frontend:**
   ```bash
   docker-compose up -d frontend
   ```

---

## ✅ Проверка

1. **Проверь что сайт работает:**
   ```bash
   curl -I http://filamenthub.ru
   curl -I https://filamenthub.ru
   ```

2. **Проверь HTTPS в браузере:**
   - Открой https://filamenthub.ru
   - Должен быть зеленый замочек

3. **Проверь логи:**
   ```bash
   docker-compose logs -f frontend
   docker-compose logs -f backend
   ```

---

## 📦 Перенос данных

Если переносишь с другого сервера:

### 1. База данных:

```bash
# На старом сервере
docker-compose exec postgres pg_dump -U filamenthub filamenthub > backup.sql

# Скопируй backup.sql на новый сервер
scp backup.sql user@new-server:/path/to/FilamentHub/

# На новом сервере
docker-compose exec -T postgres psql -U filamenthub filamenthub < backup.sql
```

### 2. Загруженные файлы:

Docker volumes автоматически создаются при первом запуске. Если нужно перенести данные:

```bash
# На старом сервере
docker run --rm -v filamenthub_uploads_data:/data -v $(pwd):/backup alpine tar czf /backup/uploads.tar.gz /data

# Скопируй на новый сервер
scp uploads.tar.gz user@new-server:/path/to/FilamentHub/

# На новом сервере (после первого запуска docker-compose up)
docker run --rm -v filamenthub_uploads_data:/data -v $(pwd):/backup alpine tar xzf /backup/uploads.tar.gz -C /
```

---

## 🔄 Автоматическое продление SSL

Сертификат действителен 90 дней. Для автоматического продления:

1. **Создай скрипт для продления:**
   ```bash
   nano /usr/local/bin/renew-cert.sh
   ```

   Содержимое:
   ```bash
   #!/bin/bash
   cd /path/to/FilamentHub
   docker-compose stop frontend
   docker run --rm \
     -v "$(pwd)/certbot/conf:/etc/letsencrypt" \
     certbot/certbot renew --manual --preferred-challenges dns
   docker-compose up -d frontend
   ```

   ```bash
   chmod +x /usr/local/bin/renew-cert.sh
   ```

2. **Добавь в crontab** (проверка раз в месяц):
   ```bash
   crontab -e
   # Добавь:
   0 3 1 * * /usr/local/bin/renew-cert.sh >> /var/log/certbot-renew.log 2>&1
   ```

**⚠️ Внимание:** При продлении certbot снова попросит добавить TXT записи в DNS. Нужно будет делать это вручную.

---

## 🛠️ Полезные команды

```bash
# Просмотр логов
docker-compose logs -f [service_name]

# Перезапуск сервиса
docker-compose restart [service_name]

# Остановка всех сервисов
docker-compose down

# Обновление кода
git pull
docker-compose build
docker-compose up -d

# Проверка статуса
docker-compose ps

# Вход в контейнер
docker-compose exec [service_name] sh
```

---

## 📝 Важные заметки

- **SSL сертификат:** При переносе на новый сервер лучше получить новый сертификат, даже если копируешь старый (для правильной работы автопродления)
- **DNS:** Убедись что DNS указывает на правильный IP перед получением сертификата
- **Порты:** Если порты 80/443 закрыты провайдером - используй DNS challenge
- **Volumes:** Все критичные данные хранятся в Docker volumes и не удалятся при обновлениях

---

## 🆘 Решение проблем

### Сайт не открывается:
- Проверь что контейнеры запущены: `docker-compose ps`
- Проверь логи: `docker-compose logs frontend`
- Проверь проброс портов на роутере

### SSL не работает:
- Проверь что сертификаты есть: `ls -la certbot/conf/live/filamenthub.ru/`
- Проверь логи nginx: `docker-compose logs frontend | grep ssl`

### Ошибки БД:
- Проверь что миграции выполнены: `docker-compose exec backend alembic current`
- Проверь логи: `docker-compose logs postgres`

---

## 🐧 Сборка OrcaSlicer для Linux (на Debian сервере)

После развертывания можно собрать Linux AppImage прямо на сервере:

### 1. Убедись что Docker установлен и запущен:

```bash
docker --version
sudo systemctl status docker
```

### 2. Перейди в директорию проекта:

```bash
cd ~/FilamentHub
```

### 3. Запусти скрипт сборки:

```bash
chmod +x scripts/build_linux_docker.sh
./scripts/build_linux_docker.sh
```

**⚠️ ВНИМАНИЕ:** Сборка может занять **1-2 часа** (компиляция C++ кода).

### 4. После сборки:

AppImage будет автоматически скопирован в:
```
backend/distributions/orcaslicer/OrcaSlicer-FilamentHub-2.0.0-fh-linux-x64.AppImage
```

### 5. Проверь что файл доступен:

```bash
ls -lh backend/distributions/orcaslicer/
```

Файл будет доступен через:
- API: `https://filamenthub.ru/api/v1/downloads/orcaslicer?platform=linux&architecture=x64`
- Прямая ссылка: `https://filamenthub.ru/distributions/orcaslicer/OrcaSlicer-FilamentHub-2.0.0-fh-linux-x64.AppImage`

### Если сборка не работает:

1. **Проверь что OrcaSlicer submodule инициализирован:**
   ```bash
   git submodule update --init --recursive
   ```

2. **Проверь что Docker имеет достаточно ресурсов:**
   - Минимум 4GB RAM
   - Минимум 20GB свободного места на диске

3. **Проверь логи Docker:**
   ```bash
   docker logs <container_id>
   ```

