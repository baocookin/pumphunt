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
import re
import time
from collections import OrderedDict, deque
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from .chain import (
    LAMPORTS,
    chain_breaks,
    classic_sol,
    create_of,
    launch_info,
    parse_curve_account,
    signature_of,
)
from .features import curve_features
from .history import History
from .live import Census, Token, Tracker
from .live_rules import WINDOW_S, LiveRules
from .native import IDS as NATIVE_IDS
from .native import evaluate as native_flags
from .outcome import Outcomes, journal_line
from .rpc import BudgetExhausted, Rpc, describe_error
from .sieve import ACTIVE, FL, FROZEN_PROBLEMS, INFO, SHADOW, light_score, score_row
from .wallets import WalletBook

WALLETS_FILE = "wallets.json.gz"
RULES_FILE = "rules.json"  # which filters decided at the last refresh, kept across restarts

LIGHT = {"below_gate": "DUOI_CONG", "beyond": "NGOAI_VUNG", "graduated": "DA_TOT_NGHIEP"}
OUTCOME_KEYS = ("status", "net", "label", "why", "how", "due", "read_at", "real_exit")


class OnDemandLimit(Exception):
    """The hour's allowance of scores asked by mint is used up."""


JOURNAL_FILE = re.compile(r"(scores|outcomes|rows)-\d{4}-\d{2}-\d{2}\.jsonl(\.gz)?")


def day_of(ts: float) -> str:
    return datetime.datetime.fromtimestamp(ts, datetime.UTC).strftime("%Y-%m-%d")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not path.is_file():
        return out
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt") as fh:
        for line in fh:
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out


