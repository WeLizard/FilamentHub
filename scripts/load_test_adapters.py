#!/usr/bin/env python3
"""Rehearse real adapter traffic against the local development stack.

The script uses the same public pairing, heartbeat and snapshot endpoints as
the OctoPrint and Bambu adapters.  It never targets a remote host and never
cleans up the devices it creates: the resulting printers and material systems
remain useful development data.

Prepare credentials (after ``seed_dev_accounts.py`` has created users):

    python scripts/load_test_adapters.py prepare --devices 100

Run the ordinary, jittered steady-state pattern:

    python scripts/load_test_adapters.py run --duration 600 --ramp 120

Rehearse many adapters returning after an outage, then deliberately exceed the
per-credential limit to prove that a broken adapter is contained:

    python scripts/load_test_adapters.py run --mode reconnect --ramp 30
    python scripts/load_test_adapters.py run --mode storm --duration 45

Credentials contain live *development* bridge tokens.  They are stored in the
OS temporary directory by default, written owner-only where the platform
supports it, and are never printed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import stat
import sys
import tempfile
import time
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import httpx

from load_common import Recorder, pretend_address, refuse_if_not_local

DEFAULT_BASE_URL = "http://localhost:8001"
DEFAULT_CREDENTIALS = Path(tempfile.gettempdir()) / "filamenthub-adapter-load.json"
PASSWORD = "qwerty123"
EMAIL_PREFIX = "established"
HEARTBEAT_SECONDS = 120.0

AdapterKind = Literal["octoprint", "bambu"]


@dataclass(frozen=True)
class AdapterCredential:
    kind: AdapterKind
    bridge_token: str
    instance_id: str
    physical_printer_id: int
    material_system_id: int

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "AdapterCredential":
        return cls(
            kind=payload["kind"],
            bridge_token=str(payload["bridge_token"]),
            instance_id=str(payload["instance_id"]),
            physical_printer_id=int(payload["physical_printer_id"]),
            material_system_id=int(payload["material_system_id"]),
        )


class AdapterRecorder(Recorder):
    def __init__(self) -> None:
        super().__init__()
        self.statuses: Counter[tuple[str, int]] = Counter()
        self.expected_limits = 0

    def report(self) -> None:
        super().report()
        if self.statuses:
            print("\nHTTP-статусы:")
            for (step, status_code), count in sorted(self.statuses.items()):
                print(f"  {step:<30} {status_code}: {count}")
        if self.expected_limits:
            print(
                f"\nожидаемых 429 в режиме storm: {self.expected_limits} "
                "(это подтверждённое ограничение неисправного адаптера)"
            )


def _write_credentials(path: Path, base_url: str, devices: list[AdapterCredential]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "base_url": base_url.rstrip("/"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "devices": [device.__dict__ for device in devices],
    }
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(temporary, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    temporary.replace(path)


def _read_credentials(path: Path, base_url: str) -> list[AdapterCredential]:
    if not path.exists():
        raise SystemExit(
            f"Нет {path}. Сначала подготовьте подключения:\n"
            f"  python scripts/load_test_adapters.py prepare --credentials {path}"
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("version") != 1:
        raise SystemExit(f"Неподдерживаемая версия файла подключений: {path}")
    prepared_for = str(payload.get("base_url", "")).rstrip("/")
    if prepared_for != base_url.rstrip("/"):
        raise SystemExit(
            f"Подключения подготовлены для {prepared_for}, а запрошен {base_url}. "
            "Токены между dev-стендами не переносим."
        )
    devices = [AdapterCredential.from_dict(item) for item in payload.get("devices", [])]
    if not devices:
        raise SystemExit(f"В {path} нет подключений")
    return devices


async def _known_accounts(wanted: int) -> list[str]:
    import asyncpg

    connection = await asyncpg.connect(
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=int(os.environ.get("POSTGRES_PORT", "5433")),
        user=os.environ.get("POSTGRES_USER", "filamenthub"),
        password=os.environ.get("POSTGRES_PASSWORD", "devpass123"),
        database=os.environ.get("POSTGRES_DB", "filamenthub_dev"),
    )
    try:
        rows = await connection.fetch(
            "SELECT email FROM users WHERE email LIKE $1 ORDER BY id DESC LIMIT $2",
            f"{EMAIL_PREFIX}-%",
            wanted,
        )
    finally:
        await connection.close()
    return [str(row["email"]) for row in rows]


async def _require_json(response: httpx.Response, operation: str) -> dict[str, Any]:
    if response.status_code >= 400:
        body = response.text[:500]
        raise RuntimeError(f"{operation}: HTTP {response.status_code}: {body}")
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError(f"{operation}: сервер вернул не JSON") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"{operation}: ожидался JSON-объект")
    return payload


async def _prepare_one(
    client: httpx.AsyncClient,
    *,
    kind: AdapterKind,
    email: str,
    index: int,
) -> AdapterCredential:
    client_headers = {"X-FilamentHub-Client-IP": pretend_address(index)}
    login = await _require_json(
        await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": PASSWORD},
            headers=client_headers,
        ),
        "вход",
    )
    owner_headers = {
        **client_headers,
        "Authorization": f"Bearer {login['access_token']}",
    }
    printer = await _require_json(
        await client.post(
            "/api/v1/physical-printers",
            json={"name": f"Adapter load {kind} {index + 1}"},
            headers=owner_headers,
        ),
        "создание физического принтера",
    )
    physical_printer_id = int(printer["id"])
    capabilities = (
        ["read", "write", "presence", "spool_identity", "consumption", "local_command"]
        if kind == "octoprint"
        else ["read", "write", "presence"]
    )
    system = await _require_json(
        await client.post(
            f"/api/v1/physical-printers/{physical_printer_id}/material-systems",
            json={
                "name": "OctoPrint slots" if kind == "octoprint" else "Bambu AMS",
                "kind": "octoprint" if kind == "octoprint" else "bambu_ams",
                "provider": kind,
                "capabilities": capabilities,
                "slot_count": 4,
                "slots": [
                    {"provider_index": slot, "label": str(slot), "kind": "slot"}
                    for slot in range(4)
                ],
            },
            headers=owner_headers,
        ),
        "создание системы подачи",
    )
    created_systems = system.get("material_systems") or []
    if not created_systems:
        raise RuntimeError("создание системы подачи: ответ не содержит material_systems")
    material_system_id = int(created_systems[-1]["id"])

    bridge_prefix = "octoprint-bridge" if kind == "octoprint" else "printer-bridge"
    pairing = await _require_json(
        await client.post(
            f"/api/v1/{bridge_prefix}/connections/"
            f"{physical_printer_id}/{material_system_id}/pairing-code",
            headers=owner_headers,
        ),
        "выпуск кода привязки",
    )
    instance_id = f"load-{kind}-{uuid.uuid4()}"
    pair_payload: dict[str, Any]
    if kind == "octoprint":
        pair_payload = {
            "pairing_code": pairing["pairing_code"],
            "instance_id": instance_id,
            "plugin_version": "load-rehearsal",
            "octoprint_version": "1.11.8",
            "capabilities": capabilities,
        }
    else:
        pair_payload = {
            "pairing_code": pairing["pairing_code"],
            "provider": "bambu",
            "transport": "orca_plugin_lan",
            "source_instance_id": instance_id,
            "plugin_version": "load-rehearsal",
            "capabilities": capabilities,
        }
    paired = await _require_json(
        await client.post(
            f"/api/v1/{bridge_prefix}/pair",
            json=pair_payload,
            headers=client_headers,
        ),
        "привязка адаптера",
    )
    return AdapterCredential(
        kind=kind,
        bridge_token=str(paired["bridge_token"]),
        instance_id=instance_id,
        physical_printer_id=physical_printer_id,
        material_system_id=material_system_id,
    )


async def prepare(args: argparse.Namespace) -> int:
    accounts = await _known_accounts(args.devices)
    if not accounts:
        print(
            "Нет подготовленных dev-пользователей. Сначала:\n"
            f"  python scripts/seed_dev_accounts.py --accounts {args.devices}",
            file=sys.stderr,
        )
        return 1
    if len(accounts) < args.devices:
        print(
            f"Найдено {len(accounts)} пользователей для {args.devices} устройств; "
            "учётные записи будут использоваться повторно."
        )

    devices: list[AdapterCredential] = []
    limits = httpx.Limits(max_connections=args.concurrency, max_keepalive_connections=50)
    async with httpx.AsyncClient(base_url=args.base_url, timeout=60.0, limits=limits) as client:
        semaphore = asyncio.Semaphore(args.concurrency)

        async def make(index: int) -> AdapterCredential:
            async with semaphore:
                kind: AdapterKind = "octoprint" if index % 2 == 0 else "bambu"
                return await _prepare_one(
                    client,
                    kind=kind,
                    email=accounts[index % len(accounts)],
                    index=index,
                )

        for start in range(0, args.devices, args.batch_size):
            batch = await asyncio.gather(
                *(make(index) for index in range(start, min(start + args.batch_size, args.devices)))
            )
            devices.extend(batch)
            _write_credentials(args.credentials, args.base_url, devices)
            print(f"подготовлено подключений: {len(devices)}/{args.devices}")

    print(f"Токены сохранены в {args.credentials}; файл не добавлять в Git.")
    return 0


async def _measured(
    recorder: AdapterRecorder,
    step: str,
    request,
    *,
    storm: bool,
) -> httpx.Response | None:
    started = time.perf_counter()
    try:
        response: httpx.Response = await request
    except Exception as exc:  # noqa: BLE001 -- transport failure is a measured result
        recorder.failed(step, type(exc).__name__)
        return None
    elapsed = time.perf_counter() - started
    recorder.statuses[(step, response.status_code)] += 1
    if response.status_code == 429 and storm:
        recorder.expected_limits += 1
        recorder.ok(f"{step}: limiter", elapsed)
        return response
    if response.status_code >= 400:
        recorder.failed(step, str(response.status_code))
        return None
    recorder.ok(step, elapsed)
    return response


def _adapter_headers(device: AdapterCredential, index: int) -> dict[str, str]:
    return {
        "X-FilamentHub-Bridge-Token": device.bridge_token,
        "X-FilamentHub-Client-IP": pretend_address(index),
    }


async def _octoprint_cycle(
    client: httpx.AsyncClient,
    recorder: AdapterRecorder,
    device: AdapterCredential,
    index: int,
    etag: str | None,
    *,
    storm: bool,
) -> str | None:
    headers = _adapter_headers(device, index)
    heartbeat = await _measured(
        recorder,
        "octoprint heartbeat",
        client.post(
            "/api/v1/octoprint-bridge/heartbeat",
            headers=headers,
            json={
                "instance_id": device.instance_id,
                "plugin_version": "load-rehearsal",
                "octoprint_version": "1.11.8",
                "capabilities": [
                    "read",
                    "write",
                    "presence",
                    "spool_identity",
                    "consumption",
                    "local_command",
                ],
                "active_slot_index": index % 4,
            },
        ),
        storm=storm,
    )
    if heartbeat is None or heartbeat.status_code == 429:
        return etag
    snapshot_headers = dict(headers)
    if etag:
        snapshot_headers["If-None-Match"] = etag
    snapshot = await _measured(
        recorder,
        "octoprint snapshot",
        client.get("/api/v1/octoprint-bridge/snapshot", headers=snapshot_headers),
        storm=storm,
    )
    return snapshot.headers.get("ETag", etag) if snapshot is not None else etag


async def _bambu_cycle(
    client: httpx.AsyncClient,
    recorder: AdapterRecorder,
    device: AdapterCredential,
    index: int,
    cycle: int,
    *,
    storm: bool,
) -> None:
    headers = _adapter_headers(device, index)
    observed_at = datetime.now(timezone.utc).isoformat()
    if cycle == 0:
        await _measured(
            recorder,
            "bambu snapshot",
            client.post(
                "/api/v1/printer-bridge/snapshot",
                headers=headers,
                json={
                    "material_system_id": device.material_system_id,
                    "provider": "bambu",
                    "transport": "orca_plugin_lan",
                    "source_instance_id": device.instance_id,
                    "observed_at": observed_at,
                    "printer": {"state": "idle", "wifi_signal": "-55dBm"},
                    "slots": [
                        {
                            "provider_index": slot,
                            "label": f"AMS {slot + 1}",
                            "kind": "slot",
                            "present": slot < 2,
                            "active_feed": slot == 0,
                            "material": "PLA" if slot < 2 else None,
                            "color_hex": "7C3AED" if slot == 0 else "22D3EE",
                            "remaining_percent": 80 - slot * 10 if slot < 2 else None,
                            "remaining_grams": 800 - slot * 100 if slot < 2 else None,
                        }
                        for slot in range(4)
                    ],
                    "slot_topology_complete": True,
                },
            ),
            storm=storm,
        )
        return
    await _measured(
        recorder,
        "bambu heartbeat",
        client.post(
            "/api/v1/printer-bridge/heartbeat",
            headers=headers,
            json={
                "material_system_id": device.material_system_id,
                "provider": "bambu",
                "transport": "orca_plugin_lan",
                "source_instance_id": device.instance_id,
                "observed_at": observed_at,
            },
        ),
        storm=storm,
    )


async def run(args: argparse.Namespace) -> int:
    devices = _read_credentials(args.credentials, args.base_url)
    if args.devices is not None:
        devices = devices[: args.devices]
    if not devices:
        raise SystemExit("После ограничения --devices не осталось подключений")

    storm = args.mode == "storm"
    interval = args.interval if args.interval is not None else (1.0 if storm else HEARTBEAT_SECONDS)
    duration = args.duration
    if args.mode == "reconnect":
        duration = 0.0

    recorder = AdapterRecorder()
    limits = httpx.Limits(
        max_connections=args.concurrency,
        max_keepalive_connections=min(args.concurrency, 200),
    )
    async with httpx.AsyncClient(base_url=args.base_url, timeout=60.0, limits=limits) as client:
        started = time.perf_counter()
        delay = args.ramp / max(len(devices), 1)

        async def adapter(index: int, device: AdapterCredential) -> None:
            await asyncio.sleep(index * delay + random.uniform(0, min(delay, 0.25)))
            cycle = 0
            etag: str | None = None
            while True:
                if device.kind == "octoprint":
                    etag = await _octoprint_cycle(
                        client, recorder, device, index, etag, storm=storm
                    )
                else:
                    await _bambu_cycle(
                        client, recorder, device, index, cycle, storm=storm
                    )
                cycle += 1
                if args.mode == "reconnect" or time.perf_counter() - started >= duration:
                    return
                await asyncio.sleep(interval)

        print(
            f"режим={args.mode}, устройств={len(devices)}, ramp={args.ramp:.0f} с, "
            f"интервал={interval:.0f} с, адрес={args.base_url}"
        )
        await asyncio.gather(*(adapter(i, device) for i, device in enumerate(devices)))
        elapsed = time.perf_counter() - started
        requests = sum(recorder.statuses.values())
        print(f"прогон занял {elapsed:.1f} с; запросов {requests}; среднее {requests / elapsed:.1f} RPS")

    recorder.report()
    if not storm and (recorder.failures or recorder.expected_limits):
        return 1
    if storm and recorder.expected_limits == 0:
        print(
            "Внимание: режим storm не получил ни одного 429; limiter не доказан.",
            file=sys.stderr,
        )
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--credentials", type=Path, default=DEFAULT_CREDENTIALS)
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare_parser = subparsers.add_parser("prepare", help="создать реальные dev-подключения")
    prepare_parser.add_argument("--devices", type=int, default=100)
    prepare_parser.add_argument("--concurrency", type=int, default=10)
    prepare_parser.add_argument("--batch-size", type=int, default=25)

    run_parser = subparsers.add_parser("run", help="воспроизвести трафик адаптеров")
    run_parser.add_argument("--mode", choices=("normal", "reconnect", "storm"), default="normal")
    run_parser.add_argument("--devices", type=int)
    run_parser.add_argument("--duration", type=float, default=600.0)
    run_parser.add_argument("--ramp", type=float, default=120.0)
    run_parser.add_argument("--interval", type=float)
    run_parser.add_argument("--concurrency", type=int, default=200)
    return parser


async def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if refuse_if_not_local(args.base_url):
        return 2
    if args.command == "prepare":
        if args.devices < 1 or args.concurrency < 1 or args.batch_size < 1:
            parser.error("devices, concurrency и batch-size должны быть положительными")
        return await prepare(args)
    if args.duration < 0 or args.ramp < 0 or args.concurrency < 1:
        parser.error("duration/ramp не могут быть отрицательными, concurrency должен быть положительным")
    if args.interval is not None and args.interval <= 0:
        parser.error("interval должен быть положительным")
    return await run(args)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
