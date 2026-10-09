"""Live launches: the census of creates, the reserve reads, and the decision times.

Census. Every pump.fun create transaction names the mint authority, so its history lists every
launch (measured 06/10/2026: 190 of 190 successful transactions were creates). The scorer reads it
every `census_s` with Helius getTransactionsForAddress (full transactions, 10 credits per 100),
from the last block time seen, and keeps classic SOL-quoted launches.

Reserves. Each live curve is read with getMultipleAccounts, 100 per call: often while the curve
holds real SOL (hot), rarely while it does not (cold). A decision time D is decided on a read
taken at or after D: complete, under 5 SOL, below the 11.66 SOL gate, past 70 SOL, or a candidate
whose history is read and scored.
"""

import asyncio
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

from .chain import LAMPORTS, MINT_AUTHORITY, classic_sol, create_of, launch_info, signature_of
from .history import History
from .rpc import Rpc
from .sieve import F0_MAX, F0_MIN, GATE_E


@dataclass
class Token:
    info: dict[str, Any]
    seen_at: float
    state: dict[str, Any] | None = None  # last curve read: slot, at, v_sol, v_tokens, real, complete
    peak_real: float = 0.0
    next_read: float = 0.0
    done: dict[int, str] = field(default_factory=dict)  # decision time -> outcome
    history: History | None = None
    scores: dict[str, dict[str, Any]] = field(default_factory=dict)
    pending: int = 0  # scorings queued or running; the history is kept until they finish
    archived: bool = False  # its scored trades are in the row archive
    lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False, compare=False)

    @property
    def mint(self) -> str:
        return self.info["mint"]

    @property
    def curve(self) -> str:
        return self.info["curve"]

    @property
    def t0(self) -> int:
        return int(self.info["create_ts"])

    def age(self, now: float) -> float:
        return now - self.t0

    def view(self, now: float) -> dict[str, Any]:
        """What the dashboard lists for a live launch."""
        st = self.state or {}
        last = max(self.scores.values(), key=lambda s: s["at"]) if self.scores else None
        return {
            "mint": self.mint,
            "symbol": self.info.get("symbol") or "",
            "name": self.info.get("name") or "",
            "age_s": round(self.age(now), 1),
            "real": st.get("real"),
            "peak_real": round(self.peak_real, 3),
            "complete": st.get("complete"),
            "state_age_s": round(now - st["at"], 1) if st else None,
            "done": {str(k): v for k, v in self.done.items()},
            "last": None
            if last is None
            else {
                k: last.get(k)
                for k in ("key", "verdict", "verdict_vi", "risk", "floor", "real", "at", "summary")
            },
        }


class Census:
    """Creates from the mint authority's history, since the last block time seen."""

    def __init__(self, rpc: Rpc, backfill_s: float):
        self.rpc = rpc
        self.backfill_s = backfill_s
        self.cursor_ts: int | None = None
        self.seen: OrderedDict[str, None] = OrderedDict()  # recent create signatures
        self.stats: dict[str, Any] = {"polls": 0, "creates": 0, "kept": 0, "skipped": 0, "last_poll": 0.0}

    async def poll(self, now: float) -> list[dict[str, Any]]:
        t_from = self.cursor_ts if self.cursor_ts is not None else int(now - self.backfill_s)
        token = None
        out = []
        while True:
            res = await self.rpc.gtfa(
                MINT_AUTHORITY, kind="census", sort="asc", limit=100, t_from=t_from, token=token
            )
            data = res["data"]
            for tx in data:
                sig = signature_of(tx)
                if not sig or sig in self.seen:
                    continue
                self.seen[sig] = None
                bt = int(tx.get("blockTime") or 0)
                if bt and (self.cursor_ts is None or bt > self.cursor_ts):
                    self.cursor_ts = bt
                create = create_of(tx)
                if create is None:
                    continue
                self.stats["creates"] += 1
                info = launch_info(create, tx, sig)
                if classic_sol(info):
                    out.append(info)
                    self.stats["kept"] += 1
                else:
                    self.stats["skipped"] += 1
            token = res.get("paginationToken")
            if not data or not token or len(data) < int(res.get("asked") or 100):
                break
        while len(self.seen) > 20_000:
            self.seen.popitem(last=False)
        if self.cursor_ts is None:
            self.cursor_ts = int(t_from)
        self.stats["polls"] += 1
        self.stats["last_poll"] = now
        return out


