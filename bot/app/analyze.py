"""Offline analysis of harvested rows.

    python -m app.analyze data/survivor.jsonl [--cost_bps 350]

Prints the delay x horizon table (net of costs) and the pre-registered verdict
for hypothesis C. `--cost_bps` re-prices every cell from gross so you can see
how fragile a result is to execution assumptions.
"""

import argparse
import sys
from typing import Any

from .config import Settings
from .jsonl import read_jsonl
from .survivor import summarize


def reprice(rows: list[dict[str, Any]], cost_bps: int) -> list[dict[str, Any]]:
    cost = cost_bps / 10_000
    out = []
    for r in rows:
        cells = {}
        for k, c in (r.get("cells") or {}).items():
            cells[k] = None if c is None else dict(c, net=(1 + c["gross"]) * (1 - cost) - 1)
        out.append(dict(r, cells=cells))
    return out


def render(summary: dict[str, Any], delays: list[int], horizons: list[int]) -> str:
    lines = [
        f"harvested={summary['harvested']} with_data={summary['with_data']} "
        f"alive_24h={summary['alive_24h_rate']:.0%}",
        "",
    ]
    head = f"{'entry':>7} | " + " | ".join(f"{'h' + str(h) + 'm':^30}" for h in horizons)
    lines += [head, "-" * len(head)]
    for d in delays:
        parts = []
        for h in horizons:
            c = summary["cells"][f"d{d}_h{h}"]
            if c["n"] == 0:
                parts.append(f"{'n=0':^30}")
            else:
                parts.append(
                    f"n={c['n']:<4} med={c['median']:+6.1%} wr={c['win_rate']:4.0%} "
                    f"top2={c['top2pct_share']:3.0%}"
                )
        lines.append(f"{'T+' + str(d) + 'm':>7} | " + " | ".join(parts))
    v = summary["verdict"]
    lines += ["", f"C (T+30m -> 1h): {v['status']} — {v['why']}"]
    return "\n".join(lines)


def main(argv: list[str]) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--cost_bps", type=int, default=None)
    ns = ap.parse_args(argv)
    cfg = Settings(_env_file=None)
    rows = list(read_jsonl(ns.path))
    if ns.cost_bps is not None:
        rows = reprice(rows, ns.cost_bps)
    print(
        render(
            summarize(rows, cfg.entry_delays_min, cfg.horizons_min), cfg.entry_delays_min, cfg.horizons_min
        )
    )


if __name__ == "__main__":
    main(sys.argv[1:])
