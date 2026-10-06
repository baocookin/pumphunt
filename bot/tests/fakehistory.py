"""Fake address histories for feature tests: pump.fun curve transactions (events logged and
mirrored by self-CPI, as the program emits them), wallets' first transactions, holder RPC calls."""

import base64

from helpers import disc_for, enc, fake_pubkey

from app import anchor
from app.anchor import PUMP_PROGRAM, b58encode
from app.fills import LAMPORTS
from app.rpc import EVENT_IX_TAG

MINT, POOL, CURVE = fake_pubkey(9001), fake_pubkey(9002), fake_pubkey(9003)
DEV, B1, B2, B3, H1, H2 = (fake_pubkey(n) for n in (11, 12, 13, 14, 15, 16))


class HolderRpc:
    def __init__(self, largest, owners, supply):
        self.largest, self.owners, self.supply = largest, owners, supply
        self.calls = []

    async def get_token_largest_accounts(self, mint):
        self.calls.append("largest")
        return [{"address": a, "amount": str(x)} for a, x in self.largest]

    async def get_multiple_accounts(self, pubkeys):
        self.calls.append("accounts")
        return [
            {"data": {"parsed": {"info": {"owner": self.owners[a]}}}} if a in self.owners else None
            for a in pubkeys
        ]

    async def get_token_supply(self, mint):
        self.calls.append("supply")
        return self.supply


def event_bytes(kind, schema, vals):
    return enc(schema, vals, disc_for(kind))


def create_event(ts, mint=MINT, curve=CURVE, dev=DEV):
    vals = {name: 0 for name, _ in anchor.CREATE}
    vals.update(name="T", symbol="T", uri="u", mint=mint, bonding_curve=curve, user=dev, creator=dev)
    vals.update(timestamp=ts, token_program=PUMP_PROGRAM, quote_mint=PUMP_PROGRAM)
    vals.update(is_mayhem_mode=False, is_cashback_enabled=False, is_holder_reward=False)
    return event_bytes("create", anchor.CREATE, vals)


def trade_event(user, sol, buy, ts, mint=MINT, dev=DEV):
    vals = {name: 0 for name, _ in anchor.TRADE}
    vals.update(mint=mint, sol_amount=int(sol * LAMPORTS), token_amount=10**6, is_buy=buy, user=user)
    vals.update(timestamp=ts, fee_recipient=PUMP_PROGRAM, creator=dev, track_volume=False)
    vals.update(ix_name="buy" if buy else "sell", mayhem_mode=False)
    return event_bytes("trade", anchor.TRADE, vals)


def curve_tx(slot, ts, events, idx=0, both=True, curve=CURVE):
    """A transaction carrying pump.fun events as log lines and (if `both`) as self-CPI copies."""
    keys = [fake_pubkey(1), PUMP_PROGRAM, curve]
    logs = [f"Program {PUMP_PROGRAM} invoke [1]"] + [
        "Program data: " + base64.b64encode(e).decode() for e in events
    ]
    inner = [{"programIdIndex": 1, "accounts": [], "data": b58encode(EVENT_IX_TAG + e)} for e in events]
    return {
        "slot": slot,
        "blockTime": ts,
        "transactionIndex": idx,
        "transaction": {
            "signatures": [f"c{slot}-{idx}"],
            "message": {"accountKeys": keys, "instructions": []},
        },
        "meta": {
            "err": None,
            "logMessages": logs,
            "innerInstructions": [{"index": 0, "instructions": inner}] if both else [],
            "loadedAddresses": {"writable": [], "readonly": []},
        },
    }


class HistoryRpc:
    """getTransactionsForAddress per address: full pages oldest or newest first, signature counts."""

    def __init__(self, by_address, page_cap=1000):
        self.by_address = by_address
        self.page_cap = page_cap
        self.calls = []

    async def get_transactions_for_address(
        self, address, *, full, sort, limit, filters, pagination_token=None, commitment="confirmed"
    ):
        self.calls.append((address, full, sort, limit))
        bt = filters.get("blockTime") or {}
        items = [
            t
            for t in self.by_address.get(address, [])
            if bt.get("gte", float("-inf")) <= t["blockTime"] <= bt.get("lte", float("inf"))
        ]
        items.sort(key=lambda t: (t["slot"], t["transactionIndex"]), reverse=(sort == "desc"))
        start = int(pagination_token or 0)
        size = min(limit, self.page_cap if full else 1000)
        chunk = items[start : start + size]
        nxt = start + size
        if not full:
            chunk = [
                {"signature": t["transaction"]["signatures"][0], "blockTime": t["blockTime"]} for t in chunk
            ]
        return {"data": chunk, "paginationToken": str(nxt) if nxt < len(items) else None}


def first_tx(wallet, funder, ts, amount=LAMPORTS):
    keys = [funder, wallet, fake_pubkey(3)]
    return {
        "slot": 1,
        "blockTime": ts,
        "transactionIndex": 0,
        "transaction": {
            "signatures": [f"f-{wallet[:6]}"],
            "message": {"accountKeys": keys, "instructions": []},
        },
        "meta": {
            "err": None,
            "preBalances": [5 * amount, 0, 1],
            "postBalances": [4 * amount - 5000, amount, 1],
        },
    }


class Router:
    """Sends each address's history to its own fake (the pool's chain, curve/wallet histories)."""

    def __init__(self, routes, default):
        self.routes, self.default = routes, default

    async def get_transactions_for_address(self, address, **kw):
        return await self.routes.get(address, self.default).get_transactions_for_address(address, **kw)
