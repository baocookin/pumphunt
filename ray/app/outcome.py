"""Outcome journal: what a 0.5 SOL ticket bought at a score's entry was worth 30 minutes later.

The labels are the research's (research/sieve/journal.py): 0.5 SOL bought at the entry reserves, the
curve's fee each side (1.25%), 0.002 SOL fixed cost, valued against the curve 30 minutes later; a
curve completed before then is sold at completion. trap = net <= -50%, winner = net >= +100%.
Two small differences: Rây's entry is the decision read itself (the research bought one slot later),
and its 30 minutes are wall-clock time from that read (the research counted slots).

Reads. On time, the curve accounts due in a round, 100 per call (1 credit). A curve found complete,
or an outcome read late (after a restart), comes from the curve's history up to the due time
(getTransactionsForAddress newest first, 10 credits a page): its last trade there is the exit, and a
completion among those transactions makes it a sale at completion.
"""

import heapq
import itertools
from collections.abc import Callable
from typing import Any

from .chain import LAMPORTS, chain_order, curve_trades, parse_curve_account
from .rpc import BudgetExhausted, Rpc, describe_error
from .sieve import FL, band

HOLD_S = 1800.0
GRACE_S = 30.0  # an account read this soon after the due time still stands for the state at it
INDEX_WAIT_S = 60.0  # a due time's history is read this long after it (the index trails the chain)
RETRY_S = 60.0
MAX_TRIES = 5
LATER_S = 600.0  # the credit cap stopped the round: try again this much later
HISTORY_PAGES = 5
TRAP_LEVEL, WIN_LEVEL = -0.5, 1.0


def ticket_net(entry: tuple[float, float], exit_: tuple[float, float], fee: float) -> float:
    """Net of a 0.5 SOL ticket bought at `entry` reserves (v_sol, v_tokens) and sold at `exit_`, the
    curve as it really was, the ticket's tokens outstanding (research/sieve/journal.ticket)."""
    vs, vt = float(entry[0]), float(entry[1])
    net_in = FL.SIZE * LAMPORTS / (1 + fee)
    dt = vt * net_in / (vs + net_in)
    xs, xt = float(exit_[0]), float(exit_[1])
    value = 0.0 if xt <= dt else (1 - fee) * xs * dt / (xt - dt)
    return (value / LAMPORTS - FL.FIXED) / FL.SIZE - 1


def label_of(net: float) -> str:
    return "trap" if net <= TRAP_LEVEL else "winner" if net >= WIN_LEVEL else "neutral"


def journal_line(sc: dict[str, Any], o: dict[str, Any]) -> dict[str, Any]:
    """One line of outcomes-*.jsonl: the score's verdict and flags with its outcome, everything the
    weekly report needs without reading the scores back."""
    groups = {g: sc.get(g) or [] for g in ("active", "shadow", "info")}
    data = sc.get("data") or {}
    rk = sc.get("risk") or {}
    real_d = sc.get("real_d")
    return {
        "mint": sc["mint"],
        "symbol": sc.get("symbol"),
        "key": sc.get("key"),
        "D": sc.get("D"),
        "score_at": sc.get("at"),
        "entry_at": sc["entry"]["at"],
        "verdict": sc.get("verdict"),
        "real": sc.get("real"),
        "real_d": real_d,
        "band": band(float(real_d)) if real_d is not None else None,
        "risk": rk.get("pct"),
        "fired": {g: [f["id"] for f in fl if f.get("fired")] for g, fl in groups.items()},
        "unscored": [f["id"] for f in groups["active"] + groups["shadow"] if not f.get("scored")],
        "chain_ok": data.get("chain_ok"),
        "synced": data.get("synced"),
        "entry": sc["entry"],
        **o,
    }


class _Due:
    __slots__ = ("sc", "due", "mode", "tries")

    def __init__(self, sc: dict[str, Any], due: float):
        self.sc, self.due, self.mode, self.tries = sc, due, "account", 0


