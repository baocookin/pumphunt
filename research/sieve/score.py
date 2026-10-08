"""Weekly scorecard of the sieve: base rates, every filter, the chains side by side, the dossier lists
and the canaries (docs/SIEVE.md sections 5 and 7; README.md for the weekly protocol).

    python research/sieve/score.py week.json.gz [more journals...] [--blocks day|week|founding]
           [--ref earlier1.json.gz ...] [--json card.json] [--out card.txt]
    python research/sieve/score.py --diff base.json.gz perturbed.json.gz

Every number here is computed on the journals given. A scored week is forward evidence only the first
time it is scored; after that it joins the discovery pool and every number on it is in-sample.

Conventions (frozen with the founding registry, 08/10/2026)
- Unit of evidence: the mint. Set J (D = 120/300/600 s) carries the statistics; set G (dense D grid)
  is description only (rows of one mint are heavily autocorrelated).
- Every veto is gated: a filter fires on a row only if real_e >= 11.66 (GATE_E) and its own condition
  holds. 'band' = gated rows.
- U = traps - 3 x winners among fired band rows. Permutation p: random mints, all their band rows in
  journal order, until the filter's own number of fires is reached; p = (#{U_null >= U} + 1) / (N + 1)
  (seed 9, N 2000). Benjamini-Hochberg q over the non-retired, non-reference filters scored.
- Mantel-Haenszel odds ratio of trap, fired vs not, within strata real_e (<20, 20-30, 30-45, >=45) x
  D (<= 180 s, > 180 s), band rows.
- Matched placebo: the k band rows with the highest (+) or lowest (-) value of a curve or activity
  covariate (n_trades, uniq_buyers, d_real_60s, real_e, buyers120, n120, an_dd_pre), k = the filter's
  fires. A filter whose U does not beat the best placebo is indistinguishable from that proxy.
- Saved SOL = -0.5 x the sum of net_b30m over vetoed rows (0.5 SOL tickets not bought).
"""

import argparse
import json
import math
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # works under python -I too
import filters as FL  # noqa: E402
import journal as JN  # noqa: E402

GATE = FL.GATE_E
BASE_STRATA = ((5, 13), (13, 30), (30, 70))
BAND_STRATA = (("<13", GATE, 13), ("13-30", 13, 30), ("30-70", 30, 70))
PLACEBO_COV = ("n_trades", "uniq_buyers", "d_real_60s", "real_e", "buyers120", "n120", "an_dd_pre")
COMPLETE_DAY_MAX_FAIL = 0.05  # a day with > 5% of candidates failing the chain check is not scored
COUNT_RULE = (3, 2, 2)  # trap mints, creators, blocks: the founding counting rule


# ------------------------------------------------------------------ statistics
def wilson(k, n, z=1.96):
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else float("nan")


def mh_stratum(x):
    r = x["real_e"]
    b = 0 if r < 20 else 1 if r < 30 else 2 if r < 45 else 3
    return (b, 0 if x["D"] <= 180 else 1)


def mh_or(R, fl):
    S = defaultdict(lambda: [0, 0, 0, 0])
    for x in R:
        s = S[mh_stratum(x)]
        f = fl(x)
        t = x["trap"]
        s[0 if f and t else 1 if f else 2 if t else 3] += 1
    num = sum(a * d / (a + b + c + d) for a, b, c, d in S.values() if a + b + c + d)
    den = sum(b * c / (a + b + c + d) for a, b, c, d in S.values() if a + b + c + d)
    return num / den if den else float("inf")


def u_stat(R, fl):
    return sum(x["trap"] for x in R if fl(x)) - 3 * sum(x["winner"] for x in R if fl(x))


def perm_p(R, fl, N=2000, seed=9):
    """Mint-clustered permutation of U over rows R (in journal order)."""
    rnd = random.Random(seed)
    k = sum(1 for x in R if fl(x))
    u0 = u_stat(R, fl)
    em = {}
    for x in R:
        em.setdefault(x["mint"], []).append(x)
    mints = list(em)
    ge = 0
    for _ in range(N):
        rnd.shuffle(mints)
        c = u = 0
        for m in mints:
            if c >= k:
                break
            for x in em[m]:
                if c >= k:
                    break
                c += 1
                u += x["trap"] - 3 * x["winner"]
        ge += u >= u0
    return k, u0, (ge + 1) / (N + 1)


