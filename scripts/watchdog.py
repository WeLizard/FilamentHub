#!/usr/bin/env python3
"""Watch production from the outside and say something when it stops answering.

Runs on the old home machine, not on the server it watches: a server cannot
report its own death, and a check from the same network cannot tell a broken
site from a broken route to it.

Checks the site, the API, the OrcaSlicer embed contract, how long the
certificate has left and whether last night's backup arrived. Given a way in,
it also asks the watched machine how
much memory and disk it has left — those are the failures worth hearing about
before they become an outage rather than after. Notifies through Telegram,
which stays reachable when our own infrastructure does not.

Reports only changes — a service that says "still fine" every five minutes is
a service nobody reads. A certificate running out is repeated once a day,
because that one needs nagging.

    BOT_TOKEN=... CHAT_ID=... python scripts/watchdog.py
"""

from __future__ import annotations

import json
import os
import re
import socket
import ssl
import subprocess
import sys
import tempfile
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
EMBED_BODY_LIMIT = 128 * 1024
EMBED_FRAME_ANCESTORS = frozenset(
    {
        "'self'",
        "file:",
        "http://127.0.0.1:*",
        "http://localhost:*",
    }
)

# The machine being watched, as ssh would address it, and the key to reach it
# with. Left unset, the two checks that need to look inside are skipped.
SERVER = os.environ.get("WATCHDOG_SERVER", "")
SERVER_KEY = os.environ.get("WATCHDOG_SERVER_KEY", "")
SERVER_PROBE_COMMAND = os.environ.get(
    "WATCHDOG_SERVER_PROBE_COMMAND", "filamenthub-watchdog-probe"
)
# Hashing a password claims 64 MiB for as long as it runs, and four workers can
# be doing that at once, so the floor has to leave room for a crowd.
MEMORY_WARN_MIB = 600
DISK_WARN_PERCENT = 85


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


def _ask_server(command: str) -> str | None:
    """Run a read-only command on the watched machine, or None if it stays silent."""
    if not SERVER:
        return None

    ssh = ["ssh", "-o", "BatchMode=yes", "-o", f"ConnectTimeout={TIMEOUT}"]
    if SERVER_KEY:
        ssh += ["-i", SERVER_KEY]

    try:
        result = subprocess.run(
            [*ssh, SERVER, command],
            capture_output=True,
            text=True,
            timeout=TIMEOUT + 10,
        )
    except Exception:  # noqa: BLE001 — an unreachable machine is the answer
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def read_server_probe() -> dict[str, object] | None:
    if not SERVER:
        return None
    answer = _ask_server(SERVER_PROBE_COMMAND)
    if answer is None:
        return None
    try:
        payload = json.loads(answer)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(payload, dict) or payload.get("version") != 1:
        return None
    return payload


def check_memory(probe: dict[str, object]) -> str | None:
    available = probe.get("memory_available_mib")
    if not isinstance(available, int):
        return "сервер ответил непонятно"
    if available < MEMORY_WARN_MIB:
        return f"свободно всего {available} МБ"
    return None


def check_embed() -> str | None:
    """Verify the public Orca iframe entry point and its framing contract."""
    url = f"{SITE.rstrip('/')}/embed/catalog"
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as response:
            if response.status != 200:
                return f"Orca embed отвечает кодом {response.status}"
            content_type = response.headers.get("Content-Type", "").lower()
            x_frame_options = response.headers.get("X-Frame-Options")
            csp = response.headers.get("Content-Security-Policy")
            body = response.read(EMBED_BODY_LIMIT + 1)
    except urllib.error.HTTPError as exc:
        return f"Orca embed отвечает кодом {exc.code}"
    except Exception as exc:  # noqa: BLE001
        return f"Orca embed недоступен: {type(exc).__name__}"

    if "text/html" not in content_type:
        return f"Orca embed вернул не HTML ({content_type or 'без Content-Type'})"
    if len(body) > EMBED_BODY_LIMIT or not re.search(
        br"\bid\s*=\s*['\"]root['\"]",
        body,
    ):
        return "Orca embed не содержит корневой маркер приложения"
    if x_frame_options is not None:
        return f"Orca embed содержит запрещённый X-Frame-Options: {x_frame_options!r}"
    if not csp:
        return "Orca embed не содержит Content-Security-Policy"

    frame_ancestors = []
    for directive in csp.split(";"):
        parts = directive.split()
        if parts and parts[0].lower() == "frame-ancestors":
            frame_ancestors.append(parts[1:])

    if len(frame_ancestors) != 1:
        return "Orca embed должен содержать ровно одну директиву frame-ancestors"
    sources = frame_ancestors[0]
    if len(sources) != len(EMBED_FRAME_ANCESTORS) or set(sources) != EMBED_FRAME_ANCESTORS:
        return f"Orca embed содержит недопустимый frame-ancestors: {' '.join(sources) or '<empty>'}"
    return None


