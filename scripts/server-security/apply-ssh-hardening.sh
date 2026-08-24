#!/usr/bin/env bash
set -Eeuo pipefail

readonly CONFIG_TARGET="/etc/ssh/sshd_config.d/00-filamenthub-hardening.conf"
readonly WATCHDOG_KEYS="/var/lib/filamenthub-watchdog/.ssh/authorized_keys"

usage() {
    cat >&2 <<'EOF'
Usage:
  sudo --preserve-env=SSH_CONNECTION bash scripts/server-security/apply-ssh-hardening.sh \
    --confirmed-lizard-key-session \
    --confirmed-watchdog-key-session

Keep the current SSH session open. Both confirmations must describe separate,
already tested SSH sessions.
EOF
}

fail() {
    echo "ERROR: $*" >&2
    exit 1
}

[[ ${EUID:-$(id -u)} -eq 0 ]] || fail "Run this script through sudo."

confirmed_lizard=false
confirmed_watchdog=false
while [[ $# -gt 0 ]]; do
    case "$1" in
        --confirmed-lizard-key-session)
            confirmed_lizard=true
            shift
            ;;
        --confirmed-watchdog-key-session)
            confirmed_watchdog=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            usage
            fail "Unknown argument: $1"
            ;;
    esac
done

[[ "$confirmed_lizard" == true ]] || fail "Verify a separate lizard key session first."
[[ "$confirmed_watchdog" == true ]] || fail "Verify the restricted watchdog key first."
[[ -n "${SSH_CONNECTION:-}" ]] || fail "Run from an existing SSH session, not an unattended job."
[[ -s "$WATCHDOG_KEYS" ]] || fail "Restricted watchdog access is not installed."
systemctl is-active --quiet ssh || fail "ssh.service is not active."

temporary="$(mktemp)"
backup=""
cleanup() {
    rm -f -- "$temporary"
}
trap cleanup EXIT

cat > "$temporary" <<'EOF'
# FilamentHub production SSH policy. OpenSSH uses the first value it reads,
# therefore this file intentionally sorts before cloud-init's 50-*.conf.
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
PubkeyAuthentication yes
MaxAuthTries 3
LoginGraceTime 30
X11Forwarding no
AllowUsers lizard filamenthub-watchdog
EOF

if [[ -e "$CONFIG_TARGET" ]]; then
    backup="${CONFIG_TARGET}.backup.$(date -u +%Y%m%dT%H%M%SZ)"
    cp --preserve=mode,ownership,timestamps -- "$CONFIG_TARGET" "$backup"
fi
install -o root -g root -m 0644 "$temporary" "$CONFIG_TARGET"

rollback_config() {
    if [[ -n "$backup" ]]; then
        cp --preserve=mode,ownership,timestamps -- "$backup" "$CONFIG_TARGET"
    else
        rm -f -- "$CONFIG_TARGET"
    fi
}

if ! sshd -t; then
    rollback_config
    fail "sshd rejected the hardening file; the previous configuration was restored."
fi

effective="$(sshd -T)"
grep -qx 'passwordauthentication no' <<< "$effective" || {
    rollback_config
    fail "PasswordAuthentication is not effectively disabled."
}
grep -qx 'permitrootlogin no' <<< "$effective" || {
    rollback_config
    fail "PermitRootLogin is not effectively disabled."
}
grep -qx 'pubkeyauthentication yes' <<< "$effective" || {
    rollback_config
    fail "Public-key authentication is not effectively enabled."
}
effective_users="$(
    awk '$1 == "allowusers" { for (i = 2; i <= NF; i++) print $i }' <<< "$effective" |
        LC_ALL=C sort -u
)"
[[ "$effective_users" == $'filamenthub-watchdog\nlizard' ]] || {
    rollback_config
    fail "AllowUsers does not match the intended accounts."
}

if ! systemctl reload ssh || ! systemctl is-active --quiet ssh; then
    rollback_config
    sshd -t
    systemctl reload ssh || true
    fail "ssh.service did not accept the reload; the previous configuration was restored."
fi

echo "SSH policy reloaded without terminating existing sessions."
echo "Do not close this session yet. Open another lizard key session and re-test the watchdog key."
echo "Then verify that password and root SSH authentication are rejected."
