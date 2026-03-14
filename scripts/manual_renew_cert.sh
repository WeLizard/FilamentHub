#!/bin/bash
set -Eeuo pipefail

BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SITE_HOST="${SITE_HOST:-filamenthub.ru}"
ALT_HOST="${ALT_HOST:-www.${SITE_HOST}}"
CERTBOT_IMAGE="${CERTBOT_IMAGE:-certbot/certbot}"
FRONTEND_SERVICE="${FRONTEND_SERVICE:-frontend}"
CERTBOT_EMAIL="${CERTBOT_EMAIL:-${1:-}}"

LIVE_ROOT="$PROJECT_DIR/certbot/conf/live"
TARGET_LINEAGE_DIR="$LIVE_ROOT/$SITE_HOST"

log() {
  echo -e "$1"
}

fail() {
  log "${RED}❌ $1${NC}"
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "Требуется команда: $1"
}

print_cert_dates() {
  local cert_path="$1"

  if [ ! -f "$cert_path" ]; then
    log "${YELLOW}⚠️  Сертификат не найден: $cert_path${NC}"
    return
  fi

  openssl x509 -in "$cert_path" -noout -dates
}

find_latest_lineage() {
  local best_dir=""
  local best_epoch=0

  shopt -s nullglob
  for dir in "$LIVE_ROOT"/"$SITE_HOST"*; do
    [ -d "$dir" ] || continue
    [ -f "$dir/fullchain.pem" ] || continue

    local end_date
    end_date="$(openssl x509 -in "$dir/fullchain.pem" -noout -enddate 2>/dev/null | sed 's/^notAfter=//')" || continue

    local epoch
    epoch="$(date -d "$end_date" +%s 2>/dev/null || echo 0)"

    if [ "$epoch" -gt "$best_epoch" ]; then
      best_epoch="$epoch"
      best_dir="$dir"
    fi
  done
  shopt -u nullglob

  printf '%s\n' "$best_dir"
}

sync_lineage_into_target() {
  local source_dir="$1"

  [ -d "$source_dir" ] || fail "Исходный lineage не найден: $source_dir"

  docker run --rm \
    -v "$PROJECT_DIR/certbot/conf:/certs" \
    alpine sh -lc "
      set -e
      mkdir -p '/certs/live/$SITE_HOST'
      cp -fL '/certs/live/$(basename "$source_dir")/cert.pem' '/certs/live/$SITE_HOST/cert.pem'
      cp -fL '/certs/live/$(basename "$source_dir")/chain.pem' '/certs/live/$SITE_HOST/chain.pem'
      cp -fL '/certs/live/$(basename "$source_dir")/fullchain.pem' '/certs/live/$SITE_HOST/fullchain.pem'
      cp -fL '/certs/live/$(basename "$source_dir")/privkey.pem' '/certs/live/$SITE_HOST/privkey.pem'
      chmod 644 '/certs/live/$SITE_HOST/cert.pem' '/certs/live/$SITE_HOST/chain.pem' '/certs/live/$SITE_HOST/fullchain.pem'
      chmod 600 '/certs/live/$SITE_HOST/privkey.pem'
    " >/dev/null
}

require_command docker
require_command openssl
require_command date

cd "$PROJECT_DIR"
mkdir -p "$PROJECT_DIR/certbot/conf" "$PROJECT_DIR/certbot/www"

log "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
log "${BLUE}🔐 Manual SSL Renewal${NC}"
log "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
log "${GREEN}📁 Директория:${NC} $PROJECT_DIR"
log "${GREEN}🌐 Домен:${NC} $SITE_HOST (+ $ALT_HOST)"

log ""
log "${YELLOW}Текущий сертификат:${NC}"
print_cert_dates "$TARGET_LINEAGE_DIR/fullchain.pem"

certbot_args=(
  docker run -it --rm
  -v "$PROJECT_DIR/certbot/conf:/etc/letsencrypt"
  "$CERTBOT_IMAGE"
  certonly
  --manual
  --preferred-challenges dns
  --manual-public-ip-logging-ok
  --cert-name "$SITE_HOST"
  -d "$SITE_HOST"
  -d "$ALT_HOST"
  --force-renewal
  --agree-tos
)

if [ -n "$CERTBOT_EMAIL" ]; then
  certbot_args+=(--email "$CERTBOT_EMAIL")
else
  certbot_args+=(--register-unsafely-without-email)
fi

log ""
log "${YELLOW}Запускаю Certbot manual DNS challenge...${NC}"
log "Добавь TXT записи, дождись распространения DNS и нажимай Enter только после проверки."

"${certbot_args[@]}"

latest_lineage_dir="$(find_latest_lineage)"
[ -n "$latest_lineage_dir" ] || fail "Не удалось найти новый lineage после успешного certbot запуска"

log ""
log "${YELLOW}Синхронизирую lineage в рабочий путь nginx...${NC}"
sync_lineage_into_target "$latest_lineage_dir"

log ""
log "${YELLOW}Перезапускаю frontend...${NC}"
docker compose up -d "$FRONTEND_SERVICE" >/dev/null

log ""
log "${GREEN}✅ Новый сертификат установлен${NC}"
log "${GREEN}Используемый lineage:${NC} $(basename "$latest_lineage_dir")"
print_cert_dates "$TARGET_LINEAGE_DIR/fullchain.pem"

log ""
log "${YELLOW}Проверка frontend:${NC}"
docker compose ps "$FRONTEND_SERVICE"

if command -v curl >/dev/null 2>&1; then
  log ""
  log "${YELLOW}Локальная HTTPS проверка:${NC}"
  curl -kfsSI "https://127.0.0.1" -H "Host: $SITE_HOST" | head -n 1 || true
fi

log ""
log "${YELLOW}Не забудь удалить временные TXT записи _acme-challenge* из DNS.${NC}"
