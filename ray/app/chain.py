"""Reading pump.fun from the chain: base58, Anchor events, launches, curve trades, curve accounts.

Copied from the research recorder (bot/app/anchor.py, rpc.py, curve_history.py, sniper.py) so the
scorer reads a launch exactly the way the census that the sieve filters were built on read it: the
same events, the same trade tuple, the same chain order.

Trade tuple (research/sieve/filters.py): [slot, tx_index, event_index, block_time, user, is_buy,
sol_lamports, token_raw, v_sol_after, v_tokens_after, ix_name].
"""

import base64
import hashlib
from collections import Counter
from collections.abc import Sequence
from typing import Any

PUMP_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
# Every create transaction names the mint authority PDA: its history is a census of launches.
MINT_AUTHORITY = "TSLvdd1pWpHVjahSpsvCXUbgwsL3JAcvokwaKt1eokM"
LAMPORTS = 1_000_000_000
# pump.fun writes the system program id as the quote mint of SOL curves; older events carry none
SOL_QUOTES = {None, "So11111111111111111111111111111111111111112", "11111111111111111111111111111111"}
DEFAULT_FEE_BPS = 125
# Anchor's event-CPI instruction tag (sha256("anchor:event")[..8]); the event follows it.
EVENT_IX_TAG = bytes([228, 69, 165, 46, 81, 203, 154, 29])
# Anchor account discriminator of BondingCurve (sha256("account:BondingCurve")[..8]).
CURVE_DISC = hashlib.sha256(b"account:BondingCurve").digest()[:8]
SYNTH_TX = 1_000_000  # stand-in transaction indexes start here (real ones are block positions)

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


# --- event schemas (field order = IDL order, pump-fun/pump-public-docs idl/pump.json) ------------
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
    # later fields (cashback, buyback, shareholders, quote) are not needed
]
COMPLETE: Schema = [
    ("user", "pubkey"),
    ("mint", "pubkey"),
    ("bonding_curve", "pubkey"),
    ("timestamp", "i64"),
    ("quote_mint", "pubkey"),
]

DISCRIMINATORS: dict[bytes, tuple[str, Schema]] = {
    bytes([27, 114, 169, 77, 222, 235, 99, 118]): ("create", CREATE),
    bytes([189, 219, 127, 211, 78, 230, 97, 238]): ("trade", TRADE),
    bytes([95, 114, 97, 156, 212, 46, 152, 8]): ("complete", COMPLETE),
}


def decode_event(payload: bytes) -> dict[str, Any] | None:
    """One pump.fun event (a stable prefix of its fields), or None if it is not one we read.
    pump.fun appends fields often; a payload shorter than the schema keeps what was read."""
    hit = DISCRIMINATORS.get(payload[:8])
    if hit is None:
        return None
    kind, schema = hit
    r = _Reader(payload[8:])
    out: dict[str, Any] = {"kind": kind}
    for name, ty in schema:
        try:
            out[name] = r.read(ty)
        except EOFError:
            out["truncated"] = True
            break
    return out


PREFIX = "Program data: "


def parse_logs(logs: Sequence[str]) -> list[dict[str, Any]]:
    """Every pump.fun event in a transaction's `Program data:` log lines."""
    events = []
    for line in logs:
        if not line.startswith(PREFIX):
            continue
        try:
            ev = decode_event(base64.b64decode(line[len(PREFIX) :]))
        except ValueError:
            continue
        if ev is not None:
            events.append(ev)
    return events


# --- transactions -------------------------------------------------------------------------------
def account_keys(tx: dict[str, Any]) -> list[str]:
    """All account keys of a getTransaction(json) result: static first, then table-loaded."""
    msg = tx["transaction"]["message"]
    static = [k if isinstance(k, str) else k.get("pubkey") for k in msg.get("accountKeys", [])]
    loaded = (tx.get("meta") or {}).get("loadedAddresses") or {}
    return static + list(loaded.get("writable") or []) + list(loaded.get("readonly") or [])


def signature_of(tx: dict[str, Any]) -> str:
    sigs = (tx.get("transaction") or {}).get("signatures") or []
    return str(sigs[0]) if sigs else ""


def events_from_tx(tx: dict[str, Any]) -> list[dict[str, Any]]:
    """pump.fun events from the logs (`via: log`) and from self-CPI copies (`via: cpi`); logs get
    truncated at 10 KB, the self-CPI copy does not."""
    meta = tx.get("meta") or {}
    events = parse_logs(meta.get("logMessages") or [])
    for ev in events:
        ev["via"] = "log"
    keys = account_keys(tx)
    for inner in meta.get("innerInstructions") or []:
        for ix in inner.get("instructions") or []:
            pidx = ix.get("programIdIndex", -1)
            if not 0 <= pidx < len(keys) or keys[pidx] != PUMP_PROGRAM:
                continue
            try:
                data = b58decode(ix.get("data") or "")
            except ValueError:
                continue
            if data[:8] != EVENT_IX_TAG:
                continue
            ev = decode_event(data[8:])
            if ev is not None:
                ev["via"] = "cpi"
                events.append(ev)
    return events


def pump_events(tx: dict[str, Any]) -> list[dict[str, Any]]:
    """The transaction's pump.fun events, each once: per kind, the self-CPI copies if any."""
    evs = events_from_tx(tx)
    out = []
    for kind in dict.fromkeys(e["kind"] for e in evs):
        same = [e for e in evs if e["kind"] == kind]
        cpi = [e for e in same if e.get("via") == "cpi"]
        out.extend(cpi or same)
    return out


