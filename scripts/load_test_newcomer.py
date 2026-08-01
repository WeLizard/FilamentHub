#!/usr/bin/env python3
"""Drive the path a newcomer takes on release day and report where it hurts.

Run before a release that brings a crowd. It answers two questions the unit
tests cannot: do concurrent requests exhaust the database connections, and does
any endpoint slow down out of proportion to the rest — the shape of a query in
a loop or a missing index.

Development only. The script refuses any host but the local machine: it creates
accounts and reads catalogue pages, which has no place on a live server.

    python scripts/load_test_newcomer.py --users 300 --ramp 300

Measure against a backend started without ``--reload``. The development stack
restarts on every saved file, each restart stalls whatever is in flight for
several seconds, and those stalls land in the report as if the application had
frozen. Run a second container on another port for the duration:

    docker run -d --name filamenthub_backend_load --network filamenthub_filamenthub_dev \
        -p 8002:8000 -v <repo>/backend:/app --env-file <dev env> filamenthub-backend-dev \
        uvicorn app.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import argparse
import asyncio
import math
import random
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
# The handful of materials the crowd converges on; filled from the catalogue.
POPULAR: list[int] = []
# Reserved documentation domain: it resolves, so registration's domain check
# passes, and nobody can ever receive mail at it.
EMAIL_DOMAIN = "example.com"
PASSWORD = "LoadTest123"


def _percentile(sorted_values: list[float], share: float) -> float:
    """Nearest-rank percentile: the value a given share of requests stayed under."""
    rank = math.ceil(share * len(sorted_values))
    return sorted_values[min(len(sorted_values), max(1, rank)) - 1]


class Recorder:
    def __init__(self) -> None:
        self.samples: dict[str, list[float]] = defaultdict(list)
        self.failures: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        # When each slow request happened, so an outlier can be matched against
        # the container and database samples taken alongside the run.
        self.slowest: list[tuple[float, str, float]] = []
        self.started = time.perf_counter()

    def ok(self, step: str, seconds: float) -> None:
        self.samples[step].append(seconds)
        self.slowest.append((seconds, step, time.perf_counter() - self.started))
        self.slowest.sort(reverse=True)
        del self.slowest[8:]

    def failed(self, step: str, reason: str) -> None:
        self.failures[step][reason] += 1

    def report(self) -> None:
        print(f"\n{'шаг':<28}{'запросов':>9}{'p50':>9}{'p95':>9}{'p99':>9}{'худший':>9}  ошибки")
        print("-" * 90)
        for step in sorted(set(self.samples) | set(self.failures)):
            values = sorted(self.samples.get(step, []))
            failures = self.failures.get(step, {})
            summary = ", ".join(f"{reason} x{count}" for reason, count in failures.items())
            if values:
                print(
                    f"{step:<28}{len(values):>9}"
                    f"{_percentile(values, 0.50):>8.2f}s"
                    f"{_percentile(values, 0.95):>8.2f}s"
                    f"{_percentile(values, 0.99):>8.2f}s"
                    f"{values[-1]:>8.2f}s"
                    f"  {summary}"
                )
            else:
                print(f"{step:<28}{0:>9}{'—':>9}{'—':>9}{'—':>9}{'—':>9}  {summary}")

        if self.slowest:
            print("\nсамые долгие запросы:")
            for seconds, step, offset in self.slowest:
                print(f"  {seconds:6.2f}s  {step:<28} на {offset:.0f}-й секунде прогона")

        total_failures = sum(sum(v.values()) for v in self.failures.values())
        print("-" * 90)
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

    # What the plugin does on its first run: pushes the presets it found locally.
    # The heaviest call of the release day — it moderates, resolves a filament
    # and writes, and it is the one that used to race with itself.
    batch = uuid.uuid4().hex[:8]
    await timed(
        recorder,
        "плагин: отправка пресетов",
        client.post(
            "/api/v1/orcaslicer/filaments/import",
            headers=headers,
            json={
                "profiles": [
                    {
                        "external_id": f"load-{batch}-{number}",
                        "name": f"Load {batch} {number} @FilamentHub",
                        "extruder_temp": random.choice([200, 210, 220]),
                        "bed_temp": random.choice([55, 60, 65]),
                        "orcaslicer_settings": {
                            "filament_type": ["PLA"],
                            "filament_vendor": ["LoadTest Vendor"],
                        },
                    }
                    for number in range(3)
                ]
            },
        ),
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
    """Reads what others wrote, adds a review, and looks at the moved rating."""
    # Reviews land on the few materials everyone owns, not spread evenly over
    # the catalogue: that is what makes a review list long enough to hurt.
    filament_id = random.choice(POPULAR) if POPULAR else filament_id
    if filament_id is None:
        return
    await timed(
        recorder,
        "отзывы: список",
        client.get(f"/api/v1/filament-reviews/filament/{filament_id}", headers=headers),
    )
    await timed(
        recorder,
        "отзывы: рейтинг",
        client.get(f"/api/v1/filament-reviews/filament/{filament_id}/stats", headers=headers),
    )
    await asyncio.sleep(random.uniform(0.3, 1.5))
    await timed(
        recorder,
        "отзыв: публикация",
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
    # The rating is read again right after writing: that is when a recount, if
    # there is one, would show up.
    await timed(
        recorder,
        "отзывы: рейтинг после",
        client.get(f"/api/v1/filament-reviews/filament/{filament_id}/stats", headers=headers),
    )
    await timed(
        recorder,
        "отзывы: мои",
        client.get("/api/v1/filament-reviews/my", headers=headers),
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
ROLES: dict[str, tuple[str, int, object]] = {
    "browse": ("только смотрит", 55, None),
    "plugin": ("синхронизирует плагин", 25, sync_slicer),
    "printer": ("заводит принтер", 8, add_printer),
    "review": ("пишет отзыв", 7, leave_review),
    "preset": ("создаёт пресет", 5, publish_preset),
}


def apply_mix(mix: str) -> None:
    """Re-weight the crowd, e.g. --mix review=60,browse=20,plugin=20.

    Release day has its own shape, but a single path sometimes has to be put
    under a crowd of its own to see where it bends.
    """
    weights = {}
    for pair in mix.split(","):
        key, _, value = pair.partition("=")
        key = key.strip()
        if key not in ROLES:
            raise SystemExit(f"неизвестная роль {key!r}; есть: {', '.join(ROLES)}")
        weights[key] = int(value)
    for key, (label, _, action) in ROLES.items():
        ROLES[key] = (label, weights.get(key, 0), action)


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

    roles = list(ROLES.values())
    action = random.choices([role[2] for role in roles], weights=[role[1] for role in roles])[0]
    if action is not None:
        await asyncio.sleep(random.uniform(0.5, 2.5))
        await action(client, headers, recorder, filament_id)


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8001")
    parser.add_argument("--users", type=int, default=300, help="сколько человек придёт")
    parser.add_argument("--ramp", type=float, default=300.0, help="за сколько секунд они придут")
    parser.add_argument("--mix", help="состав волны, например review=60,browse=20,plugin=20")
    args = parser.parse_args()

    if args.mix:
        apply_mix(args.mix)

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

        catalogue = (await client.get("/api/v1/filaments/", params={"size": 5})).json()
        POPULAR.extend(item["id"] for item in catalogue.get("items", []))

        mix = ", ".join(
            f"{name} {weight}%" for name, weight, _ in ROLES.values() if weight
        )
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