def bh(pvals):
    """{name: q} Benjamini-Hochberg over {name: p}."""
    items = sorted(pvals.items(), key=lambda kv: kv[1])
    m = len(items)
    q = {}
    prev = 1.0
    for i in range(m - 1, -1, -1):
        name, p = items[i]
        prev = min(prev, p * m / (i + 1))
        q[name] = prev
    return q


def cov(x, c):
    return x["feat"][c] if c in x["feat"] else x[c]


def placebos(R, fl):
    k = sum(1 for x in R if fl(x))
    out = {}
    for c in PLACEBO_COV:
        for sg in (1, -1):
            s = sorted(R, key=lambda x, c=c, sg=sg: (sg * cov(x, c), x["id"]), reverse=True)[:k]
            t = sum(x["trap"] for x in s)
            w = sum(x["winner"] for x in s)
            out[f"{c}{'+' if sg > 0 else '-'}"] = (t, w, t - 3 * w)
    return out


def cluster_boot(rows, key="net_b30m", B=2000, seed=11):
    """95% CI of the row mean of `key`, resampling mints."""
    if not rows:
        return (float("nan"), float("nan"))
    by = defaultdict(list)
    for r in rows:
        by[r["mint"]].append(r[key])
    groups = list(by.values())
    rnd = random.Random(seed)
    ms = []
    for _ in range(B):
        s = n = 0
        for _ in range(len(groups)):
            g = groups[rnd.randrange(len(groups))]
            s += sum(g)
            n += len(g)
        ms.append(s / n)
    ms.sort()
    return (ms[int(0.025 * B)], ms[int(0.975 * B) - 1])


def saved_boot(rows, fire, B=4000, seed=3):
    """Saved SOL and its 95% CI, resampling every mint of `rows` (0 for mints with no veto)."""
    by = defaultdict(float)
    for x in rows:
        by[x["mint"]] += -0.5 * x["net_b30m"] if fire(x) else 0.0
    g = list(by.values())
    if not g:
        return 0.0, (0.0, 0.0)
    rnd = random.Random(seed)
    bs = sorted(sum(g[rnd.randrange(len(g))] for _ in g) for _ in range(B))
    return sum(g), (bs[int(0.025 * B)], bs[int(0.975 * B) - 1])


def marginal(R, fl, base, B=4000, seed=1):
    """Rows vetoed by fl but not by `base`: counts, new trap mints, saved SOL with a mint CI."""
    u = [x for x in R if fl(x) and not base(x)]
    covered = {x["mint"] for x in R if x["trap"] and base(x)}
    by = defaultdict(float)
    for x in u:
        by[x["mint"]] += -0.5 * x["net_b30m"]
    ms = list(by.values())
    rnd = random.Random(seed)
    bs = sorted(sum(rnd.choice(ms) for _ in ms) for _ in range(B)) if ms else [0.0] * B
    return {
        "rows": len(u),
        "T": sum(x["trap"] for x in u),
        "W": sum(x["winner"] for x in u),
        "new_trap_mints": sorted({x["mint"][:8] for x in u if x["trap"] and x["mint"] not in covered}),
        "winner_mints": sorted({x["mint"][:8] for x in u if x["winner"]}),
        "saved": -0.5 * sum(x["net_b30m"] for x in u),
        "ci": (bs[int(0.025 * B)], bs[min(B - 1, int(0.975 * B))]),
    }


# ------------------------------------------------------------------ journal helpers
def load_journals(paths):
    J, G, metas = [], [], []
    seen = set()
    for p in paths:
        j = JN.load(p)
        metas.append(j["meta"])
        for x in j["rows"]:
            if (x["mint"], x["D"]) not in seen:
                seen.add((x["mint"], x["D"]))
                J.append(x)
        for x in j["grid"]:
            if (x["mint"], x["D"], "G") not in seen:
                seen.add((x["mint"], x["D"], "G"))
                G.append(x)
    return J, G, metas


def block_of(x, how):
    if how == "founding":
        return x.get("fblock") or x["day"]
    return x[how]


def creator_of(x):
    return x.get("creator") or x.get("dev")


def scored(d, x, bad_days=()):
    """A filter is scored on a row unless its raw is None, or it needs complete trades and the row's
    trade chain failed the check (or its day failed the > 5% rule): then it cannot fire."""
    if x["raw"].get(d["id"]) is None and d["id"] in x["raw"] and d["none_unscored"]:
        return False
    return not (d["complete"] and (not x["completeness"]["chain_ok"] or x["day"] in bad_days))


