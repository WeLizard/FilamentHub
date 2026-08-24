#!/usr/bin/env bash
# FILAMENTHUB_DEPLOY_JOB_PROTOCOL=1
# Durable wrapper for the owner-run production deployment worker.

set -Eeuo pipefail

PROJECT_DIR="${PROJECT_DIR:-$(pwd)}"
STATE_DIR="${FILAMENTHUB_DEPLOY_STATE_DIR:-${XDG_STATE_HOME:-$HOME/.local/state}/filamenthub/deploys}"
ACTION=""
RUN_ID=""
WORKER_REVISION=""
FROM_LINE=0
RESTART_FAILED=false
WORKER_ARGS=()
START_LOCK_DIR=""

fail() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

cleanup_start_lock() {
    trap - RETURN EXIT
    if [[ -n "$START_LOCK_DIR" ]]; then
        rmdir "$START_LOCK_DIR" 2>/dev/null || true
        START_LOCK_DIR=""
    fi
}

usage() {
    cat <<'EOF'
Usage:
  run-deploy-job.sh --start --run-id <id> --worker-revision <sha> [--restart-failed] -- <worker args>
  run-deploy-job.sh --status --run-id <id> [--from-line <number>]
EOF
}

validate_run_id() {
    [[ "$RUN_ID" =~ ^[a-z0-9][a-z0-9-]{0,79}$ ]] \
        || fail "Invalid deploy run id: $RUN_ID"
}

run_status() {
    local run_dir="$1"
    local status="missing"
    local exit_code="-"
    local pid=""

    if [[ -f "$run_dir/exit-code" ]]; then
        exit_code="$(tr -d '[:space:]' < "$run_dir/exit-code")"
        if [[ "$exit_code" == "0" ]]; then
            status="succeeded"
        else
            status="failed"
        fi
    elif [[ -f "$run_dir/pid" ]]; then
        pid="$(tr -d '[:space:]' < "$run_dir/pid")"
        if [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null; then
            status="running"
        else
            status="stale"
            exit_code="255"
        fi
    elif [[ -d "$run_dir" ]]; then
        status="stale"
        exit_code="255"
    fi

    printf '%s|%s\n' "$status" "$exit_code"
}

emit_status() {
    local run_dir="$STATE_DIR/$RUN_ID"
    local status_line status exit_code line_count=0

    status_line="$(run_status "$run_dir")"
    status="${status_line%%|*}"
    exit_code="${status_line#*|}"
    if [[ -f "$run_dir/output.log" ]]; then
        line_count="$(wc -l < "$run_dir/output.log" | tr -d '[:space:]')"
    fi

    printf 'FH_DEPLOY_JOB_STATUS_V1|%s|%s|%s|%s|%s\n' \
        "$RUN_ID" "$status" "$exit_code" "$line_count" "$run_dir/output.log"
    if (( line_count > FROM_LINE )); then
        sed -n "$((FROM_LINE + 1)),${line_count}p" "$run_dir/output.log"
    fi
}

start_job() {
    local run_dir="$STATE_DIR/$RUN_ID"
    local lock_dir="$STATE_DIR/.${RUN_ID}.lock"
    local existing_status archive_suffix

    [[ "$WORKER_REVISION" =~ ^[0-9a-f]{40}$ ]] \
        || fail "A full 40-character worker revision is required."
    ((${#WORKER_ARGS[@]} > 0)) || fail "Deploy worker arguments are required."

    cd "$PROJECT_DIR"
    git cat-file -e "${WORKER_REVISION}^{commit}" \
        || fail "Worker revision does not exist: $WORKER_REVISION"
    git merge-base --is-ancestor "$WORKER_REVISION" origin/main \
        || fail "Worker revision is not part of origin/main: $WORKER_REVISION"

    mkdir -p "$STATE_DIR"
    chmod 700 "$STATE_DIR" 2>/dev/null || true
    if ! mkdir "$lock_dir" 2>/dev/null; then
        sleep 1
        emit_status
        return
    fi
    START_LOCK_DIR="$lock_dir"
    # RETURN handles normal reattach paths; EXIT also releases the lock when a
    # validation or filesystem error calls fail() after the lock was acquired.
    trap cleanup_start_lock RETURN EXIT

    existing_status="$(run_status "$run_dir")"
    existing_status="${existing_status%%|*}"
    case "$existing_status" in
        running|succeeded)
            emit_status
            return
            ;;
        failed|stale)
            if [[ "$RESTART_FAILED" != true ]]; then
                emit_status
                return
            fi
            archive_suffix="$(date -u +%Y%m%d_%H%M%S)"
            mv -- "$run_dir" "${run_dir}.failed-${archive_suffix}"
            ;;
    esac

    mkdir "$run_dir"
    chmod 700 "$run_dir"
    printf '%s\n' "$WORKER_REVISION" > "$run_dir/revision"
    git show "${WORKER_REVISION}:scripts/deploy.sh" > "$run_dir/worker.sh"
    awk 'NR == 2 { compatible = ($0 == "# FILAMENTHUB_DEPLOY_PROTOCOL=2") } END { exit !compatible }' \
        "$run_dir/worker.sh" \
        || fail "Worker revision uses an incompatible deploy protocol."
    chmod 700 "$run_dir/worker.sh"

    cat > "$run_dir/launcher.sh" <<'EOF'
#!/usr/bin/env bash
set +e
project_dir="$1"
worker="$2"
exit_file="$3"
shift 3
cd "$project_dir" || exit 254
PROJECT_DIR="$project_dir" bash "$worker" "$@"
exit_code=$?
printf '%s\n' "$exit_code" > "${exit_file}.tmp"
mv -- "${exit_file}.tmp" "$exit_file"
exit "$exit_code"
EOF
    chmod 700 "$run_dir/launcher.sh"
    : > "$run_dir/output.log"
    chmod 600 "$run_dir/output.log"

    nohup "$run_dir/launcher.sh" \
        "$PROJECT_DIR" "$run_dir/worker.sh" "$run_dir/exit-code" \
        "${WORKER_ARGS[@]}" \
        > "$run_dir/output.log" 2>&1 </dev/null &
    printf '%s\n' "$!" > "$run_dir/pid"
    sleep 1
    emit_status
}

while (($# > 0)); do
    case "$1" in
        --start)
            ACTION="start"
            shift
            ;;
        --status)
            ACTION="status"
            shift
            ;;
        --run-id)
            [[ $# -ge 2 ]] || fail "--run-id requires a value"
            RUN_ID="$2"
            shift 2
            ;;
        --worker-revision)
            [[ $# -ge 2 ]] || fail "--worker-revision requires a value"
            WORKER_REVISION="$2"
            shift 2
            ;;
        --from-line)
            [[ $# -ge 2 ]] || fail "--from-line requires a value"
            FROM_LINE="$2"
            shift 2
            ;;
        --restart-failed)
            RESTART_FAILED=true
            shift
            ;;
        --)
            shift
            WORKER_ARGS=("$@")
            break
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

[[ -n "$ACTION" ]] || fail "Choose --start or --status."
[[ -n "$RUN_ID" ]] || fail "--run-id is required."
[[ "$FROM_LINE" =~ ^[0-9]+$ ]] || fail "--from-line must be a non-negative integer."
validate_run_id
mkdir -p "$STATE_DIR"

case "$ACTION" in
    start) start_job ;;
    status) emit_status ;;
esac
