"""Sniper tickets on launch-level outcomes: the historical measurement of docs/SNIPER.md section 3.

Data: the `launches` subset of https://huggingface.co/datasets/loopholetape/pumpfun-launches
(decoder-complete days from 2026-09-27), downloaded as parquet files into one directory:

    python research/sniper_launches.py /path/to/launches          # needs: pip install duckdb

A ticket buys `size` SOL (fee included) at real reserve R0 and is sold the first time its value
reaches m x size (optimistic: exactly m), else at graduation, else at the curve's terminal state.
Other traders' token flows are taken as given: with the ticket's tokens outstanding the curve sits
where the real one sits with that many more tokens sold (constant product over virtual reserves).
Entries: R0 = the dev's buy (the bundle's place), R0 = the reserve at the first snapshot under 10 s
(median age 1.0 s), R0 = the reserve between 10 and 60 s.
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


def ticket(r0: float, size: float) -> float:
    return tau(min(r0 + size / (1 + FEE), GRAD)) - tau(r0)


def value(dt: float, r: float) -> float:
    """SOL received for dt tokens when the historical reserve is r."""
    return max(0.0, r_of(min(tau(r) + dt, tau(GRAD) + dt)) - r) * (1 - FEE)


def outcome(row: dict, r0: float, size: float, m: float | None) -> float:
    dt = ticket(r0, size)
    peak = min(row["peak_rs"] or 0.0, GRAD)
    if m and value(dt, max(peak, r0)) >= m * size:
        return m * size
    if row["graduated"]:
        return value(dt, GRAD)
    return value(dt, min(row["terminal_rs"] or 0.0, peak))


def stats(proceeds: list[float]) -> dict:
    nets = [(p - COST) / SIZE - 1 for p in proceeds]
    n = len(nets)
    mean = sum(nets) / n
    sd = math.sqrt(sum((x - mean) ** 2 for x in nets) / (n - 1))
    s = sorted(nets)
    return {
        "n": n,
        "ev": mean,
        "ci": (mean - 1.96 * sd / math.sqrt(n), mean + 1.96 * sd / math.sqrt(n)),
        "median": s[n // 2],
        "win": sum(x > 0 for x in nets) / n,
        "p10x": sum(x >= 9 for x in nets) / n,
    }


def load(data_dir: str) -> list[dict]:
    con = duckdb.connect()
    cur = con.execute(
        f"""select t0, dev_buy_sol, f10_rs, f60_rs, peak_rs, terminal_rs, graduated,
              f10_rep_n, f10_rep_grad, f10_bundle_wallets
            from read_parquet('{data_dir}/*.parquet', union_by_name=true)
            where quote_asset = 'sol' and decoder_complete = 1 and peak_rs is not null and mayhem = 0
              and dev_buy_sol < {GRAD - 0.5}"""
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]


def main(data_dir: str) -> None:
    rows = load(data_dir)
    print(f"snipeable classic launches {len(rows)}, graduated {sum(r['graduated'] for r in rows)}")
    entries = {"dev": "dev_buy_sol", "~1 s": "f10_rs", "10-60 s": "f60_rs"}
    for label, col in entries.items():
        for m in (1.5, 2, 3, 5, 10, None):
            pay = [outcome(r, r[col], SIZE, m) for r in rows if r[col] is not None and r[col] < GRAD - 0.5]
            st = stats(pay)
            print(
                f"{label:8s} TP={m!s:4s} n={st['n']} EV={st['ev']:+.1%} "
                f"CI=[{st['ci'][0]:+.1%}, {st['ci'][1]:+.1%}] median={st['median']:+.1%} "
                f"win={st['win']:.1%} >=10x={st['p10x']:.2%}"
            )


if __name__ == "__main__":
    main(sys.argv[1])
