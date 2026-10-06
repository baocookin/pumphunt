"""HTTP API under /api, plus the dashboard's static export at / when present.

Serving the dashboard from the same origin removes the build-time API URL and
CORS: one container, one public endpoint. The recorder/harvester run in-process
when PH_RUN_RECORDER=1.
"""

import asyncio
import contextlib
import csv
import io
import json
import time
from pathlib import Path

import httpx
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .fills import size_key
from .recorder import Recorder
from .rpc import SolanaRpc, describe_http_error, http_url_from_ws, migration_from_tx, tx_diagnostics
from .store import hour_key, make_store
from .survivor import latest_by_mint, summarize

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
    return {"ok": True, "chain_scope": settings.chain_scope, "build_sha": settings.build_sha}


@api.get("/stats")
def stats():
    hours = _last_hours(24)
    chain = store.counters("creates_chain", hours)
    portal = store.counters("creates_portal", hours)
    # Mints whose pool is known from chain (websocket event or getTransaction), each counted once.
    mig = store.counters("migrations_confirmed", hours)
    mig_portal = store.counters("migrations_portal", hours)
    chain_total, portal_total = sum(chain.values()), sum(portal.values())
    full = settings.chain_scope == "full"
    return {
        "status": store.status(),
        "build_sha": settings.build_sha,
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
    return summarize(
        store.survivor_rows(), settings.entry_delays_min, settings.horizons_min, settings.fill_sizes_sol
    )


@api.get("/survivor/rows")
def survivor_rows(limit: int = 200):
    return store.survivor_rows(min(limit, 5000))


@api.get("/files")
def files():
    """What is on the data volume: the JSONL files are the durable dataset."""
    d = Path(settings.data_dir)
    out = []
    if d.is_dir():
        for p in sorted(d.iterdir()):
            if p.is_file():
                st = p.stat()
                out.append({"name": p.name, "bytes": st.st_size, "mtime": st.st_mtime})
    return {"dir": str(d), "files": out}


def _jsonl(rows):
    for r in rows:
        yield json.dumps(r, separators=(",", ":")) + "\n"


@api.get("/export/migrations.jsonl")
def export_migrations():
    rows = store.migrations(limit=1_000_000)
    return StreamingResponse(_jsonl(rows), media_type="application/x-ndjson")


@api.get("/export/survivor.jsonl")
def export_survivor_jsonl():
    return StreamingResponse(_jsonl(store.survivor_rows()), media_type="application/x-ndjson")


_SURVIVOR_COLS = [
    "mint",
    "pool",
    "t0",
    "slot",
    "source",
    "quote_mint",
    "migration_sol",
    "pool_resolved",
    "n_candles",
    "no_data",
    "reason",
    "alive_24h",
    "reserve_usd_now",
    "vol_0_30m",
    "vol_30_60m",
    "vol_1_6h",
    "vol_6_24h",
    "harvested_at",
]


# Per primary-cell detail of the executable model: what was observable at entry and how each
# execution model scored the trade.
_FILL_DETAIL = [
    "model",
    "net_ghost",
    "net_replay",
    "net_persist",
    "real_in_sol",
    "virtual_in_sol",
    "liquidity_in_sol",
    "last_trade_age_in_s",
    "exit_stale_s",
    "impact_in",
    "exit_capped",
    "mdd",
]
_FLOW = ["swaps", "buys", "sells", "traders", "buyers", "net_sol", "top_seller_share", "creator_sell_sol"]


def survivor_csv(
    rows, delays, horizons, sizes=(), detail_cell: str = "d30_h60", flow_entry: str = "d30"
) -> str:
    """One row per token (latest harvest): candle marks per cell, executable net per size and
    cell, the detail of `detail_cell` per size, order flow before `flow_entry`, swap coverage."""
    cells = [f"d{d}_h{h}" for d in delays for h in horizons]
    buf = io.StringIO()
    w = csv.writer(buf)
    head = _SURVIVOR_COLS + ["fills_version"]
    head += [f"{c}_{m}" for c in cells for m in ("net", "gross", "mdd", "exit_stale_s")]
    head += [f"fill{size_key(s)}_{c}_net" for s in sizes for c in cells]
    head += [f"fill{size_key(s)}_{detail_cell}_{m}" for s in sizes for m in _FILL_DETAIL]
    head += [f"flow_{flow_entry}_{m}" for m in _FLOW]
    head += ["swaps_fetched", "window_method", "window_complete", "window_chain_breaks"]
    head += ["states_unresolved", "swap_credits"]
    w.writerow(head)
    for r in latest_by_mint(rows):
        line = [r.get(k) for k in _SURVIVOR_COLS] + [r.get("fills_version")]
        for c in cells:
            cell = (r.get("cells") or {}).get(c) or {}
            line += [cell.get("net"), cell.get("gross"), cell.get("mdd"), cell.get("exit_stale_s")]
        fills = r.get("fills") or {}

        def fill(c: str, sz: float, fills: dict = fills) -> dict:
            by_size = fills.get(c) or {}
            return by_size.get(size_key(sz)) or by_size.get(str(float(sz))) or {}

        for s in sizes:
            for c in cells:
                line.append(fill(c, s).get("net"))
        for s in sizes:
            d = fill(detail_cell, s)
            line += [d.get(m) for m in _FILL_DETAIL]
        fl = (r.get("flow") or {}).get(flow_entry) or {}
        line += [fl.get(m) for m in _FLOW]
        sw = r.get("swaps") or {}
        win = sw.get("window") or {}
        line += [sw.get("swaps"), win.get("method"), win.get("complete"), win.get("chain_breaks")]
        line += [(sw.get("states") or {}).get("unresolved"), sw.get("credits")]
        w.writerow(line)
    return buf.getvalue()


@api.get("/export/survivor.csv")
def export_survivor_csv():
    text = survivor_csv(
        store.survivor_rows(), settings.entry_delays_min, settings.horizons_min, settings.fill_sizes_sol
    )
    return PlainTextResponse(text, media_type="text/csv")


@api.get("/debug/tx/{signature}")
async def debug_tx(signature: str):
    """Fetch one transaction through the configured RPC and show how the recorder reads it."""
    url = settings.solana_http_url or http_url_from_ws(settings.solana_ws_url)
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            rpc = SolanaRpc(client, url, max_tx_version=settings.rpc_max_tx_version)
            tx = await rpc.get_transaction(signature)
    except httpx.HTTPError as exc:
        return {"signature": signature, "error": describe_http_error(exc)}
    return {"signature": signature, "migration": migration_from_tx(tx), "diagnostics": tx_diagnostics(tx)}


@api.get("/config")
def config():
    return settings.model_dump(exclude={"pumpportal_api_key", "redis_url", "solana_ws_url", "gecko_api_key"})


app.include_router(api)

_static = (
    Path(settings.static_dir) if settings.static_dir else Path(__file__).resolve().parents[2] / "web" / "out"
)
if _static.is_dir():
    app.mount("/", StaticFiles(directory=str(_static), html=True), name="dashboard")
