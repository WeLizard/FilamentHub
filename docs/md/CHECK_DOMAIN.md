# 🌐 Проверка доступности сайта по домену

## ✅ Что уже настроено:

1. **DNS работает:** `filamenthub.ru` → `185.237.236.5` ✅
2. **Nginx настроен:** `server_name filamenthub.ru www.filamenthub.ru` ✅
3. **Порты проброшены:** `80:80` и `443:443` ✅

## 🔍 Что нужно проверить на сервере:

### 1. Запущены ли контейнеры?
```bash
docker-compose ps
# Все контейнеры должны быть "Up"
```

### 2. Доступен ли сайт по IP?
```bash
curl -I http://185.237.236.5
# Должен вернуть 200 OK
```

### 3. Доступен ли сайт по домену?
```bash
curl -I http://filamenthub.ru
# Должен вернуть 200 OK
```

Или откройте в браузере: **http://filamenthub.ru**

### 4. Порт 80 открыт в файрволе?
```bash
# Проверка на сервере
sudo ufw status
# или
sudo iptables -L -n | grep 80

# Порт 80 должен быть открыт для входящих соединений
```

### 5. Если сайт не доступен - проверьте логи:
```bash
docker-compose logs frontend
docker-compose logs backend
```

## 🚨 Возможные проблемы:

### Проблема: Сайт не доступен по домену, но доступен по IP
**Решение:** Проверьте что nginx.conf загружен в контейнер:
```bash
docker exec filamenthub_frontend_prod cat /etc/nginx/conf.d/default.conf | grep server_name
# Должно быть: server_name filamenthub.ru www.filamenthub.ru _;
```

### Проблема: Connection refused
**Решение:** Проверьте что порт 80 открыт:
```bash
sudo netstat -tlnp | grep :80
# или
sudo ss -tlnp | grep :80
```

### Проблема: 502 Bad Gateway
**Решение:** Backend не доступен, проверьте:
```bash
docker-compose ps backend
docker-compose logs backend
```

## ✅ Если все работает:

Сайт должен быть доступен по:
- **http://filamenthub.ru**
- **http://www.filamenthub.ru**

После настройки SSL также будет доступен по:
- **https://filamenthub.ru**
- **https://www.filamenthub.ru**

