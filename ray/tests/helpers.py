"""Fake pump.fun launches for the tests: events encoded the way the program logs them, curve reserves
that chain exactly, and a Helius-like RPC serving them."""

import base64
from typing import Any

from app import chain
from app.chain import CURVE_DISC, PUMP_PROGRAM, b58decode, b58encode
from app.rpc import CreditMeter, gtfa_credits

SYSTEM = "11111111111111111111111111111111"
V_SOL0 = 30_000_000_000
V_TOK0 = 1_073_000_000_000_000
LAMPORTS = 1_000_000_000


def pk(seed: int) -> str:
    return b58encode(seed.to_bytes(32, "big"))


def enc(schema: list[tuple[str, str]], values: dict[str, Any], disc: bytes) -> bytes:
    out = bytearray(disc)
    for name, ty in schema:
        v = values[name]
        if ty == "u64":
            out += int(v).to_bytes(8, "little")
        elif ty == "i64":
            out += int(v).to_bytes(8, "little", signed=True)
        elif ty == "bool":
            out += bytes([1 if v else 0])
        elif ty == "pubkey":
            out += b58decode(v).rjust(32, b"\0")
        elif ty == "string":
            b = str(v).encode()
            out += len(b).to_bytes(4, "little") + b
    return bytes(out)


def disc_for(kind: str) -> bytes:
    return next(d for d, (k, _) in chain.DISCRIMINATORS.items() if k == kind)


def log_line(payload: bytes) -> str:
    return "Program data: " + base64.b64encode(payload).decode()


class Launch:
    """One launch: its create transaction and trades whose reserves chain exactly."""

    def __init__(self, seed: int, t0: int = 1_800_000_000, s0: int = 500_000_000, mayhem: bool = False):
        self.mint, self.curve, self.dev = pk(seed), pk(seed + 1), pk(seed + 2)
        self.t0, self.s0 = t0, s0
        self.vs, self.vt = V_SOL0, V_TOK0
        self.txs: list[dict[str, Any]] = []
        self.complete = False
        self._n = 0
        vals = {name: 0 for name, _ in chain.CREATE}
        vals.update(
            name="Test",
            symbol="TST",
            uri="u",
            mint=self.mint,
            bonding_curve=self.curve,
            user=self.dev,
            creator=self.dev,
            timestamp=t0,
            virtual_token_reserves=V_TOK0,
            virtual_sol_reserves=V_SOL0,
            token_total_supply=10**15,
            token_program=PUMP_PROGRAM,
            is_mayhem_mode=mayhem,
            is_cashback_enabled=False,
            quote_mint=SYSTEM,
            is_holder_reward=False,
        )
        self.create_tx = self._tx(s0, t0, 0, [enc(chain.CREATE, vals, disc_for("create"))])
        self.txs.append(self.create_tx)

    def _tx(self, slot: int, ts: int, idx: int | None, payloads: list[bytes]) -> dict[str, Any]:
        self._n += 1
        tx: dict[str, Any] = {
            "slot": slot,
            "blockTime": ts,
            "meta": {"err": None, "logMessages": [log_line(p) for p in payloads], "innerInstructions": []},
            "transaction": {
                "signatures": [f"sig{self.mint[:6]}{self._n}"],
                "message": {"accountKeys": [pk(1), PUMP_PROGRAM, self.curve], "instructions": []},
            },
        }
        if idx is not None:
            tx["transactionIndex"] = idx
        return tx

    def _trade_payload(self, user: str, sol: int, tok: int, buy: bool, ts: int) -> bytes:
        vals = {name: 0 for name, _ in chain.TRADE}
        vals.update(
            mint=self.mint,
            sol_amount=sol,
            token_amount=tok,
            is_buy=buy,
            user=user,
            timestamp=ts,
            virtual_sol_reserves=self.vs,
            virtual_token_reserves=self.vt,
            fee_recipient=PUMP_PROGRAM,
            fee_basis_points=95,
            creator=self.dev,
            creator_fee_basis_points=30,
            ix_name="buy" if buy else "sell",
        )
        return enc(chain.TRADE, vals, disc_for("trade"))

    def buy(
        self, user: str, sol_sol: float, slot: int, ts: int, idx: int | None = 1, in_create: bool = False
    ):
        sol = int(sol_sol * LAMPORTS)
        k = self.vs * self.vt
        new_vs = self.vs + sol
        new_vt = k // new_vs
        tok = self.vt - new_vt
        self.vs, self.vt = new_vs, new_vt
        payload = self._trade_payload(user, sol, tok, True, ts)
        if in_create:
            self.create_tx["meta"]["logMessages"].append(log_line(payload))
        else:
            self.txs.append(self._tx(slot, ts, idx, [payload]))
        return tok

    def finish(self, user: str, sol_sol: float, slot: int, ts: int, idx: int | None = 1):
        """The buy that completes the curve: its trade and the complete event in one transaction."""
        sol = int(sol_sol * LAMPORTS)
        k = self.vs * self.vt
        self.vs += sol
        tok = self.vt - k // self.vs
        self.vt = k // self.vs
        vals = {"user": user, "mint": self.mint, "bonding_curve": self.curve, "timestamp": ts}
        vals["quote_mint"] = SYSTEM
        done = enc(chain.COMPLETE, vals, disc_for("complete"))
        self.txs.append(self._tx(slot, ts, idx, [self._trade_payload(user, sol, tok, True, ts), done]))
        self.complete = True

    def migrate(self):
        """The curve's reserves move to the AMM pool: the account reads empty, still complete."""
        self.vs = self.vt = 0

    def sell(self, user: str, tok: int, slot: int, ts: int, idx: int | None = 1):
        k = self.vs * self.vt
        new_vt = self.vt + tok
        new_vs = k // new_vt
        sol = self.vs - new_vs
        self.vs, self.vt = new_vs, new_vt
        self.txs.append(self._tx(slot, ts, idx, [self._trade_payload(user, sol, tok, False, ts)]))
        return sol

    @property
    def real(self) -> float:
        return (self.vs - V_SOL0) / LAMPORTS

    def account(self) -> dict[str, Any]:
        raw = bytearray(CURVE_DISC)
        for v in (self.vt, self.vs, self.vt - 279_900_000_000_000, self.vs - V_SOL0, 10**15):
            raw += int(max(0, v)).to_bytes(8, "little")
        raw += bytes([1 if self.complete else 0]) + b58decode(self.dev).rjust(32, b"\0")
        raw += bytes(70)
        return {"data": [base64.b64encode(bytes(raw)).decode(), "base64"], "owner": PUMP_PROGRAM}


