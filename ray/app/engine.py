"""The scorer: census, reserve reads, decision times, history reads, scores, and the score book.

Loops (asyncio, one process):
  census     every census_s: new classic launches from the mint authority's history
  poll       every poll_tick_s: due curve accounts in batches of 100, then the decision times
  workers    score the candidates the decision times queued (history read + frozen filters)
On demand, any mint can be scored at its current state (dashboard search, Telegram).

A score is anchored on the curve read that reached its decision time: the history is read until it
replays to exactly that read's reserves (the transaction index trails the accounts by 15-30 s on
the public RPC, measured 09/10/2026), so the filters see every trade up to the decision slot.
"""

import asyncio
import contextlib
import datetime
import gzip
import itertools
import json
import time
from collections import OrderedDict, deque
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from .chain import LAMPORTS, classic_sol, create_of, launch_info, parse_curve_account, signature_of
from .history import History
from .live import Census, Token, Tracker
from .rpc import BudgetExhausted, Rpc, describe_error
from .sieve import FROZEN_PROBLEMS, light_score, score_row

LIGHT = {"below_gate": "DUOI_CONG", "beyond": "NGOAI_VUNG", "graduated": "DA_TOT_NGHIEP"}


class OnDemandLimit(Exception):
    """The hour's allowance of scores asked by mint is used up."""


class ScoreBook:
    """Recent scores in memory, every score appended to a daily JSONL file under data_dir/ray/."""

    def __init__(self, data_dir: str | Path, keep: int = 3_000):
        self.dir = Path(data_dir) / "ray"
        self.keep = keep
        self.recent: deque[dict[str, Any]] = deque(maxlen=keep)
        self.latest: OrderedDict[str, dict[str, Any]] = OrderedDict()  # last score per mint, bounded
        self.count_today = 0
        self._day = ""

    def _path(self, ts: float) -> Path:
        day = datetime.datetime.fromtimestamp(ts, datetime.UTC).strftime("%Y-%m-%d")
        return self.dir / f"scores-{day}.jsonl"

    def _remember(self, sc: dict[str, Any]) -> None:
        self.latest[sc["mint"]] = sc
        self.latest.move_to_end(sc["mint"])
        while len(self.latest) > self.keep:
            self.latest.popitem(last=False)

    def add(self, sc: dict[str, Any]) -> None:
        self.recent.appendleft(sc)
        self._remember(sc)
        day = self._path(sc["at"]).name
        if day != self._day:
            self._day, self.count_today = day, 0
        self.count_today += 1
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            with open(self._path(sc["at"]), "a") as fh:
                fh.write(json.dumps(sc, separators=(",", ":"), ensure_ascii=False) + "\n")
        except OSError:
            pass  # the dashboard works without the log

    def load(self, now: float) -> int:
        """Scores of yesterday and today back into memory (oldest first, so the newest lead)."""
        rows: list[dict[str, Any]] = []
        for ts in (now - 86_400, now):
            p = self._path(ts)
            opener = gzip.open if p.suffix == ".gz" else open
            if not p.is_file():
                continue
            with opener(p, "rt") as fh:
                for line in fh:
                    try:
                        rows.append(json.loads(line))
                    except ValueError:
                        continue
        for sc in rows[-(self.recent.maxlen or 0) :]:
            self.recent.appendleft(sc)
            self._remember(sc)
        return len(rows)

    def save_credits(self, snap: dict[str, Any]) -> None:
        with contextlib.suppress(OSError):
            self.dir.mkdir(parents=True, exist_ok=True)
            tmp = self.dir / "credits.json.tmp"
            tmp.write_text(json.dumps(snap))
            tmp.replace(self.dir / "credits.json")

    def load_credits(self) -> dict[str, Any]:
        try:
            return json.loads((self.dir / "credits.json").read_text())
        except (OSError, ValueError):
            return {}


