"""Solana JSON-RPC over HTTP (Helius), paced, with a per-day credit meter.

Three reads do all the work (credit costs as the research recorder estimated them on Helius):
  getTransactionsForAddress  full transactions, 10 credits per 100 returned (10 minimum): the
                             launch census (mint authority) and each candidate's curve history
  getMultipleAccounts        up to 100 bonding curves per call, 1 credit: live reserves
The URL carries the API key, so it never appears in an error message or a log line.
"""

import asyncio
import re
import time
from collections import Counter
from collections.abc import Callable
from typing import Any

import httpx


def gtfa_credits(n_full: int) -> int:
    """Helius meters full-transaction responses at 10 credits per 100 returned, 10 minimum."""
    return max(10, -(-n_full // 100) * 10)


class RpcError(httpx.HTTPError):
    """A JSON-RPC error object in a 200 response (an httpx.HTTPError, so callers treat it like any
    other failed call)."""

    def __init__(self, code: int, message: str):
        super().__init__(f"rpc error {code}: {message}")
        self.code = code
        self.rpc_message = message


class BudgetExhausted(Exception):
    """The day's credit cap is reached for this kind of read."""


def describe_http_error(exc: BaseException) -> str:
    """Error text safe for logs and API responses: never the URL, which carries the RPC key."""
    if isinstance(exc, RpcError):
        return f"RpcError {exc.code}: {exc.rpc_message[:120]}"
    if isinstance(exc, BudgetExhausted):
        return "credit cap reached"
    status = getattr(getattr(exc, "response", None), "status_code", None)
    return f"{type(exc).__name__}" + (f" {status}" if status else "")


# An RPC key in a query string, a Telegram bot token in a path.
_SECRET = re.compile(r"(api[-_]?key=)[^&\s'\"]+|(/bot)\d+:[\w-]+", re.IGNORECASE)


def scrub(text: str) -> str:
    """Free text with anything that looks like a key masked."""
    return _SECRET.sub(lambda m: (m.group(1) or m.group(2)) + "***", text)


def describe_error(exc: BaseException) -> str:
    """Any error as text safe for the status, API answers and Telegram: an HTTP error by its type and
    status only (httpx puts the URL in its messages), anything else masked and cut short."""
    if isinstance(exc, httpx.HTTPError | httpx.InvalidURL | BudgetExhausted):
        return describe_http_error(exc)
    return scrub(f"{type(exc).__name__}: {exc}")[:200]


def http_url_from_ws(ws_url: str | None) -> str | None:
    if not ws_url:
        return None
    if ws_url.startswith("wss://"):
        return "https://" + ws_url[len("wss://") :]
    if ws_url.startswith("ws://"):
        return "http://" + ws_url[len("ws://") :]
    return ws_url


class CreditMeter:
    """Credits spent per UTC day, by kind of read. Scoring reads (history, on-demand) stop at the cap;
    the cheap reads that keep the live view running (census, reserves) may go 25% over it."""

    CHEAP = {"census", "poll"}

    def __init__(self, daily_cap: int, clock: Callable[[], float] = time.time):
        self.cap = int(daily_cap)
        self.clock = clock
        self.day = ""
        self.spent = 0
        self.by_kind: Counter[str] = Counter()

    def _roll(self) -> None:
        day = time.strftime("%Y-%m-%d", time.gmtime(self.clock()))
        if day != self.day:
            self.day, self.spent, self.by_kind = day, 0, Counter()

    def allows(self, kind: str) -> bool:
        self._roll()
        limit = self.cap * (1.25 if kind in self.CHEAP else 1.0)
        return self.spent < limit

    def add(self, credits: int, kind: str) -> None:
        self._roll()
        self.spent += int(credits)
        self.by_kind[kind] += int(credits)

    def snapshot(self) -> dict[str, Any]:
        self._roll()
        return {"day": self.day, "spent": self.spent, "cap": self.cap, "by_kind": dict(self.by_kind)}

    def restore(self, snap: dict[str, Any]) -> bool:
        """Take back today's count saved before a restart (another day's count is ignored)."""
        self._roll()
        if snap.get("day") != self.day:
            return False
        self.spent = int(snap.get("spent") or 0)
        self.by_kind = Counter({str(k): int(v) for k, v in (snap.get("by_kind") or {}).items()})
        return True


class Rpc:
    """JSON-RPC client: at most `rps` request starts per second across all callers; a 429 or a
    502/503/504 pushes every caller back by `penalty_s` and is retried a few times."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        url: str,
        meter: CreditMeter,
        rps: float = 10.0,
        penalty_s: float = 2.0,
    ):
        self.c = client
        self.url = url
        self.meter = meter
        self.interval = 1.0 / rps if rps > 0 else 0.0
        self.penalty_s = penalty_s
        self._next = 0.0
        self._lock = asyncio.Lock()
        self.stats: dict[str, Any] = {"calls": 0, "rate_limited": 0, "unavailable": 0, "errors": 0}

    async def _pace(self) -> None:
        async with self._lock:
            now = time.monotonic()
            wait = self._next - now
            self._next = max(now, self._next) + self.interval
        if wait > 0:
            await asyncio.sleep(wait)

    async def call(
        self, method: str, params: list[Any], *, kind: str, credits: int = 1, retries: int = 3
    ) -> Any:
        if not self.meter.allows(kind):
            raise BudgetExhausted(kind)
        for attempt in range(retries + 1):
            await self._pace()
            self.stats["calls"] += 1
            r = await self.c.post(
                self.url, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
            )
            body = r.json() if r.status_code == 200 else None
            err = (body or {}).get("error") if isinstance(body, dict) else None
            limited = r.status_code == 429 or (isinstance(err, dict) and err.get("code") == 429)
            unavailable = r.status_code in (502, 503, 504)
            if limited or unavailable:
                self.stats["rate_limited" if limited else "unavailable"] += 1
                self._next = max(self._next, time.monotonic() + self.penalty_s * (attempt + 1))
                if attempt < retries:
                    continue
            if r.status_code >= 400 or err:
                self.stats["errors"] += 1
            r.raise_for_status()
            if err:
                raise RpcError(int(err.get("code") or 0), str(err.get("message") or ""))
            if credits:
                self.meter.add(credits, kind)
            return (body or {}).get("result")
        return None

    async def gtfa(
        self,
        address: str,
        *,
        kind: str,
        sort: str = "asc",
        limit: int = 100,
        t_from: int | None = None,
        t_to: int | None = None,
        token: str | None = None,
    ) -> dict[str, Any]:
        """One getTransactionsForAddress page of successful full transactions (Helius only). A 413
        (response too large) halves the page. Returns {data, paginationToken, asked}: `asked` is the
        page size finally asked for, which a caller judging a short page must compare against."""
        flt: dict[str, Any] = {"status": "succeeded"}
        bt = {}
        if t_from is not None:
            bt["gte"] = int(t_from)
        if t_to is not None:
            bt["lte"] = int(t_to)
        if bt:
            flt["blockTime"] = bt
        while True:
            opts: dict[str, Any] = {
                "transactionDetails": "full",
                "sortOrder": sort,
                "limit": limit,
                "commitment": "confirmed",
                "encoding": "json",
                "maxSupportedTransactionVersion": 1,  # the documented maximum for this method
                "filters": flt,
            }
            if token:
                opts["paginationToken"] = token
            try:
                res = (
                    await self.call("getTransactionsForAddress", [address, opts], kind=kind, credits=0) or {}
                )
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 413 and limit > 10:
                    limit //= 2
                    continue
                raise
            data = list(res.get("data") or [])
            self.meter.add(gtfa_credits(len(data)), kind)
            return {"data": data, "paginationToken": res.get("paginationToken"), "asked": limit}

    async def multiple_accounts(
        self, pubkeys: list[str], *, kind: str
    ) -> tuple[int, list[dict[str, Any] | None]]:
        """(context slot, account values) for up to 100 accounts, base64-encoded."""
        opts = {"encoding": "base64", "commitment": "confirmed"}
        res = await self.call("getMultipleAccounts", [pubkeys, opts], kind=kind) or {}
        slot = int((res.get("context") or {}).get("slot") or 0)
        return slot, list(res.get("value") or [])