class ScoreBook:
    """Recent scores in memory, and the journal under data_dir/ray/, one file per UTC day:
    scores-*.jsonl (every score), outcomes-*.jsonl (each full score's 30-minute outcome, by the day
    of its entry) and rows-*.jsonl.gz (the trades of every launch scored at a decision time, up to
    its last decision, so a new filter can be run on past weeks without reading the chain again)."""

    def __init__(self, data_dir: str | Path, keep: int = 3_000):
        self.dir = Path(data_dir) / "ray"
        self.keep = keep
        self.recent: deque[dict[str, Any]] = deque(maxlen=keep)
        self.latest: OrderedDict[str, dict[str, Any]] = OrderedDict()  # last score per mint, bounded
        self.count_today = 0
        self._day = ""

    def _path(self, ts: float) -> Path:
        return self.dir / f"scores-{day_of(ts)}.jsonl"

    def _remember(self, sc: dict[str, Any]) -> None:
        self.latest[sc["mint"]] = sc
        self.latest.move_to_end(sc["mint"])
        while len(self.latest) > self.keep:
            self.latest.popitem(last=False)

    def _append(self, path: Path, line: dict[str, Any]) -> None:
        text = json.dumps(line, separators=(",", ":"), ensure_ascii=False) + "\n"
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            opener = gzip.open if path.suffix == ".gz" else open
            with opener(path, "at") as fh:
                fh.write(text)
        except OSError:
            pass  # the dashboard works without the journal

    def add(self, sc: dict[str, Any]) -> None:
        self.recent.appendleft(sc)
        self._remember(sc)
        day = self._path(sc["at"]).name
        if day != self._day:
            self._day, self.count_today = day, 0
        self.count_today += 1
        self._append(self._path(sc["at"]), sc)

    def add_outcome(self, line: dict[str, Any]) -> None:
        self._append(self.dir / f"outcomes-{day_of(line['entry_at'])}.jsonl", line)

    def add_row(self, row: dict[str, Any], ts: float) -> None:
        self._append(self.dir / f"rows-{day_of(ts)}.jsonl.gz", row)

    def load(self, now: float) -> int:
        """Scores of yesterday and today back into memory (oldest first, so the newest lead), with
        the outcomes already settled."""
        rows: list[dict[str, Any]] = []
        outcomes: dict[tuple[Any, Any, Any], dict[str, Any]] = {}
        for ts in (now - 86_400, now):
            rows += read_jsonl(self._path(ts))
            for o in read_jsonl(self.dir / f"outcomes-{day_of(ts)}.jsonl"):
                outcomes[(o.get("mint"), o.get("key"), o.get("score_at"))] = o
        for sc in rows[-(self.recent.maxlen or 0) :]:
            o = outcomes.get((sc.get("mint"), sc.get("key"), sc.get("at")))
            if o is not None:
                sc["outcome"] = {k: o.get(k) for k in OUTCOME_KEYS}
            self.recent.appendleft(sc)
            self._remember(sc)
        return len(rows)

    def outcome_lines(self, since: float, now: float) -> list[dict[str, Any]]:
        """The outcome journal from the day of `since` to the day of `now`."""
        out: list[dict[str, Any]] = []
        ts = since
        while day_of(ts) <= day_of(now):
            out += read_jsonl(self.dir / f"outcomes-{day_of(ts)}.jsonl")
            ts += 86_400
        return out

    def journal_files(self) -> list[dict[str, Any]]:
        if not self.dir.is_dir():
            return []
        return [
            {"name": p.name, "bytes": p.stat().st_size}
            for p in sorted(self.dir.iterdir())
            if p.is_file() and JOURNAL_FILE.fullmatch(p.name)
        ]

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
            "outcome_errors": 0,
            "rules_errors": 0,
            "wallets_errors": 0,
            "outcomes": {},  # decision outcomes: score, small, below_gate, ...
            "unsynced": 0,
            "alive": {},  # loop name -> wall time of its last round, failed or not
        }
        rpc.meter.restore(book.load_credits())  # a restart keeps the day's count
        # The 30-minute outcome of every full score; the ones a restart interrupted are read again.
        self.outcomes = Outcomes(rpc, self._outcome, clock)
        for sc in book.recent:
            self.outcomes.track(sc)
        # Which filters may decide, and the risk shown, from the journal (app/live_rules.py).
        self.rules = LiveRules()
        # What wallets did early in earlier launches (app/wallets.py); loaded or rebuilt by run().
        self.wallets = WalletBook()

    # --- loops ------------------------------------------------------------------------------------
    async def run(self) -> None:
        with contextlib.suppress(Exception):
            await self.load_wallets()
        with contextlib.suppress(OSError, ValueError, AttributeError):
            self.rules.restore(json.loads((self.book.dir / RULES_FILE).read_text()).get("ok") or [])
        tasks = [
            asyncio.create_task(self._every(self.cfg.census_s, self.census_once, "census")),
            asyncio.create_task(self._every(self.cfg.poll_tick_s, self.poll_once, "poll")),
            asyncio.create_task(self._every(self.cfg.outcome_tick_s, self.outcomes.run_once, "outcome")),
            asyncio.create_task(self._every(self.cfg.rules_refresh_s, self.refresh_rules, "rules")),
            asyncio.create_task(self._every(self.cfg.wallets_save_s, self.save_wallets, "wallets")),
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
            with contextlib.suppress(Exception):  # a deploy stops the app: keep what it learned since
                self.wallets.save(self.book.dir / WALLETS_FILE)

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

    async def refresh_rules(self) -> int:
        """The live rule from the last 7 days of the outcome journal; returns the rows it read."""
        now = self.clock()
        lines = await asyncio.to_thread(self.book.outcome_lines, now - WINDOW_S, now)
        self.rules.refresh(lines, now, ACTIVE + SHADOW + INFO + NATIVE_IDS)
        snap = json.dumps(self.rules.snapshot())
        with contextlib.suppress(OSError):
            await asyncio.to_thread(self._write, self.book.dir / RULES_FILE, snap)
        return self.rules.rows

    @staticmethod
    def _write(path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(text)
        tmp.replace(path)

    # --- wallet memory ----------------------------------------------------------------------------
    async def load_wallets(self) -> int:
        """The saved wallet memory, or one rebuilt from the last two days of the row archive and the
        outcome journal (the first start, or a lost file)."""
        path = self.book.dir / WALLETS_FILE
        now = self.clock()
        book = await asyncio.to_thread(WalletBook.load, path)
        if book is None:
            book = await asyncio.to_thread(self._rebuild_wallets, now)
        else:
            # outcomes settled after the file was saved (a crash loses at most its last 15 minutes)
            lines = await asyncio.to_thread(self.book.outcome_lines, now - 2 * 86_400, now)
            for o in sorted(lines, key=lambda o: float(o.get("entry_at") or 0)):
                if o.get("D") and o.get("status") == "ok":
                    book.note_outcome(o["mint"], o.get("label"))
        # launches scored while it loaded are noted again, in order
        for mint, rec in self.wallets.launches.items():
            if mint not in book.launches:
                book._note(mint, {u: 0.0 for u in rec["early"]}, set(rec["dumpers"]), rec["dev"], rec["at"])
        self.wallets = book
        return len(book)

    def _rebuild_wallets(self, now: float) -> WalletBook:
        def rows() -> Any:
            for ts in (now - 86_400, now):
                path = self.book.dir / f"rows-{day_of(ts)}.jsonl.gz"
                if not path.is_file():
                    continue
                with gzip.open(path, "rt") as fh:
                    for line in fh:
                        with contextlib.suppress(ValueError):
                            yield json.loads(line)

        return WalletBook.rebuild(rows(), self.book.outcome_lines(now - 2 * 86_400, now))

    async def save_wallets(self) -> int:
        """Prune and save the wallet memory (a snapshot taken here, written in a thread)."""
        now = self.clock()
        self.wallets.prune(now)
        snap = WalletBook()
        snap.wallets = {u: list(w) for u, w in self.wallets.wallets.items()}
        snap.devs = {d: list(v) for d, v in self.wallets.devs.items()}
        snap.launches = {m: dict(v) for m, v in self.wallets.launches.items()}
        await asyncio.to_thread(snap.save, self.book.dir / WALLETS_FILE)
        return len(snap)

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
        for tok in self.tracker.retire(self.clock()):
            if not tok.pending:
                self._release(tok)
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
                self._record(tok, await self.score_token(tok, D, anchor=anchor))
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - one launch failing must not stop the worker
                self.stats["score_errors"] += 1
                self.stats["last_error"] = f"{mint[:8]}: {describe_error(exc)}"
            finally:
                self._settled(tok)  # after the score is recorded: a retired launch is archived with it

    def _settled(self, tok: Token) -> None:
        """A queued scoring finished: a retired launch's history goes once none is left."""
        tok.pending = max(0, tok.pending - 1)
        if not tok.pending and tok.mint not in self.tracker.live:
            self._release(tok)

    def _release(self, tok: Token) -> None:
        """A launch out of the live set with no scoring left: the trades of a launch scored at its
        decision times go to the row archive (once), then its history is freed."""
        h, tok.history = tok.history, None
        if h is None or tok.archived or not self.cfg.archive_rows:
            return
        entries = {k: sc["entry"] for k, sc in tok.scores.items() if k.startswith("D") and sc.get("entry")}
        if not entries:
            return
        last = max(int(e["slot"]) for e in entries.values())
        row = h.row()
        row["trades"] = [t for t in row["trades"] if int(t[0]) <= last]
        if row["complete"] and int(row["complete"]["slot"]) > last:
            row["complete"] = None
        row["chain_breaks"] = chain_breaks(row["trades"], int(tok.info["v_tokens0"]))
        row["window"] = {**row["window"], "last_slot": last}
        row["scored"] = entries
        tok.archived = True
        self.book.add_row(row, tok.t0)

    def _record(self, tok: Token, sc: dict[str, Any]) -> None:
        tok.scores[sc["key"]] = sc
        self.book.add(sc)
        self.outcomes.track(sc)
        self.stats["scored"] += 1
        for fn in self.listeners:
            task = asyncio.ensure_future(fn(sc))
            task.add_done_callback(lambda t: t.exception())  # a failed push is not an engine error

    def _outcome(self, sc: dict[str, Any], o: dict[str, Any]) -> None:
        sc["outcome"] = {k: o.get(k) for k in OUTCOME_KEYS}
        if sc.get("D"):
            self.wallets.note_outcome(sc["mint"], o.get("label"))
        self.book.add_outcome(journal_line(sc, o))

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
        # the decision-time features: the launch's own trades, and its early buyers' earlier launches
        cand = FL.Cand(row, dslot, None, entry=(float(entry[0]), float(entry[1])))
        feats = {**curve_features(cand), **self.wallets.features(row, dslot)}
        sc = score_row(
            row,
            dslot,
            entry,
            D=D,
            age_s=at - tok.t0,
            now=now,
            data=data,
            rules=self.rules,
            native=native_flags(feats),
        )
        sc["features"] = {k: round(v, 6) for k, v in feats.items()}
        if D is not None:
            self.wallets.note_launch(row, dslot, at)  # remembered from its first decision on
        # what the 30-minute outcome is measured from
        sc["entry"] = {
            "at": round(at, 3),
            "slot": int(dslot),
            "v_sol": int(entry[0]),
            "v_tokens": int(entry[1]),
            "v_sol0": int(tok.info["v_sol0"]),
            "fee": FL.fee_of(row),
            "curve": tok.curve,
        }
        return sc

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
        if tok.mint not in self.tracker.live and not tok.pending:
            tok.history = None  # a launch scored by hand keeps its scores, not its trades
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
            "journal": {**self.outcomes.stats, "pending": self.outcomes.pending()},
            "rules": self.rules.snapshot(),
            "wallets": {"wallets": len(self.wallets), "launches": len(self.wallets.launches)},
            **{k: v for k, v in self.stats.items() if k != "started"},
        }