class Filt:
    """Gated fire test of one registry filter on scored rows."""

    def __init__(self, d, bad_days=()):
        self.d = d
        self.id = d["id"]
        self.bad = set(bad_days)

    def scored(self, x):
        return scored(self.d, x, self.bad) and self.id in x["flags"]

    def __call__(self, x):
        return x["real_e"] >= GATE and x["flags"].get(self.id, False) and scored(self.d, x, self.bad)


def chain_fn(gated, members, bad_days=()):
    if members is None:
        return lambda x: x["real_e"] >= GATE
    ds = [FL.BY_ID[m] for m in members]
    bad = set(bad_days)

    def fire(x):
        if gated and x["real_e"] < GATE:
            return False
        return any(x["flags"].get(d["id"], False) and scored(d, x, bad) for d in ds)

    return fire


def counts(R, fl, how):
    f = [x for x in R if fl(x)]
    tm = {x["mint"] for x in f if x["trap"]}
    wm = {x["mint"] for x in f if x["winner"]}
    tc = {creator_of(x) for x in f if x["trap"]}
    tb = {block_of(x, how) for x in f if x["trap"]}
    return {
        "k": len(f),
        "T": sum(x["trap"] for x in f),
        "W": sum(x["winner"] for x in f),
        "O": sum(1 for x in f if not x["trap"] and not x["winner"]),
        "mints": len({x["mint"] for x in f}),
        "Tm": len(tm),
        "Wm": len(wm),
        "Tc": len(tc),
        "Tb": len(tb),
        "count_rule": len(tm) >= COUNT_RULE[0] and len(tc) >= COUNT_RULE[1] and len(tb) >= COUNT_RULE[2],
        "trap_mints_by_block": dict(Counter(block_of(x, how) for x in f if x["trap"] and x["mint"] in tm)),
        "winner_rows": [x["id"] for x in f if x["winner"]],
    }


def near_threshold(d, raw):
    thr = d["thr"]
    if thr is None or raw is None or thr == 0:
        return False
    if d["dir"] == ">=":
        return 0.7 * thr <= raw < thr if thr > 0 else thr < raw <= thr / 0.7
    return thr < raw <= thr / 0.7 if thr > 0 else thr < raw <= 0.7 * thr


