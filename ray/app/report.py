"""The weekly review of the outcome journal: how the verdicts, the curve bands and each filter did on
new launches, next to the founding pool they were measured on, and the rows to read first when
patching the filter chain (traps the sieve let through, winners it said to avoid).

Only scores at the decision times count (the founding pool's rows are decision-time rows); scores
asked by hand are counted apart. The founding pool's numbers are in-sample; these are not.
"""

from typing import Any

from .live_rules import filter_record
from .sieve import ACTIVE, BASE, FL, FLAGGED, INFO, LABELS, SHADOW, VERDICTS, wilson

LET_THROUGH = ("KHONG_THAY_CO", "IT_HOAT_DONG", "CANH_GIAC", "THIEU_DU_LIEU")
ORDER = ("TRANH", "CANH_GIAC", "THIEU_DU_LIEU", "KHONG_THAY_CO", "IT_HOAT_DONG", "DUOI_CONG", "NGOAI_VUNG")
POOL_N = sum(cells["all"][0] for cells in BASE.values())
POOL_K = sum(cells["all"][1] for cells in BASE.values())
LIST_MAX = 100


def share(k: int, n: int) -> dict[str, Any]:
    return {"k": k, "n": n, "pct": k / n if n else None, "ci": list(wilson(k, n)) if n else None}


def _fired(r: dict[str, Any]) -> set[str]:
    f = r.get("fired") or {}
    return set(f.get("active") or []) | set(f.get("shadow") or []) | set(f.get("info") or [])


def _count(rows: list[dict[str, Any]], label: str) -> int:
    return sum(1 for r in rows if r.get("label") == label)


def _brief(r: dict[str, Any]) -> dict[str, Any]:
    f = r.get("fired") or {}
    return {
        "mint": r.get("mint"),
        "symbol": r.get("symbol"),
        "D": r.get("D"),
        "entry_at": r.get("entry_at"),
        "verdict": r.get("verdict"),
        "real": r.get("real"),
        "net": r.get("net"),
        "why": r.get("why"),
        "risk": r.get("risk"),
        "fired": (f.get("active") or []) + (f.get("shadow") or []),
        "info": f.get("info") or [],
        "unscored": r.get("unscored") or [],
    }


def build(
    lines: list[dict[str, Any]], now: float, days: int, pending: int, rules: Any = None
) -> dict[str, Any]:
    """`rules` (app/live_rules.LiveRules) gives each filter's current status under the live rule."""
    since = now - days * 86_400
    latest: dict[tuple[Any, Any, Any], dict[str, Any]] = {}
    for r in lines:  # one outcome per score, the last written
        if float(r.get("entry_at") or 0) >= since:
            latest[(r.get("mint"), r.get("key"), r.get("score_at"))] = r
    rows = list(latest.values())
    decided = [r for r in rows if r.get("D")]
    ok = [r for r in decided if r.get("status") == "ok"]

    verdicts = []
    for v in ORDER:
        grp = [r for r in ok if r.get("verdict") == v]
        if not grp:
            continue
        risks = [float(r["risk"]) for r in grp if r.get("risk") is not None]
        verdicts.append(
            {
                "verdict": v,
                "verdict_vi": VERDICTS.get(v, v),
                "traps": share(_count(grp, "trap"), len(grp)),
                "winners": _count(grp, "winner"),
                "risk_mean": sum(risks) / len(risks) if risks else None,
            }
        )

    bands = []
    for b, cells in BASE.items():
        for D in (120, 300, 600):
            grp = [r for r in ok if r.get("band") == b and r.get("D") == D]
            n0, k0 = cells[D]
            bands.append(
                {
                    "band": b,
                    "D": D,
                    "traps": share(_count(grp, "trap"), len(grp)),
                    "winners": _count(grp, "winner"),
                    "pool": share(k0, n0),
                }
            )

    filters = []
    banded = [r for r in ok if r.get("band")]
    for fid in ACTIVE + SHADOW + INFO:
        grp = [r for r in ok if fid in _fired(r)]
        fn, ft, fw = FLAGGED.get(fid, (0, 0, 0))
        rec = filter_record(banded, fid)
        now_rec = rules.record(fid) if rules is not None else None
        filters.append(
            {
                "id": fid,
                "tier": FL.BY_ID[fid]["tier"],
                "label": LABELS.get(fid, (fid, ""))[0],
                "traps": share(_count(grp, "trap"), len(grp)),
                "winners": _count(grp, "winner"),
                # what the same SOL band x decision time gave on the rows where it did not fire
                "trap_exp": rec["trap_exp"],
                "win_exp": rec["win_exp"],
                "status": (now_rec or rec)["status"],
                "pool": {**share(ft, fn), "winners": fw},
            }
        )

    def newest(rs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return sorted(rs, key=lambda r: -float(r.get("entry_at") or 0))

    missed = newest([r for r in ok if r.get("label") == "trap" and r.get("verdict") in LET_THROUGH])
    alarms = newest([r for r in ok if r.get("label") == "winner" and r.get("verdict") == "TRANH"])
    traps = _count(ok, "trap")
    return {
        "days": days,
        "since": since,
        "now": now,
        "totals": {
            "settled": len(ok),
            "unresolved": len(decided) - len(ok),
            "pending": pending,
            "traps": traps,
            "winners": _count(ok, "winner"),
            "by_hand": len(rows) - len(decided),
        },
        "overall": share(traps, len(ok)),
        "pool": share(POOL_K, POOL_N),
        "verdicts": verdicts,
        "bands": bands,
        "filters": filters,
        "missed": {"count": len(missed), "rows": [_brief(r) for r in missed[:LIST_MAX]]},
        "false_alarms": {"count": len(alarms), "rows": [_brief(r) for r in alarms[:LIST_MAX]]},
    }
