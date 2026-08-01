#!/usr/bin/env python3
"""Watch production from the outside and say something when it stops answering.

Runs on the old home machine, not on the server it watches: a server cannot
report its own death, and a check from the same network cannot tell a broken
site from a broken route to it.

Checks the site, the API, how long the certificate has left and whether last
night's backup arrived. Notifies through Telegram, which stays reachable when
our own infrastructure does not.

Reports only changes — a service that says "still fine" every five minutes is
a service nobody reads. A certificate running out is repeated once a day,
because that one needs nagging.

    BOT_TOKEN=... CHAT_ID=... python scripts/watchdog.py
"""

from __future__ import annotations

import json
import os
import socket
import ssl
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

SITE = os.environ.get("WATCHDOG_SITE", "https://filamenthub.ru")
BACKUP_DIR = Path(os.environ.get("WATCHDOG_BACKUP_DIR", "/home/lizard/fh-backups"))
STATE_FILE = Path(os.environ.get("WATCHDOG_STATE", "/home/lizard/watchdog-state.json"))
BACKUP_MAX_AGE = timedelta(hours=36)
CERT_WARN_DAYS = 14
TIMEOUT = 20


def check_site() -> str | None:
    try:
        with urllib.request.urlopen(SITE, timeout=TIMEOUT) as response:
            if response.status != 200:
                return f"сайт отвечает кодом {response.status}"
    except Exception as exc:  # noqa: BLE001 — any failure is the answer
        return f"сайт недоступен: {type(exc).__name__}"
    return None


def check_api() -> str | None:
    try:
        with urllib.request.urlopen(f"{SITE}/health", timeout=TIMEOUT) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        return f"API не отвечает: {type(exc).__name__}"
    if payload.get("status") != "ok":
        return f"API отвечает статусом {payload.get('status')!r}"
    if payload.get("maintenance_mode"):
        return "включён режим обслуживания"
    return None


def check_certificate() -> str | None:
    host = urllib.parse.urlparse(SITE).hostname or ""
    try:
        context = ssl.create_default_context()
        with socket.create_connection((host, 443), timeout=TIMEOUT) as raw:
            with context.wrap_socket(raw, server_hostname=host) as tls:
                not_after = tls.getpeercert()["notAfter"]
    except Exception as exc:  # noqa: BLE001
        return f"сертификат не проверить: {type(exc).__name__}"

    expires = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
    days_left = (expires - datetime.now(timezone.utc)).days
    if days_left <= CERT_WARN_DAYS:
        return f"сертификату осталось {days_left} дн."
    return None


def check_backup() -> str | None:
    if not BACKUP_DIR.is_dir():
        return f"каталог копий не найден: {BACKUP_DIR}"
    copies = sorted(BACKUP_DIR.glob("backup_*.sql.gz.gpg"), key=lambda p: p.stat().st_mtime)
    if not copies:
        return "резервных копий нет"
    newest = datetime.fromtimestamp(copies[-1].stat().st_mtime, tz=timezone.utc)
    age = datetime.now(timezone.utc) - newest
    if age > BACKUP_MAX_AGE:
        return f"последняя копия старше {int(age.total_seconds() // 3600)} ч."
    return None


CHECKS = {
    "сайт": check_site,
    "API": check_api,
    "сертификат": check_certificate,
    "резервные копии": check_backup,
}


def notify(text: str) -> None:
    token, chat = os.environ.get("BOT_TOKEN"), os.environ.get("CHAT_ID")
    if not token or not chat:
        print(f"[без Telegram] {text}")
        return

    # Telegram is not reachable directly from here, so the request goes through
    # the same proxy the other bot on this machine uses. curl speaks SOCKS5
    # without extra packages, and its options arrive on stdin so the token never
    # appears in the process list.
    proxy = os.environ.get("TELEGRAM_PROXY_URL") or os.environ.get("TELEGRAM_PROXY")
    options = [
        f'url = "https://api.telegram.org/bot{token}/sendMessage"',
        f'data-urlencode = "chat_id={chat}"',
        f'data-urlencode = "text={text}"',
        f"max-time = {TIMEOUT}",
        "silent",
        "show-error",
    ]
    if proxy:
        options.append(f'proxy = "{proxy}"')

    try:
        result = subprocess.run(
            ["curl", "--config", "-"],
            input="\n".join(options),
            capture_output=True,
            text=True,
            timeout=TIMEOUT + 10,
        )
        if result.returncode != 0:
            print(f"не удалось отправить в Telegram: {result.stderr.strip()}", file=sys.stderr)
    except Exception as exc:  # noqa: BLE001
        print(f"не удалось отправить в Telegram: {exc}", file=sys.stderr)


def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — a missing or broken state file is a fresh start
        return {}


def main() -> int:
    previous = load_state()
    today = datetime.now(timezone.utc).date().isoformat()
    state: dict[str, str] = {}
    failing = []

    for name, check in CHECKS.items():
        problem = check()
        state[name] = problem or "ok"
        was = previous.get(name, "ok")
        if problem:
            failing.append(f"{name}: {problem}")
            # A new problem, a changed one, or a standing one worth a daily nudge.
            if was == "ok" or was != problem or previous.get("_day") != today:
                notify(f"FilamentHub — {name}: {problem}")
        elif was != "ok":
            notify(f"FilamentHub — {name}: снова в порядке")

    state["_day"] = today
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

    print("; ".join(failing) if failing else "всё в порядке")
    return 1 if failing else 0


if __name__ == "__main__":
    raise SystemExit(main())
