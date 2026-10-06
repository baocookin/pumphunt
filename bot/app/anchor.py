"""Decode pump.fun Anchor events straight from transaction logs.

Anchor programs emit events as `Program data: <base64>` log lines. The payload
is an 8-byte discriminator followed by Borsh-encoded fields. Discriminators
and field order below are copied verbatim from the official IDL
(pump-fun/pump-public-docs, idl/pump.json) — not from memory.

We decode a stable *prefix* of each event and keep the raw base64 alongside,
so when pump.fun appends fields (they do, often) nothing breaks and old
recordings can be re-decoded later.
"""

import base64
from dataclasses import dataclass
from typing import Any

PUMP_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
LAMPORTS = 1e9
TOKEN_DECIMALS = 1e6

# --- base58 (no dependency) -------------------------------------------------
_B58 = b"123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def b58encode(raw: bytes) -> str:
    n = int.from_bytes(raw, "big")
    out = bytearray()
    while n:
        n, r = divmod(n, 58)
        out.append(_B58[r])
    pad = len(raw) - len(raw.lstrip(b"\0"))
    return (_B58[:1] * pad + out[::-1]).decode()


def b58decode(s: str) -> bytes:
    n = 0
    for ch in s.encode():
        n = n * 58 + _B58.index(ch)
    pad = len(s) - len(s.lstrip("1"))
    body = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\0" * pad + body


# --- borsh reader -----------------------------------------------------------
class _Reader:
    def __init__(self, data: bytes):
        self.d = data
        self.p = 0

    def take(self, n: int) -> bytes:
        if len(self.d) - self.p < n:
            raise EOFError
        b = self.d[self.p : self.p + n]
        self.p += n
        return b

    def read(self, ty: str) -> Any:
        if ty == "u64":
            return int.from_bytes(self.take(8), "little")
        if ty == "i64":
            return int.from_bytes(self.take(8), "little", signed=True)
        if ty == "bool":
            return self.take(1)[0] != 0
        if ty == "pubkey":
            return b58encode(self.take(32))
        if ty == "string":
            n = int.from_bytes(self.take(4), "little")
            return self.take(n).decode("utf-8", "replace")
        raise ValueError(ty)


# --- schemas (field order = IDL order) -------------------------------------
Schema = list[tuple[str, str]]

CREATE: Schema = [
    ("name", "string"),
    ("symbol", "string"),
    ("uri", "string"),
    ("mint", "pubkey"),
    ("bonding_curve", "pubkey"),
    ("user", "pubkey"),
    ("creator", "pubkey"),
    ("timestamp", "i64"),
    ("virtual_token_reserves", "u64"),
    ("virtual_sol_reserves", "u64"),
    ("real_token_reserves", "u64"),
    ("token_total_supply", "u64"),
    ("token_program", "pubkey"),
    ("is_mayhem_mode", "bool"),
    ("is_cashback_enabled", "bool"),
    ("quote_mint", "pubkey"),
    ("virtual_quote_reserves", "u64"),
    ("creator_fee_bps", "u64"),
    ("is_holder_reward", "bool"),
]
TRADE: Schema = [
    ("mint", "pubkey"),
    ("sol_amount", "u64"),
    ("token_amount", "u64"),
    ("is_buy", "bool"),
    ("user", "pubkey"),
    ("timestamp", "i64"),
    ("virtual_sol_reserves", "u64"),
    ("virtual_token_reserves", "u64"),
    ("real_sol_reserves", "u64"),
    ("real_token_reserves", "u64"),
    ("fee_recipient", "pubkey"),
    ("fee_basis_points", "u64"),
    ("fee", "u64"),
    ("creator", "pubkey"),
    ("creator_fee_basis_points", "u64"),
    ("creator_fee", "u64"),
    ("track_volume", "bool"),
    ("total_unclaimed_tokens", "u64"),
    ("total_claimed_tokens", "u64"),
    ("current_sol_volume", "u64"),
    ("last_update_timestamp", "i64"),
    ("ix_name", "string"),
    ("mayhem_mode", "bool"),
    ("cashback_fee_basis_points", "u64"),
    ("cashback", "u64"),
    ("buyback_fee_basis_points", "u64"),
    ("buyback_fee", "u64"),
    # followed by `shareholders: Vec<Shareholder>` and quote-mint fields; not decoded.
]
COMPLETE: Schema = [
    ("user", "pubkey"),
    ("mint", "pubkey"),
    ("bonding_curve", "pubkey"),
    ("timestamp", "i64"),
    ("quote_mint", "pubkey"),
]
MIGRATE: Schema = [
    ("user", "pubkey"),
    ("mint", "pubkey"),
    ("mint_amount", "u64"),
    ("sol_amount", "u64"),
    ("pool_migration_fee", "u64"),
    ("bonding_curve", "pubkey"),
    ("timestamp", "i64"),
    ("pool", "pubkey"),
    ("quote_mint", "pubkey"),
]

