#!/usr/bin/env bash
# FILAMENTHUB_DEPLOY_PROTOCOL=2
# Production deployment worker for FilamentHub.
#
# Run directly on the production host, or through deploy-server.ps1. The
# worker is interactive by default. --yes is intended only for the local owner
# console, which performs its own exact-SHA confirmation and CI check first.

set -Eeuo pipefail

readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly NC='\033[0m'

if [[ -n "${PROJECT_DIR:-}" ]]; then
    PROJECT_DIR="$(cd "$PROJECT_DIR" && pwd)"
else
    PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fi
SITE_HOST="${SITE_HOST:-filamenthub.ru}"
PUBLIC_HEALTH_HOSTS="${PUBLIC_HEALTH_HOSTS:-filamenthub.ru filamenthub.club}"
CERTBOT_LIVE_DIR="${CERTBOT_LIVE_DIR:-$PROJECT_DIR/certbot/conf/live}"
REQUIRED_CERTIFICATE_HOSTS="${REQUIRED_CERTIFICATE_HOSTS:-filamenthub.ru filamenthub.club}"
PREVIOUS_IMAGE_TAG="previous"
DEPLOY_STATE_FILE="${DEPLOY_STATE_FILE:-$PROJECT_DIR/.last-deploy-state}"
BACKUP_DIR="${BACKUP_DIR:-$PROJECT_DIR/backups}"
BACKUP_KEY="${BACKUP_PUBLIC_KEY:-$PROJECT_DIR/backup-key.pub.asc}"
REVISION="origin/main"
ASSUME_YES=false
DRY_RUN=false
ACTION="deploy"
LATEST_BACKUP=""
PREVIOUS_REVISION=""
TARGET_REVISION=""
BUILD_CACHE_RETENTION_OVERRIDE=""

info() { printf "%b\n" "${BLUE}$*${NC}"; }
success() { printf "%b\n" "${GREEN}$*${NC}"; }
warn() { printf "%b\n" "${YELLOW}$*${NC}"; }
fail() { printf "%b\n" "${RED}$*${NC}" >&2; exit 1; }

usage() {
    cat <<'EOF'
Usage:
  bash scripts/deploy.sh [--revision <commit>] [--yes] [--dry-run]
  bash scripts/deploy.sh --rollback [--yes]
  bash scripts/deploy.sh --status
  bash scripts/deploy.sh --backup-only
  bash scripts/deploy.sh --prune-build-cache [--build-cache-retention <duration>] [--yes]

Options:
  --revision <ref>  Commit to deploy. It must be a fast-forward commit already
                    present on origin/main. Default: origin/main.
  --yes             Skip the server-side confirmation. Use only after an
                    owner-side preflight and exact-SHA confirmation.
  --dry-run         Fetch and validate the target without changing anything.
  --rollback        Put the images kept before the last release back in service.
                    Code only: a migration that already ran stays applied.
  --status          Show container, migration and public health status.
  --backup-only     Create and verify an encrypted database backup, then exit.
  --prune-build-cache
                    Remove Docker build cache older than BUILD_CACHE_RETENTION
                    (default: 336h). Application images are not pruned.
  --build-cache-retention <duration>
                    Override build-cache retention for this cleanup. The value
                    must be a positive Docker duration such as 168h or 336h.
  --help            Show this help.
EOF
}

require_command() {
    command -v "$1" >/dev/null 2>&1 || fail "Required command is missing: $1"
}

check_required_certificates() {
    local host cert_path key_path covered_name host_failed
    local failed=false

    require_command openssl

    info "Checking TLS certificates required by the frontend configuration..."
    for host in $REQUIRED_CERTIFICATE_HOSTS; do
        [[ "$host" =~ ^[a-z0-9.-]+$ ]] \
            || fail "Invalid host in REQUIRED_CERTIFICATE_HOSTS: $host"

        cert_path="$CERTBOT_LIVE_DIR/$host/fullchain.pem"
        key_path="$CERTBOT_LIVE_DIR/$host/privkey.pem"

        if [[ ! -s "$cert_path" || ! -s "$key_path" ]]; then
            warn "  $host: missing fullchain.pem or privkey.pem in $CERTBOT_LIVE_DIR/$host"
            failed=true
            continue
        fi

        # nginx serves www.<host> from this same lineage and only redirects it
        # afterwards, so a certificate without the www name fails the handshake
        # before the visitor ever reaches the redirect.
        host_failed=false
        for covered_name in "$host" "www.$host"; do
            if ! openssl x509 -in "$cert_path" -noout -checkhost "$covered_name" >/dev/null 2>&1; then
                warn "  $host: certificate does not cover $covered_name"
                host_failed=true
            fi
        done

        if [[ "$host_failed" == true ]]; then
            failed=true
            continue
        fi

        if ! openssl x509 -in "$cert_path" -noout -checkend 86400 >/dev/null 2>&1; then
            warn "  $host: certificate is expired or expires within 24 hours"
            failed=true
            continue
        fi

        success "  $host: certificate and private key are present; hostnames and validity are acceptable"
    done

    [[ "$failed" == false ]] \
        || fail "Required TLS certificates are not ready. No backup, build, migration or service switch was started."
}

