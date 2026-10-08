"""Sieve journal: every F0 candidate of a census window, with labels, curve states and filter flags.

    python research/sieve/journal.py CENSUS... --from-t0 A --to-t0 B [--dense] --out week.json.gz

Census rows (bot /api/export/file/sniper-YYYY-MM-DD.jsonl[.gz]): one row per sampled launch, every
curve trade of its first 2 h. Rows with create_ts > --to-t0 are dropped while parsing, before anything
else is read from them (forward data stays untouched). Candidates are classic (non-mayhem) status-ok
launches with --from-t0 <= t0 <= --to-t0; the memory filters read every row up to --to-t0, so pass
the earlier census files too when a reputation memory should reach before the window.

Candidate (gate F0, docs/SIEVE.md section 5) at D seconds after create, dslot = s0 + round(D / 0.269):
not complete by the entry slot dslot+1, a trade in the 60 s before dslot, 5 <= real SOL < 70 at the
end of dslot, >= 5 trades and >= 3 distinct buyers in the last 120 s. D = 120/300/600 (set J) and,
with --dense, D = 60..900 every 60 s (set G: autocorrelated within a mint, description only).

Ticket: 0.5 SOL bought at the curve state at the end of the entry slot, 1.25% fee each side (row
fee_bps), 0.002 SOL fixed cost, valued against the real curve with the ticket's tokens outstanding.
Entries: e1 = dslot+1, t45 = dslot + round(45 / 0.269), t90 = dslot + round(90 / 0.269) (SIEVE law 4).
Exits: 10 / 30 / 60 min, or held to graduation / the end of the 2 h window (a completed curve is sold
at completion). trap = net at 30 min (e1) <= -50%; winner = net at 30 min (e1) >= +100%.

Robustness runs (labels and the F0 gate always come from the full rows):
  --drop-small P     silent loss of sub-0.3 SOL trades after the create slot with probability P,
                     seeded per mint, applied to candidates and to the memory (stream_sim).
  --lookahead-test   flags computed on rows cut at dslot; any difference from a normal run is a
                     look-ahead bug (compare with score.py --diff).
"""

import argparse
import datetime
import gzip
import hashlib
import json
import random
import re
import sys
from bisect import bisect_right
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # works under python -I too
import filters as FL  # noqa: E402

SPS = FL.SPS
LAMPORTS = FL.LAMPORTS
W60 = FL.W60
W120 = FL.W120
SIZE, FIXED = FL.SIZE, FL.FIXED
DECISIONS = (120, 300, 600)
DENSE = tuple(range(60, 901, 60))
EXITS = {"a10m": 600, "b30m": 1800, "c60m": 3600, "hold": None}
ENTRIES = {"e1": 1, "t45": round(45 / SPS), "t90": round(90 / SPS)}
TRAP_LEVEL, WIN_LEVEL = -0.5, 1.0
# Founding pool (06/10 20:53Z .. 07/10 23:03Z) and its three blocks for the counting rule.
FOUNDING = (1791319998, 1791414202)
FOUNDING_BLOCKS = ((1791352800, "B1"), (1791386123, "B2"), (None, "B3"))
VERSION = "sieve-journal-1"
_T0_RE = re.compile(r'"create_ts":\s*(-?\d+)')


class Curve:
    """A launch's curve in chain order (the subset of bot/app/sniper.CurvePath the ticket needs)."""

    def __init__(self, row):
        tr = row.get("trades") or []
        self.s0 = int(row["create_slot"])
        self.v_sol0 = float(row["v_sol0"])
        self.v_tok0 = float(row["v_tokens0"])
        self.slots = [int(t[FL.SLOT]) for t in tr]
        self.vs = [float(t[FL.VS]) for t in tr]
        self.vt = [float(t[FL.VT]) for t in tr]
        self.users = [t[FL.USER] for t in tr]
        self.buys = [bool(t[FL.BUY]) for t in tr]
        c = row.get("complete")
        self.complete_slot = int(c["slot"]) if c else None
        self.fee = FL.fee_of(row)
        win = row.get("window") or {}
        self.truncated = bool(win.get("truncated"))
        self.known_slot = int(win.get("last_slot") or 0) - 1 if self.truncated else None

    def last(self, slot):
        return bisect_right(self.slots, slot) - 1

    def value(self, i, dt):
        vs, vt = (self.v_sol0, self.v_tok0) if i < 0 else (self.vs[i], self.vt[i])
        return 0.0 if vt <= dt else (1 - self.fee) * vs * dt / (vt - dt)

    def real(self, slot):
        i = self.last(slot)
        return ((self.v_sol0 if i < 0 else self.vs[i]) - self.v_sol0) / LAMPORTS