class Tracker:
    """Live launches, their reserve-read schedule and their decision times."""

    def __init__(self, cfg: Any):
        self.cfg = cfg
        self.live: dict[str, Token] = {}
        self.archive: OrderedDict[str, Token] = OrderedDict()  # retired launches, for lookups
        self.horizon = max(cfg.checkpoints_s) + cfg.checkpoint_late_s + 15

    def get(self, mint: str) -> Token | None:
        return self.live.get(mint) or self.archive.get(mint)

    def add(self, info: dict[str, Any], now: float) -> Token | None:
        if info["mint"] in self.live or info["mint"] in self.archive:
            return None
        if now - int(info["create_ts"]) > self.horizon:
            return None  # too old to reach any decision time
        tok = Token(info=info, seen_at=now)
        self.live[tok.mint] = tok
        return tok

    def adopt(self, tok: Token) -> None:
        """Keep a launch read on demand (not live) for later lookups."""
        self.archive[tok.mint] = tok
        self.archive.move_to_end(tok.mint)
        while len(self.archive) > 5_000:
            self.archive.popitem(last=False)

    def due_reads(self, now: float) -> list[Token]:
        return [t for t in self.live.values() if t.next_read <= now]

    def apply_read(self, tok: Token, slot: int, account: dict[str, Any] | None, now: float) -> None:
        cfg = self.cfg
        if account is None:
            tok.next_read = now + cfg.cold_poll_s
            return
        real = (int(account["v_sol"]) - int(tok.info["v_sol0"])) / LAMPORTS
        if account["complete"] and real < 0:
            real = tok.peak_real  # migrated: the curve was emptied into the AMM pool
        tok.state = {
            "slot": slot,
            "at": now,
            "v_sol": int(account["v_sol"]),
            "v_tokens": int(account["v_tokens"]),
            "real": round(real, 6),
            "complete": bool(account["complete"]),
        }
        tok.peak_real = max(tok.peak_real, real)
        hot = real >= cfg.hot_min_sol or tok.age(now) < cfg.hot_age_s
        tok.next_read = now + (cfg.hot_poll_s if hot else cfg.cold_poll_s)

    def decisions(self, now: float) -> list[tuple[Token, int, str]]:
        """Decision times reached since the last call: (token, D, outcome). Outcomes: score (read the
        history), below_gate, beyond, graduated, small, missed. A decision whose last read predates
        it asks for a read now and waits for it."""
        cfg = self.cfg
        out = []
        for tok in self.live.values():
            age = tok.age(now)
            for D in cfg.checkpoints_s:
                if D in tok.done or age < D:
                    continue
                st = tok.state
                if age > D + cfg.checkpoint_late_s:
                    tok.done[D] = "missed"
                    out.append((tok, D, "missed"))
                    continue
                if st is None or st["at"] - tok.t0 < D:
                    tok.next_read = min(tok.next_read, now)  # read it on the next poll
                    continue
                real = st["real"]
                if st["complete"]:
                    outcome = "graduated"
                elif real < F0_MIN:
                    outcome = "small"
                elif real < GATE_E and not cfg.score_below_gate:
                    outcome = "below_gate"
                elif real >= F0_MAX:
                    outcome = "beyond"
                else:
                    outcome = "score"
                tok.done[D] = outcome
                out.append((tok, D, outcome))
        return out

    def retire(self, now: float) -> list[Token]:
        """Move launches past the last decision time (or graduated) out of the live set; returns them
        (the engine frees their histories)."""
        gone = []
        for mint, tok in self.live.items():
            age = tok.age(now)
            finished = all(D in tok.done for D in self.cfg.checkpoints_s)
            graduated = bool(tok.state and tok.state["complete"] and age > 60)
            if age > self.horizon or (finished and age > max(self.cfg.checkpoints_s)) or graduated:
                gone.append(mint)
        out = []
        for mint in gone:
            tok = self.live.pop(mint)
            self.adopt(tok)
            out.append(tok)
        return out

    def counts(self, now: float) -> dict[str, int]:
        hot = sum(1 for t in self.live.values() if t.state and t.state["real"] >= self.cfg.hot_min_sol)
        return {"live": len(self.live), "hot": hot, "archive": len(self.archive)}