container_state() {
    docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$1" 2>/dev/null || printf 'not_found'
}

check_alembic_head() {
    local current_output head_output current_versions head_versions
    local current_count head_count current_version head_version

    current_output="$(docker exec filamenthub_backend_prod alembic current 2>&1)" || {
        warn "  database: alembic current failed ($current_output)"
        return 1
    }
    head_output="$(docker exec filamenthub_backend_prod alembic heads 2>&1)" || {
        warn "  database: alembic heads failed ($head_output)"
        return 1
    }
    current_versions="$(printf '%s\n' "$current_output" | awk '/^[[:alnum:]_]+([[:space:]]+\(head\))?$/ { print $1 }')"
    head_versions="$(printf '%s\n' "$head_output" | awk '/^[[:alnum:]_]+[[:space:]]+\(head\)$/ { print $1 }')"
    current_count="$(printf '%s\n' "$current_versions" | grep -c . || true)"
    head_count="$(printf '%s\n' "$head_versions" | grep -c . || true)"
    current_version="$(printf '%s\n' "$current_versions" | head -n 1)"
    head_version="$(printf '%s\n' "$head_versions" | head -n 1)"

    if [[ "$current_count" == "1" \
        && "$head_count" == "1" \
        && "$current_version" == "$head_version" ]]; then
        success "  database: Alembic head ($current_version)"
        return 0
    fi

    warn "  database: expected exactly one matching current/head; current=${current_versions:-unknown}, heads=${head_versions:-unknown}"
    return 1
}

check_semantic_health() {
    local payload

    payload="$(docker exec filamenthub_backend_prod python -c '
import json
import sys
import urllib.request

with urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=10) as response:
    data = json.load(response)

issues = []
if data.get("status") != "ok":
    issues.append("status is not ok")
auth_region = data.get("auth_region") or {}
if auth_region.get("ready") is not True:
    issues.append("auth_region is not ready")
mail_storage = data.get("inbound_mail_storage") or {}
if mail_storage.get("ready") is not True:
    issues.append("inbound_mail_storage is not ready")
if mail_storage.get("over_quota") is True:
    issues.append("inbound_mail_storage is over quota")

print(json.dumps(data, ensure_ascii=True, separators=(",", ":")))
if issues:
    print("; ".join(issues), file=sys.stderr)
    raise SystemExit(1)
' 2>&1)" || {
        warn "  semantic health: failed ($payload)"
        return 1
    }

    success "  semantic health: auth region and inbound mail ready"
}

wait_for_semantic_health() {
    local attempts="${1:-24}"
    local attempt

    for (( attempt=1; attempt<=attempts; attempt++ )); do
        if check_semantic_health; then
            return 0
        fi
        sleep 5
    done
    return 1
}

show_status() {
    local failed=false
    local state

    info "FilamentHub production status"
    docker compose ps || failed=true

    for container in \
        filamenthub_postgres_prod \
        filamenthub_redis_prod \
        filamenthub_backend_prod \
        filamenthub_frontend_prod; do
        state="$(container_state "$container")"
        if [[ "$state" == "healthy" || "$state" == "running" ]]; then
            success "  $container: $state"
        else
            warn "  $container: $state"
            failed=true
        fi
    done

    if docker ps --format '{{.Names}}' | grep -qx filamenthub_backend_prod; then
        check_alembic_head || failed=true
        check_semantic_health || failed=true
    fi

    if curl -kfsS --max-time 10 -H "Host: $SITE_HOST" https://127.0.0.1/health >/dev/null; then
        success "  public backend health: OK"
    else
        warn "  public backend health: failed"
        failed=true
    fi

    if curl -kfsS --max-time 10 -H "Host: $SITE_HOST" https://127.0.0.1/ >/dev/null; then
        success "  public SPA: OK"
    else
        warn "  public SPA: failed"
        failed=true
    fi

    if curl -fsS --max-time 15 "https://$SITE_HOST/health" >/dev/null; then
        success "  external DNS/TLS health: OK"
    else
        warn "  external DNS/TLS health: failed"
        failed=true
    fi

    [[ "$failed" == false ]]
}