def ticket(p, entry_slot, exit_s):
    """(net, why, resolved) of a 0.5 SOL ticket bought at the end of entry_slot and sold exit_s seconds
    of slots later (None: held to graduation or the end of the window); None if no ticket."""
    if p.complete_slot is not None and p.complete_slot <= entry_slot:
        return None
    i0 = p.last(entry_slot)
    vs, vt = (p.v_sol0, p.v_tok0) if i0 < 0 else (p.vs[i0], p.vt[i0])
    net_in = SIZE * LAMPORTS / (1 + p.fee)
    dt = vt * net_in / (vs + net_in)
    n = len(p.vs)
    xs = None
    if exit_s is None:
        j, why = n - 1, ("grad" if p.complete_slot is not None else "end")
    else:
        xs = entry_slot + round(exit_s / SPS)
        if p.complete_slot is not None and p.complete_slot <= xs:
            j, why = n - 1, "grad"
        else:
            j, why = p.last(xs), "time"
    j = max(j, i0)
    resolved = not p.truncated or why == "grad" or (xs is not None and xs <= p.known_slot)
    return (p.value(j, dt) / LAMPORTS - FIXED) / SIZE - 1, why, resolved


def decide(p, D):
    """(dslot, real_d, n120, buyers120) if the launch is an F0 candidate at D, else None."""
    dslot = p.s0 + round(D / SPS)
    if p.complete_slot is not None and p.complete_slot <= dslot + 1:
        return None
    i_d = p.last(dslot)
    if i_d < 0 or p.slots[i_d] <= dslot - W60:
        return None
    real_d = (p.vs[i_d] - p.v_sol0) / LAMPORTS
    if not 5 <= real_d < 70:
        return None
    lo = dslot - W120
    n120 = 0
    b120 = set()
    for i in range(i_d, -1, -1):
        if p.slots[i] <= lo:
            break
        n120 += 1
        if p.buys[i]:
            b120.add(p.users[i])
    if n120 < 5 or len(b120) < 3:
        return None
    return dslot, real_d, n120, len(b120)


def fblock(t0):
    if not FOUNDING[0] <= t0 <= FOUNDING[1]:
        return None
    for end, name in FOUNDING_BLOCKS:
        if end is None or t0 < end:
            return name
    return None


def day_week(t0):
    d = datetime.datetime.fromtimestamp(t0, datetime.UTC)
    y, w, _ = d.isocalendar()
    return d.strftime("%Y-%m-%d"), f"{y}-W{w:02d}"


def file_sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _open_text(path):
    if str(path).endswith(".gz"):
        return gzip.open(path, "rt")
    return open(path)  # noqa: SIM115 - the caller holds it in a with block


def load_census(paths, to_t0):
    """Status-ok rows by kind (one per mint, the last read wins) and the launch index, t0 <= to_t0.
    Rows past to_t0 are dropped from the raw line, before the JSON is parsed."""
    classic, mayhem, order = {}, {}, {}
    launches = []
    stats = Counter()
    k = 0
    for path in paths:
        with _open_text(path) as fh:
            for line in fh:
                m = _T0_RE.search(line)
                if m and int(m.group(1)) > to_t0:
                    stats["forward_dropped"] += 1
                    continue
                try:
                    r = json.loads(line)
                except ValueError:
                    stats["bad_json"] += 1
                    continue
                t0 = r.get("create_ts")
                if t0 is None:
                    stats["no_create_ts"] += 1
                    continue
                if t0 > to_t0:
                    stats["forward_dropped"] += 1
                    continue
                launches.append((r.get("mint"), t0, r.get("creator"), r.get("dev")))
                if r.get("status") != "ok":
                    stats["status_" + str(r.get("status"))] += 1
                    continue
                for t in r.get("trades") or []:  # one string object per wallet: a week fits in RAM
                    t[FL.USER] = sys.intern(t[FL.USER])
                    if isinstance(t[FL.IX], str):
                        t[FL.IX] = sys.intern(t[FL.IX])
                (mayhem if r.get("mayhem") else classic)[r["mint"]] = r
                order[r["mint"]] = k
                k += 1
    stats["classic_ok"] = len(classic)
    stats["mayhem_ok"] = len(mayhem)
    return classic, mayhem, launches, order, stats