def create_of(tx: dict[str, Any]) -> dict[str, Any] | None:
    """The create event of a successful create transaction (None when it holds none)."""
    if not tx or (tx.get("meta") or {}).get("err"):
        return None
    return next((e for e in pump_events(tx) if e["kind"] == "create"), None)


def launch_info(create: dict[str, Any], tx: dict[str, Any], signature: str) -> dict[str, Any]:
    """A launch as the census row header describes it (bot/app/sniper.launch_info)."""
    return {
        "signature": signature,
        "mint": create.get("mint"),
        "curve": create.get("bonding_curve"),
        "dev": create.get("user"),
        "creator": create.get("creator"),
        "name": (create.get("name") or "")[:64],
        "symbol": (create.get("symbol") or "")[:24],
        "uri": (create.get("uri") or "")[:200],
        "create_slot": int(tx.get("slot") or 0),
        "create_ts": int(tx.get("blockTime") or create.get("timestamp") or 0),
        "quote_mint": create.get("quote_mint"),
        "mayhem": bool(create.get("is_mayhem_mode")),
        "cashback": bool(create.get("is_cashback_enabled")),
        "holder_reward": bool(create.get("is_holder_reward")),
        "token_program": create.get("token_program"),
        "supply": create.get("token_total_supply"),
        "v_sol0": create.get("virtual_sol_reserves"),
        "v_tokens0": create.get("virtual_token_reserves"),
    }


def classic_sol(info: dict[str, Any]) -> bool:
    """A launch the sieve can score: a SOL-quoted curve without mayhem mode (the filters were built
    on classic launches only; mayhem curves move their reserves outside trade events)."""
    return (
        info.get("quote_mint") in SOL_QUOTES
        and not info.get("mayhem")
        and bool(info.get("mint"))
        and bool(info.get("curve"))
        and bool(info.get("v_sol0"))
        and bool(info.get("v_tokens0"))
    )


def curve_trades(txs: Sequence[dict[str, Any]], mint: str) -> dict[str, Any]:
    """The mint's curve trades in these transactions (trade tuples), its completion and fee bps."""
    trades: list[list[Any]] = []
    complete: dict[str, Any] | None = None
    fees: Counter[int] = Counter()
    synthetic = 0
    for tx in txs:
        if (tx.get("meta") or {}).get("err"):
            continue
        slot, ts = int(tx.get("slot") or 0), int(tx.get("blockTime") or 0)
        idx = tx.get("transactionIndex")
        if idx is None:
            # Never seen from Helius, but the filters need one id per transaction: a stand-in from
            # the signature keeps "same transaction" right; chain order then breaks visibly.
            idx = SYNTH_TX + int.from_bytes(hashlib.sha256(signature_of(tx).encode()).digest()[:3], "big")
            synthetic += 1
        idx = int(idx)
        ev_i = 0
        for ev in pump_events(tx):
            if ev.get("mint") != mint:
                continue
            if ev["kind"] == "trade":
                trades.append(
                    [
                        slot,
                        idx,
                        ev_i,
                        ts,
                        ev.get("user"),
                        bool(ev.get("is_buy")),
                        int(ev.get("sol_amount") or 0),
                        int(ev.get("token_amount") or 0),
                        int(ev.get("virtual_sol_reserves") or 0),
                        int(ev.get("virtual_token_reserves") or 0),
                        ev.get("ix_name") or "",
                    ]
                )
                ev_i += 1
                bps = int(ev.get("fee_basis_points") or 0) + int(ev.get("creator_fee_basis_points") or 0)
                if bps:
                    fees[bps] += 1
            elif ev["kind"] == "complete" and complete is None:
                complete = {"slot": slot, "tx": idx, "ts": ts}
    return {"trades": trades, "complete": complete, "fees": fees, "synthetic_tx_index": synthetic}


def chain_order(trades: list[list[Any]]) -> None:
    """Sort trade tuples in chain order: slot, position in the block, event order."""
    trades.sort(key=lambda t: (t[0], t[1], t[2]))


def chain_breaks(trades: Sequence[Sequence[Any]], v_tok0: int) -> int:
    """Trades whose token reserve does not hand over exactly from the previous one (a missing or
    misordered trade): pre = post + bought for a buy, post - sold for a sell."""
    breaks = 0
    prev = int(v_tok0)
    for t in trades:
        pre = int(t[9]) + int(t[7]) if t[5] else int(t[9]) - int(t[7])
        if pre != prev:
            breaks += 1
        prev = int(t[9])
    return breaks


def parse_curve_account(value: dict[str, Any] | None) -> dict[str, Any] | None:
    """A BondingCurve account from getMultipleAccounts (base64): reserves, completion, creator.
    None for anything else (closed account, another program's account, a short read)."""
    if not value:
        return None
    data = value.get("data")
    if not isinstance(data, list) or not data:
        return None
    try:
        raw = base64.b64decode(data[0])
    except ValueError:
        return None
    if len(raw) < 81 or raw[:8] != CURVE_DISC:
        return None
    u64 = [int.from_bytes(raw[8 + 8 * i : 16 + 8 * i], "little") for i in range(5)]
    return {
        "v_tokens": u64[0],
        "v_sol": u64[1],
        "real_tokens": u64[2],
        "real_sol": u64[3],
        "supply": u64[4],
        "complete": raw[48] != 0,
        "creator": b58encode(raw[49:81]),
    }
