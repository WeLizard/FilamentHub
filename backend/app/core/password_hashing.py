"""Keep a crowd from turning password checks into a queue nobody outlives.

Checking a password is deliberately slow — that slowness is what makes a stolen
database expensive to crack — and it is one of the few parts of a request that
needs a processor core to itself. When more people arrive at once than the
machine has cores, the checks pile up behind each other: everyone waits, nobody
is told why, and the wait outlasts the browser's patience.

So the number of checks running at once is capped, and whoever cannot get a turn
within a short wait is told plainly to come back rather than left hanging. The
hashing itself is unchanged: nothing here trades away strength.
"""

from __future__ import annotations

from app.core.capacity import Gate
from app.core.config import settings
from app.core.security import get_password_hash, verify_password

_gate = Gate(
    "password",
    settings.PASSWORD_HASH_CONCURRENCY,
    settings.PASSWORD_HASH_WAIT_SECONDS,
)


async def hash_password(password: str) -> str:
    """Hash a password, waiting for a turn and giving up rather than queueing."""
    return await _gate.run(get_password_hash, password)


async def check_password(password: str, password_hash: str) -> bool:
    """Check a password the same way."""
    return await _gate.run(verify_password, password, password_hash)
