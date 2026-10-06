"""HTTP API for the dashboard. Hosts the recorder/harvester in-process when PH_RUN_RECORDER=1."""

import asyncio
import contextlib
import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .recorder import Recorder
from .store import hour_key, make_store
from .survivor import summarize

store = make_store(settings.redis_url)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(Recorder(settings, store).run()) if settings.run_recorder else None
    try:
        yield
    finally:
        if task:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


app = FastAPI(title="pumphunt", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def _last_hours(n: int) -> list[str]:
    now = time.time()
    return [hour_key(now - 3600 * i) for i in range(n - 1, -1, -1)]


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/stats")
def stats():
    hours = _last_hours(24)
    chain = store.counters("creates_chain", hours)
    portal = store.counters("creates_portal", hours)
    mig = store.counters("migrations_chain", hours)
    chain_total, portal_total = sum(chain.values()), sum(portal.values())
    return {
        "status": store.status(),
        "creates_24h_chain": chain_total,
        "creates_24h_portal": portal_total,
        # <1 means PumpPortal missed events; >1 means the chain feed did. Either way: evidence.
        "portal_coverage": (portal_total / chain_total) if chain_total else None,
        "migrations_24h": sum(mig.values()),
        "migrations_total": store.migration_count(),
        "hourly": [
            {"hour": h, "creates_chain": chain[h], "creates_portal": portal[h], "migrations": mig[h]}
            for h in hours
        ],
    }


@app.get("/migrations")
def migrations(limit: int = 100):
    return store.migrations(min(limit, 1000))


@app.get("/survivor/summary")
def survivor_summary():
    return summarize(store.survivor_rows(), settings.entry_delays_min, settings.horizons_min)


@app.get("/survivor/rows")
def survivor_rows(limit: int = 200):
    return store.survivor_rows(min(limit, 5000))


@app.get("/config")
def config():
    return settings.model_dump(exclude={"pumpportal_api_key", "redis_url", "solana_ws_url"})
