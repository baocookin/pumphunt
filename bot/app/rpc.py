"""Solana JSON-RPC over HTTP: confirm a migration by signature and learn the fixed accounts.

PumpPortal hands us the migration's signature. One `getTransaction` (1 credit on
Helius) gives the slot, the logs, the inner instructions and the account list of
the `migrate` / `migrate_v2` instruction. The IDL does not pin
`withdraw_authority` to a fixed address, so we read it from real transactions
instead of guessing; the recorder re-subscribes the websocket feed to it.

Three places can carry the migration, and a real transaction may only have some:
  1. `Program data:` log line with CompletePumpAmmMigrationEvent (Anchor `emit!`).
     Solana truncates logs at 10 KB and a migrate creates the PumpSwap pool via
     CPI, so this line is often cut off.
  2. A self-CPI inner instruction (Anchor `emit_cpi!`): the program invokes itself
     with EVENT_IX_TAG + the same event bytes. Not subject to log truncation.
  3. The migrate instruction's own accounts, which name the mint and the pool.
"""

import asyncio
import base64
import time
from typing import Any

import httpx

from .anchor import PREFIX, PUMP_PROGRAM, b58decode, decode_event, parse_logs

# Account order copied from pump-fun/pump-public-docs idl/pump.json.
_MIGRATE_ACCOUNTS = [
    "global",
    "withdraw_authority",
    "mint",
    "bonding_curve",
    "associated_bonding_curve",
    "user",
    "system_program",
    "token_program",
    "pump_amm",
    "pool",
    "pool_authority",
    "pool_authority_mint_account",
    "pool_authority_wsol_account",
    "amm_global_config",
    "wsol_mint",
    "lp_mint",
    "user_pool_token_account",
    "pool_base_token_account",
    "pool_quote_token_account",
    "token_2022_program",
    "associated_token_program",
    "pump_amm_event_authority",
    "event_authority",
    "program",
    "rent",
]
_MIGRATE_V2_ACCOUNTS = [
    "global",
    "withdraw_authority",
    "base_mint",
    "quote_mint",
    "bonding_curve",
    "associated_base_bonding_curve",
    "associated_quote_bonding_curve",
    "user",
    "system_program",
    "pump_amm",
    "pool",
    "pool_authority",
    "pool_authority_mint_account",
    "pool_authority_quote_account",
    "amm_global_config",
    "lp_mint",
    "user_pool_token_account",
    "pool_base_token_account",
    "pool_quote_token_account",
    "base_token_program",
    "quote_token_program",
    "token_2022_program",
    "associated_token_program",
    "pump_amm_event_authority",
    "rent",
    "event_authority",
    "program",
]
PUMP_AMM = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"  # a real migrate creates the pool here via CPI
MIGRATE_IX: dict[bytes, tuple[str, list[str]]] = {
    bytes([155, 234, 231, 146, 236, 158, 162, 30]): ("migrate", _MIGRATE_ACCOUNTS),
    bytes([187, 203, 18, 31, 206, 237, 254, 41]): ("migrate_v2", _MIGRATE_V2_ACCOUNTS),
}
# Anchor's event-CPI instruction tag (sha256("anchor:event")[..8]); the event follows it.
EVENT_IX_TAG = bytes([228, 69, 165, 46, 81, 203, 154, 29])
_KNOWN_DISCS = {d.hex(): name for d, (name, _) in MIGRATE_IX.items()} | {EVENT_IX_TAG.hex(): "event_cpi"}


def http_url_from_ws(ws_url: str) -> str:
    if ws_url.startswith("wss://"):
        return "https://" + ws_url[len("wss://") :]
    if ws_url.startswith("ws://"):
        return "http://" + ws_url[len("ws://") :]
    return ws_url


def describe_http_error(exc: httpx.HTTPError) -> str:
    """Error text safe for logs and API responses: never the URL, which carries the RPC key."""
    if isinstance(exc, RpcError):
        return f"RpcError {exc.code}: {exc.rpc_message[:120]}"
    status = getattr(getattr(exc, "response", None), "status_code", None)
    return f"{type(exc).__name__}" + (f" {status}" if status else "")


