#!/usr/bin/env python3
"""Drive what people already using the service actually do, and report the cost.

The newcomer rehearsal measures the first minute of an account's life. This one
measures the rest of it: the shelf of spools, the machines, writing off material,
pricing a job, sending a customer a quote, and handing the slicer a full set of
profiles. Several of these are closed to a fresh account — the calculator needs a
confirmed address and an entitlement — so it signs in as accounts prepared by
``scripts/seed_dev_accounts.py``.

Development only. The script refuses any host but the local machine.

    python scripts/seed_dev_accounts.py --accounts 50
    python scripts/load_test_returning.py --users 50 --ramp 60

Measure against a backend started without ``--reload``; see the newcomer script
for why.
"""

from __future__ import annotations

import argparse
import asyncio
import random
import sys
import time
import uuid
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))

from load_common import (  # noqa: E402
    Recorder,
    pretend_address,
    refuse_if_not_local,
    timed,
)

PASSWORD = "qwerty123"

# Roughly the shape of a quote a customer receives: a page of tables, which is
# what the renderer is asked to turn into a PDF.
QUOTE_HTML = (
    "<html><head><style>body{font-family:'Segoe UI',Arial,sans-serif}"
    "table{width:100%;border-collapse:collapse}td,th{border:1px solid #ccc;padding:6px}"
    "</style></head><body><h1>Коммерческое предложение</h1>"
    "<table><tr><th>Позиция</th><th>Кол-во</th><th>Цена</th></tr>"
    + "".join(
        f"<tr><td>Деталь {n}</td><td>{n}</td><td>{n * 137} ₽</td></tr>" for n in range(1, 40)
    )
    + "</table><p>Итого: 12 345 ₽</p></body></html>"
)


async def look_at_the_shelf(client, headers, recorder, state) -> None:
    """The most common visit: what do I have and on what machines."""
    spools = await timed(recorder, "катушки: список", client.get("/api/v1/spools", headers=headers))
    await timed(
        recorder, "принтеры: список", client.get("/api/v1/physical-printers", headers=headers)
    )
    if spools is not None:
        state["spools"] = [item["id"] for item in spools.json()]


async def write_off_material(client, headers, recorder, state) -> None:
    """Printed something: take it off a spool and look at the history."""
    if not state.get("spools"):
        return
    spool_id = random.choice(state["spools"])
    await timed(
        recorder,
        "катушка: списание",
        client.post(
            f"/api/v1/spools/{spool_id}/use",
            headers=headers,
            json={"delta_weight_g": round(random.uniform(5, 120), 1)},
        ),
    )
    await timed(
        recorder,
        "катушка: история",
        client.get(f"/api/v1/spools/{spool_id}/usage", headers=headers),
    )


async def price_a_job(client, headers, recorder, state) -> dict | None:
    """The calculator: the reason the subscription exists."""
    request = {
        "pricing_method": "combined",
        "weight_g": round(random.uniform(20, 900), 1),
        "supports_weight_g": round(random.uniform(0, 60), 1),
        "spool_price": round(random.uniform(1200, 3200), 2),
        "spool_weight_kg": 1.0,
        "time_hours": round(random.uniform(0.5, 30), 2),
        "electricity_cost_per_kwh": 6.2,
        "printer_power_w": 350,
        "modeling_hours": round(random.uniform(0, 4), 2),
        "modeling_rate_per_hour": 1500,
        "postprocessing_hours": round(random.uniform(0, 2), 2),
        "postprocessing_rate_per_hour": 900,
        "printing_rate_per_hour": 250,
        "amortization_rate_per_hour": 40,
    }
    estimate = await timed(
        recorder,
        "калькулятор: расчёт",
        client.post("/api/v1/calculator/estimate", headers=headers, json=request),
    )
    if estimate is None:
        return None

    result = estimate.json()
    await timed(
        recorder,
        "калькулятор: сохранить",
        client.post(
            "/api/v1/calculator/history",
            headers=headers,
            json={
                "title": f"Заказ {uuid.uuid4().hex[:6]}",
                "request_data": request,
                "result_data": result,
            },
        ),
    )
    await timed(
        recorder,
        "калькулятор: история",
        client.get("/api/v1/calculator/history", headers=headers, params={"page": 1}),
    )
    return result


async def send_a_quote(client, headers, recorder, state) -> None:
    """Price a job, then hand the customer a link and a PDF."""
    if await price_a_job(client, headers, recorder, state) is None:
        return

    title = f"КП {uuid.uuid4().hex[:6]}"
    await timed(
        recorder,
        "КП: ссылка",
        client.post(
            "/api/v1/calculator/quote/share",
            headers=headers,
            json={"title": title, "html_content": QUOTE_HTML},
        ),
    )
    await timed(
        recorder,
        "КП: PDF",
        client.post(
            "/api/v1/calculator/quote/pdf",
            headers=headers,
            json={"title": title, "html_content": QUOTE_HTML},
        ),
    )