prune_build_cache() {
    local retention="${BUILD_CACHE_RETENTION_OVERRIDE:-${BUILD_CACHE_RETENTION:-336h}}"
    local answer

    require_command docker
    [[ "$retention" =~ ^[1-9][0-9]*[hms]$ ]] \
        || fail "BUILD_CACHE_RETENTION must look like 336h, 30m or 60s."

    if [[ "$ASSUME_YES" != true ]]; then
        printf 'Type PRUNE to remove Docker build cache older than %s: ' "$retention"
        read -r answer
        [[ "$answer" == "PRUNE" ]] || fail "Build-cache cleanup cancelled."
    fi

    info "Docker disk usage before cleanup:"
    docker system df
    docker builder prune -f --filter "until=$retention"
    info "Docker disk usage after cleanup:"
    docker system df
    df -h "$PROJECT_DIR"
}

create_backup() {
    local timestamp final_file partial_file

    require_command docker
    require_command gzip
    require_command gpg

    [[ "$(docker inspect --format='{{.State.Running}}' filamenthub_postgres_prod 2>/dev/null || true)" == "true" ]] \
        || fail "Production PostgreSQL is not running; deployment without a backup is forbidden."
    [[ -s "$BACKUP_KEY" ]] || fail "Backup public key is missing or empty: $BACKUP_KEY"

    mkdir -p "$BACKUP_DIR"
    [[ -d "$BACKUP_DIR" && -w "$BACKUP_DIR" ]] \
        || fail "Backup directory is not writable: $BACKUP_DIR"
    chmod 700 "$BACKUP_DIR" 2>/dev/null || true
    umask 077

    timestamp="$(date -u +%Y%m%d_%H%M%S)"
    final_file="$BACKUP_DIR/backup_${timestamp}.sql.gz.gpg"
    partial_file="$final_file.partial"
    rm -f -- "$partial_file"

    info "Creating encrypted database backup..."
    if docker exec filamenthub_postgres_prod sh -c \
        'exec pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' \
        | gzip -c \
        | gpg --batch --yes --quiet --trust-model always \
            --recipient-file "$BACKUP_KEY" \
            --output "$partial_file" --encrypt; then
        [[ -s "$partial_file" ]] || {
            rm -f -- "$partial_file"
            fail "Backup pipeline completed without producing a non-empty encrypted file."
        }
        mv -- "$partial_file" "$final_file"
    else
        rm -f -- "$partial_file"
        fail "Encrypted database backup failed. Deployment has not started."
    fi

    # --list-only validates the packet structure without trying to decrypt it;
    # the production host intentionally does not have the private backup key.
    gpg --batch --quiet --list-only --list-packets "$final_file" >/dev/null 2>&1 \
        || fail "The new backup is not a valid OpenPGP file: $final_file"
    LATEST_BACKUP="$final_file"
    success "Backup verified: $LATEST_BACKUP"
}

resolve_target() {
    local branch dirty

    require_command git
    require_command docker
    require_command curl

    cd "$PROJECT_DIR"
    [[ -f docker-compose.yml ]] || fail "docker-compose.yml was not found in $PROJECT_DIR"

    # These paths are production runtime storage. Excluding them explicitly is
    # required for the first rollout of this worker, before the new .gitignore
    # itself has reached the production checkout.
    dirty="$(git status --porcelain --untracked-files=normal -- . \
        ':(exclude)inbound-mail' \
        ':(exclude)inbound-mail/**' \
        ':(exclude)backend/distributions/plugins' \
        ':(exclude)backend/distributions/plugins/**')"
    [[ -z "$dirty" ]] || {
        printf '%s\n' "$dirty" >&2
        fail "Production worktree is not clean. Resolve it manually; deployment never discards files."
    }

    branch="$(git branch --show-current)"
    [[ "$branch" == "main" ]] || fail "Production worktree must be on main, found: ${branch:-detached HEAD}"

    info "Fetching origin/main without submodules..."
    git fetch --no-recurse-submodules origin main

    PREVIOUS_REVISION="$(git rev-parse HEAD)"
    TARGET_REVISION="$(git rev-parse --verify "${REVISION}^{commit}" 2>/dev/null)" \
        || fail "Could not resolve deployment revision: $REVISION"

    git merge-base --is-ancestor "$PREVIOUS_REVISION" "$TARGET_REVISION" \
        || fail "Target is not a fast-forward from the currently deployed revision."
    git merge-base --is-ancestor "$TARGET_REVISION" origin/main \
        || fail "Target revision is not part of origin/main."

    printf 'Current: %s\nTarget : %s\n' "$PREVIOUS_REVISION" "$TARGET_REVISION"
    if [[ "$PREVIOUS_REVISION" == "$TARGET_REVISION" ]]; then
        warn "The requested revision is already checked out; containers will still be rebuilt after confirmation."
    else
        git log --oneline --no-decorate "$PREVIOUS_REVISION..$TARGET_REVISION" | sed 's/^/  /'
    fi
}

