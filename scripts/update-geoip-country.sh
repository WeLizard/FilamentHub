#!/usr/bin/env bash

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TARGET_DIR="${GEOIP_TARGET_DIR:-$PROJECT_DIR/backend/data/geoip}"
TARGET_FILE="$TARGET_DIR/dbip-country-lite.mmdb"
PREVIOUS_FILE="$TARGET_DIR/dbip-country-lite.previous.mmdb"
CONTAINER_NAME="${GEOIP_BACKEND_CONTAINER:-filamenthub_backend_prod}"

mkdir -p "$TARGET_DIR"
if [ ! -w "$TARGET_DIR" ]; then
    echo "GeoIP directory is not writable: $TARGET_DIR" >&2
    exit 1
fi

TMP_DIR="$(mktemp -d "$TARGET_DIR/.dbip-update.XXXXXX")"
trap 'rm -rf -- "$TMP_DIR"' EXIT

CURRENT_MONTH="$(date -u +%Y-%m)"
PREVIOUS_MONTH="$(date -u -d '1 month ago' +%Y-%m)"
ARCHIVE="$TMP_DIR/country.mmdb.gz"
DATABASE="$TMP_DIR/country.mmdb"
DOWNLOADED_MONTH=""

for month in "$CURRENT_MONTH" "$PREVIOUS_MONTH"; do
    url="https://download.db-ip.com/free/dbip-country-lite-${month}.mmdb.gz"
    if curl --fail --silent --show-error --location --retry 3 \
        --connect-timeout 15 --output "$ARCHIVE" "$url"; then
        DOWNLOADED_MONTH="$month"
        break
    fi
done

if [ -z "$DOWNLOADED_MONTH" ]; then
    echo "Could not download the current or previous DB-IP Country Lite release." >&2
    exit 1
fi

gzip --test "$ARCHIVE"
gzip --decompress --stdout "$ARCHIVE" > "$DATABASE"
if [ ! -s "$DATABASE" ]; then
    echo "Downloaded MMDB is empty." >&2
    exit 1
fi

VALIDATION_CODE="import sys, geoip2.database; p=sys.argv[1]; r=geoip2.database.Reader(p); t=r.metadata().database_type; assert t.startswith('DBIP-Country-Lite'), t; assert r.country('77.88.8.8').country.iso_code == 'RU'; assert r.country('8.8.8.8').country.iso_code != 'RU'; print(t); r.close()"

if command -v docker >/dev/null 2>&1 \
    && docker ps --format '{{.Names}}' 2>/dev/null | grep -Fxq "$CONTAINER_NAME"; then
    CONTAINER_DATABASE="/app/data/geoip/$(basename "$TMP_DIR")/$(basename "$DATABASE")"
    docker exec "$CONTAINER_NAME" python -c "$VALIDATION_CODE" "$CONTAINER_DATABASE"
else
    HOST_PYTHON=""
    for candidate in python3 python; do
        if command -v "$candidate" >/dev/null 2>&1 \
            && "$candidate" -c 'import geoip2' >/dev/null 2>&1; then
            HOST_PYTHON="$candidate"
            break
        fi
    done
    if [ -z "$HOST_PYTHON" ]; then
        echo "Cannot validate the downloaded MMDB: start $CONTAINER_NAME or install geoip2 for Python." >&2
        exit 1
    fi
    "$HOST_PYTHON" -c "$VALIDATION_CODE" "$DATABASE"
fi

chmod 0644 "$DATABASE"
if [ -s "$TARGET_FILE" ]; then
    cp -- "$TARGET_FILE" "$TMP_DIR/previous.mmdb"
    chmod 0644 "$TMP_DIR/previous.mmdb"
    mv -f -- "$TMP_DIR/previous.mmdb" "$PREVIOUS_FILE"
fi
mv -f -- "$DATABASE" "$TARGET_FILE"

echo "Installed DB-IP Country Lite $DOWNLOADED_MONTH: $TARGET_FILE"
if [ -s "$PREVIOUS_FILE" ]; then
    echo "Previous database retained for rollback: $PREVIOUS_FILE"
fi
echo "The backend will reopen the database automatically; no restart is required."