# ------------------------------------------------------------------ the scorecard
def scorecard(J, G, metas, how="day", perm_n=2000, seed=9, refs=()):
    out = {"journals": [{k: m.get(k) for k in ("from_t0", "to_t0", "census", "perturbation")} for m in metas]}
    warn = []
    for m in metas:
        p = m.get("perturbation") or {}
        if p.get("drop_small") or p.get("lookahead_test"):
            warn.append(f"journal built with a robustness perturbation {p}: not a scorecard input")
        for fid, info in (m.get("registry") or {}).items():
            if fid in FL.BY_ID and info.get("hash") != FL.definition_hash(fid):
                warn.append(f"{fid}: journal built with another definition (hash {info.get('hash')})")
    # data quality and the completeness rule
    by_day = defaultdict(lambda: [0, 0])
    for x in J:
        by_day[x["day"]][0] += 1
        by_day[x["day"]][1] += not x["completeness"]["chain_ok"]
    bad_days = sorted(d for d, (n, f) in by_day.items() if n and f / n > COMPLETE_DAY_MAX_FAIL)
    out["quality"] = {
        "rows_chain_fail": sum(not x["completeness"]["chain_ok"] for x in J),
        "rows_label_unresolved": sum(not x["label_ok"] for x in J),
        "rows_without_tx_index": sum(not x["completeness"]["tx_index"] for x in J),
        "days_not_scored_for_complete_filters": bad_days,
        "by_day": {d: {"rows": n, "chain_fail": f} for d, (n, f) in sorted(by_day.items())},
    }
    band = [x for x in J if x["real_e"] >= GATE]
    out["totals"] = {
        "J_rows": len(J),
        "G_rows": len(G),
        "mints": len({x["mint"] for x in J}),
        "trap_rows": sum(x["trap"] for x in J),
        "winner_rows": sum(x["winner"] for x in J),
        "trap_mints": len({x["mint"] for x in J if x["trap"]}),
        "winner_mints": len({x["mint"] for x in J if x["winner"]}),
        "band_rows": len(band),
        "band_trap_rows": sum(x["trap"] for x in band),
        "below_gate_rows": len(J) - len(band),
        "below_gate_traps": sum(x["trap"] for x in J if x["real_e"] < GATE),
        "blocks": dict(Counter(block_of(x, how) for x in J)),
    }
    # base trap rate by stratum (real SOL at dslot) and D
    base = []
    for lo, hi in BASE_STRATA:
        for D in sorted({x["D"] for x in J}) + ["all"]:
            s = [x for x in J if lo <= x["real_d"] < hi and (D == "all" or x["D"] == D)]
            t = sum(x["trap"] for x in s)
            base.append(
                {
                    "stratum": f"{lo}-{hi}",
                    "D": D,
                    "n": len(s),
                    "traps": t,
                    "rate": t / len(s) if s else float("nan"),
                    "ci": wilson(t, len(s)),
                    "winners": sum(x["winner"] for x in s),
                    "mean_net": mean(x["net_b30m"] for x in s),
                }
            )
    out["base"] = base
    # filters
    act = chain_fn(True, FL.members("active"), bad_days)
    act_members = set(FL.members("active"))
    rows = {}
    pv = {}
    for d in FL.REGISTRY:
        if not d["score"]:
            continue
        f = Filt(d, bad_days)
        R = [x for x in band if f.scored(x)]
        if not R:
            rows[d["id"]] = {"tier": d["tier"], "not_scored": True}
            continue
        c = counts(R, f, how)
        rest = [x for x in R if not f(x)]
        k, u, p = perm_p(R, f, perm_n, seed)
        pl = placebos(R, f)
        best = max(pl.items(), key=lambda kv: (kv[1][2], kv[0]))
        if d["id"] in act_members:
            others = [m for m in act_members if m != d["id"]]
            mg = marginal(band, act, chain_fn(True, others, bad_days))
            mg["kind"] = "leave-one-out from active"
        else:
            mg = marginal(band, f, act)
            mg["kind"] = "over active"
        strata = {}
        for name, lo, hi in BAND_STRATA:
            s = [x for x in R if lo <= x["real_e"] < hi]
            sf = [x for x in s if f(x)]
            strata[name] = (
                sum(x["trap"] for x in sf),
                len(sf),
                sum(x["trap"] for x in s) - sum(x["trap"] for x in sf),
                len(s) - len(sf),
            )
        g = [x for x in G if x["real_e"] >= GATE and f.scored(x)]
        rows[d["id"]] = {
            "tier": d["tier"],
            "family": d["family"],
            **c,
            "rate_f": c["T"] / c["k"] if c["k"] else float("nan"),
            "ci_f": wilson(c["T"], c["k"]),
            "rate_r": sum(x["trap"] for x in rest) / len(rest) if rest else float("nan"),
            "ci_r": wilson(sum(x["trap"] for x in rest), len(rest)),
            "mh": mh_or(R, f),
            "U": u,
            "p": p,
            "best_placebo": (best[0], *best[1]),
            "beats_placebo": u > best[1][2],
            "marginal": mg,
            "strata": strata,
            "not_scored_rows": len(band) - len(R),
            "dense": counts(g, f, how) if g else None,
        }
        if d["tier"] != "retired" and d["family"] != "reference":
            pv[d["id"]] = p
    q = bh(pv)
    for fid, v in rows.items():
        v["q"] = q.get(fid)
    out["filters"] = rows
    out["bh_family"] = sorted(pv)
    # chains side by side
    out["chains"] = {}
    for setname, R in (("J", J), ("G", G)):
        cs = {}
        for name, (gated, ms) in FL.chains().items():
            fire = chain_fn(gated, ms, bad_days)
            vet = [x for x in R if fire(x)]
            pas = [x for x in R if not fire(x)]
            tm = defaultdict(lambda: [0, 0])
            wm = defaultdict(lambda: [0, 0])
            for x in R:
                if x["trap"]:
                    tm[x["mint"]][0] += 1
                    tm[x["mint"]][1] += fire(x)
                if x["winner"]:
                    wm[x["mint"]][0] += 1
                    wm[x["mint"]][1] += fire(x)
            sv, sci = (
                saved_boot(R, fire) if setname == "J" else (-0.5 * sum(x["net_b30m"] for x in vet), None)
            )
            cs[name] = {
                "vetoed": len(vet),
                "traps_caught": sum(x["trap"] for x in vet),
                "traps": sum(x["trap"] for x in R),
                "winners_killed": sum(x["winner"] for x in vet),
                "winners": sum(x["winner"] for x in R),
                "trap_mints_caught": sum(1 for v in tm.values() if v[1]),
                "trap_mints": len(tm),
                "winner_mints_killed": sum(1 for v in wm.values() if v[1]),
                "winner_mints": len(wm),
                "saved_sol": sv,
                "saved_ci": sci,
                "passed": len(pas),
                "passed_mean": mean(x["net_b30m"] for x in pas),
                "passed_ci": cluster_boot(pas) if setname == "J" else None,
                "passed_traps": sum(x["trap"] for x in pas),
                "passed_winners": sum(x["winner"] for x in pas),
            }
        out["chains"][setname] = cs
    # dossier lists
    info_ids = [d["id"] for d in FL.REGISTRY if d["tier"] not in ("active",) and d["score"]]
    dossier = {}
    for name in ("active", "active+shadow"):
        gated, ms = FL.chains()[name]
        fire = chain_fn(gated, ms, bad_days)
        dossier[name] = {
            "missed_traps": [
                {
                    "id": x["id"],
                    "block": block_of(x, how),
                    "real_e": round(x["real_e"], 2),
                    "net": round(x["net_b30m"], 3),
                    "creator": (creator_of(x) or "")[:8],
                    "fired_other": [i for i in info_ids if x["flags"].get(i)],
                }
                for x in J
                if x["trap"] and x["real_e"] >= GATE and not fire(x)
            ],
            "killed_winners": [
                {
                    "id": x["id"],
                    "block": block_of(x, how),
                    "real_e": round(x["real_e"], 2),
                    "net": round(x["net_b30m"], 3),
                    "by": [m for m in ms if x["flags"].get(m)],
                }
                for x in J
                if x["winner"] and fire(x)
            ],
        }
    out["dossier"] = dossier
    # canaries
    missed_active = [x for x in band if x["trap"] and not act(x)]
    ref_rates = defaultdict(list)
    ref_base = []
    for path in refs:
        RJ, _, _ = load_journals([path])
        rb = [x for x in RJ if x["real_e"] >= GATE]
        if rb:
            ref_base.append(sum(x["trap"] for x in rb) / len(rb))
            for d in FL.REGISTRY:
                ref_rates[d["id"]].append(sum(1 for x in rb if Filt(d)(x)) / len(rb))
    base_rate = out["totals"]["band_trap_rows"] / len(band) if band else float("nan")
    can = {}
    for d in FL.REGISTRY:
        if not d["score"] or d["tier"] == "retired":
            continue
        f = Filt(d, bad_days)
        rate = sum(1 for x in band if f(x)) / len(band) if band else float("nan")
        by_s = {}
        for name, lo, hi in BAND_STRATA:
            s = [x for x in band if lo <= x["real_e"] < hi]
            by_s[name] = (sum(1 for x in s if f(x)), len(s))
        near = [x["id"] for x in missed_active if near_threshold(d, x["raw"].get(d["id"]))]
        e = {"rate": rate, "by_stratum": by_s, "near_threshold_missed": near}
        if ref_rates.get(d["id"]):
            rm = mean(ref_rates[d["id"]])
            e["ref_rate"] = rm
            e["ratio"] = rate / rm if rm else float("inf")
            low = rm > 0 and rate < 0.5 * rm and base_rate >= mean(ref_base)
            e["alarm"] = (
                "DROP (evasion or data loss? check data first)"
                if low
                else ("SURGE (check data)" if rm > 0 and rate > 2 * rm else "")
            )
        wal = Counter()
        nf = 0
        for x in band:
            if f(x) and d["id"] in x.get("detail", {}):
                nf += 1
                det = x["detail"][d["id"]]
                for w in det.get("ind_wallets", ()) or ([det["vet_mint"]] if det.get("vet_mint") else []):
                    wal[w] += 1
        if wal:
            w, n = wal.most_common(1)[0]
            e["top_entity"] = (w[:8], n, n / nf)
        can[d["id"]] = e
    out["canary"] = can
    out["warnings"] = warn
    return out