def drop_small(row, p):
    """Silent loss of sub-0.3 SOL trades after the create slot (seeded per mint), as stream_sim."""
    if not p:
        return row
    rnd = random.Random(int(hashlib.md5(row["mint"].encode()).hexdigest(), 16) % 10**6)
    r = dict(row)
    s0 = int(row["create_slot"])
    r["trades"] = [
        t
        for t in row.get("trades") or []
        if not (int(t[FL.SOL]) < 0.3e9 and int(t[FL.SLOT]) > s0 and rnd.random() < p)
    ]
    return r


def labels(p, dslot):
    nets = {}
    reals = {}
    why_b = None
    ok = True
    for ename, off in ENTRIES.items():
        es = dslot + off
        reals[ename] = p.real(es)
        nets[ename] = {}
        for xname, ex in EXITS.items():
            t = ticket(p, es, ex)
            nets[ename][xname] = None if t is None else t[0]
            if ename == "e1" and t is not None:
                ok = ok and t[2]
                if xname == "b30m":
                    why_b = t[1]
    return nets, reals, why_b, ok


def build(args):
    paths = [str(x) for x in args.census]
    classic, mayhem, launches, order, stats = load_census(paths, args.to_t0)
    lt = None
    if args.lt_ledger:
        with open(args.lt_ledger) as fh:
            lt = {w: sorted(v) for w, v in json.load(fh).items()}
    flag_classic = {m: drop_small(r, args.drop_small) for m, r in classic.items()}
    flag_mayhem = [drop_small(r, args.drop_small) for r in mayhem.values()]
    mem = FL.Memory(flag_classic.values(), flag_mayhem, launches, lt_ledger=lt)
    cands = sorted(
        (r for r in classic.values() if args.from_t0 <= r["create_ts"] <= args.to_t0),
        key=lambda r: (r["create_ts"], order[r["mint"]]),
    )
    curves = {r["mint"]: Curve(r) for r in cands}
    decisions = tuple(int(x) for x in args.decisions.split(","))
    cache = {}

    def record(r, D, dec, set_name):
        mint = r["mint"]
        p = curves[mint]
        dslot, real_d, n120, b120 = dec
        key = (mint, D)
        if key not in cache:
            nets, reals, why_b, ok = labels(p, dslot)
            full = FL.Cand(r, dslot, mem, slots=p.slots)
            frow = flag_classic[mint]
            if args.lookahead_test:
                frow = dict(frow)
                frow["trades"] = [t for t in frow.get("trades") or [] if int(t[FL.SLOT]) <= dslot]
                frow.pop("complete", None)
                frow.pop("window", None)
            fc = full if frow is r else FL.Cand(frow, dslot, mem, entry=full.entry)
            ev = FL.evaluate(fc) if not args.no_flags else {}
            feat = FL.row_features(full)
            co = FL.check_ordered(frow, dslot)  # on the trades the flags saw
            e1 = nets["e1"]
            day, week = day_week(r["create_ts"])
            cache[key] = {
                "id": f"{mint[:8]}@{D}",
                "mint": mint,
                "t0": r["create_ts"],
                "D": D,
                "dslot": dslot,
                "creator": r.get("creator"),
                "dev": r.get("dev"),
                "graduated": r.get("complete") is not None,
                "day": day,
                "week": week,
                "fblock": fblock(r["create_ts"]),
                "real_d": real_d,
                "real_e": full.real_e,
                "real_t45": reals["t45"],
                "real_t90": reals["t90"],
                "net_a10m": e1["a10m"],
                "net_b30m": e1["b30m"],
                "net_c_hold": e1["hold"],
                "nets": nets,
                "exit_b30m": why_b,
                "label_ok": ok,
                "trap": e1["b30m"] <= TRAP_LEVEL,
                "winner": e1["b30m"] >= WIN_LEVEL,
                "n120": n120,
                "buyers120": b120,
                "feat": feat,
                "completeness": {
                    "ordered_gaps": co["gaps"],
                    "chain_ok": FL.complete_chain(frow, fc.vis),
                    "tx_index": all(t[FL.TX] is not None for t in fc.vis),
                },
                "flags": {k: v[0] for k, v in ev.items()},
                "raw": {k: v[1] for k, v in ev.items()},
                "detail": fc.detail,
            }
        return dict(cache[key], set=set_name)

    rows = []
    for D in decisions:
        for r in cands:
            dec = decide(curves[r["mint"]], D)
            if dec:
                rows.append(record(r, D, dec, "J"))
    grid = []
    if args.dense:
        for r in cands:
            for D in DENSE:
                dec = decide(curves[r["mint"]], D)
                if dec:
                    grid.append(record(r, D, dec, "G"))
    meta = {
        "version": VERSION,
        "census": [{"name": Path(x).name, "sha256": file_sha(x)} for x in paths],
        "from_t0": args.from_t0,
        "to_t0": args.to_t0,
        "decisions": list(decisions),
        "dense": bool(args.dense),
        "load": dict(stats),
        "candidate_launches": len(cands),
        "memory_launches": {"classic": len(mem.classic), "mayhem": len(mem.mayhem)},
        "lt_ledger": None if not args.lt_ledger else {"name": Path(args.lt_ledger).name},
        "perturbation": {"drop_small": args.drop_small, "lookahead_test": bool(args.lookahead_test)},
        "filters_sha256": file_sha(FL.__file__),
        "registry": {d["id"]: {"tier": d["tier"], "hash": FL.definition_hash(d["id"])} for d in FL.REGISTRY},
        "chains": {k: {"gated": g, "members": m} for k, (g, m) in FL.chains().items()},
        "wstore_gap_launches": mem.stores["wstore"]["n_gap_launches"] if "wstore" in mem.stores else None,
    }
    return {"meta": meta, "rows": rows, "grid": grid}