confirm_deploy() {
    local answer short
    [[ "$ASSUME_YES" == true ]] && return 0
    short="${TARGET_REVISION:0:8}"
    printf 'Type DEPLOY %s to continue: ' "$short"
    read -r answer
    [[ "$answer" == "DEPLOY $short" ]] || fail "Deployment cancelled."
}

tag_release_images() {
    local service container image

    info "Keeping the running images so a failed release can be undone..."
    for service in backend frontend; do
        container="filamenthub_${service}_prod"
        image="$(docker inspect --format '{{.Image}}' "$container" 2>/dev/null || true)"
        if [[ -z "$image" ]]; then
            warn "  $container is not running; nothing kept for $service"
            continue
        fi
        if docker tag "$image" "filamenthub-${service}:${PREVIOUS_IMAGE_TAG}"; then
            success "  $service kept as filamenthub-${service}:${PREVIOUS_IMAGE_TAG}"
        else
            warn "  could not keep the running $service image"
        fi
    done
}

schema_revision() {
    docker compose run --rm --no-deps --entrypoint alembic backend current 2>/dev/null \
        | tr -d '[:space:]'
}

record_deploy_state() {
    printf 'previous_revision=%s\ntarget_revision=%s\nmigrations_applied=%s\n' \
        "$PREVIOUS_REVISION" "$TARGET_REVISION" "$1" > "$DEPLOY_STATE_FILE"
}

wait_for_container() {
    local container="$1"
    local attempts="${2:-24}"
    local state=""
    local attempt

    for (( attempt=1; attempt<=attempts; attempt++ )); do
        state="$(container_state "$container")"
        if [[ "$state" == "healthy" || "$state" == "running" ]]; then
            success "  $container: $state"
            return 0
        fi
        sleep 5
    done

    warn "  $container did not become ready (last state: $state)"
    return 1
}

verify_release() {
    local container public_host
    local failed=false

    info "Waiting for production services..."
    for container in \
        filamenthub_postgres_prod \
        filamenthub_redis_prod \
        filamenthub_backend_prod \
        filamenthub_frontend_prod; do
        wait_for_container "$container" || failed=true
    done

    wait_for_semantic_health || failed=true

    check_alembic_head || failed=true

    if ! curl -kfsS --max-time 10 -H "Host: $SITE_HOST" https://127.0.0.1/health >/dev/null; then
        warn "Public backend health check failed."
        failed=true
    else
        success "Public backend health check passed."
    fi
    if ! curl -kfsS --max-time 10 -H "Host: $SITE_HOST" https://127.0.0.1/ >/dev/null; then
        warn "Public SPA check failed."
        failed=true
    else
        success "Public SPA check passed."
    fi
    if ! curl -kfsS --max-time 10 -H "Host: $SITE_HOST" https://127.0.0.1/logo.svg >/dev/null; then
        warn "Public static asset check failed."
        failed=true
    else
        success "Public static asset check passed."
    fi
    for public_host in $PUBLIC_HEALTH_HOSTS; do
        if [[ ! "$public_host" =~ ^[a-z0-9.-]+$ ]]; then
            warn "Invalid host in PUBLIC_HEALTH_HOSTS: $public_host"
            failed=true
            continue
        fi
        if ! curl -fsS --max-time 15 "https://$public_host/health" >/dev/null; then
            warn "External HTTPS health check failed for $public_host (DNS/TLS/public route)."
            failed=true
        else
            success "External HTTPS health check passed for $public_host."
        fi
    done

    [[ "$failed" == false ]]
}

