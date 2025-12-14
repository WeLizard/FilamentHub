#!/bin/bash
# Скрипт для сборки Linux версии через Docker и копирования в distributions
# ⚠️ Работает на Windows/Mac/Linux (нужен Docker)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORCA_DIR="$SCRIPT_DIR/../docs/OrcaSlicer"
DIST_DIR="$SCRIPT_DIR/../backend/distributions/orcaslicer"
VERSION="2.0.0-fh"

echo "🔨 Сборка OrcaSlicer для Linux через Docker..."
echo ""

# Проверяем наличие Docker
if ! command -v docker &> /dev/null; then
    echo "❌ Docker не установлен! Установите Docker Desktop для Windows/Mac или Docker для Linux."
    exit 1
fi

cd "$ORCA_DIR"

# Проверяем наличие скрипта Docker сборки
if [ ! -f "scripts/DockerBuild.sh" ]; then
    echo "❌ Скрипт scripts/DockerBuild.sh не найден!"
    exit 1
fi

# Сборка через Docker (может занять много времени - 1-2 часа)
echo "⚠️  ВНИМАНИЕ: Сборка может занять 1-2 часа!"
echo "Запускаю сборку через Docker..."
echo ""

# Переходим в scripts директорию для запуска
cd scripts
chmod +x DockerBuild.sh
./DockerBuild.sh

# Возвращаемся обратно
cd ..

# Ищем собранный AppImage в контейнере
echo ""
echo "Ищу собранный AppImage..."

# Запускаем временный контейнер для извлечения файла
TEMP_CONTAINER=$(docker run -d --rm orcaslicer sleep 60)
echo "Контейнер запущен: $TEMP_CONTAINER"

# Ищем AppImage
APPIMAGE_PATH=$(docker exec "$TEMP_CONTAINER" find /OrcaSlicer/build -name "OrcaSlicer-*.AppImage" 2>/dev/null | head -1)

if [ -z "$APPIMAGE_PATH" ]; then
    echo "❌ AppImage не найден в контейнере!"
    docker stop "$TEMP_CONTAINER" 2>/dev/null || true
    exit 1
fi

echo "Найден AppImage: $APPIMAGE_PATH"

# Создаем папку distributions
mkdir -p "$DIST_DIR"

# Копируем AppImage
echo "Копирую AppImage..."
docker cp "$TEMP_CONTAINER:$APPIMAGE_PATH" "$DIST_DIR/OrcaSlicer-FilamentHub-${VERSION}-linux-x64.AppImage"

# Останавливаем контейнер
docker stop "$TEMP_CONTAINER" 2>/dev/null || true

# Проверяем размер
FILE_SIZE=$(du -h "$DIST_DIR/OrcaSlicer-FilamentHub-${VERSION}-linux-x64.AppImage" | cut -f1)

echo ""
echo "✅ Готово! AppImage скопирован в: $DIST_DIR"
echo "   Файл: OrcaSlicer-FilamentHub-${VERSION}-linux-x64.AppImage"
echo "   Размер: $FILE_SIZE"
echo ""
echo "Файл будет доступен через:"
echo "   - API: /api/v1/downloads/orcaslicer"
echo "   - Прямая ссылка: http://filamenthub.ru/distributions/orcaslicer/OrcaSlicer-FilamentHub-${VERSION}-linux-x64.AppImage"