def save(obj, path):
    data = json.dumps(obj, separators=(",", ":"), sort_keys=True).encode()
    if str(path).endswith(".gz"):  # mtime 0 and no name in the header: same bytes on every rebuild
        with open(path, "wb") as raw, gzip.GzipFile("", "wb", 6, raw, mtime=0) as fh:
            fh.write(data)
    else:
        Path(path).write_bytes(data)


def load(path):
    if str(path).endswith(".gz"):
        with gzip.open(path, "rt") as fh:
            return json.load(fh)
    return json.loads(Path(path).read_text())


def main(argv=None):
    ap = argparse.ArgumentParser(description="Build the sieve journal from census files.")
    ap.add_argument("census", nargs="+", help="sniper-YYYY-MM-DD.jsonl[.gz] files")
    ap.add_argument("--to-t0", type=int, required=True, help="last create_ts read (inclusive)")
    ap.add_argument("--from-t0", type=int, default=0, help="first candidate create_ts (inclusive)")
    ap.add_argument("--decisions", default=",".join(map(str, DECISIONS)))
    ap.add_argument("--dense", action="store_true", help="also the D = 60..900 s grid (set G)")
    ap.add_argument("--out", required=True, help="journal path (.json or .json.gz)")
    ap.add_argument("--lt-ledger", help="external creator ledger {wallet: [t0...]} for N-LTE-FACTORY")
    ap.add_argument("--drop-small", type=float, default=0.0, help="robustness: silent loss probability")
    ap.add_argument("--lookahead-test", action="store_true", help="robustness: flags on rows cut at dslot")
    ap.add_argument("--no-flags", action="store_true", help="labels and features only")
    args = ap.parse_args(argv)
    if args.from_t0 > args.to_t0:
        ap.error("--from-t0 is after --to-t0")
    j = build(args)
    save(j, args.out)
    tr = sum(r["trap"] for r in j["rows"])
    wn = sum(r["winner"] for r in j["rows"])
    print(
        f"{args.out}: {len(j['rows'])} J rows ({tr} traps, {wn} winners), {len(j['grid'])} G rows, "
        f"{j['meta']['candidate_launches']} launches in window, load {j['meta']['load']}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
