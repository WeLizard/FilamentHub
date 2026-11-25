#!/usr/bin/env python3
"""Record the guest demo: what the showcase account's screens read from the API.

The guest demo on the site shows real account screens with sample data. This
script asks the backend, as the showcase account, for every read listed in
``frontend/src/demo/endpoints.json`` and writes the answers to
``frontend/src/demo/fixtures.json``. Run it again whenever an API response used
by the demo changes shape::

    python scripts/record_demo_fixtures.py

``--serve`` starts the same database and leaves its API on a local port, to
look at or capture pages of the showcase without loading it into shared dev.

Preparing the recording database takes a few minutes. While the list of reads
is being worked out, ``--keep`` leaves it running for the next run to reuse;
a run without the flag removes it.

It never touches the shared dev database. It starts its own throwaway
PostgreSQL and Redis next to the dev backend image, applies the migrations,
loads ``seed_dev_showcase.py`` and removes everything when done. It reads only
through the API, creates no session and needs no password: the requests go to
the application in-process with the showcase account supplied directly.

Values that look like credentials are replaced before anything is written.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parent.parent
ENDPOINTS = ROOT / "frontend" / "src" / "demo" / "endpoints.json"
FIXTURES = ROOT / "frontend" / "src" / "demo" / "fixtures.json"
SHOWCASE_EMAIL = "olga@example.com"

BACKEND_IMAGE = "filamenthub-backend-dev"
PREFIX = "fh_demo_record"
NETWORK = f"{PREFIX}_net"
POSTGRES = f"{PREFIX}_postgres"
REDIS = f"{PREFIX}_redis"
BACKEND = f"{PREFIX}_backend"
# The same names and values as docker-compose.dev.yml, on a private network:
# the showcase seed accepts only a database it can recognise as local dev.
DATABASE_ENV = {"POSTGRES_USER": "filamenthub", "POSTGRES_PASSWORD": "devpass123", "POSTGRES_DB": "filamenthub_dev"}
BACKEND_ENV = {
    **DATABASE_ENV,
    "POSTGRES_HOST": "postgres-dev",
    "POSTGRES_PORT": "5432",
    "REDIS_URL": "redis://:devredis123@redis-dev:6379/0",
    "SECRET_KEY": "dev-secret-key-not-for-production",
    "DEBUG": "true",
    "AUTH_REGION_MODE": "development",
}

# Runs inside the backend container: the printer catalogue from the tracked
# OrcaSlicer bundle, the same source the admin import uses.
IMPORT_PRINTERS = r'''
import asyncio, tempfile, zipfile
from pathlib import Path

from app.db.session import AsyncSessionLocal
from app.services.orca_bundle_importer import OrcaBundleImporter


async def main() -> None:
    with tempfile.TemporaryDirectory() as extracted:
        with zipfile.ZipFile("/app/data/catalog_sources/orca/bundle.zip") as bundle:
            bundle.extractall(extracted)
        async with AsyncSessionLocal() as session:
            await OrcaBundleImporter(root_path=Path(extracted)).import_all(session)
            await session.commit()


asyncio.run(main())
'''

# Runs inside the backend container.
IN_CONTAINER = r'''
import asyncio, json, sys
from typing import Annotated

from fastapi import Depends
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core import dependencies
from app.db.session import get_db
from app.main import app
from app.models.user import User

request = json.loads(sys.stdin.read())


async def showcase_user(db: Annotated[AsyncSession, Depends(get_db)]) -> User:
    user = await db.scalar(
        select(User)
        .options(selectinload(User.subscription))
        .where(func.lower(User.email) == request["email"])
    )
    if user is None:
        raise SystemExit("the showcase account is missing from the recording database")
    return user


for name in dir(dependencies):
    target = getattr(dependencies, name)
    if (
        callable(target)
        and name.startswith(("get_current_user", "get_current_active_user_optional", "require_"))
        and getattr(target, "__module__", "") == dependencies.__name__
    ):
        app.dependency_overrides[target] = showcase_user
app.state.limiter.enabled = False


async def main() -> None:
    responses, failures = {}, {}
    # Keys carry no trailing slash; the application redirects to its own form.
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://demo.local", follow_redirects=True,
    ) as client:
        async def read(key: str) -> None:
            response = await client.get("/api/v1" + key, headers={"Accept-Language": "en"})
            if response.status_code == 200:
                responses[key] = response.json()
            else:
                failures[key] = response.status_code

        for key in request["endpoints"]:
            if "{" not in key:
                await read(key)
        # Reads that name records by id follow from the lists just recorded,
        # so the list of reads does not depend on the ids a database hands out.
        saved = responses.get("/saved-presets") or []
        saved = saved.get("items", []) if isinstance(saved, dict) else saved
        values = {"saved_preset_ids": ",".join(str(item["preset_id"]) for item in saved)}
        for key in request["endpoints"]:
            if "{" in key:
                await read(key.format(**values))
    print("\n__FH_DEMO__" + json.dumps({"responses": responses, "failures": failures}))


asyncio.run(main())
'''

# Field names that hold credentials. Deliberately not a bare "key": that also
# names translation keys and content keys the screens need.
SECRET_FIELD = re.compile(
    r"api_key|device_key|bridge_key|plain_key|key_hash|secret|password|token|pairing_code|auth_version",
    re.I,
)
PLACEHOLDER = "demo"


def scrub(value: Any, field: str = "") -> Any:
    """Replace anything that could be a credential."""
    if isinstance(value, dict):
        return {name: scrub(item, name) for name, item in value.items()}
    if isinstance(value, list):
        return [scrub(item, field) for item in value]
    if isinstance(value, str) and value and SECRET_FIELD.search(field):
        return PLACEHOLDER
    return value


def docker(*arguments: str, stdin: str | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        ["docker", *arguments], input=stdin, capture_output=True, text=True, encoding="utf-8", check=False,
    )
    if check and completed.returncode != 0:
        raise RuntimeError(f"docker {' '.join(arguments[:3])} failed:\n{completed.stderr[-3000:]}")
    return completed


def env_arguments(values: dict[str, str]) -> list[str]:
    return [item for name, value in values.items() for item in ("-e", f"{name}={value}")]


def remove_stack() -> None:
    docker("rm", "-f", BACKEND, POSTGRES, REDIS, check=False)
    docker("network", "rm", NETWORK, check=False)


SEEDED_MARKER = "/tmp/fh-demo-showcase-loaded"
# `--serve` leaves the API of the recording database on this local port, for
# capturing pages of the showcase (a frontend proxied to it shows them).
SERVE_PORT = 8011


@contextmanager
def recording_stack(keep: bool) -> Iterator[None]:
    """A private database with the showcase loaded, and a backend to ask."""
    if docker("exec", BACKEND, "test", "-f", SEEDED_MARKER, check=False).returncode == 0:
        try:
            yield
        finally:
            if not keep:
                remove_stack()
        return
    remove_stack()
    docker("network", "create", NETWORK)
    try:
        docker(
            "run", "-d", "--name", POSTGRES, "--network", NETWORK, "--network-alias", "postgres-dev",
            *env_arguments(DATABASE_ENV), "postgres:15-alpine",
        )
        docker(
            "run", "-d", "--name", REDIS, "--network", NETWORK, "--network-alias", "redis-dev",
            "redis:7-alpine", "redis-server", "--requirepass", "devredis123",
        )
        docker(
            "run", "-d", "--name", BACKEND, "--network", NETWORK, *env_arguments(BACKEND_ENV),
            "-p", f"127.0.0.1:{SERVE_PORT}:8000",
            "-v", f"{ROOT / 'backend'}:/app", "-v", f"{ROOT / 'scripts'}:/recording-scripts:ro",
            BACKEND_IMAGE, "sleep", "infinity",
        )
        for _ in range(60):
            # Over TCP: the image's first-run setup server answers only on the socket.
            ready = docker(
                "exec", POSTGRES, "pg_isready", "-h", "127.0.0.1", "-U", DATABASE_ENV["POSTGRES_USER"], check=False,
            )
            if ready.returncode == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError("the recording database did not start")
        docker("exec", BACKEND, "alembic", "upgrade", "head")
        # The showcase gives its people real printer models, so the printer
        # catalogue has to be there first.
        docker("exec", "-i", BACKEND, "python", "-", stdin=IMPORT_PRINTERS)
        docker("exec", BACKEND, "python", "/recording-scripts/seed_dev_showcase.py")
        docker("exec", BACKEND, "touch", SEEDED_MARKER)
        yield
    except BaseException:
        remove_stack()
        raise
    else:
        if not keep:
            remove_stack()


def record(endpoints: list[str]) -> dict[str, Any]:
    completed = docker(
        # The first input line carries the program, the rest is its request.
        "exec", "-i", BACKEND, "python", "-c",
        "import sys, json; exec(compile(json.loads(sys.stdin.readline()), 'record', 'exec'))",
        stdin=json.dumps(IN_CONTAINER) + "\n" + json.dumps({"email": SHOWCASE_EMAIL, "endpoints": endpoints}),
        check=False,
    )
    marker = "__FH_DEMO__"
    if completed.returncode != 0 or marker not in completed.stdout:
        raise RuntimeError((completed.stderr or completed.stdout)[-4000:])
    return json.loads(completed.stdout.rsplit(marker, 1)[1])


def main() -> int:
    endpoints: list[str] = json.loads(ENDPOINTS.read_text(encoding="utf-8"))
    if "--serve" in sys.argv[1:]:
        try:
            with recording_stack(keep=True):
                docker("exec", "-d", BACKEND, "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000")
        except RuntimeError as error:
            sys.stderr.write(f"{error}\n")
            return 1
        print(f"showcase API: http://127.0.0.1:{SERVE_PORT} (a run without flags removes it)")
        return 0
    try:
        with recording_stack(keep="--keep" in sys.argv[1:]):
            recorded = record(endpoints)
    except RuntimeError as error:
        sys.stderr.write(f"{error}\n")
        return 1
    responses = {key: scrub(recorded["responses"][key]) for key in sorted(recorded["responses"])}
    FIXTURES.write_text(
        json.dumps({"responses": responses}, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"recorded {len(responses)} of {len(endpoints)} reads -> {FIXTURES.relative_to(ROOT)}")
    for key, status in sorted(recorded["failures"].items()):
        print(f"  not recorded ({status}): {key}")
    return 0 if not recorded["failures"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
