# 🔒 Настройка SSL сертификатов для FilamentHub

## ⚠️ Важно: Это НЕ самоподписанные сертификаты!

**Let's Encrypt** - это официальный доверенный центр сертификации (CA), как Comodo или DigiCert.
- ✅ Браузеры **не показывают предупреждения**
- ✅ Полностью **бесплатно**
- ✅ **Официальные** сертификаты для продакшена
- ✅ Работают как платные сертификаты

**Самоподписанные** сертификаты создаются вами самими, браузеры их не доверяют и показывают "Небезопасный сайт".

---

## Подготовка

### 1. Убедитесь что DNS уже работает

Перед получением сертификатов домен должен резолвиться на ваш IP:

```bash
nslookup filamenthub.ru
# Должен вернуть: 185.237.236.5
```

### 2. Установите certbot на сервере

```bash
sudo apt update
sudo apt install certbot python3-certbot-nginx
```

## Получение SSL сертификата

### Вариант 1: Через Nginx в Docker (рекомендуется)

Этот способ работает с текущей конфигурацией Docker:

```bash
# 1. Создайте директории для certbot
mkdir -p certbot/conf certbot/www

# 2. Временно запустите frontend контейнер (если не запущен)
docker-compose up -d frontend

# 3. Получите сертификат (standalone режим, nginx должен быть остановлен)
docker-compose stop frontend
sudo certbot certonly --standalone \
  -d filamenthub.ru \
  -d www.filamenthub.ru \
  --email your-email@example.com \
  --agree-tos \
  --non-interactive

# 4. Скопируйте сертификаты в папку проекта
sudo cp -r /etc/letsencrypt/live/filamenthub.ru certbot/conf/live/
sudo cp -r /etc/letsencrypt/archive/filamenthub.ru certbot/conf/archive/
sudo chown -R $USER:$USER certbot/

# 5. Запустите frontend обратно
docker-compose up -d frontend
```

### Вариант 2: Через веб-сервер (проще)

Если nginx уже запущен и доступен из интернета:

```bash
# 1. Временно измените docker-compose.yml - добавьте volume для certbot
# (уже сделано в обновленном docker-compose.yml)

# 2. Создайте директории
mkdir -p certbot/conf certbot/www

# 3. Получите сертификат через webroot
sudo certbot certonly --webroot \
  -w ./certbot/www \
  -d filamenthub.ru \
  -d www.filamenthub.ru \
  --email your-email@example.com \
  --agree-tos

# 4. Скопируйте сертификаты
sudo cp -r /etc/letsencrypt/live/filamenthub.ru certbot/conf/live/
sudo chown -R $USER:$USER certbot/

# 5. Перезапустите frontend
docker-compose restart frontend
```

## Автоматическое обновление сертификатов

Сертификаты Let's Encrypt действуют 90 дней. Настройте автообновление:

### 1. Создайте скрипт для обновления

```bash
cat > renew-cert.sh << 'EOF'
#!/bin/bash
# Обновление SSL сертификатов

# Останавливаем frontend
docker-compose stop frontend

# Обновляем сертификаты
sudo certbot renew

# Копируем обновленные сертификаты
sudo cp -r /etc/letsencrypt/live/filamenthub.ru certbot/conf/live/
sudo cp -r /etc/letsencrypt/archive/filamenthub.ru certbot/conf/archive/
sudo chown -R $USER:$USER certbot/

# Перезапускаем frontend
docker-compose up -d frontend
EOF

chmod +x renew-cert.sh
```

### 2. Добавьте в crontab (запуск раз в неделю)

```bash
# Открыть crontab
crontab -e

# Добавить строку (каждый понедельник в 3:00)
0 3 * * 1 cd /path/to/FilamentHub && ./renew-cert.sh >> /var/log/certbot-renew.log 2>&1
```

## Проверка работы

После получения сертификатов:

1. **Проверьте HTTPS:**
   ```bash
   curl -I https://filamenthub.ru
   # Должен вернуть 200 OK
   ```

2. **Проверьте в браузере:**
   - Откройте `https://filamenthub.ru`
   - Должна быть иконка замочка (SSL работает)

3. **Проверьте редирект HTTP → HTTPS:**
   ```bash
   curl -I http://filamenthub.ru
   # Должен вернуть 301 Redirect на https://
   ```

## Важные замечания

- ⚠️ **Не получайте сертификаты до того как DNS заработал** - Let's Encrypt проверяет домен
- ⚠️ **Email в certbot** - укажите реальный email, на него придут уведомления об истечении
- ⚠️ **Автообновление** - обязательно настройте, иначе через 90 дней сайт перестанет работать
- ⚠️ **Права доступа** - certbot должен иметь доступ к сертификатам

## Troubleshooting

### Ошибка: "Connection refused"
DNS ещё не работает. Подождите или проверьте настройки DNS.

### Ошибка: "Port 80 already in use"
Остановите nginx перед получением сертификата:
```bash
docker-compose stop frontend
```

### Сертификаты не работают в контейнере
Проверьте что volumes правильно подключены в docker-compose.yml:
```yaml
volumes:
  - ./certbot/conf:/etc/letsencrypt
```

### Нужно перевыпустить сертификат
```bash
sudo certbot renew --force-renewal
```

