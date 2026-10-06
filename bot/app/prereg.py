"""Pre-registered hypotheses, fixed before the data that tests them exists (see docs/PREREG.md).

Only migrations at or after a hypothesis' `since` are its confirmatory sample. The harvester
computes a row a day after the migration, so when this file was committed (2026-10-06, before
PREREG_TS) no outcome of that sample existed. A changed rule is a new registration with a new
timestamp; an old rule keeps its own sample.

Every hypothesis is read on one cell: enter at T+30 min, hold 1 h, a 1 SOL position, the
executable net under the replay model when it was computed and the pessimistic ghost model
otherwise, with the kill criteria of `survivor.verdict`. Membership uses only what was known at
the decision time (T+30 min, before the 3 s execution latency).
"""

import math
from collections.abc import Callable, Sequence
from typing import Any

from .survivor import FILLS_VERSION, _cell_stats, latest_by_mint, verdict

PREREG_TS = 1_791_302_400  # 2026-10-06T16:00:00Z
EXPLORE_DAYS = 14  # feature rules are chosen on [PREREG_TS, +14 d) and tested only after their registration
PRIMARY_CELL, PRIMARY_SIZE, DECISION = "d30_h60", "1", "d30"

# C2: tradeable at the decision time. A 1 SOL order is at most a tenth of the real vault, and
# the pool traded within the last minute. Chosen from market mechanics, not from outcomes.
C2_MIN_REAL_SOL = 10.0
C2_MAX_IDLE_S = 60.0

SOL_QUOTES = {None, "So11111111111111111111111111111111111111112", "11111111111111111111111111111111"}


def t_mig(row: dict[str, Any]) -> float:
    return float(row.get("fills_t0") or row.get("t0") or 0)


def decision(row: dict[str, Any], key: str = DECISION) -> dict[str, Any] | None:
    return (row.get("decision") or {}).get(key)


def c2_member(row: dict[str, Any]) -> bool:
    dec = decision(row)
    if not dec or dec.get("real_sol") is None or dec.get("last_trade_age_s") is None:
        return False
    return dec["real_sol"] >= C2_MIN_REAL_SOL and dec["last_trade_age_s"] <= C2_MAX_IDLE_S


HYPOTHESES: list[dict[str, Any]] = [
    {
        "name": "C",
        "desc": "every SOL-quoted graduate (registered at the start of recording)",
        "since": None,
        "member": lambda r: True,
    },
    {
        "name": "C*",
        "desc": "C on the confirmatory sample only, for comparison with C2",
        "since": PREREG_TS,
        "member": lambda r: True,
    },
    {
        "name": "C2",
        "desc": f">= {C2_MIN_REAL_SOL:g} SOL real in the pool, a swap in the last {C2_MAX_IDLE_S:g} s (T+30)",
        "since": PREREG_TS,
        "member": c2_member,
    },
]

# Feature rules join here, each with its own `since` (its registration time), after being chosen on
# the exploration window. At most three; each is tested once, on rows after its registration.
RULES: list[dict[str, Any]] = []


def median_ci(vals: Sequence[float], z: float = 1.96) -> tuple[float, float] | None:
    """Distribution-free ~95% interval for the median from order statistics (binomial)."""
    n = len(vals)
    if n < 10:
        return None
    s = sorted(vals)
    k = max(0, math.floor(n / 2 - z * math.sqrt(n) / 2))
    return s[k], s[min(n - 1, n - 1 - k)]


def _net(row: dict[str, Any]) -> float | None:
    by_size = (row.get("fills") or {}).get(PRIMARY_CELL) or {}
    cell = by_size.get(PRIMARY_SIZE) or by_size.get(str(float(PRIMARY_SIZE)))
    return cell.get("net") if cell else None


def evaluate(rows: Sequence[dict[str, Any]], now: float | None = None) -> dict[str, Any]:
    """Each registered hypothesis on its own sample: counts, the primary cell's statistics, the
    verdict, and how far the sample is."""
    current = [
        r for r in latest_by_mint(rows) if r.get("fills") and (r.get("fills_version") or 1) >= FILLS_VERSION
    ]
    rows = [r for r in current if r.get("quote_mint") in SOL_QUOTES]
    out = []
    for h in [*HYPOTHESES, *RULES]:
        member: Callable[[dict[str, Any]], bool] = h["member"]
        sample = [r for r in rows if h["since"] is None or t_mig(r) >= h["since"]]
        sel = [r for r in sample if member(r)]
        nets = [v for r in sel if (v := _net(r)) is not None]
        st = _cell_stats(nets)
        out.append(
            {
                "name": h["name"],
                "desc": h["desc"],
                "since": h["since"],
                "eligible": len(sample),  # harvested rows in the sample window
                "members": len(sel),
                **{k: st.get(k) for k in ("n", "median", "win_rate", "p10", "p90", "top2pct_share")},
                "median_ci95": median_ci(nets),
                "verdict": verdict(st),
            }
        )
    return {
        "prereg_ts": PREREG_TS,
        "explore_until": PREREG_TS + EXPLORE_DAYS * 86_400,
        "cell": PRIMARY_CELL,
        "size": PRIMARY_SIZE,
        "c2": {"min_real_sol": C2_MIN_REAL_SOL, "max_idle_s": C2_MAX_IDLE_S},
        "hypotheses": out,
    }