class Engine:
    def __init__(
        self,
        cfg: Any,
        rpc: Rpc,
        book: ScoreBook,
        clock: Callable[[], float] = time.time,
    ):
        self.cfg = cfg
        self.rpc = rpc
        self.book = book
        self.clock = clock
        self.tracker = Tracker(cfg)
        self.census = Census(rpc, cfg.census_backfill_s)
        # (D, seq, mint, D, anchor): earlier decision times first; the anchor is the curve read
        self.queue: asyncio.PriorityQueue[tuple[int, int, str, int, dict[str, Any]]] = asyncio.PriorityQueue()
        self._seq = itertools.count()
        self.listeners: list[Callable[[dict[str, Any]], Awaitable[None]]] = []
        self.ondemand: deque[float] = deque()
        self.stats: dict[str, Any] = {
            "started": clock(),
            "census_errors": 0,
            "poll_errors": 0,
            "score_errors": 0,
            "last_census": 0.0,
            "last_poll": 0.0,
            "last_error": None,
            "scored": 0,
            "outcomes": {},
            "unsynced": 0,
            "alive": {},  # loop name -> wall time of its last round, failed or not
        }
        rpc.meter.restore(book.load_credits())  # a restart keeps the day's count

    # --- loops ------------------------------------------------------------------------------------
    async def run(self) -> None:
        tasks = [
            asyncio.create_task(self._every(self.cfg.census_s, self.census_once, "census")),
            asyncio.create_task(self._every(self.cfg.poll_tick_s, self.poll_once, "poll")),
        ]
        tasks += [asyncio.create_task(self._worker()) for _ in range(max(1, self.cfg.workers))]
        try:
            await asyncio.gather(*tasks)
        finally:
            for t in tasks:
                t.cancel()
            for t in tasks:
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await t

    async def _every(self, period: float, fn: Callable[[], Awaitable[Any]], name: str) -> None:
        """Run `fn` every `period` seconds. A failed round is counted and the loop goes on; the health
        probe watches `alive`, so a failing RPC or the credit cap (which a restart cannot fix) does
        not restart the app, while a loop stuck in a round does."""
        while True:
            t = time.monotonic()
            try:
                await fn()
            except asyncio.CancelledError:
                raise
            except BudgetExhausted:
                pass  # the status shows the cap; the cheap reads resume tomorrow
            except Exception as exc:  # noqa: BLE001 - a failed round must not stop the loop
                self.stats[f"{name}_errors"] += 1
                self.stats["last_error"] = describe_error(exc)
            self.stats["alive"][name] = time.time()
            await asyncio.sleep(max(0.2, period - (time.monotonic() - t)))

    async def census_once(self) -> int:
        now = self.clock()
        infos = await self.census.poll(now)
        added = sum(1 for info in infos if self.tracker.add(info, now))
        self.stats["last_census"] = now
        self.book.save_credits(self.rpc.meter.snapshot())
        return added

    async def poll_once(self) -> int:
        now = self.clock()
        due = self.tracker.due_reads(now)
        due.sort(key=lambda t: t.next_read)
        for i in range(0, len(due), 100):
            batch = due[i : i + 100]
            slot, values = await self.rpc.multiple_accounts([t.curve for t in batch], kind="poll")
            at = self.clock()
            for tok, val in zip(batch, values + [None] * (len(batch) - len(values)), strict=False):
                self.tracker.apply_read(tok, slot, parse_curve_account(val), at)
        for tok, D, outcome in self.tracker.decisions(self.clock()):
            self._decided(tok, D, outcome)
        self.tracker.retire(self.clock())
        self.stats["last_poll"] = now
        return len(due)

    def _decided(self, tok: Token, D: int, outcome: str) -> None:
        oc = self.stats["outcomes"]
        oc[outcome] = oc.get(outcome, 0) + 1
        if outcome == "score" and tok.state:
            tok.pending += 1
            self.queue.put_nowait((D, next(self._seq), tok.mint, D, dict(tok.state)))
        elif outcome in LIGHT and tok.state:
            sc = light_score(
                tok.info, tok.state["real"], D, tok.state["at"] - tok.t0, tok.state["at"], LIGHT[outcome]
            )
            self._record(tok, sc)

    async def _worker(self) -> None:
        while True:
            _, _, mint, D, anchor = await self.queue.get()
            tok = self.tracker.get(mint)
            if tok is None:
                continue
            try:
                sc = await self.score_token(tok, D, anchor=anchor)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - one launch failing must not stop the worker
                self.stats["score_errors"] += 1
                self.stats["last_error"] = f"{mint[:8]}: {describe_error(exc)}"
                continue
            finally:
                self._settled(tok)
            self._record(tok, sc)

    def _settled(self, tok: Token) -> None:
        """A queued scoring finished: a retired launch's history goes once none is left."""
        tok.pending = max(0, tok.pending - 1)
        if not tok.pending and tok.mint not in self.tracker.live:
            tok.history = None

    def _record(self, tok: Token, sc: dict[str, Any]) -> None:
        tok.scores[sc["key"]] = sc
        self.book.add(sc)
        self.stats["scored"] += 1
        for fn in self.listeners:
            task = asyncio.ensure_future(fn(sc))
            task.add_done_callback(lambda t: t.exception())  # a failed push is not an engine error

    # --- scoring ----------------------------------------------------------------------------------
    async def _read_state(self, tok: Token) -> None:
        slot, values = await self.rpc.multiple_accounts([tok.curve], kind="history")
        self.tracker.apply_read(tok, slot, parse_curve_account(values[0] if values else None), self.clock())

    async def score_token(
        self, tok: Token, D: int | None, kind: str = "history", anchor: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Score the launch at `anchor`, the curve read that reached the decision time (the latest read
        when none is given). Its history is read, then re-read after each of `sync_waits_s` until it
        replays to exactly the anchor's reserves; a history that never does is scored up to its last
        trade and marked unsynced."""
        async with tok.lock:
            return await self._score_locked(tok, D, kind, dict(anchor or tok.state or {}) or None)

    async def _score_locked(
        self, tok: Token, D: int | None, kind: str, anchor: dict[str, Any] | None
    ) -> dict[str, Any]:
        cfg = self.cfg
        if tok.history is None:
            tok.history = History(tok.info)
        h = tok.history
        await h.update(self.rpc, cfg.history_max_tx, kind=kind)
        synced = anchor is not None and h.synced_with(anchor, anchor["slot"])
        waits = list(cfg.sync_waits_s) if anchor is not None else []
        while not synced and waits and not h.truncated:
            await asyncio.sleep(waits.pop(0))
            await h.update(self.rpc, cfg.history_max_tx, kind=kind)
            synced = h.synced_with(anchor, anchor["slot"])
        if not synced:
            self.stats["unsynced"] += 1
        row = h.row()
        if synced and anchor is not None:
            dslot, entry = int(anchor["slot"]), (int(anchor["v_sol"]), int(anchor["v_tokens"]))
        else:
            dslot = int(row["trades"][-1][0]) if row["trades"] else int(tok.info["create_slot"])
            entry = h.state_at(dslot)
        now = self.clock()
        at = float(anchor["at"]) if anchor is not None else now
        last_ts = int(row["trades"][-1][3]) if row["trades"] else tok.t0
        data = {
            "tx_read": h.n_tx,
            "reads": h.reads,
            "truncated": h.truncated,
            "synthetic_tx_index": h.synthetic_tx_index,
            "synced": synced,
            # how far the last trade read is behind the decision read (unsynced: trades are missing)
            "lag_s": round(max(0.0, at - last_ts), 1),
            "wait_s": round(max(0.0, now - at), 1),
        }
        if row["complete"] is not None:
            real = max((entry[0] - int(tok.info["v_sol0"])) / LAMPORTS, tok.peak_real)
            return light_score(tok.info, real, D, at - tok.t0, now, "DA_TOT_NGHIEP")
        return score_row(row, dslot, entry, D=D, age_s=at - tok.t0, now=now, data=data)

    def ondemand_left(self) -> int:
        now = self.clock()
        while self.ondemand and now - self.ondemand[0] > 3600:
            self.ondemand.popleft()
        return self.cfg.ondemand_per_hour - len(self.ondemand)

    async def score_mint(self, mint: str) -> dict[str, Any]:
        """Score any mint now: a live or recent launch reuses what was read, another one is found from
        the mint's own history (its first transaction is the create)."""
        if self.ondemand_left() <= 0:
            raise OnDemandLimit("đã dùng hết lượt chấm theo yêu cầu trong giờ này")
        self.ondemand.append(self.clock())
        tok = self.tracker.get(mint)
        if tok is None:
            res = await self.rpc.gtfa(mint, kind="ondemand", sort="asc", limit=10)
            info = None
            for tx in res["data"]:
                create = create_of(tx)
                if create is not None and create.get("mint") == mint:
                    info = launch_info(create, tx, signature_of(tx))
                    break
            if info is None:
                raise LookupError("không tìm thấy lệnh tạo pump.fun của mint này")
            if not classic_sol(info):
                raise LookupError("không phải curve classic quote SOL (mayhem hoặc quote khác)")
            tok = Token(info=info, seen_at=self.clock())
            self.tracker.adopt(tok)
        await self._read_state(tok)
        if tok.state is None:
            raise LookupError("không đọc được tài khoản bonding curve")
        if tok.state["complete"]:
            sc = light_score(
                tok.info, tok.state["real"], None, tok.age(self.clock()), self.clock(), "DA_TOT_NGHIEP"
            )
        else:
            sc = await self.score_token(tok, None, kind="ondemand")
        self._record(tok, sc)
        return sc

    def status(self) -> dict[str, Any]:
        now = self.clock()
        return {
            "now": now,
            "uptime_s": round(now - self.stats["started"], 1),
            "census": self.census.stats,
            "census_age_s": round(now - self.stats["last_census"], 1) if self.stats["last_census"] else None,
            "poll_age_s": round(now - self.stats["last_poll"], 1) if self.stats["last_poll"] else None,
            "queue": self.queue.qsize(),
            "tracker": self.tracker.counts(now),
            "credits": self.rpc.meter.snapshot(),
            "rpc": self.rpc.stats,
            "ondemand_left": self.ondemand_left(),
            "scores_today": self.book.count_today,
            "frozen_problems": FROZEN_PROBLEMS,
            **{k: v for k, v in self.stats.items() if k != "started"},
        }