# ------------------------------------------------------------------ text rendering
def f2(x, n=2):
    if x is None:
        return "-"
    if isinstance(x, float) and (math.isnan(x) or math.isinf(x)):
        return "inf" if isinstance(x, float) and math.isinf(x) else "nan"
    return f"{x:.{n}f}"


def render(card, how):
    L = []
    t = card["totals"]
    L.append("SIEVE SCORECARD (in-sample on every journal given; G = description only)")
    for j in card["journals"]:
        names = ",".join(c["name"] for c in j["census"])
        L.append(f"  journal t0 {j['from_t0']}..{j['to_t0']}  census {names}")
    for w in card["warnings"]:
        L.append("  WARNING " + w)
    q = card["quality"]
    L.append(
        f"  J rows {t['J_rows']} ({t['mints']} mints), G rows {t['G_rows']}; trap rows {t['trap_rows']} "
        f"({t['trap_mints']} mints), winner rows {t['winner_rows']} ({t['winner_mints']} mints); band "
        f"(real_e >= {GATE}) {t['band_rows']} rows, {t['band_trap_rows']} traps; below gate "
        f"{t['below_gate_rows']} rows, {t['below_gate_traps']} traps"
    )
    L.append(f"  blocks ({how}): {t['blocks']}")
    L.append(
        f"  data: chain-check failures {q['rows_chain_fail']}, "
        f"unresolved labels {q['rows_label_unresolved']}, "
        f"rows without tx_index {q['rows_without_tx_index']}, days not scored for complete-trade filters "
        f"{q['days_not_scored_for_complete_filters'] or 'none'}"
    )
    L.append("\nBASE TRAP RATE by real SOL at dslot x D (net at 30 min <= -50%)")
    L.append(
        f"  {'stratum':8s} {'D':>4s} {'n':>5s} {'traps':>5s} {'rate':>6s} {'Wilson 95%':>14s} "
        f"{'win':>4s} {'mean':>7s}"
    )
    for b in card["base"]:
        L.append(
            f"  {b['stratum']:8s} {b['D']!s:>4s} {b['n']:5d} {b['traps']:5d} {f2(b['rate']):>6s} "
            f"[{f2(b['ci'][0])},{f2(b['ci'][1])}] {b['winners']:4d} {f2(b['mean_net'], 3):>7s}"
        )
    L.append("\nFILTERS on band rows (gated). k fired rows; T/W trap/winner rows; Tm/Wm trap/winner mints;")
    L.append("  Tc creators and Tb blocks of the trap mints (counting rule >= 3/2/2 -> R); rate = trap rate")
    L.append("  fired [Wilson] vs rest; MH = odds ratio in real_e x D strata; U = T - 3W; p mint-clustered")
    L.append("  permutation; q BH; placebo = best matched curve/activity placebo (its U); * = U beats it.")
    hdr = (
        f"  {'id':24s} {'tier':7s} {'k':>3s} {'T':>3s} {'W':>2s} {'Tm':>3s} {'Wm':>2s} "
        f"{'Tc':>3s} {'Tb':>2s} R "
        f"{'fired':>16s} {'rest':>16s} {'MH':>6s} {'U':>4s} {'p':>6s} {'q':>6s}  placebo"
    )
    L.append(hdr)
    order = {"active": 0, "shadow": 1, "watch": 2, "info": 3, "retired": 4}
    fl = sorted(card["filters"].items(), key=lambda kv: (order.get(kv[1]["tier"], 9), kv[0]))
    for fid, v in fl:
        if v.get("not_scored"):
            L.append(f"  {fid:24s} {v['tier']:7s} not scored (needs data this journal does not carry)")
            continue
        bp = v["best_placebo"]
        L.append(
            f"  {fid:24s} {v['tier']:7s} {v['k']:3d} {v['T']:3d} {v['W']:2d} {v['Tm']:3d} {v['Wm']:2d} "
            f"{v['Tc']:3d} {v['Tb']:2d} {'R' if v['count_rule'] else '.'} "
            f"{f2(v['rate_f'])}[{f2(v['ci_f'][0])},{f2(v['ci_f'][1])}] "
            f"{f2(v['rate_r'])}[{f2(v['ci_r'][0])},{f2(v['ci_r'][1])}] {f2(v['mh']):>6s} {v['U']:4d} "
            f"{f2(v['p'], 3):>6s} {f2(v['q'], 3):>6s}  {bp[0]} {bp[3]}{' *' if v['beats_placebo'] else ''}"
        )
    L.append(
        "\nPER FILTER: trap rate by band stratum (T/k fired vs T/n rest), marginal saved SOL, dense grid"
    )
    for fid, v in fl:
        if v.get("not_scored"):
            continue
        st = "; ".join(f"{s} {a}/{b} vs {c}/{d}" for s, (a, b, c, d) in v["strata"].items())
        mg = v["marginal"]
        dn = v["dense"]
        dtxt = f"G {dn['k']} rows {dn['T']}T/{dn['W']}W, {dn['Tm']}Tm/{dn['Wm']}Wm" if dn else "G -"
        L.append(f"  {fid:24s} {st}")
        L.append(
            f"  {'':24s} {mg['kind']}: {mg['rows']} rows {mg['T']}T/{mg['W']}W, saved {mg['saved']:+.2f} SOL "
            f"[{mg['ci'][0]:+.2f},{mg['ci'][1]:+.2f}], "
            f"new trap mints {len(mg['new_trap_mints'])}, winner mints "
            f"{mg['winner_mints'] or '-'}; {dtxt}; killed winner rows {v['winner_rows'] or '-'}"
        )
    for setname in ("J", "G") if card["totals"]["G_rows"] else ("J",):
        L.append(f"\nCHAINS on set {setname}" + (" (description only)" if setname == "G" else ""))
        L.append(
            f"  {'chain':14s} {'vetoed':>6s} {'traps':>7s} {'trapM':>7s} {'killW':>6s} {'killWM':>6s} "
            f"{'saved SOL':>10s} {'saved CI':>16s} {'passed':>6s} {'mean':>7s} {'mint CI':>17s} "
            f"{'pT':>3s} {'pW':>3s}"
        )
        for name, c in card["chains"][setname].items():
            sci = f"[{c['saved_ci'][0]:+.2f},{c['saved_ci'][1]:+.2f}]" if c["saved_ci"] else "-"
            pci = f"[{c['passed_ci'][0]:+.3f},{c['passed_ci'][1]:+.3f}]" if c["passed_ci"] else "-"
            L.append(
                f"  {name:14s} {c['vetoed']:6d} {c['traps_caught']:3d}/{c['traps']:<3d} "
                f"{c['trap_mints_caught']:3d}/{c['trap_mints']:<3d} "
                f"{c['winners_killed']:2d}/{c['winners']:<3d} "
                f"{c['winner_mints_killed']:2d}/{c['winner_mints']:<3d} {c['saved_sol']:+10.2f} {sci:>16s} "
                f"{c['passed']:6d} {c['passed_mean']:+7.3f} {pci:>17s} "
                f"{c['passed_traps']:3d} {c['passed_winners']:3d}"
            )
    for name, d in card["dossier"].items():
        L.append(
            f"\nDOSSIER ({name}): {len(d['missed_traps'])} missed band trap rows, "
            f"{len(d['killed_winners'])} killed winners"
        )
        for x in d["missed_traps"]:
            L.append(
                f"  MISSED {x['id']:14s} {x['block']:10s} real_e {x['real_e']:6.2f} net {x['net']:+.3f} "
                f"creator {x['creator']} other flags: {', '.join(x['fired_other']) or '-'}"
            )
        for x in d["killed_winners"]:
            L.append(
                f"  KILLED {x['id']:14s} {x['block']:10s} real_e {x['real_e']:6.2f} "
                f"net {x['net']:+.3f} by {x['by']}"
            )
    L.append("\nCANARY: fire rate on band rows (by stratum fired/n), ref = mean over --ref journals;")
    L.append("  near = missed band traps (active chain) with the raw at 70-100% of the threshold.")
    for fid, e in card["canary"].items():
        st = " ".join(f"{s} {a}/{b}" for s, (a, b) in e["by_stratum"].items())
        ref = ""
        if "ref_rate" in e:
            ref = f" ref {e['ref_rate']:.3f} x{f2(e['ratio'])} {e['alarm']}"
        top = ""
        if "top_entity" in e:
            w, n, s = e["top_entity"]
            top = f" top entity {w} in {n} fires ({s:.0%})"
        near = f" near {len(e['near_threshold_missed'])}" if e["near_threshold_missed"] else ""
        L.append(f"  {fid:24s} rate {e['rate']:.3f} ({st}){ref}{near}{top}")
    return "\n".join(L)


