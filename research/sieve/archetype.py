"""Exit-mechanism archetype of every trap row of sieve journals, for the dossier and the counting rule.

    python research/sieve/archetype.py WEEK.json.gz [more journals...] CENSUS...
           [--chain active|active+shadow] [--blocks day|founding] [--out FILE]

Outcome side only: every quantity here reads trades AFTER the decision (up to the 30-min exit), so an
archetype says how a trap paid its exit. It is a description for the dossier step after scoring
(README.md), never a filter, and nothing here may feed a filter definition.

Inputs: journals from journal.py (*.json[.gz]) and the census files they were built from
(*.jsonl[.gz]). Only the rows of the journals' trap mints are kept; rows with create_ts past the
latest journal window are dropped from the raw line, before the JSON is parsed (as journal.py does).
Each kept row is checked against its journal row (create time, dslot, the 30-min net).
Caught / missed: the chosen chain of the registry tiers (filters.chains), gated by GATE_E
(real_e >= 11.66), on the journal's flags, with the scorecard's completeness rule (score.chain_fn).

Conventions (journal.py): eslot = dslot + 1 (the ticket is bought at the end of eslot); xslot =
eslot + round(1800 / SPS) (exit b; a curve completed by xslot is read to its last trade); real SOL =
(v_sol - v_sol0) / 1e9; "SOL sold" = the sell trades' SOL. The router is left out of every wallet
quantity (its trades still move the curve).
- D-holders: wallets with a positive net curve balance (tokens bought - sold) over trades with
  slot <= dslot.
- Trap crossing: the first trade after the entry state (later than the last trade by eslot, up to
  xslot) at which the ticket is at net <= -50%, valued as journal.ticket does (0.5 SOL bought at the
  entry state, sold against the curve after that trade, fee both sides, 0.002 SOL fixed cost).
  t_trap = (its slot - eslot) x SPS; the trap slot is its slot.
- Creation set: wallets whose first buy by dslot is in the create slot or the next, plus dev and creator.
- Transfer-in wallets: (a) outside dev, creator and the creation set, a wallet whose first trade by
  dslot is a sell, or whose sells by dslot exceed its curve buys by > 1e12 raw (oversold, counted at
  each sell); (b) a wallet with no trade by dslot (not dev or creator) that, in (dslot, xslot], sells
  before any buy of its own, or makes one sell that adds > 1e12 raw to its oversold amount. A wallet
  of kind (b) counts as transfer-in for all its sells.
- Crash-60s window: the largest real-SOL drop from a curve state to a later one at most 60 s
  (round(60 / SPS) slots) after it, over the entry state and the trades up to xslot (first largest;
  among equal highs, the latest); its sells are the trades after the high state up to the low one.
- New-wallet buys: SOL bought in (dslot, trap slot] by wallets with no trade by dslot.
- Curve minimum within 30 min: the lowest real SOL of the entry state and of the trades in (eslot, xslot].

Primary archetype, first rule that matches:
  SWARM-EXIT         some slot in (dslot, trap slot + 60 s] (and <= xslot) holds sells by >= 10 distinct
                     D-holders, who are >= 20% of the D-holders
  INSIDER-XFER-EXIT  transfer-in wallets sold >= 30% of the SOL sold in the crash-60s window, or the
                     creation set sold >= 50% of the SOL sold after the entry state up to the crossing
  WHALE-DUMP         one wallet sold >= 50% of the SOL sold in (dslot, trap slot]
  CLOSED-LOOP-DRAIN  new-wallet buys < 15% of real_e, curve minimum <= 1 SOL, and t_trap <= 300 s
  LATE-COLLAPSE      t_trap >= 300 s (the ticket survives 5+ min; often a second wave first)
  CROWD-CASCADE      everything else (a distributed exit of D-holders and early buyers into the crowd)
Ported from the scratch sieve3/anatomy/classify.py: same archetype on all 82 founding-pool trap rows
(08/10/2026). The shares and the curve minimum are compared unrounded here (the scratch rounded them to
3 and 2 decimals first; no pool row lies within that rounding of a threshold).
"""

import argparse
import json
import re
import sys
from collections import Counter, defaultdict, deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # works under python -I too
import filters as FL  # noqa: E402
import journal as JN  # noqa: E402
import score as SC  # noqa: E402