class FakeRpc:
    """Helius-like: getTransactionsForAddress pages (always with a pagination token) and
    getMultipleAccounts over registered launches."""

    def __init__(self, meter: CreditMeter | None = None):
        self.meter = meter or CreditMeter(10**9)
        self.history: dict[str, list[dict[str, Any]]] = {}
        self.launches: dict[str, Launch] = {}
        self.slot = 0
        self.calls: list[tuple[str, str]] = []
        self.stats: dict[str, Any] = {"calls": 0}
        self.hidden_after: dict[str, int] = {}  # address -> hide txs with blockTime above (index lag)
        self.reveal_after: dict[str, int] = {}  # address -> reads that still hide them (then caught up)

    def add(self, launch: Launch) -> None:
        self.launches[launch.curve] = launch

    async def gtfa(self, address, *, kind, sort="asc", limit=100, t_from=None, t_to=None, token=None):
        self.calls.append(("gtfa", address))
        if address in self.reveal_after:
            if self.reveal_after[address] <= 0:
                self.hidden_after.pop(address, None)
            self.reveal_after[address] -= 1
        txs = self._txs_for(address)
        lag = self.hidden_after.get(address)
        txs = [
            tx
            for tx in txs
            if (t_from is None or tx["blockTime"] >= t_from)
            and (t_to is None or tx["blockTime"] <= t_to)
            and (lag is None or tx["blockTime"] <= lag)
        ]
        txs.sort(
            key=lambda tx: (tx["blockTime"], tx["slot"], tx.get("transactionIndex") or 0),
            reverse=sort == "desc",
        )
        start = int(token or 0)
        page = txs[start : start + limit]
        self.meter.add(gtfa_credits(len(page)), kind)
        return {"data": page, "paginationToken": str(start + len(page) or 1), "asked": limit}

    def _txs_for(self, address: str) -> list[dict[str, Any]]:
        if address in self.history:
            return list(self.history[address])
        for la in self.launches.values():
            if address in (la.curve, la.mint):
                return list(la.txs)
        return []

    async def multiple_accounts(self, pubkeys, *, kind):
        self.calls.append(("accounts", ",".join(p[:4] for p in pubkeys)))
        self.meter.add(1, kind)
        return self.slot, [self.launches[p].account() if p in self.launches else None for p in pubkeys]


class TrustAll:
    """Live rules under which every filter decides by its tier (the engine tests' default)."""

    rows = 0

    def allows(self, fid: str) -> bool:
        return True

    def record(self, fid: str) -> None:
        return None

    def base(self, band: str, D: int) -> None:
        return None

    def by_time(self, band: str) -> list[dict[str, Any]]:
        return []

    def snapshot(self) -> dict[str, Any]:
        return {"rows": 0, "suspended": [], "ok": []}


class Cfg:
    """Settings for the engine tests (the defaults of app.config, made fast)."""

    census_s = 60.0
    census_backfill_s = 660.0
    poll_tick_s = 5.0
    hot_poll_s = 5.0
    cold_poll_s = 30.0
    hot_min_sol = 2.0
    hot_age_s = 45.0
    checkpoints_s = [120, 300, 600]
    checkpoint_late_s = 45.0
    score_below_gate = False
    history_max_tx = 6_000
    workers = 1
    sync_waits_s = [0.0, 0.0]
    ondemand_per_hour = 60
    keep_scores = 100
    outcome_tick_s = 5.0
    archive_rows = True
    rules_refresh_s = 600.0

    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


def row_of(launch: Launch) -> dict[str, Any]:
    """The census row of a launch read through the chain module (what History.row builds)."""
    info = chain.launch_info(
        chain.create_of(launch.create_tx), launch.create_tx, chain.signature_of(launch.create_tx)
    )
    path = chain.curve_trades(launch.txs, launch.mint)
    trades = path["trades"]
    chain.chain_order(trades)
    return {**info, "status": "ok", "trades": trades, "complete": path["complete"], "fee_bps": 125}
