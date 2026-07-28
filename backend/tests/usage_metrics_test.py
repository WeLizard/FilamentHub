"""Calculator usage counters: day-keyed totals, distinct users, silent failure."""

import pytest

from app.services import usage_metrics_service as metrics


class FakeRedis:
    """Enough of the Redis surface for the counters: plain keys and the
    HyperLogLog behaviour we rely on (union across keys via multi-key pfcount)."""

    def __init__(self) -> None:
        self.values: dict[str, int] = {}
        self.sets: dict[str, set] = {}

    def pipeline(self):
        return FakePipeline(self)

    async def mget(self, keys):
        return [self.values.get(key) for key in keys]

    async def pfcount(self, *keys):
        merged: set = set()
        for key in keys:
            merged |= self.sets.get(key, set())
        return len(merged)


class FakePipeline:
    def __init__(self, redis: FakeRedis) -> None:
        self.redis = redis
        self.ops: list = []
        self.log: list = []

    def incr(self, key):
        self.ops.append(("incr", key, None))
        self.log.append(("incr", key, None))

    def expire(self, key, ttl):
        self.ops.append(("expire", key, ttl))
        self.log.append(("expire", key, ttl))

    def pfadd(self, key, value):
        self.ops.append(("pfadd", key, value))
        self.log.append(("pfadd", key, value))

    async def execute(self):
        for op, key, value in self.ops:
            if op == "incr":
                self.redis.values[key] = self.redis.values.get(key, 0) + 1
            elif op == "pfadd":
                self.redis.sets.setdefault(key, set()).add(value)
        self.ops.clear()


class BrokenRedis:
    def pipeline(self):
        raise RuntimeError("redis is down")

    async def mget(self, keys):
        raise RuntimeError("redis is down")


@pytest.fixture
def fake_redis(monkeypatch) -> FakeRedis:
    redis = FakeRedis()
    monkeypatch.setattr(metrics, "_redis", lambda: redis)
    return redis


@pytest.mark.asyncio
async def test_counts_estimates_and_distinct_users(fake_redis: FakeRedis) -> None:
    await metrics.record_calculator_estimate(1, "combined")
    await metrics.record_calculator_estimate(1, "combined")
    await metrics.record_calculator_estimate(2, "by_weight")

    usage = await metrics.calculator_usage(("by_weight", "by_time", "combined"))

    assert usage["available"] is True
    assert usage["estimates_24h"] == 3
    assert usage["estimates_7d"] == 3
    assert usage["users_24h"] == 2
    assert usage["methods_30d"] == {"by_weight": 1, "by_time": 0, "combined": 2}


@pytest.mark.asyncio
async def test_expiry_is_set_on_every_key(fake_redis: FakeRedis) -> None:
    pipe = FakePipeline(fake_redis)
    fake_redis.pipeline = lambda: pipe

    await metrics.record_calculator_estimate(7, "by_time")
    expired = {key for op, key, _ in pipe.log if op == "expire"}
    written = {key for op, key, _ in pipe.log if op in ("incr", "pfadd")}

    # Without a TTL on each key the counters would accumulate forever.
    assert written and written == expired


@pytest.mark.asyncio
async def test_recording_never_raises(monkeypatch) -> None:
    monkeypatch.setattr(metrics, "_redis", lambda: BrokenRedis())

    await metrics.record_calculator_estimate(1, "combined")

    usage = await metrics.calculator_usage(("combined",))
    assert usage == {"available": False}
