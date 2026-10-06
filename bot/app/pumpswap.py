"""PumpSwap (pump.fun's AMM) swap events, decoded from transactions.

Schemas copied from pump-fun/pump-public-docs idl/pump_amm.json (BuyEvent, SellEvent).
Facts verified against mainnet transactions (tests/fixtures/pumpswap*):
  * `pool_base_token_reserves` / `pool_quote_token_reserves` are the reserves BEFORE the swap,
    and the state after one swap is exactly the next swap's "before".
  * The base side always moves by the event's token amount.
  * The quote vault does not move the same way for every instruction. The classic rule
        buy : quote + quote_in + lp_fee        sell: quote - quote_out + lp_fee
    (LP fee stays, protocol and creator fees leave) holds for `buy` and sells, but the
    BuyEvent fields are permuted for `buy_exact_quote_in` (`quote_amount_in` is what the user
    paid, `user_quote_amount_in` the curve input) and `buy_exact_quote_in_v2` keeps every fee
    but the buyback share in the vault. `quote_amount_in_with_lp_fee - lp_fee` is the curve
    input for all three. The vault's own balance change, read from the transaction's token
    balances, is used whenever the transaction holds a single swap of the pool.
Pools also carry `virtual_quote_reserves`: it enters the price but is not real SOL.
"""

import hashlib
from collections import Counter
from dataclasses import dataclass, replace
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
    tx_index: int = 0  # position of the transaction in its block (getTransactionsForAddress only)
    ev_index: int = 0  # position of the swap inside its transaction
    coin_creator: str = ""  # wallet that earns the pool's creator fee: the token's creator
    vault_delta: int | None = None  # change of the real quote vault; None: the classic rule
    ix_name: str = ""  # buy, buy_exact_quote_in, buy_exact_quote_in_v2 (sells carry none)

    @property
    def order(self) -> tuple[int, int, int]:
        """Chain order. Block time has one-second resolution and many swaps share a second."""
        return (self.slot, self.tx_index, self.ev_index)

    @property
    def base_post(self) -> int:
        return self.base_pre - self.base_amount if self.side == "buy" else self.base_pre + self.base_amount

    @property
    def quote_post(self) -> int:
        if self.vault_delta is not None:
            return self.quote_pre + self.vault_delta
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


def _buy_amounts(ev: dict[str, Any]) -> tuple[int, int, int]:
    """(curve input, what the user paid, quote vault change) of a BuyEvent, per instruction."""
    ix = ev.get("ix_name") or "buy"
    curve_in = ev["quote_amount_in_with_lp_fee"] - ev["lp_fee"]
    # exact-in buys fix the user's total spend, fees included, and report it as quote_amount_in
    paid = ev["quote_amount_in"] if ix.startswith("buy_exact_quote_in") else ev["user_quote_amount_in"]
    if ix == "buy_exact_quote_in_v2":
        return curve_in, paid, paid - ev["buyback_fee"]
    return curve_in, paid, ev["quote_amount_in_with_lp_fee"]


def _to_swap(
    ev: dict[str, Any], tx: dict[str, Any], signature: str, ev_index: int = 0, vault_delta: int | None = None
) -> Swap | None:
    if ev.get("truncated") or "virtual_quote_reserves" not in ev:
        return None
    buy = ev["side"] == "buy"
    if buy:
        quote_amount, user_quote, rule_delta = _buy_amounts(ev)
    else:
        quote_amount, user_quote = ev["quote_amount_out"], ev["user_quote_amount_out"]
        rule_delta = ev["lp_fee"] - quote_amount
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
        quote_amount=quote_amount,
        lp_fee=ev["lp_fee"],
        lp_bps=ev["lp_fee_basis_points"],
        protocol_bps=ev["protocol_fee_basis_points"],
        creator_bps=ev["coin_creator_fee_basis_points"],
        user_quote=user_quote,
        tx_index=int(tx.get("transactionIndex") or 0),
        ev_index=ev_index,
        coin_creator=ev.get("coin_creator") or "",
        vault_delta=rule_delta if vault_delta is None else vault_delta,
        ix_name=ev.get("ix_name") or "",
    )


WSOL = "So11111111111111111111111111111111111111112"


def quote_vault_deltas(tx: dict[str, Any]) -> dict[str, int]:
    """Pool -> change of its WSOL vault over the whole transaction, from the token balances."""
    meta = tx.get("meta") or {}

    def side(key: str) -> dict[int, tuple[str, int]]:
        out = {}
        for b in meta.get(key) or []:
            if b.get("mint") == WSOL and b.get("owner"):
                out[int(b["accountIndex"])] = (
                    b["owner"],
                    int((b.get("uiTokenAmount") or {}).get("amount") or 0),
                )
        return out

    pre, post = side("preTokenBalances"), side("postTokenBalances")
    deltas: dict[str, int] = {}
    for idx, (owner, amount) in post.items():
        before = pre.get(idx, (owner, 0))[1]
        deltas[owner] = deltas.get(owner, 0) + amount - before
    return deltas


def tx_signature(tx: dict[str, Any]) -> str:
    sigs = (tx.get("transaction") or {}).get("signatures") or []
    return str(sigs[0]) if sigs else ""


def swaps_from_tx(tx: dict[str, Any], pool: str | None = None, signature: str = "") -> list[Swap]:
    """Every PumpSwap swap in a transaction (optionally only those of `pool`), each once.

    Events are mirrored in the logs and through self-CPI; the CPI copy is authoritative
    because logs get truncated, so logs are only used when no CPI copy decoded."""
    if not tx or (tx.get("meta") or {}).get("err"):
        return []
    signature = signature or tx_signature(tx)
    keys, _ = account_keys(tx)
    found: list[Swap] = []
    n = 0
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
        sw = _to_swap(ev, tx, signature, n) if ev else None
        if sw:
            n += 1
            if pool is None or sw.pool == pool:
                found.append(sw)
    if not found:
        for payload in parse_logs_payloads((tx.get("meta") or {}).get("logMessages") or []):
            ev = decode_swap_event(payload)
            sw = _to_swap(ev, tx, signature, n) if ev else None
            if sw:
                n += 1
                if pool is None or sw.pool == pool:
                    found.append(sw)
    # A pool swapped once in this transaction: its vault's measured change replaces the rule.
    once = Counter(s.pool for s in found)
    if found and any(c == 1 for c in once.values()):
        deltas = quote_vault_deltas(tx)
        found = [
            replace(s, vault_delta=deltas[s.pool]) if once[s.pool] == 1 and s.pool in deltas else s
            for s in found
        ]
    return found
