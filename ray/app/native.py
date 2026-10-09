"""Ray-native filters: definitions that read Ray's wallet memory (app/wallets.py), which the frozen
research package cannot hold. Same discipline as research/sieve/filters.py: one function per
id/version, frozen by a hash of everything it reads (the function, the feature definitions in
app/features.py and the memory's counting in app/wallets.py). Editing any of them in place shows on
the health check and the dashboard; a new threshold is a new id (docs/PREREG-RAY-L2.md).

Like every filter, a native one decides a verdict only once the live rule (app/live_rules.py)
confirms it on data after its registration.
"""

import hashlib
import inspect
from typing import Any

from . import features, wallets
from .sieve import FL, FROZEN_PROBLEMS, _raw_text


def ray_serial_v1(f: dict[str, float]) -> tuple[bool, float]:
    return f["serial_vol"] >= 0.50, f["serial_vol"]


REGISTRY: list[dict[str, Any]] = [
    {
        "id": "RAY-SERIAL-v1",
        "fn": ray_serial_v1,
        "tier": "shadow",
        "label": "Ví mua sớm chuyên nghiệp (đã mua sớm ở ≥ 2 coin trước) chiếm ≥ 50% tiền mua sớm",
        "kind": "pct",
        "thr": 0.50,
        "definition": "Wallets that bought in the first 60 s of >= 2 earlier launches Ray scored carry "
        ">= 50% of the SOL this launch's early buyers spent in its first 60 s.",
        "evidence": "Ray journal 09/10/2026, 837 rows replayed in time order with the live memory: the "
        "ticket did 15 points worse than the rows' band x D on the first 60% (interval -5..+35, memory "
        "still filling) and 20 points worse on the last 40% (+6..+33); threshold 0.506 (67th percentile "
        "of the first 60%), rounded.",
    },
]
BY_ID = {d["id"]: d for d in REGISTRY}
IDS = [d["id"] for d in REGISTRY]


def _reads() -> str:
    """The definitions every native filter reads, as they stand."""
    parts = [
        inspect.getsource(features.early_slot),
        inspect.getsource(features.early_activity),
        inspect.getsource(features.memory_features),
        inspect.getsource(wallets.WalletBook.features),
        inspect.getsource(wallets.WalletBook.note_launch),
        inspect.getsource(wallets.WalletBook._note),
        inspect.getsource(wallets.WalletBook.note_outcome),
        repr(
            (
                features.EARLY_S,
                features.DUMP_SHARE,
                features.SERIAL_MIN,
                features.TRAPW_MIN_RESOLVED,
                features.TRAPW_SHARE,
                FL.SPS,
            )
        ),
    ]
    return "\n".join(parts)


def definition_hash(fid: str) -> str:
    src = inspect.getsource(BY_ID[fid]["fn"]) + _reads()
    return hashlib.sha256(src.encode()).hexdigest()[:16]


# Frozen 2026-10-09 (docs/PREREG-RAY-L2.md). Never edit a value here to make the check pass:
# register a new id/version instead and freeze its hash.
FROZEN = {
    "RAY-SERIAL-v1": "ea22fbee3198ff9c",
}


def check_frozen() -> list[tuple[str, str, str]]:
    bad = []
    for d in REGISTRY:
        h = definition_hash(d["id"])
        want = FROZEN.get(d["id"])
        if not want:
            bad.append((d["id"], "not frozen", h))
        elif want != h:
            bad.append((d["id"], f"edited in place (frozen {want})", h))
    return bad


# One list of frozen-definition problems for the whole app: the research package's (sieve) and these.
FROZEN_PROBLEMS.extend(check_frozen())


def evaluate(f: dict[str, float] | None) -> list[dict[str, Any]]:
    """The native flags for these features, shaped like sieve._flag's (deciding and live are added
    by sieve.score_row). Unscored without memory features (no early buyer to look up)."""
    out = []
    for d in REGISTRY:
        scored = bool(f) and f.get("n_early", 0) > 0
        fired, raw = d["fn"](f) if scored else (False, None)
        out.append(
            {
                "id": d["id"],
                "tier": d["tier"],
                "label": d["label"],
                "fired": bool(fired) and scored,
                "scored": scored,
                "raw": raw,
                "raw_text": _raw_text(d["kind"], raw),
                "thr": d["thr"],
                "needs_all_trades": False,
                "pool": None,
            }
        )
    return out


def registry() -> list[dict[str, Any]]:
    return [
        {
            "id": d["id"],
            "tier": d["tier"],
            "label": d["label"],
            "definition": d["definition"],
            "evidence": d["evidence"],
            "needs_all_trades": False,
            "pool": {"flagged": 0, "traps": 0, "winners": 0},
        }
        for d in REGISTRY
    ]
