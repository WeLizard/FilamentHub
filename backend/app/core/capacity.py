"""Let heavy work run a few at a time, and answer the rest instead of queueing.

Some requests need a processor core to themselves for a noticeable time: hashing
a password, rendering a document, reading a sliced model. The machine has two
cores. When more of those arrive at once than it can carry, waiting is not a
plan — everyone sits, nobody is told why, and the wait outlasts the browser's
patience.

So each kind of heavy work gets a gate: a fixed number of turns, a short wait
for one, and a plain answer to whoever cannot get in. The work itself runs off
the event loop, so a long job never stops the process from answering everything
else.

Gates count per worker process; a machine running four of them allows four times
the number set here.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from fastapi import status
from starlette.concurrency import run_in_threadpool

from app.core.errors import ERR_SERVER_BUSY, raise_error


class Gate:
    """A fixed number of turns at one kind of heavy work."""

    def __init__(self, name: str, slots: int, wait_seconds: float) -> None:
        self.name = name
        self.slots = slots
        self.wait_seconds = wait_seconds
        # One limiter per event loop: asyncio primitives refuse to be shared
        # across loops, and tests, scripts and the server each bring their own.
        self._limiters: dict[asyncio.AbstractEventLoop, asyncio.Semaphore] = {}

    def _limiter(self) -> asyncio.Semaphore:
        loop = asyncio.get_running_loop()
        limiter = self._limiters.get(loop)
        if limiter is None:
            limiter = asyncio.Semaphore(self.slots)
            self._limiters[loop] = limiter
        return limiter

    def reset(self) -> None:
        """Forget existing limiters — for tests that change the size."""
        self._limiters.clear()

    async def run(self, work: Callable[..., Any], *args: Any) -> Any:
        """Wait briefly for a turn, then do the work off the event loop."""
        limiter = self._limiter()
        try:
            await asyncio.wait_for(limiter.acquire(), self.wait_seconds)
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
