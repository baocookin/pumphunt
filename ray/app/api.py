"""HTTP: the private dashboard at /, its API under /api, a public health probe.

Everything but /api/health and the old research files is behind HTTP Basic auth (RAY_PASSWORD, any
user name): the scores are for the owner only. Without RAY_PASSWORD those routes answer 503.
The research recorder's data files (/api/files, /api/export/file/<name>) stay downloadable as they
were, so docs/TONG-KET-NGHIEN-CUU.md's download steps still work after the switch.
"""

import asyncio
import contextlib
import re
import secrets
import time
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .config import settings
from .engine import JOURNAL_FILE, Engine, OnDemandLimit, ScoreBook
from .outcome import HOLD_S
from .report import build as build_report
from .rpc import BudgetExhausted, CreditMeter, Rpc, describe_error
from .sieve import FROZEN_PROBLEMS, POOL_TEXT, registry
from .telegram import TelegramBot

STATIC = Path(__file__).resolve().parent / "static"
MINT_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")
_DATA_FILE = re.compile(r"[a-z]+(-\d{4}-\d{2}-\d{2})?\.jsonl(\.gz)?")
STALE_S = 180  # the poll loop runs every few seconds; this long without a round means it is stuck


class State:
    engine: Engine | None = None
    book: ScoreBook | None = None
    telegram: TelegramBot | None = None
    started = time.time()
    error: str | None = None


state = State()


async def lifespan(app: FastAPI):
    tasks: list[asyncio.Task[Any]] = []
    client = httpx.AsyncClient(timeout=30)
    state.book = ScoreBook(settings.data_dir, settings.keep_scores)
    with contextlib.suppress(OSError):
        state.book.load(time.time())
    if settings.run_engine:
        meter = CreditMeter(settings.daily_credits)
        rpc = Rpc(client, settings.http_url(), meter, settings.rps(), settings.rpc_429_penalty_s)
        state.engine = Engine(settings, rpc, state.book)
        tasks.append(asyncio.create_task(state.engine.run()))
        if settings.telegram_bot_token and settings.telegram_chat_id:
            state.telegram = TelegramBot(
                client,
                settings.telegram_bot_token,
                settings.telegram_chat_id,
                state.engine.score_mint,
                settings.telegram_push,
                settings.public_url,
            )
            state.engine.listeners.append(state.telegram.push)
            tasks.append(asyncio.create_task(state.telegram.run()))
    else:
        state.error = "Bộ chấm đang tắt (RAY_RUN_ENGINE=false)."
    try:
        yield
    finally:
        for t in tasks:
            t.cancel()
        for t in tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await t
        await client.aclose()