class RpcError(httpx.HTTPError):
    """A JSON-RPC error object in a 200 response. Subclasses httpx.HTTPError so every existing
    `except httpx.HTTPError` treats it like any other failed call."""

    def __init__(self, code: int, message: str):
        super().__init__(f"rpc error {code}: {message}")
        self.code = code
        self.rpc_message = message

    @property
    def method_unsupported(self) -> bool:
        return self.code == -32601 or "method not found" in self.rpc_message.lower()


def gtfa_credits(n_full: int) -> int:
    """Helius meters full-transaction responses at 10 credits per 100 returned, 10 minimum."""
    return max(10, -(-n_full // 100) * 10)


class SolanaRpc:
    """JSON-RPC client with a global pace: at most `rps` request starts per second across all
    callers, and a 429 pushes every caller back by `penalty_s`. Helius' free tier allows ~10/s;
    a backfill of a few hundred getTransaction calls must not trip it."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        url: str,
        rps: float = 5.0,
        penalty_s: float = 2.0,
        max_tx_version: int = 255,
    ):
        self.c = client
        self.url = url
        # Solana now has version-1 transactions; asking for at most version 0 makes the RPC
        # answer null (json) or an error (jsonParsed) for them, which looked like "not found".
        self.max_tx_version = max_tx_version
        self.interval = 1.0 / rps if rps > 0 else 0.0
        self.penalty_s = penalty_s
        self._next = 0.0
        self._lock = asyncio.Lock()
        self.stats: dict[str, Any] = {"calls": 0, "rate_limited": 0, "errors": 0, "credits_est": 0}

    async def _pace(self) -> None:
        async with self._lock:
            now = time.monotonic()
            wait = self._next - now
            self._next = max(now, self._next) + self.interval
        if wait > 0:
            await asyncio.sleep(wait)

    async def _call(self, method: str, params: list[Any], retries: int = 3, credits: int = 1) -> Any:
        """One JSON-RPC call. A 429 (HTTP status, or a JSON error with code 429 as some providers
        send it) pushes every caller back by `penalty_s` and is retried here, so callers only see
        rate limiting that persists. Any other JSON-RPC error raises RpcError."""
        for attempt in range(retries + 1):
            await self._pace()
            self.stats["calls"] += 1
            r = await self.c.post(
                self.url, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
            )
            body = r.json() if r.status_code == 200 else None
            err = (body or {}).get("error") if isinstance(body, dict) else None
            limited = r.status_code == 429 or (isinstance(err, dict) and err.get("code") == 429)
            if limited:
                self.stats["rate_limited"] += 1
                self._next = max(self._next, time.monotonic() + self.penalty_s * (attempt + 1))
                if attempt < retries:
                    continue
            if r.status_code >= 400 or err:
                self.stats["errors"] += 1
            r.raise_for_status()
            if err:
                raise RpcError(int(err.get("code") or 0), str(err.get("message") or ""))
            self.stats["credits_est"] += credits
            return (body or {}).get("result")
        return None

    async def get_transaction(self, signature: str) -> dict[str, Any] | None:
        opts = {
            "encoding": "json",
            "commitment": "confirmed",
            "maxSupportedTransactionVersion": self.max_tx_version,
        }
        return await self._call("getTransaction", [signature, opts])

    async def get_signatures(
        self, address: str, limit: int = 1000, before: str | None = None, until: str | None = None
    ) -> list[dict[str, Any]]:
        """Signatures mentioning `address`, newest first. Unlike logsSubscribe, this index also
        covers addresses loaded through lookup tables (measured: 143/143 migrations listed)."""
        opts: dict[str, Any] = {"limit": limit, "commitment": "confirmed"}
        if before:
            opts["before"] = before
        if until:
            opts["until"] = until
        return await self._call("getSignaturesForAddress", [address, opts]) or []

    async def get_transactions_for_address(
        self,
        address: str,
        *,
        full: bool = True,
        sort: str = "asc",
        limit: int = 1000,
        filters: dict[str, Any] | None = None,
        pagination_token: str | None = None,
    ) -> dict[str, Any]:
        """Helius `getTransactionsForAddress`: an address's history with time/status filters, oldest
        first if asked, full transactions included (no getTransaction round trips). Metered at
        10 credits per 100 full transactions (10 minimum) or 10 flat for signatures; not part of
        standard Solana RPC, so other providers answer -32601 (RpcError.method_unsupported)."""
        opts: dict[str, Any] = {
            "transactionDetails": "full" if full else "signatures",
            "sortOrder": sort,
            "limit": limit,
            "commitment": "confirmed",
        }
        if full:
            opts["encoding"] = "json"
            opts["maxSupportedTransactionVersion"] = 1  # the documented maximum for this method
        if filters:
            opts["filters"] = filters
        if pagination_token:
            opts["paginationToken"] = pagination_token
        res = await self._call("getTransactionsForAddress", [address, opts], credits=0) or {}
        n = len(res.get("data") or [])
        self.stats["credits_est"] += gtfa_credits(n) if full else 10
        return res

    async def get_token_largest_accounts(self, mint: str) -> list[dict[str, Any]]:
        res = await self._call("getTokenLargestAccounts", [mint, {"commitment": "confirmed"}]) or {}
        return list(res.get("value") or [])

    async def get_multiple_accounts(self, pubkeys: list[str]) -> list[dict[str, Any] | None]:
        opts = {"encoding": "jsonParsed", "commitment": "confirmed"}
        res = await self._call("getMultipleAccounts", [pubkeys, opts]) or {}
        return list(res.get("value") or [])

    async def get_token_supply(self, mint: str) -> int | None:
        res = await self._call("getTokenSupply", [mint, {"commitment": "confirmed"}]) or {}
        amount = (res.get("value") or {}).get("amount")
        return int(amount) if amount is not None else None


def account_keys(tx: dict[str, Any]) -> tuple[list[str], int]:
    """All account keys (static first, then address-table loaded) and the static count."""
    msg = tx["transaction"]["message"]
    static = [k if isinstance(k, str) else k.get("pubkey") for k in msg.get("accountKeys", [])]
    loaded = (tx.get("meta") or {}).get("loadedAddresses") or {}
    return static + list(loaded.get("writable") or []) + list(loaded.get("readonly") or []), len(static)


def _instructions(tx: dict[str, Any]) -> list[tuple[dict[str, Any], bool]]:
    """Top-level then inner instructions, each tagged with whether it is inner (a CPI)."""
    msg = tx["transaction"]["message"]
    out = [(ix, False) for ix in msg.get("instructions") or []]
    for inner in (tx.get("meta") or {}).get("innerInstructions") or []:
        out.extend((ix, True) for ix in inner.get("instructions") or [])
    return out


def _ix_data(ix: dict[str, Any]) -> bytes:
    try:
        return b58decode(ix.get("data") or "")
    except ValueError:
        return b""


def _program_of(ix: dict[str, Any], keys: list[str]) -> str | None:
    pidx = ix.get("programIdIndex", -1)
    return keys[pidx] if 0 <= pidx < len(keys) else None


def find_migrate_ix(tx: dict[str, Any]) -> dict[str, Any] | None:
    """IDL account name -> pubkey for the migrate instruction in this tx (top-level or inner)."""
    keys, n_static = account_keys(tx)
    for ix, _inner in _instructions(tx):
        if _program_of(ix, keys) != PUMP_PROGRAM:
            continue
        hit = MIGRATE_IX.get(_ix_data(ix)[:8])
        if hit is None:
            continue
        name, names = hit
        idxs = ix.get("accounts") or []
        out: dict[str, Any] = {"ix": name}
        for nm, i in zip(names, idxs, strict=False):
            out[nm] = keys[i] if i < len(keys) else None
        # logsSubscribe `mentions` only matches static keys; an account loaded via an
        # address lookup table cannot be subscribed to. Signers are always static.
        out["withdraw_authority_static"] = len(idxs) > 1 and idxs[1] < n_static
        u = names.index("user")
        out["user_static"] = len(idxs) > u and idxs[u] < n_static
        return out
    return None


def events_from_tx(tx: dict[str, Any]) -> list[dict[str, Any]]:
    """pump.fun events from the logs (`via: log`) plus those mirrored through self-CPI (`via: cpi`)."""
    meta = tx.get("meta") or {}
    events = parse_logs(meta.get("logMessages") or [])
    for ev in events:
        ev["via"] = "log"
    keys, _ = account_keys(tx)
    for ix, inner in _instructions(tx):
        if not inner or _program_of(ix, keys) != PUMP_PROGRAM:
            continue
        data = _ix_data(ix)
        if data[:8] != EVENT_IX_TAG:
            continue
        ev = decode_event(data[8:])
        if ev is not None:
            ev["via"] = "cpi"
            events.append(ev)
    return events


def creates_pool(tx: dict[str, Any]) -> bool:
    """True when the tx CPIs into PumpSwap: a migrate that did the work. Bots lose the migrate race
    all day long; their `migrate_v2` still succeeds, logs "Bonding curve already migrated" and
    returns without touching anything."""
    keys, _ = account_keys(tx)
    return any(inner and _program_of(ix, keys) == PUMP_AMM for ix, inner in _instructions(tx))


def migration_from_tx(tx: dict[str, Any] | None) -> dict[str, Any] | None:
    """Migrate event + slot + instruction accounts, or None if this is not a successful migrate tx.

    Prefers the decoded event (log or CPI copy). When both copies are missing but the
    migrate instruction is there and the pool was created in this tx, the mint and pool
    are taken from the instruction's accounts (`via: accounts`). A migrate instruction that
    created nothing is a no-op race loser: `{"noop": True, ...}` so callers can count it.
    """
    if not tx or (tx.get("meta") or {}).get("err"):
        return None
    accounts = find_migrate_ix(tx)
    ev = next((e for e in events_from_tx(tx) if e["kind"] == "migrate"), None)
    if ev is None and accounts is None:
        return None
    if ev is None:
        assert accounts is not None
        if not creates_pool(tx):
            return {"noop": True, "event": None, "slot": tx.get("slot"), "accounts": accounts}
        ev = {
            "kind": "migrate",
            "via": "accounts",
            "mint": accounts.get("mint") or accounts.get("base_mint"),
            "pool": accounts.get("pool"),
            "bonding_curve": accounts.get("bonding_curve"),
            "user": accounts.get("user"),
            "timestamp": tx.get("blockTime"),
        }
    return {
        "event": ev,
        "slot": tx.get("slot"),
        "block_time": tx.get("blockTime"),
        "accounts": accounts,
    }


def tx_diagnostics(tx: dict[str, Any] | None) -> dict[str, Any]:
    """Compact, key-free description of a transaction: why did it (not) parse as a migration?"""
    if not tx:
        return {"found": False}
    meta = tx.get("meta") or {}
    keys, n_static = account_keys(tx)
    logs = meta.get("logMessages") or []
    ixs = []
    for ix, inner in _instructions(tx):
        disc = _ix_data(ix)[:8].hex()
        ixs.append(
            {
                "program": _program_of(ix, keys),
                "disc": disc,
                "name": _KNOWN_DISCS.get(disc),
                "n_accounts": len(ix.get("accounts") or []),
                "inner": inner,
            }
        )
    log_discs = []
    for line in logs:
        if line.startswith(PREFIX):
            try:
                log_discs.append(base64.b64decode(line[len(PREFIX) :])[:8].hex())
            except ValueError:
                continue
    return {
        "found": True,
        "version": tx.get("version"),
        "slot": tx.get("slot"),
        "err": meta.get("err"),
        "n_keys": len(keys),
        "n_static": n_static,
        "n_logs": len(logs),
        "log_truncated": any("Log truncated" in line for line in logs),
        "already_migrated_log": any("already migrated" in line for line in logs),
        "creates_pool": creates_pool(tx),
        "log_event_discs": log_discs,
        "programs": sorted({i["program"] for i in ixs if i["program"]}),
        "pump_ixs": [i for i in ixs if i["program"] == PUMP_PROGRAM][:20],
        "events": [{"kind": e["kind"], "via": e["via"]} for e in events_from_tx(tx)],
    }