DISCRIMINATORS: dict[bytes, tuple[str, Schema]] = {
    bytes([27, 114, 169, 77, 222, 235, 99, 118]): ("create", CREATE),
    bytes([189, 219, 127, 211, 78, 230, 97, 238]): ("trade", TRADE),
    bytes([95, 114, 97, 156, 212, 46, 152, 8]): ("complete", COMPLETE),
    bytes([189, 233, 93, 185, 92, 148, 234, 148]): ("migrate", MIGRATE),
}

_LAMPORT_FIELDS = {
    "sol_amount",
    "virtual_sol_reserves",
    "real_sol_reserves",
    "fee",
    "creator_fee",
    "pool_migration_fee",
    "current_sol_volume",
    "cashback",
    "buyback_fee",
}
_TOKEN_FIELDS = {
    "token_amount",
    "virtual_token_reserves",
    "real_token_reserves",
    "token_total_supply",
    "mint_amount",
}


def decode_event(payload: bytes) -> dict[str, Any] | None:
    """Decode one `Program data` payload. None if it's not one of our events."""
    hit = DISCRIMINATORS.get(payload[:8])
    if hit is None:
        return None
    kind, schema = hit
    r = _Reader(payload[8:])
    out: dict[str, Any] = {"kind": kind}
    truncated = False
    for name, ty in schema:
        try:
            out[name] = r.read(ty)
        except EOFError:
            truncated = True
            break
    out["truncated"] = truncated
    # human units next to raw ints
    for k in list(out):
        if k in _LAMPORT_FIELDS and isinstance(out[k], int):
            out[k + "_sol"] = out[k] / LAMPORTS
        elif k in _TOKEN_FIELDS and isinstance(out[k], int):
            out[k + "_ui"] = out[k] / TOKEN_DECIMALS
    return out


PREFIX = "Program data: "


def parse_logs(logs: list[str]) -> list[dict[str, Any]]:
    """Extract every pump.fun event from a transaction's log lines."""
    events = []
    for line in logs:
        if not line.startswith(PREFIX):
            continue
        b64 = line[len(PREFIX) :]
        try:
            payload = base64.b64decode(b64)
        except ValueError:
            continue
        ev = decode_event(payload)
        if ev is not None:
            ev["raw_b64"] = b64
            events.append(ev)
    return events


@dataclass
class ChainEvent:
    ts: float  # local receive time
    slot: int
    signature: str
    kind: str  # create | trade | complete | migrate
    data: dict[str, Any]


def parse_logs_notification(msg: dict[str, Any], ts: float) -> list[ChainEvent]:
    """Turn a `logsNotification` RPC message into ChainEvents (empty for others)."""
    if msg.get("method") != "logsNotification":
        return []
    res = msg["params"]["result"]
    value = res.get("value", {})
    if value.get("err"):
        return []
    slot = int(res.get("context", {}).get("slot", 0))
    sig = str(value.get("signature", ""))
    return [ChainEvent(ts, slot, sig, ev["kind"], ev) for ev in parse_logs(value.get("logs", []))]