class NoStore:
    """Marks every answer no-store, so the Bunny CDN in front of the app never keeps the owner's pages
    whatever the zone's cache settings (it does not keep them today)."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_no_store(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = [(k, v) for k, v in message.get("headers", []) if k.lower() != b"cache-control"]
                message = {**message, "headers": [*headers, (b"cache-control", b"no-store, private")]}
            await send(message)

        await self.app(scope, receive, send_no_store)


app = FastAPI(title="ray", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(NoStore)
api = APIRouter(prefix="/api")
_basic = HTTPBasic(auto_error=False)


LOCKED = "Chưa đặt RAY_PASSWORD trong biến môi trường của app: bảng điều khiển bị khoá."
# Said when a request carried credentials anyway: they reached the app through the CDN.
SENT = " Trình duyệt đã gửi mật khẩu, nhưng app chưa có mật khẩu để so."


def require_owner(creds: HTTPBasicCredentials | None = Depends(_basic)) -> None:
    if not settings.password:
        raise HTTPException(503, LOCKED + (SENT if creds else ""))
    if creds is None or not secrets.compare_digest(creds.password.encode(), settings.password.encode()):
        raise HTTPException(401, "Cần mật khẩu.", headers={"WWW-Authenticate": 'Basic realm="ray"'})


def _engine() -> Engine:
    if state.engine is None:
        raise HTTPException(503, state.error or "Bộ chấm chưa chạy.")
    return state.engine


@api.get("/health")
def health():
    """Public. 503 when the poll loop stopped (a container probe then restarts the app)."""
    body: dict[str, Any] = {
        "ok": True,
        "app": "ray",
        "build_sha": settings.build_sha,
        "engine": state.engine is not None,
        "rpc": settings.rpc_kind(),
        "auth": bool(settings.password),
        "filters_frozen": not FROZEN_PROBLEMS,
        "error": state.error,
    }
    eng = state.engine
    if eng is not None:
        now = time.time()
        last = eng.stats["last_poll"]
        body["poll_age_s"] = round(now - last, 1) if last else None  # last successful read of the curves
        alive = eng.stats["alive"].get("poll")  # last round of the poll loop, failed or not
        if (alive and now - alive > STALE_S) or (not alive and now - state.started > STALE_S):
            body["ok"] = False
            return JSONResponse(body, status_code=503)
    return body


def _compact(sc: dict[str, Any]) -> dict[str, Any]:
    fired = [f["id"] for f in (sc.get("active") or []) + (sc.get("shadow") or []) if f.get("fired")]
    info = [f["id"] for f in sc.get("info") or [] if f.get("fired")]
    rk = sc.get("risk") or {}
    o = sc.get("outcome")
    entry = sc.get("entry")
    return {
        "mint": sc["mint"],
        "symbol": sc.get("symbol"),
        "name": sc.get("name"),
        "key": sc.get("key"),
        "D": sc.get("D"),
        "at": sc.get("at"),
        "age_s": sc.get("age_s"),
        "real": sc.get("real"),
        "floor": sc.get("floor"),
        "verdict": sc.get("verdict"),
        "verdict_vi": sc.get("verdict_vi"),
        "risk": {"pct": rk.get("pct"), "basis": rk.get("basis"), "n": rk.get("n")},
        "fired": fired,
        "info": info,
        "outcome": {k: o.get(k) for k in ("status", "net", "label", "why")} if o else None,
        "due": round(float(entry["at"]) + HOLD_S, 1) if entry and not o else None,
    }


@api.get("/state", dependencies=[Depends(require_owner)])
def live_state(limit: int = 300):
    now = time.time()
    eng = state.engine
    live = []
    if eng is not None:
        toks = [t for t in eng.tracker.live.values() if t.state and (t.state["real"] >= 2 or t.scores)]
        toks.sort(key=lambda t: -(t.state["real"] if t.state else 0))
        live = [t.view(now) for t in toks[:200]]
    recent = (
        [_compact(sc) for sc in list(state.book.recent)[: max(1, min(limit, 1000))]] if state.book else []
    )
    return {
        "now": now,
        "build_sha": settings.build_sha,
        "rpc": settings.rpc_kind(),
        "status": eng.status() if eng else {"error": state.error},
        "telegram": state.telegram.stats if state.telegram else None,
        "live": live,
        "recent": recent,
        "pool_text": POOL_TEXT,
    }


@api.get("/token/{mint}", dependencies=[Depends(require_owner)])
def token(mint: str):
    if not MINT_RE.match(mint):
        raise HTTPException(400, "Mint không hợp lệ.")
    eng = state.engine
    tok = eng.tracker.get(mint) if eng else None
    scores = sorted((tok.scores.values() if tok else []), key=lambda s: s["at"])
    if not scores and state.book and mint in state.book.latest:
        scores = [state.book.latest[mint]]
    if tok is None and not scores:
        raise HTTPException(404, "Chưa theo dõi mint này: dùng nút Chấm ngay.")
    return {
        "view": tok.view(time.time()) if tok else None,
        "info": tok.info if tok else None,
        "scores": scores,
    }


@api.post("/score/{mint}", dependencies=[Depends(require_owner)])
async def score_now(mint: str):
    if not MINT_RE.match(mint):
        raise HTTPException(400, "Mint không hợp lệ.")
    eng = _engine()
    try:
        return await eng.score_mint(mint)
    except OnDemandLimit as exc:
        raise HTTPException(429, str(exc)) from None
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from None
    except BudgetExhausted:
        raise HTTPException(503, "Đã tới trần credit hôm nay.") from None
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"Lỗi đọc RPC: {describe_error(exc)}") from None
    except Exception as exc:  # noqa: BLE001 - answered without a traceback, which could carry the URL
        raise HTTPException(500, describe_error(exc)) from None


@api.get("/report", dependencies=[Depends(require_owner)])
def report(days: int = 7):
    """The outcome journal of the last `days` days against the founding pool."""
    days = max(1, min(int(days), 90))
    now = time.time()
    lines = state.book.outcome_lines(now - days * 86_400, now) if state.book else []
    return build_report(lines, now, days, state.engine.outcomes.pending() if state.engine else 0)


@api.get("/journal", dependencies=[Depends(require_owner)])
def journal():
    """The journal's daily files: scores, outcomes and the archived rows."""
    return {"files": state.book.journal_files() if state.book else []}


@api.get("/journal/{name}", dependencies=[Depends(require_owner)])
def journal_file(name: str):
    path = state.book.dir / name if state.book else None
    if path is None or not JOURNAL_FILE.fullmatch(name) or not path.is_file():
        raise HTTPException(404, "Không có file này.")
    media = "application/gzip" if name.endswith(".gz") else "application/x-ndjson"
    return FileResponse(path, media_type=media, filename=name)


@api.get("/registry", dependencies=[Depends(require_owner)])
def filters():
    return {"filters": registry(), "pool_text": POOL_TEXT, "frozen_problems": FROZEN_PROBLEMS}


# --- the research recorder's data files (public, as before the switch) --------------------------
@api.get("/files")
def files():
    d = Path(settings.data_dir)
    out = []
    if d.is_dir():
        for p in sorted(d.iterdir()):
            if p.is_file():
                st = p.stat()
                out.append({"name": p.name, "bytes": st.st_size, "mtime": st.st_mtime})
    return {"dir": str(d), "files": out}


@api.get("/export/file/{name}")
def export_file(name: str):
    path = Path(settings.data_dir) / name
    if not _DATA_FILE.fullmatch(name) or not path.is_file():
        return JSONResponse({"error": "no such data file"}, status_code=404)
    media = "application/gzip" if name.endswith(".gz") else "application/x-ndjson"
    return FileResponse(path, media_type=media, filename=name)


app.include_router(api)


@app.get("/", include_in_schema=False)
def dashboard(creds: HTTPBasicCredentials | None = Depends(_basic)):
    if not settings.password:
        return HTMLResponse(f"<h1>Rây</h1><p>{LOCKED}{SENT if creds else ''}</p>", status_code=503)
    require_owner(creds)
    return FileResponse(STATIC / "index.html", media_type="text/html")
