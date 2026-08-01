#!/usr/bin/env python3
"""Drive the path a newcomer takes on release day and report where it hurts.

Run before a release that brings a crowd. It answers two questions the unit
tests cannot: do concurrent requests exhaust the database connections, and does
any endpoint slow down out of proportion to the rest — the shape of a query in
a loop or a missing index.

Development only. The script refuses any host but the local machine: it creates
accounts and reads catalogue pages, which has no place on a live server.

    python scripts/load_test_newcomer.py --users 300 --ramp 300
"""

from __future__ import annotations

import argparse
import asyncio
import random
import statistics
import sys
import time
import uuid
from collections import defaultdict
from urllib.parse import urlparse

import httpx

# A Windows console defaults to a codepage that cannot print the report, and a
# tool must not die at the moment it finally has something to say.
for stream in (sys.stdout, sys.stderr):
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(encoding="utf-8", errors="replace")

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}
# Reserved documentation domain: it resolves, so registration's domain check
# passes, and nobody can ever receive mail at it.
EMAIL_DOMAIN = "example.com"
PASSWORD = "LoadTest123"


class Recorder:
    def __init__(self) -> None:
        self.samples: dict[str, list[float]] = defaultdict(list)
        self.failures: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    def ok(self, step: str, seconds: float) -> None:
        self.samples[step].append(seconds)

    def failed(self, step: str, reason: str) -> None:
        self.failures[step][reason] += 1

    def report(self) -> None:
        print(f"\n{'шаг':<28}{'запросов':>9}{'медиана':>10}{'95-й':>9}{'худший':>9}  ошибки")
        print("-" * 82)
        for step in sorted(set(self.samples) | set(self.failures)):
            values = sorted(self.samples.get(step, []))
            failures = self.failures.get(step, {})
            summary = ", ".join(f"{reason} x{count}" for reason, count in failures.items())
            if values:
                index = min(len(values) - 1, int(len(values) * 0.95))
                print(
                    f"{step:<28}{len(values):>9}"
                    f"{statistics.median(values):>9.2f}s"
                    f"{values[index]:>8.2f}s"
                    f"{values[-1]:>8.2f}s"
                    f"  {summary}"
                )
            else:
                print(f"{step:<28}{0:>9}{'—':>10}{'—':>9}{'—':>9}  {summary}")

        total_failures = sum(sum(v.values()) for v in self.failures.values())
        print("-" * 82)
        print(f"ошибок всего: {total_failures}")
        if any("500" in reason or "database" in reason.lower() for step in self.failures for reason in self.failures[step]):
            print("Внимание: есть отказы сервера — смотрите логи бэкенда, это не про скорость.")


async def timed(recorder: Recorder, step: str, coro) -> httpx.Response | None:
    started = time.perf_counter()
    try:
        response = await coro
    except Exception as exc:  # noqa: BLE001 — any transport failure is a result too
        recorder.failed(step, type(exc).__name__)
        return None
    elapsed = time.perf_counter() - started
    if response.status_code >= 400:
        recorder.failed(step, str(response.status_code))
        return None
    recorder.ok(step, elapsed)
    return response


async def browse(client: httpx.AsyncClient, headers: dict, recorder: Recorder) -> int | None:
    """What everyone does: opens the catalogue and looks at one material."""
    listing = await timed(
        recorder, "каталог", client.get("/api/v1/filaments/", params={"size": 20}, headers=headers)
    )
    await asyncio.sleep(random.uniform(0.3, 1.5))
    await timed(
        recorder,
        "каталог с фильтром",
        client.get(
            "/api/v1/filaments/", params={"size": 20, "material_type": "PLA"}, headers=headers
        ),
    )
    if listing is None:
        return None
    items = listing.json().get("items") or []
    if not items:
        return None
    filament = random.choice(items)
    await asyncio.sleep(random.uniform(0.3, 1.5))
    await timed(
        recorder,
        "карточка филамента",
        client.get(f"/api/v1/filaments/{filament['id']}", headers=headers),
    )
    return filament["id"]


async def sync_slicer(
    client: httpx.AsyncClient, headers: dict, recorder: Recorder, filament_id: int | None
) -> None:
    """Someone who came from the plugin.

    These are the calls the plugin actually makes — its own presets, the sync
    preferences, and the export it fetches when a preset is saved from the
    embedded catalogue.
    """
    await timed(recorder, "плагин: мои пресеты", client.get("/api/v1/auth/my-presets", headers=headers))
    await timed(
        recorder, "плагин: настройки синка", client.get("/api/v1/orcaslicer/sync-prefs", headers=headers)
    )

    if filament_id is None:
        return
    catalogue = await timed(
        recorder,
        "плагин: пресеты материала",
        client.get(f"/api/v1/filaments/{filament_id}/presets", headers=headers),
    )
    if catalogue is None:
        return
    presets = catalogue.json()
    items = presets.get("items") if isinstance(presets, dict) else presets
    if not items:
        return
    await asyncio.sleep(random.uniform(0.3, 1.0))
    await timed(
        recorder,
        "плагин: выгрузка пресета",
        client.get(
            f"/api/v1/presets/{random.choice(items)['id']}/export/orcaslicer.json", headers=headers
        ),
    )