# ------------------------------------------------------------------ robustness diff
def _tw(rows, keys):
    return f"{sum(rows[k]['trap'] for k in keys)}/{sum(rows[k]['winner'] for k in keys)}"


def diff(base_path, other_path):
    """Flag flips (ungated) between a base journal and a perturbed rebuild of the same window.
    raw: as the definitions read the perturbed trades (the red team's stream_sim view); checked: with
    the scored rule, so rows whose trade chain fails the check are 'unscored' instead of flipping."""
    A = JN.load(base_path)
    B = JN.load(other_path)
    L = [f"FLAG DIFF {base_path} -> {other_path} (perturbation {B['meta'].get('perturbation')})"]
    L.append("  base = fires in base; raw lost/gained (new T/W); checked: unscored, lost, gained, flip share")
    for setname, key in (("J", "rows"), ("G", "grid")):
        a = {(x["mint"], x["D"]): x for x in A[key]}
        b = {(x["mint"], x["D"]): x for x in B[key]}
        ks = sorted(set(a) & set(b))
        if set(a) != set(b):
            L.append(f"  set {setname}: row sets differ ({len(set(a) ^ set(b))} rows)")
        lab = sum(1 for k in ks if a[k]["net_b30m"] != b[k]["net_b30m"])
        if lab:
            L.append(f"  set {setname}: {lab} rows with different labels")
        nc = sum(1 for k in ks if not b[k]["completeness"]["chain_ok"])
        L.append(f"  set {setname}: {len(ks)} rows, {nc} fail the chain check in the perturbed journal")
        L.append(
            f"  {'id':24s} {'base':>5s} {'lost':>5s} {'gained':>6s} {'T/W':>7s} | "
            f"{'unscored':>8s} {'lost':>5s} "
            f"{'gained':>6s} {'T/W':>7s} {'flip':>5s}"
        )
        for d in FL.REGISTRY:
            fid = d["id"]
            fa = {k for k in ks if a[k]["flags"].get(fid)}
            fb = {k for k in ks if b[k]["flags"].get(fid)}
            if not fa and not fb:
                continue
            sb = {k for k in ks if scored(d, b[k])}
            lost_r, gain_r = fa - fb, fb - fa
            uns = fa - sb
            lost_c, gain_c = (fa & sb) - fb, (fb & sb) - fa
            flip = (len(lost_c) + len(gain_c)) / len(fa) if fa else float("inf")
            L.append(
                f"  {fid:24s} {len(fa):5d} {len(lost_r):5d} {len(gain_r):6d} {_tw(a, gain_r):>7s} | "
                f"{len(uns):8d} "
                f"{len(lost_c):5d} {len(gain_c):6d} {_tw(a, gain_c):>7s} {f2(flip):>5s}"
            )
    return "\n".join(L)


