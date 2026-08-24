#!/usr/bin/env bash
set -Eeuo pipefail

readonly CONFIG_TARGET="/etc/fail2ban/jail.d/filamenthub-sshd.local"

fail() {
    echo "ERROR: $*" >&2
    exit 1
}

[[ ${EUID:-$(id -u)} -eq 0 ]] || fail "Run this script through sudo."

effective="$(sshd -T)"
grep -qx 'passwordauthentication no' <<< "$effective" \
    || fail "Disable SSH password authentication before installing Fail2ban."
grep -qx 'permitrootlogin no' <<< "$effective" \
    || fail "Disable SSH root login before installing Fail2ban."
grep -qx 'pubkeyauthentication yes' <<< "$effective" \
    || fail "Public-key authentication must remain enabled."

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends fail2ban

temporary="$(mktemp)"
trap 'rm -f -- "$temporary"' EXIT
cat > "$temporary" <<'EOF'
[DEFAULT]
backend = systemd
banaction = nftables-multiport
bantime = 1h
findtime = 10m
maxretry = 5
bantime.increment = true
bantime.factor = 2
bantime.maxtime = 7d

[sshd]
enabled = true
mode = normal
port = ssh
EOF

install -d -o root -g root -m 0755 /etc/fail2ban/jail.d
install -o root -g root -m 0644 "$temporary" "$CONFIG_TARGET"

fail2ban-client -t
systemctl enable --now fail2ban
systemctl restart fail2ban
systemctl is-active --quiet fail2ban || fail "fail2ban.service is not active."
fail2ban-client status sshd | grep -q 'Jail list\|Currently failed\|File list' \
    || fail "The sshd jail did not return a valid status."

echo "Fail2ban sshd jail is active with bounded incremental bans."
fail2ban-client status sshd