async def publish_preset(
    client: httpx.AsyncClient, headers: dict, recorder: Recorder, filament_id: int | None
) -> None:
    """The heaviest path: moderation runs and the weighted preset is affected."""
    if filament_id is None:
        return
    await timed(
        recorder,
        "создание пресета",
        client.post(
            "/api/v1/presets/",
            headers=headers,
            json={
                "name": f"Load {uuid.uuid4().hex[:8]}",
                "filament_id": filament_id,
                "extruder_temp": random.choice([200, 205, 210, 215, 220]),
                "bed_temp": random.choice([55, 60, 65]),
                "flow_rate": random.choice([95, 98, 100, 102]),
            },
        ),
    )


async def leave_review(
    client: httpx.AsyncClient, headers: dict, recorder: Recorder, filament_id: int | None
) -> None:
    """Writes a review, which moves the material's rating."""
    if filament_id is None:
        return
    await timed(
        recorder,
        "отзыв",
        client.post(
            "/api/v1/filament-reviews/",
            headers=headers,
            json={
                "filament_id": filament_id,
                "success": random.random() > 0.2,
                "rating": round(random.uniform(3.0, 5.0), 1),
                "comment": "Печатается ровно, без проблем.",
            },
        ),
    )


async def add_printer(
    client: httpx.AsyncClient, headers: dict, recorder: Recorder, _: int | None
) -> None:
    """Registers a machine, then loads the list back the way the profile page does."""
    await timed(
        recorder,
        "добавление принтера",
        client.post(
            "/api/v1/physical-printers",
            headers=headers,
            json={"name": f"Voron {uuid.uuid4().hex[:6]}"},
        ),
    )
    await timed(
        recorder, "список принтеров", client.get("/api/v1/physical-printers", headers=headers)
    )


# Release day is mostly onlookers; a minority contributes. Weights say how many
# of a hundred newcomers do each thing beyond browsing.
ROLES: list[tuple[str, int, object]] = [
    ("только смотрит", 55, None),
    ("синхронизирует плагин", 25, sync_slicer),
    ("заводит принтер", 8, add_printer),
    ("пишет отзыв", 7, leave_review),
    ("создаёт пресет", 5, publish_preset),
]


def _pretend_address(index: int) -> str:
    """Give each simulated visitor its own address.

    Everything here leaves one machine, so without this the per-visitor rate
    limits would all count into a single bucket and the rehearsal would measure
    the limiter rather than the application. The development stack is
    configured to trust this header; production trusts it only from its own
    proxy.
    """
    return f"198.51.{(index // 250) % 250}.{index % 250 + 1}"


async def newcomer(
    client: httpx.AsyncClient, legal: dict, recorder: Recorder, index: int
) -> None:
    """One person: signs up, looks around, and then does their own thing."""
    handle = uuid.uuid4().hex[:12]
    email = f"load-{handle}@{EMAIL_DOMAIN}"
    payload = {
        "email": email,
        "username": f"load_{handle}",
        "password": PASSWORD,
        "role": "user",
        "terms_accepted": True,
        "personal_data_consent": True,
        "terms_version": legal["terms_version"],
        "personal_data_consent_version": legal["personal_data_consent_version"],
        "privacy_policy_version": legal["privacy_policy_version"],
        "legal_language": "ru",
    }
    visitor = {"X-FilamentHub-Client-IP": _pretend_address(index)}
    if await timed(
        recorder, "регистрация", client.post("/api/v1/auth/register", json=payload, headers=visitor)
    ) is None:
        return

    await asyncio.sleep(random.uniform(0.5, 2.0))
    login = await timed(
        recorder,
        "вход",
        client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": PASSWORD},
            headers=visitor,
        ),
    )
    if login is None:
        return
    token = login.json().get("access_token")
    headers = dict(visitor)
    if token:
        headers["Authorization"] = f"Bearer {token}"

    await asyncio.sleep(random.uniform(0.5, 2.0))
    filament_id = await browse(client, headers, recorder)

    action = random.choices([role[2] for role in ROLES], weights=[role[1] for role in ROLES])[0]
    if action is not None:
        await asyncio.sleep(random.uniform(0.5, 2.5))
        await action(client, headers, recorder, filament_id)


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8001")
    parser.add_argument("--users", type=int, default=300, help="сколько человек придёт")
    parser.add_argument("--ramp", type=float, default=300.0, help="за сколько секунд они придут")
    args = parser.parse_args()

    host = (urlparse(args.base_url).hostname or "").casefold()
    if host not in LOCAL_HOSTS:
        print(
            f"Отказ: {args.base_url} — не локальный адрес.\n"
            "Скрипт создаёт учётные записи и нагружает базу; на боевом сервере это недопустимо.",
            file=sys.stderr,
        )
        return 2

    recorder = Recorder()
    async with httpx.AsyncClient(base_url=args.base_url, timeout=30.0) as client:
        try:
            legal = (await client.get("/api/v1/auth/legal-requirements")).json()
        except Exception as exc:  # noqa: BLE001
            print(f"Не отвечает {args.base_url}: {exc}", file=sys.stderr)
            return 1

        mix = ", ".join(f"{name} {weight}%" for name, weight, _ in ROLES)
        print(f"{args.users} человек приходят волной за {args.ramp:.0f} с на {args.base_url}")
        print(f"состав: {mix}")
        started = time.perf_counter()
        delay = args.ramp / max(args.users, 1)

        async def arrival(index: int) -> None:
            await asyncio.sleep(index * delay)
            await newcomer(client, legal, recorder, index)

        await asyncio.gather(*(arrival(i) for i in range(args.users)))
        print(f"прогон занял {time.perf_counter() - started:.0f} с")

    recorder.report()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
