"""HTTP API under /api, plus the dashboard's static export at / when present.

Serving the dashboard from the same origin removes the build-time API URL and
CORS: one container, one public endpoint. The recorder/harvester run in-process
when PH_RUN_RECORDER=1.
"""

import asyncio
import contextlib
import time
from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

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
# CORS only matters for `next dev` on another port; in production the dashboard is same-origin.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
api = APIRouter(prefix="/api")


def _last_hours(n: int) -> list[str]:
    now = time.time()
    return [hour_key(now - 3600 * i) for i in range(n - 1, -1, -1)]


@api.get("/health")
def health():
    return {"ok": True, "chain_scope": settings.chain_scope}


@api.get("/stats")
def stats():
    hours = _last_hours(24)
    chain = store.counters("creates_chain", hours)
    portal = store.counters("creates_portal", hours)
    mig = store.counters("migrations_chain", hours)
    mig_portal = store.counters("migrations_portal", hours)
    chain_total, portal_total = sum(chain.values()), sum(portal.values())
    full = settings.chain_scope == "full"
    return {
        "status": store.status(),
        "chain_scope": settings.chain_scope,
        # In "migrations" scope the chain feed never sees creates; PumpPortal is the only count.
        "creates_24h": chain_total if full else portal_total,
        "creates_24h_chain": chain_total,
        "creates_24h_portal": portal_total,
        # <1 means PumpPortal missed events; >1 means the chain feed did. Only meaningful in full scope.
        "portal_coverage": (portal_total / chain_total) if (full and chain_total) else None,
        "migrations_24h": sum(mig.values()),
        "migrations_24h_portal": sum(mig_portal.values()),
        "migrations_total": store.migration_count(),
        "hourly": [
            {
                "hour": h,
                "creates_chain": chain[h],
                "creates_portal": portal[h],
                "migrations": mig[h],
                "migrations_portal": mig_portal[h],
            }
            for h in hours
        ],
    }


@api.get("/migrations")
def migrations(limit: int = 100):
    return store.migrations(min(limit, 1000))


@api.get("/survivor/summary")
def survivor_summary():
    return summarize(store.survivor_rows(), settings.entry_delays_min, settings.horizons_min)


@api.get("/survivor/rows")
def survivor_rows(limit: int = 200):
    return store.survivor_rows(min(limit, 5000))


@api.get("/config")
def config():
    return settings.model_dump(exclude={"pumpportal_api_key", "redis_url", "solana_ws_url"})


app.include_router(api)

_static = (
    Path(settings.static_dir) if settings.static_dir else Path(__file__).resolve().parents[2] / "web" / "out"
)
if _static.is_dir():
    app.mount("/", StaticFiles(directory=str(_static), html=True), name="dashboard")