rollback_release() {
    local service answer
    local missing=false

    for service in backend frontend; do
        docker image inspect "filamenthub-${service}:${PREVIOUS_IMAGE_TAG}" >/dev/null 2>&1 && continue
        warn "No kept image for $service (filamenthub-${service}:${PREVIOUS_IMAGE_TAG})"
        missing=true
    done
    [[ "$missing" == false ]] \
        || fail "Nothing to put back. Deploy a fixed revision the normal way instead."

    if grep -qx 'migrations_applied=true' "$DEPLOY_STATE_FILE" 2>/dev/null; then
        warn "The last deployment applied migrations, and they stay applied."
        warn "The previous code will meet a newer schema than it was built against."
        if [[ "$ASSUME_YES" != true ]]; then
            printf 'Type ROLLBACK to continue: '
            read -r answer
            [[ "$answer" == "ROLLBACK" ]] || fail "Rollback cancelled."
        fi
    fi

    info "Putting the kept images back in service..."
    for service in backend frontend; do
        docker tag "filamenthub-${service}:${PREVIOUS_IMAGE_TAG}" "filamenthub-${service}:latest"
    done
    COMPOSE_BAKE=false docker compose up -d --no-build --remove-orphans

    if ! verify_release; then
        printf '\n' >&2
        fail "The restored release did not pass verification either. Inspect: docker compose logs --tail=200 backend frontend"
    fi

    printf '\n'
    success "The images from before the last release are serving again."
    warn "The worktree still points at $(git rev-parse --short HEAD); deploy a fixed revision to line them up."
    docker compose ps
}

deploy() {
    local migration_heads head_count schema_before schema_after
    local failed=false

    resolve_target
    check_required_certificates
    if [[ "$DRY_RUN" == true ]]; then
        success "Dry run complete. No backup, Git update, build, migration or restart was performed."
        return 0
    fi
    confirm_deploy

    create_backup

    info "Fast-forwarding the production worktree..."
    git merge --ff-only "$TARGET_REVISION"

    tag_release_images

    info "Building new application images while the current containers keep serving traffic..."
    COMPOSE_BAKE=false docker compose build backend frontend

    info "Checking the migration graph in the newly built backend image..."
    migration_heads="$(docker compose run --rm --no-deps --entrypoint alembic backend heads)"
    printf '%s\n' "$migration_heads" | sed 's/^/  /'
    head_count="$(printf '%s\n' "$migration_heads" | grep -c '(head)' || true)"
    [[ "$head_count" == "1" ]] \
        || fail "Expected exactly one Alembic head, found $head_count. The current app is still running."

    schema_before="$(schema_revision)"
    info "Applying migrations with the newly built image before switching the API..."
    docker compose run --rm --no-deps --entrypoint alembic backend upgrade head
    schema_after="$(schema_revision)"
    if [[ "$schema_before" == "$schema_after" ]]; then
        record_deploy_state false
    else
        record_deploy_state true
    fi

    info "Switching services to the new images..."
    COMPOSE_BAKE=false docker compose up -d --no-build --remove-orphans

    if ! verify_release; then
        printf '\n' >&2
        warn "Deployment verification failed. Automatic schema rollback is intentionally disabled."
        warn "Previous revision: $PREVIOUS_REVISION"
        warn "Pre-deploy backup: $LATEST_BACKUP"
        warn "Put the previous code back: bash scripts/deploy.sh --rollback"
        warn "Inspect immediately: docker compose ps && docker compose logs --tail=200 backend frontend"
        exit 1
    fi

    printf '\n'
    success "Deployment completed and verified: $TARGET_REVISION"
    success "Pre-deploy backup: $LATEST_BACKUP"
    docker compose ps
}

while (( $# > 0 )); do
    case "$1" in
        --revision)
            [[ $# -ge 2 ]] || fail "--revision requires a value"
            REVISION="$2"
            shift 2
            ;;
        --yes)
            ASSUME_YES=true
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --rollback)
            ACTION="rollback"
            shift
            ;;
        --status)
            ACTION="status"
            shift
            ;;
        --backup-only)
            ACTION="backup"
            shift
            ;;
        --prune-build-cache)
            ACTION="prune"
            shift
            ;;
        --build-cache-retention)
            [[ $# -ge 2 ]] || fail "--build-cache-retention requires a value"
            BUILD_CACHE_RETENTION_OVERRIDE="$2"
            shift 2
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            fail "Unknown argument: $1"
            ;;
    esac
done

if [[ -n "$BUILD_CACHE_RETENTION_OVERRIDE" && "$ACTION" != "prune" ]]; then
    fail "--build-cache-retention can only be used with --prune-build-cache"
fi

cd "$PROJECT_DIR"
case "$ACTION" in
    deploy) deploy ;;
    rollback) rollback_release ;;
    status) show_status ;;
    backup) create_backup ;;
    prune) prune_build_cache ;;
    *) fail "Unknown action: $ACTION" ;;
esac
