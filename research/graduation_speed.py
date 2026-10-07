"""Graduation-run tickets split by how fast the curve reached the trigger: docs/SNIPER.md
sections 8 (exploration update) and 9 (hypothesis GS).

Data: the `launches` subset of https://huggingface.co/datasets/loopholetape/pumpfun-launches
(decoder-complete days from 2026-09-27), downloaded as parquet files into one directory:

    python research/graduation_speed.py /path/to/launches [level] [slip] [exit_factor]

Population: classic SOL launches whose dev did not buy the whole curve and whose curve reached
`level` SOL real. A ticket buys 0.5 SOL (fee included) at `level + slip` SOL real, or at the
curve's peak when it never got that far (dropping those curves would keep only survivors). A
graduate is sold at the graduation price times `exit_factor` (the pool 3 s after the migration
relative to the graduation price: mean 1.04, median 1.02 on 04-05/10), a failure at the curve's
terminal state. Groups: completed within 60 s of the create (`migrate_dt_s`), at >= level at
t0+60 s (`f60_rs`) but not complete, and reached the level after the first minute (GS).
"""

import math
import sys

import duckdb

FEE = 0.0125
VS, VT = 30.0, 1.073e9  # virtual SOL and tokens at launch
K = VS * VT
GRAD = 85.005  # real SOL at which the curve completes
SIZE, COST = 0.5, 0.002


def tau(r: float) -> float:
    """Tokens out of the curve at real reserve r."""
    return VT - K / (VS + r)


def r_of(t: float) -> float:
    return K / (VT - t) - VS


def value(dt: float, r: float) -> float:
    """SOL received for dt tokens when the historical reserve is r."""
    return max(0.0, r_of(min(tau(r) + dt, tau(GRAD) + dt)) - r) * (1 - FEE)


def net(row: dict, entry: float, exit_factor: float) -> float:
    # the ticket cannot buy above the curve's peak: one that never got past the trigger by `slip`
    # buys at its top
    r0 = min(entry, row["peak_rs"], GRAD - 0.5)
    dt = tau(min(r0 + SIZE / (1 + FEE), GRAD)) - tau(r0)
    if row["graduated"]:
        pay = value(dt, GRAD) * exit_factor
    else:
        pay = value(dt, min(row["terminal_rs"] or 0.0, min(row["peak_rs"], GRAD)))
    return (pay - COST) / SIZE - 1


def line(name: str, rows: list[dict], nets: list[float], total: int) -> str:
    n = len(nets)
    if n < 3:
        return f"{name:46s} n={n}"
    mean = sum(nets) / n
    half = 1.96 * math.sqrt(sum((x - mean) ** 2 for x in nets) / (n - 1) / n)
    grad = sum(r["graduated"] for r in rows) / n
    by_time = [x for _, x in sorted(zip((r["t0"] for r in rows), nets, strict=True))]
    h = n // 2
    halves = f"{sum(by_time[:h]) / h:+.3f} / {sum(by_time[h:]) / (n - h):+.3f}"
    return (
        f"{name:46s} n={n:5d} share={n / total:.2f} P(grad)={grad:.2f} "
        f"mean={mean:+.3f} [{mean - half:+.3f}, {mean + half:+.3f}] halves {halves}"
    )


def main(path: str, level: float = 60.0, slip: float = 1.0, exit_factor: float = 1.04) -> None:
    con = duckdb.connect()
    cur = con.execute(
        f"""select t0, dev_buy_sol, f60_rs, peak_rs, terminal_rs, graduated, migrate_dt_s
        from read_parquet('{path}/*.parquet', union_by_name=true)
        where quote_asset = 'sol' and decoder_complete = 1 and peak_rs is not null and mayhem = 0"""
    )
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]
    rows = [r for r in rows if (r["dev_buy_sol"] or 0) < GRAD - 0.5 and r["peak_rs"] >= level]
    r0 = level + slip

    def done_in_first_minute(r: dict) -> bool:
        return bool(r["graduated"]) and r["migrate_dt_s"] is not None and r["migrate_dt_s"] <= 60

    first_minute = [r for r in rows if done_in_first_minute(r)]
    rest = [r for r in rows if not done_in_first_minute(r)]
    groups = {
        "all": rows,
        "completed within 60 s of the create": first_minute,
        f"at >= {level:g} SOL at t0+60 s, not complete": [r for r in rest if (r["f60_rs"] or 0) >= level],
        f"reached {level:g} SOL after 60 s (GS)": [r for r in rest if (r["f60_rs"] or 0) < level],
    }
    print(f"level {level:g} SOL, entry at {r0:g} SOL, exit factor {exit_factor:g}, curves {len(rows)}")
    for name, sub in groups.items():
        print(line(name, sub, [net(r, r0, exit_factor) for r in sub], len(rows)))
    fast = sorted(r["migrate_dt_s"] for r in first_minute)
    for lim in (2, 10, 60):
        print(f"  completed within {lim:2d} s of the create: {sum(1 for x in fast if x <= lim)}")


if __name__ == "__main__":
    args = sys.argv[1:]
    main(args[0], *(float(a) for a in args[1:4]))
