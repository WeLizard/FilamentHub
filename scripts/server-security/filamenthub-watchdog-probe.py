#!/usr/bin/env python3
"""Return a bounded, non-sensitive production security snapshot as JSON."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

SSH_EVENT = re.compile(
    r"^Accepted (?P<method>\S+) for (?P<user>\S+) from (?P<source>\S+) port \d+"
)
SSH_POLICY_KEYS = {
    "passwordauthentication",
    "permitrootlogin",
    "pubkeyauthentication",
}


def memory_available_mib() -> int:
    for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) // 1024
    raise RuntimeError("MemAvailable is missing from /proc/meminfo")


def disk_used_percent() -> int:
    usage = shutil.disk_usage("/")
    return round(usage.used * 100 / usage.total)


def ssh_policy() -> dict[str, str]:
    result = subprocess.run(
        ["/usr/sbin/sshd", "-T"],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    policy: dict[str, str] = {}
    for line in result.stdout.splitlines():
        key, _, value = line.partition(" ")
        if key in SSH_POLICY_KEYS:
            policy[key] = value.strip()
    if policy.keys() != SSH_POLICY_KEYS:
        raise RuntimeError("sshd did not return every required policy key")
    return policy


def ssh_security_events() -> list[dict[str, str]]:
    result = subprocess.run(
        [
            "/usr/bin/journalctl",
            "-u",
            "ssh",
            "--since=-7 days",
            "--no-pager",
            "--output=json",
            "--grep=^Accepted (password for|[^ ]+ for root from)",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    if result.returncode not in (0, 1):
        raise RuntimeError(f"journalctl failed with exit code {result.returncode}")
    events = []
    for line in result.stdout.splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        message = entry.get("MESSAGE")
        timestamp = entry.get("__REALTIME_TIMESTAMP")
        if not isinstance(message, str) or not isinstance(timestamp, str):
            continue
        match = SSH_EVENT.match(message)
        if match is None:
            continue
        event_id = hashlib.sha256(f"{timestamp}\0{message}".encode()).hexdigest()
        occurred_at = datetime.fromtimestamp(
            int(timestamp) / 1_000_000,
            tz=timezone.utc,
        ).isoformat(timespec="seconds")
        events.append(
            {
                "id": event_id,
                "description": (
                    f"{match.group('method')} для {match.group('user')} "
                    f"с {match.group('source')} в {occurred_at}"
                ),
            }
        )
    return events[-100:]


def main() -> int:
    payload = {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "memory_available_mib": memory_available_mib(),
        "disk_used_percent": disk_used_percent(),
        "reboot_required": Path("/var/run/reboot-required").exists(),
        "ssh_policy": ssh_policy(),
        "ssh_security_events": ssh_security_events(),
    }
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
