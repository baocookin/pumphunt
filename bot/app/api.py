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
import re
import time
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .explore import explore_c, explore_s
from .fills import size_key
from .prereg import evaluate
from .recorder import Recorder
from .rpc import SolanaRpc, describe_http_error, http_url_from_ws, migration_from_tx, tx_diagnostics
from .sniper import lottery
from .sniper import summarize as sniper_summarize
from .store import hour_key, make_store
from .survivor import latest_by_mint, summarize

store = make_store(settings.redis_url)


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


STARTED = time.time()
STATUS_STALE_S = 120  # the recorder writes its status every 5 s


@api.get("/health")
def health():
    """503 when the recorder stopped writing its status (or never started within 5 minutes),
    so a container health probe can restart it; the API itself may still be fine."""
    body: dict[str, Any] = {"ok": True, "chain_scope": settings.chain_scope, "build_sha": settings.build_sha}
    if settings.run_recorder:
        last = store.status().get("now")
        age = time.time() - float(last) if last else None
        body["status_age_s"] = round(age, 1) if age is not None else None
        if (age is not None and age > STATUS_STALE_S) or (age is None and time.time() - STARTED > 300):
            body["ok"] = False
            return JSONResponse(body, status_code=503)
    return body


@api.get("/stats")
def stats():
    hours = _last_hours(24)
    chain = store.counters("creates_chain", hours)
    portal = store.counters("creates_portal", hours)
    census = store.counters("creates_census", hours)  # the sniper sample's census of launches
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
        "creates_24h_census": sum(census.values()),
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
                "creates_census": census[h],
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
    rows = store.survivor_rows()
    out = summarize(rows, settings.entry_delays_min, settings.horizons_min, settings.fill_sizes_sol)
    out["prereg"] = evaluate(rows)
    return out


_SNIPER_CACHE: dict[str, Any] = {"ts": 0.0, "body": None}


@api.get("/sniper/summary")
def sniper_summary():
    """Hypothesis S (docs/SNIPER.md): the sampled launches' simulated tickets over the whole grid,
    the pre-registered verdict, the lottery touches, and the census. Cached for a minute."""
    now = time.time()
    if _SNIPER_CACHE["body"] is not None and now - _SNIPER_CACHE["ts"] < 60:
        return _SNIPER_CACHE["body"]
    results = store.rows("sniper")
    body = sniper_summarize(results)
    body["lottery"] = lottery(results, latest_by_mint(store.survivor_rows()))
    hours = _last_hours(24)
    body["creates_24h_census"] = sum(store.counters("creates_census", hours).values())
    body["creates_24h_portal"] = sum(store.counters("creates_portal", hours).values())
    body["recorder"] = store.status().get("sniper")
    _SNIPER_CACHE.update(ts=now, body=body)
    return body


_EXPLORE_CACHE: dict[str, tuple[float, Any]] = {}


def _cached(key: str, ttl_s: float, compute):
    now = time.time()
    hit = _EXPLORE_CACHE.get(key)
    if hit is not None and now - hit[0] < ttl_s:
        return hit[1]
    body = compute()
    _EXPLORE_CACHE[key] = (now, body)
    return body


@api.get("/survivor/explore")
def survivor_explore():
    """Where feature rules for C2 are looked for (not evidence): feature terciles with the median,
    mean, win rate and rug share, on the registered exploration window and on earlier rows."""
    return _cached("c", 300, lambda: explore_c(store.survivor_rows()))


@api.get("/sniper/explore")
def sniper_explore():
    """The same for sniper tickets (rules S2 onward), by what was public at the entry slot."""
    return _cached("s", 60, lambda: explore_s(store.rows("sniper")))


@api.get("/sniper/rows")
def sniper_rows(limit: int = 200):
    """The newest simulated launches (compact: nets aligned with the summary's grid)."""
    return store.rows("sniper", min(limit, 5000))


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


_DATA_FILE = re.compile(r"[a-z]+(-\d{4}-\d{2}-\d{2})?\.jsonl(\.gz)?")


@api.get("/export/file/{name}")
def export_file(name: str):
    """One dataset file from the data volume, as listed by /files (swaps, holders, chain, ...)."""
    path = Path(settings.data_dir) / name
    if not _DATA_FILE.fullmatch(name) or not path.is_file():
        return JSONResponse({"error": "no such data file"}, status_code=404)
    media = "application/gzip" if name.endswith(".gz") else "application/x-ndjson"
    return FileResponse(path, media_type=media, filename=name)


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
_HOLDERS = [
    "pool_share",
    "top1",
    "top5",
    "top10",
    "holders_1pct",
    "dev_share",
    "bundle_share",
    "top1_exit_share",
    "top10_exit_share",
    "late_s",
]
_CURVE = [
    "graduate_s",
    "dev_buy_sol",
    "bundle_buyers",
    "bundle_sol",
    "early_buyers",
    "early_sol",
    "buyers_60s",
    "buy_sol_60s",
    "sell_sol_60s",
    "dev_sell_sol",
    "curve_tx",
    "first_minute_complete",
]
_FUNDING = ["wallets", "fresh_1d", "max_cluster", "cluster_hold_share", "dev_linked", "dev_group_hold_share"]


def survivor_csv(
    rows,
    delays,
    horizons,
    sizes=(),
    detail_cell: str = "d30_h60",
    flow_entry: str = "d30",
    holder_delays=(),
) -> str:
    """One row per token (latest harvest): candle marks per cell, executable net per size and
    cell, the detail of `detail_cell` per size, order flow before `flow_entry`, swap coverage,
    then the decision-time features: holders at each snapshot, the curve's history, funders."""
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
    head += [f"h{d}_{m}" for d in holder_delays for m in _HOLDERS]
    head += [f"curve_{m}" for m in _CURVE] + [f"fund_{m}" for m in _FUNDING]
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
        for d in holder_delays:
            h = (r.get("holders") or {}).get(f"d{d}") or {}
            line += [h.get(m) for m in _HOLDERS]
        cv = r.get("curve") or {}
        line += [cv.get(m) for m in _CURVE]
        fu = r.get("funding") or {}
        line += [fu.get(m) for m in _FUNDING]
        w.writerow(line)
    return buf.getvalue()


@api.get("/export/survivor.csv")
def export_survivor_csv():
    text = survivor_csv(
        store.survivor_rows(),
        settings.entry_delays_min,
        settings.horizons_min,
        settings.fill_sizes_sol,
        holder_delays=settings.holder_snapshot_delays_min,
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
    secret = {"pumpportal_api_key", "redis_url", "solana_ws_url", "solana_http_url", "gecko_api_key"}
    return settings.model_dump(exclude=secret)


app.include_router(api)

_static = (
    Path(settings.static_dir) if settings.static_dir else Path(__file__).resolve().parents[2] / "web" / "out"
)
if _static.is_dir():
    app.mount("/", StaticFiles(directory=str(_static), html=True), name="dashboard")