ROUTER = FL.ROUTER
LAMPORTS = FL.LAMPORTS
SPS = FL.SPS
W60 = FL.W60
SIZE, FIXED = FL.SIZE, FL.FIXED
XFER_LINE = FL.XFER_LINE  # 1e12 raw: 0.1% of supply
W30M = round(JN.EXITS["b30m"] / SPS)  # exit b, 6691 slots
SWARM_HOLDERS, SWARM_FRAC = 10, 0.20
XFER_SHARE, INSIDER_SHARE, WHALE_SHARE = 0.30, 0.50, 0.50
NEW_MONEY_REL, DRAIN_MIN_REAL, LATE_S = 0.15, 1.0, 300
ARCHETYPES = (
    "SWARM-EXIT",
    "INSIDER-XFER-EXIT",
    "WHALE-DUMP",
    "CLOSED-LOOP-DRAIN",
    "LATE-COLLAPSE",
    "CROWD-CASCADE",
)
CHAINS = ("active", "active+shadow")
_MINT_RE = re.compile(r'"mint":\s*"([^"]*)"')


def is_census(path):
    return str(path).endswith((".jsonl", ".jsonl.gz"))


def load_rows(paths, mints, to_t0):
    """Status-ok classic census rows of `mints` (one per mint, the last read wins), t0 <= to_t0.
    Rows past to_t0 are dropped from the raw line, before the JSON is parsed (journal.load_census)."""
    rows = {}
    for path in paths:
        with JN._open_text(path) as fh:
            for line in fh:
                m = JN._T0_RE.search(line)
                if m and int(m.group(1)) > to_t0:
                    continue
                k = _MINT_RE.search(line)
                if k and k.group(1) not in mints:  # another launch: never parsed
                    continue
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                t0 = r.get("create_ts")
                if t0 is None or t0 > to_t0 or r.get("mint") not in mints:
                    continue
                if r.get("status") != "ok" or r.get("mayhem"):
                    continue
                rows[r["mint"]] = r
    return rows


def anatomy(row, dslot):
    """The archetype metrics of one trap row (census row, decision slot)."""
    p = JN.Curve(row)
    tr = row.get("trades") or []
    sols = [int(t[FL.SOL]) for t in tr]
    toks = [int(t[FL.TOK]) for t in tr]
    eslot = dslot + 1
    xslot = eslot + W30M
    i_d, i_e, i_x = p.last(dslot), p.last(eslot), p.last(xslot)
    if p.complete_slot is not None and p.complete_slot <= xslot:
        i_x = len(tr) - 1  # a completed curve is read to its last trade (journal.ticket)

    def real(i):
        return ((p.v_sol0 if i < 0 else p.vs[i]) - p.v_sol0) / LAMPORTS

    real_e = real(i_e)
    insiders = {w for w in (row.get("dev"), row.get("creator")) if w}

    # pre-D ledgers (slot <= dslot): who traded, first side, first buy slot, net tokens, oversold
    seen = set()
    sell_first = set()
    first_buy = {}
    bought, sold, oversold = Counter(), Counter(), Counter()
    for i in range(i_d + 1):
        u = p.users[i]
        if u == ROUTER:
            continue
        if u not in seen:
            seen.add(u)
            if not p.buys[i]:
                sell_first.add(u)
        if p.buys[i]:
            bought[u] += toks[i]
            first_buy.setdefault(u, p.slots[i])
        else:
            before = max(0, sold[u] - bought[u])
            sold[u] += toks[i]
            oversold[u] += max(0, sold[u] - bought[u]) - before
    holders = {u for u in seen if bought[u] > sold[u]}
    creation = {u for u, s in first_buy.items() if s <= p.s0 + 1} | insiders  # with dev and creator
    xfer = {u for u in seen - creation if u in sell_first or oversold[u] > XFER_LINE}

    # transfer-in wallets new after D, over the whole post window (dslot, xslot]
    nb, ns = Counter(), Counter()
    post_buyers = set()
    for j in range(i_d + 1, i_x + 1):
        u = p.users[j]
        if u == ROUTER or u in seen or u in insiders:
            continue
        if p.buys[j]:
            nb[u] += toks[j]
            post_buyers.add(u)
            continue
        before = max(0, ns[u] - nb[u])
        ns[u] += toks[j]
        if u not in post_buyers or max(0, ns[u] - nb[u]) - before > XFER_LINE:
            xfer.add(u)

    def sell_shares(lo, hi):
        """(creation set, transfer-in) shares of the SOL sold by trades lo..hi (indices)."""
        tot = ins = xin = 0
        for j in range(lo, hi + 1):
            u = p.users[j]
            if u == ROUTER or p.buys[j]:
                continue
            tot += sols[j]
            if u in creation:
                ins += sols[j]
            elif u in xfer:
                xin += sols[j]
        return (ins / tot, xin / tot) if tot else (0.0, 0.0)

    # trap crossing: the ticket's tokens, bought at the entry state (journal.ticket)
    vs, vt = (p.v_sol0, p.v_tok0) if i_e < 0 else (p.vs[i_e], p.vt[i_e])
    net_in = SIZE * LAMPORTS / (1 + p.fee)
    dt = vt * net_in / (vs + net_in)

    def net(j):
        return (p.value(j, dt) / LAMPORTS - FIXED) / SIZE - 1

    i_trap = next((j for j in range(i_e + 1, i_x + 1) if net(j) <= JN.TRAP_LEVEL), None)
    trap_slot = xslot if i_trap is None else p.slots[i_trap]
    t_trap = None if i_trap is None else (trap_slot - eslot) * SPS
    insider_share = 0.0 if i_trap is None else sell_shares(i_e + 1, i_trap)[0]

    # crash-60s window: largest drop between curve states <= W60 slots apart (monotone queue of highs)
    best, hi_i, lo_i = 0.0, None, None
    dq = deque()
    seq = [(eslot, real_e, i_e)] + [(p.slots[j], real(j), j) for j in range(i_e + 1, i_x + 1)]
    for sl, rv, j in seq:
        while dq and dq[0][0] < sl - W60:
            dq.popleft()
        if dq and dq[0][1] - rv > best:
            best, hi_i, lo_i = dq[0][1] - rv, dq[0][2], j
        while dq and dq[-1][1] <= rv:
            dq.pop()
        dq.append((sl, rv, j))
    xfer_share = 0.0 if hi_i is None else sell_shares(hi_i + 1, lo_i)[1]

    # new-wallet buys and sellers up to the trap slot; D-holders selling per slot up to trap + 60 s
    new_money = 0
    sold_by = Counter()
    per_slot = defaultdict(set)
    for j in range(i_d + 1, i_x + 1):
        u, sl = p.users[j], p.slots[j]
        if u == ROUTER:
            continue
        if sl <= trap_slot:
            if not p.buys[j]:
                sold_by[u] += sols[j]
            elif u not in seen:
                new_money += sols[j]
        if not p.buys[j] and u in holders and sl <= trap_slot + W60:
            per_slot[sl].add(u)
    swarm = max((len(v) for v in per_slot.values()), default=0)
    return {
        "real_e": real_e,
        "holders": len(holders),
        "swarm": swarm,
        "swarm_frac": swarm / max(len(holders), 1),
        "xfer_share": xfer_share,
        "insider_share": insider_share,
        "top1": max(sold_by.values(), default=0) / (sum(sold_by.values()) or 1),
        "new_rel": new_money / LAMPORTS / max(real_e, 1e-9),
        "real_min": min([real_e] + [real(j) for j in range(i_e + 1, i_x + 1)]),
        "t_trap": t_trap,
    }


