"""PumpSwap (pump.fun's AMM) swap events, decoded from transactions.

Schemas copied from pump-fun/pump-public-docs idl/pump_amm.json (BuyEvent, SellEvent).
Two facts verified against mainnet transactions (tests/fixtures/pumpswap):
  * `pool_base_token_reserves` / `pool_quote_token_reserves` are the reserves BEFORE the swap.
  * The LP fee stays in the pool, so the state after a swap is
        buy : base - base_out,  quote + quote_in + lp_fee
        sell: base + base_in,   quote - quote_out + lp_fee
    and that state is exactly the next swap's "before".
Pools also carry a constant `virtual_quote_reserves` that enters the price but is not real SOL.
"""

import hashlib
from dataclasses import dataclass
from typing import Any

from .anchor import _Reader, b58decode, parse_logs_payloads
from .rpc import EVENT_IX_TAG, PUMP_AMM, _instructions, _program_of, account_keys

_BUY_HEAD = [
    ("timestamp", "i64"),
    ("base_amount_out", "u64"),
    ("max_quote_amount_in", "u64"),
    ("user_base_token_reserves", "u64"),
    ("user_quote_token_reserves", "u64"),
    ("pool_base_token_reserves", "u64"),
    ("pool_quote_token_reserves", "u64"),
    ("quote_amount_in", "u64"),
    ("lp_fee_basis_points", "u64"),
    ("lp_fee", "u64"),
    ("protocol_fee_basis_points", "u64"),
    ("protocol_fee", "u64"),
    ("quote_amount_in_with_lp_fee", "u64"),
    ("user_quote_amount_in", "u64"),
    ("pool", "pubkey"),
    ("user", "pubkey"),
    ("user_base_token_account", "pubkey"),
    ("user_quote_token_account", "pubkey"),
    ("protocol_fee_recipient", "pubkey"),
    ("protocol_fee_recipient_token_account", "pubkey"),
    ("coin_creator", "pubkey"),
    ("coin_creator_fee_basis_points", "u64"),
    ("coin_creator_fee", "u64"),
    ("track_volume", "bool"),
    ("total_unclaimed_tokens", "u64"),
    ("total_claimed_tokens", "u64"),
    ("current_sol_volume", "u64"),
    ("last_update_timestamp", "i64"),
    ("min_base_amount_out", "u64"),
    ("ix_name", "string"),
]
_SELL_HEAD = [
    ("timestamp", "i64"),
    ("base_amount_in", "u64"),
    ("min_quote_amount_out", "u64"),
    ("user_base_token_reserves", "u64"),
    ("user_quote_token_reserves", "u64"),
    ("pool_base_token_reserves", "u64"),
    ("pool_quote_token_reserves", "u64"),
    ("quote_amount_out", "u64"),
    ("lp_fee_basis_points", "u64"),
    ("lp_fee", "u64"),
    ("protocol_fee_basis_points", "u64"),
    ("protocol_fee", "u64"),
    ("quote_amount_out_without_lp_fee", "u64"),
    ("user_quote_amount_out", "u64"),
    ("pool", "pubkey"),
    ("user", "pubkey"),
    ("user_base_token_account", "pubkey"),
    ("user_quote_token_account", "pubkey"),
    ("protocol_fee_recipient", "pubkey"),
    ("protocol_fee_recipient_token_account", "pubkey"),
    ("coin_creator", "pubkey"),
    ("coin_creator_fee_basis_points", "u64"),
    ("coin_creator_fee", "u64"),
]
_TAIL = [
    ("cashback_fee_basis_points", "u64"),
    ("cashback", "u64"),
    ("buyback_fee_basis_points", "u64"),
    ("buyback_fee", "u64"),
    ("virtual_quote_reserves", "i128"),
    ("can_boost", "bool"),
    ("base_supply", "u64"),
    ("holder_rewards_bps", "u64"),
    ("holder_rewards", "u64"),
]
SCHEMAS = {"buy": _BUY_HEAD + _TAIL, "sell": _SELL_HEAD + _TAIL}