class Outcomes:
    """Scores waiting for their 30-minute outcome, and the reads that settle them. `record(score,
    outcome)` gets each settled one (the engine attaches it to the score and writes the journal)."""

    def __init__(
        self,
        rpc: Rpc,
        record: Callable[[dict[str, Any], dict[str, Any]], None],
        clock: Callable[[], float],
    ):
        self.rpc = rpc
        self.record = record
        self.clock = clock
        self.heap: list[tuple[float, int, _Due]] = []
        self._seq = itertools.count()
        self.stats: dict[str, Any] = {
            "settled": 0,
            "trap": 0,
            "winner": 0,
            "neutral": 0,
            "unresolved": 0,
            "by_account": 0,
            "by_history": 0,
            "errors": 0,
            "last_error": None,
        }

    def pending(self) -> int:
        return len(self.heap)

    def track(self, sc: dict[str, Any]) -> bool:
        """Wait for this score's outcome (a full score: it carries its entry)."""
        e = sc.get("entry")
        if not e or sc.get("outcome") is not None:
            return False
        due = float(e["at"]) + HOLD_S
        self._push(due, _Due(sc, due))
        return True

    def _push(self, ready: float, d: _Due) -> None:
        heapq.heappush(self.heap, (ready, next(self._seq), d))

    async def run_once(self) -> int:
        """Settle the outcomes that are due; returns how many were settled."""
        now = self.clock()
        if not self.heap or self.heap[0][0] > now or not self.rpc.meter.allows("outcome"):
            return 0
        ready: list[_Due] = []
        while self.heap and self.heap[0][0] <= now:
            ready.append(heapq.heappop(self.heap)[2])
        on_time = [d for d in ready if d.mode == "account" and now - d.due <= GRACE_S]
        late = [d for d in ready if not (d.mode == "account" and now - d.due <= GRACE_S)]
        settled = 0
        capped = False
        for i in range(0, len(on_time), 100):
            batch = on_time[i : i + 100]
            if capped:
                self._later(batch, now)
                continue
            try:
                _, values = await self.rpc.multiple_accounts(
                    [d.sc["entry"]["curve"] for d in batch], kind="outcome"
                )
            except BudgetExhausted:
                capped = True
                self._later(batch, now)
                continue
            except Exception as exc:  # noqa: BLE001 - read again from the history
                self._failed(batch, exc, now)
                continue
            for d, val in zip(batch, values + [None] * (len(batch) - len(values)), strict=False):
                acc = parse_curve_account(val)
                if acc is None or acc["complete"]:
                    # sold at completion (or no account to read): the history says when and at what
                    d.mode = "history"
                    self._push(d.due + INDEX_WAIT_S, d)
                    continue
                self._settle(d, (acc["v_sol"], acc["v_tokens"]), "time", "account", now)
                settled += 1
        for d in late:
            d.mode = "history"
            if capped:
                self._later([d], now)
                continue
            if now < d.due + INDEX_WAIT_S:
                self._push(d.due + INDEX_WAIT_S, d)
                continue
            try:
                found = await self._from_history(d)
            except BudgetExhausted:
                capped = True
                self._later([d], now)
                continue
            except Exception as exc:  # noqa: BLE001 - retried, then given up on
                self._failed([d], exc, now)
                continue
            if found is None:
                self._unresolved(d, now, "no_trade")
            else:
                self._settle(d, found[0], found[1], "history", now)
            settled += 1
        return settled

    async def _from_history(self, d: _Due) -> tuple[tuple[int, int], str] | None:
        """(exit reserves, why) from the curve's last trade up to the due time, newest first."""
        e = d.sc["entry"]
        mint = d.sc["mint"]
        txs: list[dict[str, Any]] = []
        token = None
        for _ in range(HISTORY_PAGES):
            res = await self.rpc.gtfa(
                e["curve"], kind="outcome", sort="desc", limit=100, t_to=int(d.due), token=token
            )
            data = res["data"]
            txs.extend(data)
            if curve_trades(data, mint)["trades"]:
                break  # newest first: this page holds the last trade before the due time
            token = res.get("paginationToken")
            if not data or not token or len(data) < int(res.get("asked") or 100):
                break
        path = curve_trades(txs, mint)
        trades = path["trades"]
        if not trades:
            return None
        chain_order(trades)
        last = trades[-1]
        # the completing buy carries the complete event: after it the curve has no trades
        return (int(last[8]), int(last[9])), ("grad" if path["complete"] else "time")

    def _settle(self, d: _Due, exit_: tuple[int, int], why: str, how: str, now: float) -> None:
        e = d.sc["entry"]
        net = ticket_net((e["v_sol"], e["v_tokens"]), exit_, float(e["fee"]))
        label = label_of(net)
        self.stats["settled"] += 1
        self.stats[label] += 1
        self.stats[f"by_{how}"] += 1
        o = {
            "status": "ok",
            "net": round(net, 4),
            "label": label,
            "why": why,
            "how": how,
            "due": round(d.due, 3),
            "read_at": round(now, 3),
            "real_exit": round((int(exit_[0]) - int(e["v_sol0"])) / LAMPORTS, 4),
        }
        self.record(d.sc, o)

    def _unresolved(self, d: _Due, now: float, why: str) -> None:
        self.stats["unresolved"] += 1
        o = {"status": "unresolved", "net": None, "label": None, "why": why, "how": d.mode}
        self.record(d.sc, {**o, "due": round(d.due, 3), "read_at": round(now, 3), "real_exit": None})

    def _failed(self, items: list[_Due], exc: BaseException, now: float) -> None:
        self.stats["errors"] += 1
        self.stats["last_error"] = describe_error(exc)
        for d in items:
            d.tries += 1
            if d.tries >= MAX_TRIES:
                self._unresolved(d, now, "read_error")
                continue
            d.mode = "history"
            self._push(max(now + RETRY_S, d.due + INDEX_WAIT_S), d)

    def _later(self, items: list[_Due], now: float) -> None:
        for d in items:
            self._push(now + LATER_S, d)