def archetype(e):
    """Primary archetype: the first rule of the module docstring that matches."""
    if e["swarm"] >= SWARM_HOLDERS and e["swarm_frac"] >= SWARM_FRAC:
        return "SWARM-EXIT"
    if e["xfer_share"] >= XFER_SHARE or e["insider_share"] >= INSIDER_SHARE:
        return "INSIDER-XFER-EXIT"
    if e["top1"] >= WHALE_SHARE:
        return "WHALE-DUMP"
    t = e["t_trap"]
    if t is not None and t <= LATE_S and e["new_rel"] < NEW_MONEY_REL and e["real_min"] <= DRAIN_MIN_REAL:
        return "CLOSED-LOOP-DRAIN"
    if t is not None and t >= LATE_S:
        return "LATE-COLLAPSE"
    return "CROWD-CASCADE"


def check_row(x, row):
    """Why the census row cannot be the one the journal row was built from (None if it can)."""
    p = JN.Curve(row)
    if int(row["create_ts"]) != x["t0"] or p.s0 + round(x["D"] / SPS) != x["dslot"]:
        return "create time or slot differs"
    t = JN.ticket(p, x["dslot"] + JN.ENTRIES["e1"], JN.EXITS["b30m"])
    if t is None or abs(t[0] - x["net_b30m"]) > 1e-9:
        return "30-min net differs"
    return None


def chain_fire(J, name):
    """The scorecard's fire test of a chain (score.py: gated, completeness rule and bad days)."""
    by_day = defaultdict(lambda: [0, 0])
    for x in J:
        by_day[x["day"]][0] += 1
        by_day[x["day"]][1] += not x["completeness"]["chain_ok"]
    bad = [d for d, (n, f) in by_day.items() if n and f / n > SC.COMPLETE_DAY_MAX_FAIL]
    gated, members = FL.chains()[name]
    return SC.chain_fn(gated, members, bad)


