"""Fill the CRM search index for customers created before it existed.

The table the migration adds starts empty, so until this runs a search finds nothing
for older records. Rows whose protected fields cannot be read are reported and skipped:
there is nothing to index and nothing this script can do about it.

    python scripts/backfill_crm_search_tokens.py [--dry-run]
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
# Run either from a checkout, where the application lives under backend/, or from
# inside the container, where that directory is already the working root.
_BACKEND = PROJECT_ROOT / "backend"
sys.path.insert(0, str(_BACKEND if _BACKEND.is_dir() else PROJECT_ROOT))

from sqlalchemy import select  # noqa: E402

from app.core.field_encryption import FieldDecryptionError, decrypt_field  # noqa: E402
from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.crm import CrmCustomer  # noqa: E402
from app.services.crm_customer_search_service import (  # noqa: E402
    ENCRYPTED_FIELDS,
    reindex_customer,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


async def main() -> int:
    args = _parse_args()
    indexed = 0
    skipped: list[int] = []

    async with AsyncSessionLocal() as db:
        customers = (await db.execute(select(CrmCustomer))).scalars().all()
        for customer in customers:
            try:
                plain = {
                    name: decrypt_field(getattr(customer, name))
                    for name in ENCRYPTED_FIELDS
                }
            except FieldDecryptionError:
                skipped.append(customer.id)
                continue
            if not args.dry_run:
                await reindex_customer(db, customer, plain)
            indexed += 1
        if not args.dry_run:
            await db.commit()

    print(f"Проиндексировано клиентов: {indexed}")
    if skipped:
        print(f"Пропущено (поля не читаются): {len(skipped)} — id {skipped}")
    if args.dry_run:
        print("Это был пробный прогон, ничего не записано.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
