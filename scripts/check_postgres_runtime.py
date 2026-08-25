#!/usr/bin/env python3
"""Verify the production PostgreSQL contract against a disposable database."""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
POSTGRES_IMAGE = "postgres:15-alpine"
POSTGRES_USER = "filamenthub_contract"
POSTGRES_DB = "filamenthub_contract"
POSTGRES_PASSWORD = "runtime-contract-only"


def _run(
    command: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    capture_output: bool = False,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        check=check,
        text=True,
        capture_output=capture_output,
    )


def _wait_for_postgres(container_name: str) -> None:
    for _ in range(60):
        result = _run(
            [
                "docker",
                "exec",
                container_name,
                "pg_isready",
                "-U",
                POSTGRES_USER,
                "-d",
                POSTGRES_DB,
            ],
            capture_output=True,
            check=False,
        )
        if result.returncode == 0:
            return
        time.sleep(0.5)

    logs = _run(
        ["docker", "logs", container_name], capture_output=True, check=False
    ).stdout.strip()
    raise RuntimeError(f"PostgreSQL did not become ready. Container log:\n{logs}")


def _published_port(container_name: str) -> int:
    result = _run(
        [
            "docker",
            "inspect",
            "--format",
            '{{(index (index .NetworkSettings.Ports "5432/tcp") 0).HostPort}}',
            container_name,
        ],
        capture_output=True,
    )
    port = int(result.stdout.strip())
    if not 1 <= port <= 65535:
        raise RuntimeError(f"Docker returned an invalid PostgreSQL port: {port}")
    return port


def _runtime_environment(port: int) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "POSTGRES_HOST": "127.0.0.1",
            "POSTGRES_PORT": str(port),
            "POSTGRES_USER": POSTGRES_USER,
            "POSTGRES_PASSWORD": POSTGRES_PASSWORD,
            "POSTGRES_DB": POSTGRES_DB,
            "SECRET_KEY": "postgres-runtime-contract-secret",
            "REDIS_URL": "memory://",
            "DEBUG": "false",
        }
    )
    return env


def _single_alembic_head(env: dict[str, str]) -> str:
    result = _run(
        [sys.executable, "-m", "alembic", "heads"],
        cwd=BACKEND,
        env=env,
        capture_output=True,
    )
    heads = [
        line.split()[0]
        for line in result.stdout.splitlines()
        if line.strip().endswith("(head)")
    ]
    if len(heads) != 1:
        raise RuntimeError(f"Expected one Alembic head, found: {heads or 'none'}")
    return heads[0]


async def _verify_application_contract(expected_head: str) -> None:
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy import inspect, text

    import app.models  # noqa: F401 - registers every ORM table in Base.metadata
    from app.db.base import Base
    from app.db.session import AsyncSessionLocal, engine
    from app.main import app
    from app.models.brand import Brand
    from app.models.filament import Filament
    from app.models.printer import Printer

    try:
        async with engine.begin() as connection:
            server_version = int(
                await connection.scalar(text("SHOW server_version_num"))
            )
            current_head = await connection.scalar(
                text("SELECT version_num FROM alembic_version")
            )
            database_tables = await connection.run_sync(
                lambda sync_connection: set(inspect(sync_connection).get_table_names())
            )

        if not 150000 <= server_version < 160000:
            raise RuntimeError(
                f"Expected PostgreSQL 15, server reported {server_version}"
            )
        if current_head != expected_head:
            raise RuntimeError(
                f"Database revision {current_head!r} does not match head {expected_head!r}"
            )

        missing_tables = sorted(set(Base.metadata.tables) - database_tables)
        if missing_tables:
            raise RuntimeError(
                "Migrated database is missing ORM tables: " + ", ".join(missing_tables)
            )

        async with AsyncSessionLocal() as session:
            brand = Brand(
                name="PostgreSQL Runtime Contract",
                slug="postgres-runtime-contract",
                active=True,
            )
            printer = Printer(
                name="Runtime Contract Printer",
                manufacturer="FilamentHub",
                model="Contract 15",
                slug="runtime-contract-printer",
                active=True,
            )
            session.add_all([brand, printer])
            await session.flush()
            filament = Filament(
                brand_id=brand.id,
                name="Runtime Contract PLA",
                slug="runtime-contract-pla",
                material_type="PLA",
                color_name="Contract Blue",
                color_hex="#3366FF",
                active=True,
            )
            session.add(filament)
            await session.commit()
            filament_id = filament.id
            printer_id = printer.id

        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://contract"
        ) as client:
            filament_response = await client.get(f"/api/v1/filaments/{filament_id}")
            printer_response = await client.get(f"/api/v1/printers/{printer_id}")
            ranked_catalog_response = await client.get(
                "/api/v1/filaments/", params={"printer_id": printer_id}
            )
            removed_filament_route = await client.get(
                f"/api/v1/filaments/{filament_id}/compatible-printers"
            )
            removed_printer_route = await client.get(
                f"/api/v1/printers/{printer_id}/compatible-filaments"
            )

        expected_statuses = {
            "filament detail": (filament_response.status_code, 200),
            "printer detail": (printer_response.status_code, 200),
            "printer-ranked catalog": (ranked_catalog_response.status_code, 200),
            "removed compatible-printers route": (
                removed_filament_route.status_code,
                404,
            ),
            "removed compatible-filaments route": (
                removed_printer_route.status_code,
                404,
            ),
        }
        failures = [
            f"{name}: got {actual}, expected {expected}"
            for name, (actual, expected) in expected_statuses.items()
            if actual != expected
        ]
        if failures:
            raise RuntimeError("PostgreSQL API smoke failed: " + "; ".join(failures))
    finally:
        await engine.dispose()