def check_disk(probe: dict[str, object]) -> str | None:
    used = probe.get("disk_used_percent")
    if not isinstance(used, int):
        return "сервер ответил непонятно"
    if used >= DISK_WARN_PERCENT:
        return f"занято {used}%"
    return None


def check_ssh_policy(probe: dict[str, object]) -> str | None:
    policy = probe.get("ssh_policy")
    if not isinstance(policy, dict):
        return "не удалось проверить эффективные настройки"

    problems = []
    if policy.get("passwordauthentication") != "no":
        problems.append("разрешён вход по паролю")
    if policy.get("permitrootlogin") != "no":
        problems.append("разрешён вход root")
    if policy.get("pubkeyauthentication") != "yes":
        problems.append("отключены SSH-ключи")
    return "; ".join(problems) or None


BASE_CHECKS = {
    "сайт": check_site,
    "API": check_api,
    "Orca embed": check_embed,
    "сертификат": check_certificate,
    "резервные копии": check_backup,
}


def collect_checks(probe: dict[str, object] | None) -> dict[str, str | None]:
    checks = {name: check() for name, check in BASE_CHECKS.items()}
    if not SERVER:
        return checks
    if probe is None:
        checks["серверный probe"] = "не удалось получить безопасный снимок"
        return checks
    checks["серверный probe"] = None
    checks["память"] = check_memory(probe)
    checks["диск"] = check_disk(probe)
    checks["SSH-политика"] = check_ssh_policy(probe)
    if probe.get("reboot_required") is True:
        checks["перезагрузка ОС"] = "установлено новое ядро, требуется перезагрузка"
    else:
        checks["перезагрузка ОС"] = None
    return checks


def security_events(probe: dict[str, object] | None) -> list[dict[str, str]]:
    if probe is None:
        return []
    raw_events = probe.get("ssh_security_events")
    if not isinstance(raw_events, list):
        return []
    events = []
    for item in raw_events:
        if not isinstance(item, dict):
            continue
        event_id = item.get("id")
        description = item.get("description")
        if isinstance(event_id, str) and isinstance(description, str):
            events.append({"id": event_id, "description": description})
    return events


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


def save_state(state: dict[str, object]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=STATE_FILE.parent,
        prefix=f".{STATE_FILE.name}.",
        text=True,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(state, handle, ensure_ascii=False)
        os.chmod(temporary, 0o600)
        os.replace(temporary, STATE_FILE)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    previous = load_state()
    today = datetime.now(timezone.utc).date().isoformat()
    state: dict[str, object] = {}
    failing = []
    probe = read_server_probe()

    for name, problem in collect_checks(probe).items():
        state[name] = problem or "ok"
        was = previous.get(name, "ok")
        if problem:
            failing.append(f"{name}: {problem}")
            # A new problem, a changed one, or a standing one worth a daily nudge.
            if was == "ok" or was != problem or previous.get("_day") != today:
                notify(f"FilamentHub — {name}: {problem}")
        elif was != "ok":
            notify(f"FilamentHub — {name}: снова в порядке")

    previous_event_ids = previous.get("_ssh_security_event_ids", [])
    if not isinstance(previous_event_ids, list):
        previous_event_ids = []
    known_event_ids = {event_id for event_id in previous_event_ids if isinstance(event_id, str)}
    current_events = security_events(probe)
    for event in current_events:
        if event["id"] not in known_event_ids:
            notify(f"FilamentHub — опасный SSH-вход: {event['description']}")
    state["_ssh_security_event_ids"] = list(
        dict.fromkeys([*previous_event_ids, *(event["id"] for event in current_events)])
    )[-512:]

    state["_day"] = today
    save_state(state)

    print("; ".join(failing) if failing else "всё в порядке")
    return 1 if failing else 0


if __name__ == "__main__":
    raise SystemExit(main())
