"""Shared machinery for the load rehearsals: timing, percentiles, reporting.

Two rehearsals exist — the crowd arriving for the first time, and the people who
already use the service — and both are judged the same way, so the measuring
belongs in one place rather than in each of them.
"""

from __future__ import annotations

import math
import sys
import time
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


def refuse_if_not_local(base_url: str) -> bool:
    """Development only: these scripts create accounts and hammer the database."""
    host = (urlparse(base_url).hostname or "").casefold()
    if host in LOCAL_HOSTS:
        return False
    print(
        f"Отказ: {base_url} — не локальный адрес.\n"
        "Скрипт создаёт данные и нагружает базу; на боевом сервере это недопустимо.",
        file=sys.stderr,
    )
    return True


def percentile(sorted_values: list[float], share: float) -> float:
    """Nearest-rank percentile: the value a given share of requests stayed under."""
    rank = math.ceil(share * len(sorted_values))
    return sorted_values[min(len(sorted_values), max(1, rank)) - 1]


def pretend_address(index: int) -> str:
    """Give each simulated visitor its own address.

    Everything here leaves one machine, so without this the per-visitor rate
    limits would all count into a single bucket and the rehearsal would measure
    the limiter rather than the application. The development stack is configured
    to trust this header; production trusts it only from its own proxy.
    """
    return f"198.51.{(index // 250) % 250}.{index % 250 + 1}"


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
                    f"{percentile(values, 0.50):>8.2f}s"
                    f"{percentile(values, 0.95):>8.2f}s"
                    f"{percentile(values, 0.99):>8.2f}s"
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
        if any(
            "500" in reason or "database" in reason.lower()
            for step in self.failures
            for reason in self.failures[step]
        ):
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
