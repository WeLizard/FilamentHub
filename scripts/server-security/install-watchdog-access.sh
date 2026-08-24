#!/usr/bin/env bash
set -Eeuo pipefail

readonly WATCHDOG_USER="filamenthub-watchdog"
readonly WATCHDOG_HOME="/var/lib/filamenthub-watchdog"
readonly PROBE_TARGET="/usr/local/sbin/filamenthub-watchdog-probe"
readonly SUDOERS_TARGET="/etc/sudoers.d/filamenthub-watchdog"

usage() {
    echo "Usage: sudo bash scripts/server-security/install-watchdog-access.sh --public-key-file PATH" >&2
}

fail() {
    echo "ERROR: $*" >&2
    exit 1
}

[[ ${EUID:-$(id -u)} -eq 0 ]] || fail "Run this script through sudo."

public_key_file=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --public-key-file)
            [[ $# -ge 2 ]] || fail "--public-key-file requires a path."
            public_key_file="$2"
            shift 2
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

[[ -n "$public_key_file" ]] || {
    usage
    fail "A dedicated watchdog public key is required."
}
[[ -f "$public_key_file" ]] || fail "Public key file does not exist: $public_key_file"

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
probe_source="$script_dir/filamenthub-watchdog-probe.py"
[[ -f "$probe_source" ]] || fail "Probe source is missing: $probe_source"

public_key="$(tr -d '\r\n' < "$public_key_file")"
[[ "$public_key" == ssh-ed25519\ * ]] || fail "The watchdog key must be an Ed25519 public key."
ssh-keygen -lf "$public_key_file" >/dev/null || fail "Invalid SSH public key."

if ! id "$WATCHDOG_USER" >/dev/null 2>&1; then
    useradd \
        --system \
        --create-home \
        --home-dir "$WATCHDOG_HOME" \
        --shell /bin/bash \
        "$WATCHDOG_USER"
fi
passwd --lock "$WATCHDOG_USER" >/dev/null

install -o root -g root -m 0755 "$probe_source" "$PROBE_TARGET"

install -d -o root -g root -m 0755 "$WATCHDOG_HOME"
install -d -o root -g root -m 0700 "$WATCHDOG_HOME/.ssh"
authorized_key="restrict,command=\"/usr/bin/sudo -n $PROBE_TARGET\" $public_key"
authorized_keys_temp="$(mktemp)"
sudoers_temp="$(mktemp)"
trap 'rm -f -- "$authorized_keys_temp" "$sudoers_temp"' EXIT
printf '%s\n' "$authorized_key" > "$authorized_keys_temp"
install -o root -g root -m 0600 "$authorized_keys_temp" "$WATCHDOG_HOME/.ssh/authorized_keys"

printf '%s ALL=(root) NOPASSWD: %s\n' "$WATCHDOG_USER" "$PROBE_TARGET" > "$sudoers_temp"
visudo -cf "$sudoers_temp" >/dev/null
install -o root -g root -m 0440 "$sudoers_temp" "$SUDOERS_TARGET"
visudo -cf "$SUDOERS_TARGET" >/dev/null

probe_output="$(sudo -u "$WATCHDOG_USER" sudo -n "$PROBE_TARGET")"
python3 -c 'import json,sys; data=json.load(sys.stdin); assert data["version"] == 1' <<< "$probe_output"

echo "Restricted watchdog access installed."
echo "Key fingerprint: $(ssh-keygen -lf "$public_key_file" | awk '{print $2}')"
echo "Test this key from the home server before changing sshd policy."