def main() -> int:
    if shutil.which("docker") is None:
        raise RuntimeError("Docker is required for the PostgreSQL runtime contract")

    container_name = f"fh-postgres-contract-{uuid.uuid4().hex[:12]}"
    started = False
    try:
        print(f"Starting disposable {POSTGRES_IMAGE} database...", flush=True)
        _run(
            [
                "docker",
                "run",
                "--detach",
                "--rm",
                "--name",
                container_name,
                "--publish",
                "127.0.0.1::5432",
                "--env",
                f"POSTGRES_DB={POSTGRES_DB}",
                "--env",
                f"POSTGRES_USER={POSTGRES_USER}",
                "--env",
                f"POSTGRES_PASSWORD={POSTGRES_PASSWORD}",
                "--tmpfs",
                "/var/lib/postgresql/data:rw,noexec,nosuid",
                POSTGRES_IMAGE,
            ],
            capture_output=True,
        )
        started = True
        _wait_for_postgres(container_name)
        env = _runtime_environment(_published_port(container_name))

        print("Applying every Alembic migration to the empty database...", flush=True)
        migration = _run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=BACKEND,
            env=env,
            capture_output=True,
            check=False,
        )
        if migration.returncode != 0:
            if migration.stdout:
                print(migration.stdout, file=sys.stderr)
            if migration.stderr:
                print(migration.stderr, file=sys.stderr)
            raise RuntimeError(
                f"Alembic upgrade failed with exit code {migration.returncode}"
            )
        expected_head = _single_alembic_head(env)

        os.environ.update(
            {
                key: env[key]
                for key in (
                    "POSTGRES_HOST",
                    "POSTGRES_PORT",
                    "POSTGRES_USER",
                    "POSTGRES_PASSWORD",
                    "POSTGRES_DB",
                    "SECRET_KEY",
                    "REDIS_URL",
                    "DEBUG",
                )
            }
        )
        sys.path.insert(0, str(BACKEND))
        print(
            "Checking migrated schema and PostgreSQL-backed API paths...",
            flush=True,
        )
        original_cwd = Path.cwd()
        # Settings normally load .env from the process working directory. A
        # runtime contract must neither depend on nor echo a developer's
        # credentials, so import the application from an empty directory.
        with tempfile.TemporaryDirectory(prefix="fh-postgres-contract-") as clean_cwd:
            try:
                os.chdir(clean_cwd)
                asyncio.run(_verify_application_contract(expected_head))
            finally:
                # Windows cannot remove the temporary directory while it is the
                # process working directory.
                os.chdir(original_cwd)
        print("PostgreSQL 15 runtime contract passed.", flush=True)
        return 0
    finally:
        if started:
            _run(
                ["docker", "rm", "--force", container_name],
                capture_output=True,
                check=False,
            )


if __name__ == "__main__":
    raise SystemExit(main())