def jsonable(o):
    if isinstance(o, float) and (math.isnan(o) or math.isinf(o)):
        return str(o)
    if isinstance(o, dict):
        return {str(k): jsonable(v) for k, v in o.items()}
    if isinstance(o, list | tuple):
        return [jsonable(v) for v in o]
    return o


def main(argv=None):
    ap = argparse.ArgumentParser(description="Sieve scorecard from journal files.")
    ap.add_argument("journals", nargs="*", help="journal.py outputs (concatenated in this order)")
    ap.add_argument("--blocks", choices=("day", "week", "founding"), default="day")
    ap.add_argument("--perm-n", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=9)
    ap.add_argument("--ref", nargs="*", default=[], help="earlier journals (one per period) for the canary")
    ap.add_argument("--json", help="write the full scorecard as JSON")
    ap.add_argument("--out", help="write the text scorecard here too")
    ap.add_argument("--diff", nargs=2, metavar=("BASE", "OTHER"), help="flag flips between two journals")
    a = ap.parse_args(argv)
    if a.diff:
        txt = diff(*a.diff)
    else:
        if not a.journals:
            ap.error("no journal given")
        J, G, metas = load_journals(a.journals)
        card = scorecard(J, G, metas, how=a.blocks, perm_n=a.perm_n, seed=a.seed, refs=a.ref)
        txt = render(card, a.blocks)
        if a.json:
            with open(a.json, "w") as fh:
                json.dump(jsonable(card), fh, indent=1, sort_keys=True)
    print(txt)
    if a.out:
        with open(a.out, "w") as fh:
            fh.write(txt + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
