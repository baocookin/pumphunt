"""Persistence: hourly counters, migration registry, harvested survivor rows, status.

Redis in prod, in-memory for tests. JSONL files (see recorder/harvester) are the
durable dataset; Redis is the queryable view for the API and the harvester queue.
"""

import json
import time
from typing import Any, Protocol

MAX_SURVIVOR_ROWS = 200_000


def hour_key(ts: float) -> str:
    return time.strftime("%Y-%m-%dT%H", time.gmtime(ts))


def day_key(ts: float) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(ts))


class Store(Protocol):
    def incr(self, name: str, hour: str, n: int = 1) -> None: ...
    def counters(self, name: str, hours: list[str]) -> dict[str, int]: ...
    def add_migration(self, row: dict[str, Any]) -> bool: ...
    def migrations(self, limit: int = 100) -> list[dict[str, Any]]: ...
    def migration_count(self) -> int: ...
    def pending_harvest(self, before_ts: float, limit: int) -> list[dict[str, Any]]: ...
    def mark_harvested(self, mint: str, metrics: dict[str, Any]) -> None: ...
    def survivor_rows(self, limit: int = MAX_SURVIVOR_ROWS) -> list[dict[str, Any]]: ...
    def set_status(self, **kv: Any) -> None: ...
    def status(self) -> dict[str, Any]: ...


class MemoryStore:
    def __init__(self) -> None:
        self._counters: dict[str, dict[str, int]] = {}
        self._migrations: dict[str, dict[str, Any]] = {}
        self._survivor: list[dict[str, Any]] = []
        self._status: dict[str, Any] = {}

    def incr(self, name: str, hour: str, n: int = 1) -> None:
        self._counters.setdefault(name, {})
        self._counters[name][hour] = self._counters[name].get(hour, 0) + n

    def counters(self, name: str, hours: list[str]) -> dict[str, int]:
        c = self._counters.get(name, {})
        return {h: c.get(h, 0) for h in hours}

    def add_migration(self, row: dict[str, Any]) -> bool:
        if row["mint"] in self._migrations:
            return False
        self._migrations[row["mint"]] = dict(row, harvested=False)
        return True

    def migrations(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = sorted(self._migrations.values(), key=lambda r: r["ts"], reverse=True)
        return rows[:limit]

    def migration_count(self) -> int:
        return len(self._migrations)

    def pending_harvest(self, before_ts: float, limit: int) -> list[dict[str, Any]]:
        rows = [r for r in self._migrations.values() if not r["harvested"] and r["ts"] <= before_ts]
        return sorted(rows, key=lambda r: r["ts"])[:limit]

    def mark_harvested(self, mint: str, metrics: dict[str, Any]) -> None:
        if mint in self._migrations:
            self._migrations[mint]["harvested"] = True
        self._survivor.append(metrics)
        del self._survivor[:-MAX_SURVIVOR_ROWS]

    def survivor_rows(self, limit: int = MAX_SURVIVOR_ROWS) -> list[dict[str, Any]]:
        return self._survivor[-limit:]

    def set_status(self, **kv: Any) -> None:
        self._status.update(kv)

    def status(self) -> dict[str, Any]:
        return dict(self._status)


class RedisStore:
    K_MIG, K_PENDING, K_SURV, K_STATUS = "ph:migrations", "ph:pending", "ph:survivor", "ph:status"

    def __init__(self, url: str) -> None:
        import redis

        self.r = redis.Redis.from_url(url, decode_responses=True)

    @staticmethod
    def _ck(name: str) -> str:
        return f"ph:counter:{name}"

    def incr(self, name: str, hour: str, n: int = 1) -> None:
        self.r.hincrby(self._ck(name), hour, n)

    def counters(self, name: str, hours: list[str]) -> dict[str, int]:
        if not hours:
            return {}
        vals = self.r.hmget(self._ck(name), hours)
        return {h: int(v or 0) for h, v in zip(hours, vals, strict=True)}

    def add_migration(self, row: dict[str, Any]) -> bool:
        row = dict(row, harvested=False)
        added = self.r.hsetnx(self.K_MIG, row["mint"], json.dumps(row))
        if added:
            self.r.zadd(self.K_PENDING, {row["mint"]: row["ts"]})
        return bool(added)

    def migrations(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = [json.loads(v) for v in self.r.hvals(self.K_MIG)]
        rows.sort(key=lambda r: r["ts"], reverse=True)
        return rows[:limit]

    def migration_count(self) -> int:
        return self.r.hlen(self.K_MIG)

    def pending_harvest(self, before_ts: float, limit: int) -> list[dict[str, Any]]:
        mints = self.r.zrangebyscore(self.K_PENDING, "-inf", before_ts, start=0, num=limit)
        if not mints:
            return []
        return [json.loads(v) for v in self.r.hmget(self.K_MIG, mints) if v]

    def mark_harvested(self, mint: str, metrics: dict[str, Any]) -> None:
        raw = self.r.hget(self.K_MIG, mint)
        p = self.r.pipeline()
        if raw:
            p.hset(self.K_MIG, mint, json.dumps(dict(json.loads(raw), harvested=True)))
        p.zrem(self.K_PENDING, mint)
        p.rpush(self.K_SURV, json.dumps(metrics))
        p.ltrim(self.K_SURV, -MAX_SURVIVOR_ROWS, -1)
        p.execute()

    def survivor_rows(self, limit: int = MAX_SURVIVOR_ROWS) -> list[dict[str, Any]]:
        return [json.loads(v) for v in self.r.lrange(self.K_SURV, -limit, -1)]

    def set_status(self, **kv: Any) -> None:
        self.r.hset(self.K_STATUS, mapping={k: json.dumps(v) for k, v in kv.items()})

    def status(self) -> dict[str, Any]:
        return {k: json.loads(v) for k, v in self.r.hgetall(self.K_STATUS).items()}


def make_store(redis_url: str | None) -> Store:
    if redis_url:
        try:
            s = RedisStore(redis_url)
            s.r.ping()
            return s
        except Exception as exc:  # noqa: BLE001 - degrade loudly, keep recording
            print(f"[store] redis unavailable ({exc}); using in-memory store")
    return MemoryStore()