def run(journals, census, chain, how):
    J, _, metas = SC.load_journals(journals)
    warn = []
    members = FL.chains()[chain][1]
    for m in metas:
        p = m.get("perturbation") or {}
        if p.get("drop_small") or p.get("lookahead_test"):
            warn.append(f"journal built with a robustness perturbation {p}")
        jc = (m.get("chains") or {}).get(chain)
        if jc and jc.get("members") != members:
            warn.append(f"chain {chain} was {jc.get('members')} when the journal was built, now {members}")
    to_t0 = max(m["to_t0"] for m in metas)
    traps = [x for x in J if x["trap"]]
    rows = load_rows(census, {x["mint"] for x in traps}, to_t0)
    fire = chain_fire(J, chain)
    out = []
    for x in traps:
        row = rows.get(x["mint"])
        why = "no census row" if row is None else check_row(x, row)
        if why:
            warn.append(f"{x['id']}: {why} (pass the census files the journal was built from)")
            continue
        e = anatomy(row, x["dslot"])
        out.append({"x": x, "caught": fire(x), "arch": archetype(e), "m": e, "block": SC.block_of(x, how)})
    return out, warn, len(traps)


def render(out, warn, n_traps, chain, how):
    L = [f"Exit archetypes of journal trap rows (outcome side, dossier only). Chain: {chain}, gated."]
    L += [f"WARNING {w}" for w in warn]
    miss = [r for r in out if not r["caught"]]
    L.append(
        f"trap rows {n_traps} ({len({r['x']['mint'] for r in out})} mints classified), "
        f"caught {len(out) - len(miss)}, missed {len(miss)} ({len({r['x']['mint'] for r in miss})} mints)"
    )
    L.append("")
    L.append(
        f"{'id':14s} {'block':10s} {'chain':5s} {'archetype':18s} D-holders max/slot, transfer-in share "
        "(crash 60 s), creation-set share and top seller (to the crossing), new-wallet buys / real_e, "
        "curve min, t_trap"
    )
    order = {a: k for k, a in enumerate(ARCHETYPES)}
    for r in sorted(out, key=lambda r: (order[r["arch"]], r["x"]["t0"], r["x"]["D"], r["x"]["mint"])):
        e = r["m"]
        tt = "-" if e["t_trap"] is None else f"{e['t_trap']:.1f}s"
        L.append(
            f"{r['x']['id']:14s} {r['block']:10s} {'ACT' if r['caught'] else 'MISS':5s} {r['arch']:18s} "
            f"hold={e['swarm']}/{e['holders']} xfer={e['xfer_share']:.2f} ins={e['insider_share']:.2f} "
            f"top1={e['top1']:.2f} new={e['new_rel']:.2f} min={e['real_min']:.2f} trap@{tt}"
        )
    unit = "blocks" if how == "founding" else "days"
    need = SC.COUNT_RULE
    L.append("")
    L.append(
        f"Counting rule over MISSED trap rows ({chain}): an archetype is a filter candidate at >= {need[0]} "
        f"trap mints, >= {need[1]} creators, >= {need[2]} {unit}; otherwise it goes to the watch list."
    )
    head = f"{'archetype':18s} {'rows':>4s} {'mints':>5s} {'creators':>8s} {'days':>4s}"
    L.append(head + (f" {'blocks':>6s}" if how == "founding" else "") + "  rule")
    for a in ARCHETYPES:
        s = [r for r in miss if r["arch"] == a]
        tm = {r["x"]["mint"] for r in s}
        tc = {SC.creator_of(r["x"]) for r in s}
        td = {r["x"]["day"] for r in s}
        tb = {r["block"] for r in s}
        ok = len(tm) >= need[0] and len(tc) >= need[1] and len(tb if how == "founding" else td) >= need[2]
        line = f"{a:18s} {len(s):4d} {len(tm):5d} {len(tc):8d} {len(td):4d}"
        if how == "founding":
            line += f" {len(tb):6d} " + ",".join(sorted(tb)).ljust(8)
        L.append(line + ("  meets" if ok else "  watch"))
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Exit archetype of the trap rows of sieve journals.")
    ap.add_argument("files", nargs="+", help="journal.py outputs (*.json[.gz]), then census *.jsonl[.gz]")
    ap.add_argument("--chain", choices=CHAINS, default="active")
    ap.add_argument("--blocks", choices=("day", "founding"), default="day", help="counting-rule unit")
    ap.add_argument("--out", help="write the text here too")
    a = ap.parse_args(argv)
    census = [f for f in a.files if is_census(f)]
    journals = [f for f in a.files if not is_census(f)]
    bad = [f for f in journals if not str(f).endswith((".json", ".json.gz"))]
    if bad or not journals or not census:
        ap.error("give journals (*.json[.gz]) and census files (*.jsonl[.gz])")
    out, warn, n = run(journals, census, a.chain, a.blocks)
    txt = render(out, warn, n, a.chain, a.blocks)
    print(txt)
    if a.out:
        with open(a.out, "w") as fh:
            fh.write(txt + "\n")
    return 0 if len(out) == n else 1  # 1: some trap rows had no matching census row


if __name__ == "__main__":
    sys.exit(main())
