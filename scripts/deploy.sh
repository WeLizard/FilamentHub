#!/bin/bash
# Простой скрипт деплоя для сервера
# Делает git pull и перезапускает контейнеры БЕЗ удаления volumes (БД сохраняется)

set -e  # Остановка при ошибке

echo "🚀 Начинаю деплой..."

# Переходим в директорию проекта
cd "$(dirname "$0")/.." || exit 1

# 1. Обновляем код из Git
echo "📥 Обновляю код из Git..."

# Сначала получаем изменения
git fetch origin main || git fetch origin master

# Удаляем untracked файлы, которые конфликтуют с git (они будут скачаны из git)
echo "🧹 Удаляю конфликтующие локальные файлы..."
git clean -fd

# Обновляем до последней версии из git (безопасно для деплоя)
git reset --hard origin/main || git reset --hard origin/master

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