def event_discriminator(name: str) -> bytes:
    return hashlib.sha256(b"event:" + name.encode()).digest()[:8]


DISCRIMINATORS = {event_discriminator("BuyEvent"): "buy", event_discriminator("SellEvent"): "sell"}


@dataclass(frozen=True)
class Swap:
    ts: int  # block time of the transaction
    slot: int
    signature: str
    side: str  # buy | sell
    pool: str
    user: str
    base_pre: int  # reserves before the swap (raw token units / lamports)
    quote_pre: int
    virtual_quote: int
    base_amount: int  # tokens out (buy) or in (sell)
    quote_amount: int  # lamports into the curve (buy) or out of it (sell), before fees
    lp_fee: int
    lp_bps: int
    protocol_bps: int
    creator_bps: int
    user_quote: int = 0  # what the user paid (buy) or received (sell), all fees included

    @property
    def base_post(self) -> int:
        return self.base_pre - self.base_amount if self.side == "buy" else self.base_pre + self.base_amount

    @property
    def quote_post(self) -> int:
        delta = self.quote_amount if self.side == "buy" else -self.quote_amount
        return self.quote_pre + delta + self.lp_fee

    @property
    def fee_bps(self) -> int:
        return self.lp_bps + self.protocol_bps + self.creator_bps


def decode_swap_event(payload: bytes) -> dict[str, Any] | None:
    side = DISCRIMINATORS.get(payload[:8])
    if side is None:
        return None
    r = _Reader(payload[8:])
    out: dict[str, Any] = {"side": side}
    for name, ty in SCHEMAS[side]:
        try:
            out[name] = r.read(ty)
        except EOFError:
            out["truncated"] = True
            break
    return out


def _to_swap(ev: dict[str, Any], tx: dict[str, Any], signature: str) -> Swap | None:
    if ev.get("truncated") or "virtual_quote_reserves" not in ev:
        return None
    buy = ev["side"] == "buy"
    return Swap(
        ts=int(tx.get("blockTime") or ev["timestamp"]),
        slot=int(tx.get("slot") or 0),
        signature=signature,
        side=ev["side"],
        pool=ev["pool"],
        user=ev["user"],
        base_pre=ev["pool_base_token_reserves"],
        quote_pre=ev["pool_quote_token_reserves"],
        virtual_quote=ev["virtual_quote_reserves"],
        base_amount=ev["base_amount_out"] if buy else ev["base_amount_in"],
        quote_amount=ev["quote_amount_in"] if buy else ev["quote_amount_out"],
        lp_fee=ev["lp_fee"],
        lp_bps=ev["lp_fee_basis_points"],
        protocol_bps=ev["protocol_fee_basis_points"],
        creator_bps=ev["coin_creator_fee_basis_points"],
        user_quote=ev["user_quote_amount_in"] if buy else ev["user_quote_amount_out"],
    )


def swaps_from_tx(tx: dict[str, Any], pool: str | None = None, signature: str = "") -> list[Swap]:
    """Every PumpSwap swap in a transaction (optionally only those of `pool`), each once.

    Events are mirrored in the logs and through self-CPI; the CPI copy is authoritative
    because logs get truncated, so logs are only used when no CPI copy decoded."""
    if not tx or (tx.get("meta") or {}).get("err"):
        return []
    keys, _ = account_keys(tx)
    found: list[Swap] = []
    for ix, inner in _instructions(tx):
        if not inner or _program_of(ix, keys) != PUMP_AMM:
            continue
        try:
            data = b58decode(ix.get("data") or "")
        except ValueError:
            continue
        if data[:8] != EVENT_IX_TAG:
            continue
        ev = decode_swap_event(data[8:])
        sw = _to_swap(ev, tx, signature) if ev else None
        if sw and (pool is None or sw.pool == pool):
            found.append(sw)
    if not found:
        for payload in parse_logs_payloads((tx.get("meta") or {}).get("logMessages") or []):
            ev = decode_swap_event(payload)
            sw = _to_swap(ev, tx, signature) if ev else None
            if sw and (pool is None or sw.pool == pool):
                found.append(sw)
    return found
