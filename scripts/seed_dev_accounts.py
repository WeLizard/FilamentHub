#!/usr/bin/env python3
"""Fill the development database with people who already use the service.

The newcomer rehearsal only ever measured the first minute of an account's life:
sign up, look around, leave. Everything the product is actually for — spools,
machines, the calculator, quotes — belongs to people who already have an
inventory, and some of it is closed to a fresh account entirely: the calculator
needs a confirmed address and an entitlement.

So this makes established accounts: address confirmed, entitlement granted,
machines and spools already on the shelf. They are all created with one known
password so a load run can sign in as any of them.

Development only. The script refuses any database but a local one.

    POSTGRES_PORT=5433 POSTGRES_DB=filamenthub_dev POSTGRES_PASSWORD=devpass123 \
        python scripts/seed_dev_accounts.py --accounts 50
"""

from __future__ import annotations

import argparse
import asyncio
import os
import random
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

for stream in (sys.stdout, sys.stderr):
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(encoding="utf-8", errors="replace")

LOCAL_DB_HOSTS = {"localhost", "127.0.0.1", "::1", "postgres-dev"}
# The load run signs in with this; it never leaves a development machine.
PASSWORD = "qwerty123"
EMAIL_PREFIX = "established"


async def seed(accounts: int, spools_each: int, printers_each: int) -> int:
    from app.core.config import settings
    from app.core.security import get_password_hash
    from app.db.session import AsyncSessionLocal
    from app.models.filament import Filament
    from app.models.subscription import Subscription, SubscriptionStatus
    from app.models.user import User, UserRole
    from app.models.user_printer_device import UserPrinterDevice
    from app.models.user_spool import UserSpool, UserSpoolState
    from app.services.legal_acceptance_service import (
        CURRENT_PERSONAL_DATA_CONSENT_VERSION,
        CURRENT_PRIVACY_POLICY_VERSION,
        CURRENT_TERMS_VERSION,
    )

    if settings.POSTGRES_HOST.casefold() not in LOCAL_DB_HOSTS:
        print(
            f"Отказ: база на {settings.POSTGRES_HOST} — не локальная.\n"
            "Скрипт заводит учётные записи; боевой базе это ни к чему.",
            file=sys.stderr,
        )
        return 2

    # One hash for everyone: Argon2id costs a fifth of a second, and fifty of
    # them would be a minute spent proving nothing.
    password_hash = get_password_hash(PASSWORD)
    run = f"{int(time.time()):x}"
    now = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as db:
        from sqlalchemy import select

        filament_ids = list(
            (await db.execute(select(Filament.id).where(Filament.active.is_(True)).limit(500)))
            .scalars()
            .all()
        )
        if not filament_ids:
            print(
                "В базе нет материалов — сначала наполните каталог "
                "(scripts/seed_dev_volume.py), иначе катушки не к чему привязать.",
                file=sys.stderr,
            )
            return 3

        made = 0
        for index in range(accounts):
            user = User(
                email=f"{EMAIL_PREFIX}-{run}-{index:04d}@example.com",
                username=f"{EMAIL_PREFIX}_{run}_{index:04d}",
                password_hash=password_hash,
                role=UserRole.USER,
                active=True,
                email_verified=True,
                terms_version_accepted=CURRENT_TERMS_VERSION,
                personal_data_consent_version=CURRENT_PERSONAL_DATA_CONSENT_VERSION,
                privacy_policy_version_presented=CURRENT_PRIVACY_POLICY_VERSION,
                legal_accepted_at=now,
            )
            db.add(user)
            await db.flush()

            # Complimentary rather than trialing: a trial expires, and a
            # rehearsal run months from now should still reach the calculator.
            db.add(
                Subscription(
                    user_id=user.id,
                    status=SubscriptionStatus.ACTIVE,
                    is_comp=True,
                    current_period_end=now + timedelta(days=3650),
                )
            )

            for machine in range(random.randint(1, printers_each)):
                db.add(
                    UserPrinterDevice(
                        user_id=user.id,
                        name=f"Voron {run}-{index:04d}-{machine}",
                    )
                )

            for _ in range(random.randint(spools_each // 2, spools_each)):
                initial = random.choice([1000.0, 750.0, 500.0, 2000.0])
                db.add(
                    UserSpool(
                        user_id=user.id,
                        filament_id=random.choice(filament_ids),
                        initial_weight_g=initial,
                        used_weight_g=round(random.uniform(0, initial * 0.8), 1),
                        state=random.choice(
                            [UserSpoolState.shelf, UserSpoolState.active, UserSpoolState.empty]
                        ),
                        price=round(random.uniform(900, 3500), 2),
                        source="manual",
                    )
                )

            made += 1
            if made % 25 == 0:
                await db.commit()
                print(f"учётных записей: {made}")

        await db.commit()

    print(f"готово: {made} действующих пользователей, пароль у всех «{PASSWORD}»")
    print(f"адреса вида {EMAIL_PREFIX}-{run}-0000@example.com")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--accounts", type=int, default=50)
    parser.add_argument("--spools-each", type=int, default=30, help="верхняя граница")
    parser.add_argument("--printers-each", type=int, default=3, help="верхняя граница")
    args = parser.parse_args()
    return asyncio.run(seed(args.accounts, args.spools_each, args.printers_each))


if __name__ == "__main__":
    raise SystemExit(main())
