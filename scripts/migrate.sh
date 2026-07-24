#!/usr/bin/env bash
# Apply / roll back Alembic migrations on a running FilamentHub backend container.
#
# Usage:
#   bash scripts/migrate.sh dev              # interactive menu (local dev stack)
#   bash scripts/migrate.sh prod             # interactive menu (run on the server)
#   bash scripts/migrate.sh dev up           # non-interactive: upgrade to head
#   bash scripts/migrate.sh prod current     # show current revision
#   bash scripts/migrate.sh prod down        # downgrade one step (asks to confirm)
#   bash scripts/migrate.sh prod to <rev>    # downgrade to <rev> (asks to confirm)
#
# up/current/history are safe. down/to run a DOWNGRADE, which can DROP columns
# or tables — they always ask for confirmation. For prod, take a DB backup first
# (scripts/deploy.sh already does a pg_dump).
set -euo pipefail

ENV="${1:-}"
case "$ENV" in
  prod) CONTAINER="filamenthub_backend_prod" ;;
  dev)  CONTAINER="filamenthub_backend_dev" ;;
  *) echo "usage: $0 <dev|prod> [up|down|to <rev>|history|current]" >&2; exit 1 ;;
esac

if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  echo "Container '$CONTAINER' is not running." >&2
  [ "$ENV" = dev ] && echo "Start it first:  docker compose -f docker-compose.dev.yml up -d" >&2
  exit 1
fi

al() { docker exec "$CONTAINER" alembic "$@"; }
confirm() { local a; read -rp "$1 [напиши yes]: " a; [ "$a" = "yes" ]; }

action="${2:-}"
REV="${3:-}"

if [ -z "$action" ]; then
  echo "== [$ENV] текущая ревизия =="
  al current || true
  echo
  echo "  1) up       — накатить всё новое (upgrade head)"
  echo "  2) down     — откат на 1 шаг (downgrade -1) — удаляет схему!"
  echo "  3) to REV   — откат до конкретной ревизии — удаляет схему!"
  echo "  4) history  — список ревизий"
  echo "  5) current  — показать текущую"
  read -rp "Выбор [1-5]: " choice
  case "$choice" in
    1) action="up" ;;
    2) action="down" ;;
    3) action="to"; read -rp "Ревизия: " REV ;;
    4) action="history" ;;
    5) action="current" ;;
    *) echo "отмена"; exit 1 ;;
  esac
fi

case "$action" in
  up)
    al upgrade head ;;
  current)
    al current; exit 0 ;;
  history)
    al history; exit 0 ;;
  down)
    confirm "ОТКАТ на 1 шаг на [$ENV] может УДАЛИТЬ колонки/таблицы. Продолжить?" \
      && al downgrade -1 || { echo "отменено"; exit 0; } ;;
  to)
    [ -n "$REV" ] || { echo "ревизия не задана" >&2; exit 1; }
    confirm "ОТКАТ до '$REV' на [$ENV] может УДАЛИТЬ колонки/таблицы. Продолжить?" \
      && al downgrade "$REV" || { echo "отменено"; exit 0; } ;;
  *)
    echo "unknown action: $action" >&2; exit 1 ;;
esac

echo "== [$ENV] стало =="
al current