async def sync_the_slicer(client, headers, recorder, state) -> None:
    """A full round of what the plugin sends, not just one of the three kinds."""
    batch = uuid.uuid4().hex[:8]
    await timed(
        recorder,
        "слайсер: профили принтера",
        client.post(
            "/api/v1/orcaslicer/printer-profiles/import",
            headers=headers,
            json={
                "profiles": [
                    {
                        "external_id": f"ret-machine-{batch}-{n}",
                        "name": f"Voron {batch} {n}",
                        "slug": f"ret-machine-{batch}-{n}",
                        "orcaslicer_settings": {"printable_height": "250"},
                    }
                    for n in range(2)
                ]
            },
        ),
    )
    await timed(
        recorder,
        "слайсер: профили печати",
        client.post(
            "/api/v1/orcaslicer/print-profiles/import",
            headers=headers,
            json={
                "profiles": [
                    {
                        "external_id": f"ret-process-{batch}-{n}",
                        "name": f"0.20mm {batch} {n} @FilamentHub",
                        "slug": f"ret-process-{batch}-{n}",
                        "layer_height_mm": 0.2,
                        "orcaslicer_settings": {"layer_height": "0.2"},
                    }
                    for n in range(3)
                ]
            },
        ),
    )
    await timed(
        recorder,
        "слайсер: пресеты филамента",
        client.post(
            "/api/v1/orcaslicer/filaments/import",
            headers=headers,
            json={
                "profiles": [
                    {
                        "external_id": f"ret-filament-{batch}-{n}",
                        "name": f"PLA {batch} {n} @FilamentHub",
                        "extruder_temp": 210,
                        "bed_temp": 60,
                        "orcaslicer_settings": {
                            "filament_type": ["PLA"],
                            "filament_vendor": ["Load Vendor"],
                        },
                    }
                    for n in range(5)
                ]
            },
        ),
    )
    await timed(
        recorder, "слайсер: мои пресеты", client.get("/api/v1/auth/my-presets", headers=headers)
    )


ROLES: dict[str, tuple[str, int, object]] = {
    "shelf": ("смотрит склад", 40, look_at_the_shelf),
    "writeoff": ("списывает материал", 20, write_off_material),
    "calculator": ("считает заказ", 20, price_a_job),
    "quote": ("делает КП", 10, send_a_quote),
    "sync": ("синхронизирует слайсер", 10, sync_the_slicer),
}


def apply_mix(mix: str) -> None:
    """Re-weight what the crowd does, e.g. --mix quote=100."""
    weights = {}
    for pair in mix.split(","):
        key, _, value = pair.partition("=")
        key = key.strip()
        if key not in ROLES:
            raise SystemExit(f"неизвестная роль {key!r}; есть: {', '.join(ROLES)}")
        weights[key] = int(value)
    for key, (label, _, action) in ROLES.items():
        ROLES[key] = (label, weights.get(key, 0), action)


async def returning_person(
    client: httpx.AsyncClient, recorder: Recorder, email: str, index: int
) -> None:
    visitor = {"X-FilamentHub-Client-IP": pretend_address(index)}
    signed_in = await timed(
        recorder,
        "вход",
        client.post(
            "/api/v1/auth/login", json={"email": email, "password": PASSWORD}, headers=visitor
        ),
    )
    if signed_in is None:
        return

    headers = dict(visitor)
    headers["Authorization"] = f"Bearer {signed_in.json()['access_token']}"
    state: dict = {}

    # Everyone looks at their shelf on arrival; the rest is what they came for.
    await look_at_the_shelf(client, headers, recorder, state)

    roles = list(ROLES.values())
    action = random.choices([role[2] for role in roles], weights=[role[1] for role in roles])[0]
    await asyncio.sleep(random.uniform(0.5, 2.5))
    await action(client, headers, recorder, state)


async def known_accounts(client: httpx.AsyncClient, wanted: int) -> list[str]:
    """Ask the database for the accounts the seeding script prepared."""
    import os

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
            "SELECT email FROM users WHERE email LIKE 'established-%' ORDER BY id DESC LIMIT $1",
            wanted,
        )
    finally:
        await connection.close()
    return [row["email"] for row in rows]


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8001")
    parser.add_argument("--users", type=int, default=50, help="сколько человек придёт")
    parser.add_argument("--ramp", type=float, default=60.0, help="за сколько секунд они придут")
    parser.add_argument("--mix", help="состав, например quote=100")
    args = parser.parse_args()

    if args.mix:
        apply_mix(args.mix)
    if refuse_if_not_local(args.base_url):
        return 2

    recorder = Recorder()
    async with httpx.AsyncClient(base_url=args.base_url, timeout=60.0) as client:
        accounts = await known_accounts(client, args.users)
        if not accounts:
            print(
                "Нет подготовленных учётных записей. Сначала:\n"
                "  python scripts/seed_dev_accounts.py --accounts 50",
                file=sys.stderr,
            )
            return 1

        mix = ", ".join(f"{name} {weight}%" for name, weight, _ in ROLES.values() if weight)
        print(f"{len(accounts)} действующих пользователей за {args.ramp:.0f} с на {args.base_url}")
        print(f"состав: {mix}")

        started = time.perf_counter()
        delay = args.ramp / max(len(accounts), 1)

        async def arrival(index: int, email: str) -> None:
            await asyncio.sleep(index * delay)
            await returning_person(client, recorder, email, index)

        await asyncio.gather(*(arrival(i, email) for i, email in enumerate(accounts)))
        print(f"прогон занял {time.perf_counter() - started:.0f} с")

    recorder.report()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
