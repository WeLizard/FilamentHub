#!/bin/bash
# Простой скрипт деплоя для сервера
# Делает git pull и перезапускает контейнеры БЕЗ удаления volumes (БД сохраняется)

set -e  # Остановка при ошибке

echo "🚀 Начинаю деплой..."

# Переходим в директорию проекта
cd "$(dirname "$0")/.." || exit 1

# 1. Обновляем код из Git
echo "📥 Обновляю код из Git..."
git pull origin main || git pull origin master

# 2. Перезапускаем контейнеры с пересборкой (если нужно)
# --build пересоберёт только если изменились Dockerfile/docker-compose.yml
# volumes НЕ удаляются - база данных сохранится!
echo "🔄 Перезапускаю контейнеры..."
docker-compose up -d --build

# 3. Показываем статус
echo ""
echo "✅ Деплой завершён!"
echo ""
echo "Статус контейнеров:"
docker-compose ps

echo ""
echo "💡 Для просмотра логов: docker-compose logs -f"

