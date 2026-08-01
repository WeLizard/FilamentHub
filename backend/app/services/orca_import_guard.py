"""Keep two simultaneous OrcaSlicer imports of one account from duplicating rows.

An import looks for an existing row and creates one when it finds nothing. Two
slicers signed into the same account run that sequence at the same moment: both
look, neither finds, both create. The account lock makes the second one wait
until the first has committed, so it finds what the first wrote and updates it.

The lock is held until the transaction ends, so nothing has to release it by
hand, and it is keyed by the account, so different people never wait for each
other.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.print_profile import PrintProfile
from app.models.printer_profile import PrinterProfile

# "ORCA" in ASCII, so the number is recognisable in pg_locks during an incident.
_LOCK_NAMESPACE = 0x4F524341


async def hold_account_import_lock(db: AsyncSession, user_id: int) -> None:
    """Let one account's imports run one after another instead of racing."""
    if db.get_bind().dialect.name != "postgresql":
        return
    await db.execute(select(func.pg_advisory_xact_lock(_LOCK_NAMESPACE, user_id)))


async def profile_external_id_taken(
    db: AsyncSession,
    model: type[PrinterProfile] | type[PrintProfile],
    *,
    owner_user_id: int | None,
    external_id: str | None,
    exclude_id: int | None = None,
) -> bool:
    """Whether this account already has a profile carrying that OrcaSlicer id.

    The database refuses the second one anyway; asking first turns that refusal
    into an answer the person can act on.
    """
    if owner_user_id is None or not external_id:
        return False

    query = select(model.id).where(
        model.owner_user_id == owner_user_id,
        model.external_id == external_id,
    )
    if exclude_id is not None:
        query = query.where(model.id != exclude_id)

    return await db.scalar(query.limit(1)) is not None
