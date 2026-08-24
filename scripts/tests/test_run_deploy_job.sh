#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TEMP_ROOT="$(mktemp -d)"
trap 'rm -rf "$TEMP_ROOT"' EXIT

REPOSITORY="$TEMP_ROOT/repository"
STATE_HOME="$TEMP_ROOT/state"
mkdir -p "$REPOSITORY/scripts"

cat > "$REPOSITORY/scripts/deploy.sh" <<'EOF'
#!/usr/bin/env bash
# FILAMENTHUB_DEPLOY_PROTOCOL=2
set -Eeuo pipefail
printf 'fixture deploy started\n'
sleep 2
printf 'fixture deploy completed\n'
EOF

git -C "$REPOSITORY" init -q
git -C "$REPOSITORY" config user.email test@filamenthub.invalid
git -C "$REPOSITORY" config user.name FilamentHubTest
git -C "$REPOSITORY" add scripts/deploy.sh
git -C "$REPOSITORY" commit -qm fixture
REVISION="$(git -C "$REPOSITORY" rev-parse HEAD)"
git -C "$REPOSITORY" update-ref refs/remotes/origin/main "$REVISION"
RUN_ID="deploy-$REVISION"

start_output="$(
    PROJECT_DIR="$REPOSITORY" XDG_STATE_HOME="$STATE_HOME" \
        bash "$ROOT/scripts/run-deploy-job.sh" \
        --start --run-id "$RUN_ID" --worker-revision "$REVISION" \
        -- --revision "$REVISION" --yes
)"
grep -q "FH_DEPLOY_JOB_STATUS_V1|$RUN_ID|running|-|" <<< "$start_output"

deadline=$((SECONDS + 15))
status_output=""
while ((SECONDS < deadline)); do
    status_output="$(
        PROJECT_DIR="$REPOSITORY" XDG_STATE_HOME="$STATE_HOME" \
            bash "$ROOT/scripts/run-deploy-job.sh" \
            --status --run-id "$RUN_ID" --from-line 0
    )"
    if grep -q "FH_DEPLOY_JOB_STATUS_V1|$RUN_ID|succeeded|0|" <<< "$status_output"; then
        break
    fi
    sleep 1
done

grep -q "FH_DEPLOY_JOB_STATUS_V1|$RUN_ID|succeeded|0|" <<< "$status_output"
grep -q "fixture deploy started" <<< "$status_output"
grep -q "fixture deploy completed" <<< "$status_output"

reattach_output="$(
    PROJECT_DIR="$REPOSITORY" XDG_STATE_HOME="$STATE_HOME" \
        bash "$ROOT/scripts/run-deploy-job.sh" \
        --start --run-id "$RUN_ID" --worker-revision "$REVISION" \
        -- --revision "$REVISION" --yes
)"
grep -q "FH_DEPLOY_JOB_STATUS_V1|$RUN_ID|succeeded|0|" <<< "$reattach_output"

LOG_FILE="$STATE_HOME/filamenthub/deploys/$RUN_ID/output.log"
[[ "$(grep -c '^fixture deploy started$' "$LOG_FILE")" -eq 1 ]]
