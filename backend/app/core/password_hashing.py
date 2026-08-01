"""Keep a crowd from turning password checks into a queue nobody outlives.

Checking a password is deliberately slow — that slowness is what makes a stolen
database expensive to crack — and it is the one part of a request that needs a
processor core to itself. When more people arrive at once than the machine has
cores, the checks pile up behind each other: everyone waits, nobody is told
why, and the wait outlasts the browser's patience.

So the number of checks running at once is capped, and whoever cannot get a
turn within a short wait is told plainly to come back rather than left hanging.
The hashing itself is unchanged: nothing here trades away strength.

The cap is per worker process, so a machine running four of them allows four
times this many at once.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from fastapi import status
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.core.errors import ERR_SERVER_BUSY, raise_error
from app.core.security import get_password_hash, verify_password

# One limiter per event loop: asyncio primitives refuse to be shared across
# loops, and tests, scripts and the server each bring their own.
_limiters: dict[asyncio.AbstractEventLoop, asyncio.Semaphore] = {}


def _limiter() -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    limiter = _limiters.get(loop)
    if limiter is None:
        limiter = asyncio.Semaphore(settings.PASSWORD_HASH_CONCURRENCY)
        _limiters[loop] = limiter
    return limiter


async def _in_turn(work: Callable[..., Any], *args: Any) -> Any:
    limiter = _limiter()
    try:
        await asyncio.wait_for(limiter.acquire(), settings.PASSWORD_HASH_WAIT_SECONDS)
    except (TimeoutError, asyncio.TimeoutError):
        raise_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            ERR_SERVER_BUSY,
            headers={"Retry-After": "60"},
        )

    try:
        return await run_in_threadpool(work, *args)
    finally:
        limiter.release()


async def hash_password(password: str) -> str:
    """Hash a password, waiting for a turn and giving up rather than queueing."""
    return await _in_turn(get_password_hash, password)


async def check_password(password: str, password_hash: str) -> bool:
    """Check a password the same way."""
    return await _in_turn(verify_password, password, password_hash)
