"""Scoring one launch at one moment with the frozen sieve filters (research/sieve/filters.py).

The filter registry is loaded from the research package as is, and its FROZEN hashes are checked at
start: the scorer runs the very definitions the founding pool measured. Only filters that read the
launch itself are run; the memory filters (N-WM-*, P2, N-LTE-*) need every launch's trades, which a
real-time reader of candidates does not have.

Verdict, most severe first, all above the entry gate (below it a 0.5 SOL ticket cannot lose 50%):
  TRANH          an active filter fires (SH-DEV-1, N-MMAAS-WAVE-STREAM): "cờ (chưa kiểm)"
  THIEU_DU_LIEU  an active filter that needs every trade could not be computed
  CANH_GIAC      only a shadow filter fires (weaker evidence)
  KHONG_THAY_CO  nothing fires. This is NOT a buy signal: the base trap rate still applies.
Risk: the share of tickets that lost >= 50% within 30 minutes on the founding pool (06-07/10/2026,
26 hours, in-sample, never tested forward), for the curve band and decision time, or for the
active filter that fired when that share is higher.
"""

import importlib.util
import math
import os
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

LAMPORTS = 1_000_000_000
V_SOL0 = 30 * LAMPORTS
V_TOK0 = 1_073_000_000_000_000
SIZE, FIXED, FEE = 0.5, 0.002, 0.0125
F0_MIN, F0_MAX = 5.0, 70.0  # gate F0: the curve band the sieve was built on


def load_filters() -> ModuleType:
    """research/sieve/filters.py: from RAY_SIEVE_DIR (the image copies it to /app/sieve) or the repo."""
    here = Path(__file__).resolve()
    for d in (os.environ.get("RAY_SIEVE_DIR"), "/app/sieve", str(here.parents[2] / "research" / "sieve")):
        if d and (Path(d) / "filters.py").is_file():
            path = Path(d) / "filters.py"
            spec = importlib.util.spec_from_file_location("sieve_filters", path)
            assert spec and spec.loader
            mod = importlib.util.module_from_spec(spec)
            sys.modules["sieve_filters"] = mod
            spec.loader.exec_module(mod)
            return mod
    raise RuntimeError("research/sieve/filters.py not found (set RAY_SIEVE_DIR)")


FL = load_filters()
FROZEN_PROBLEMS = FL.check_frozen()
GATE_E = float(FL.GATE_E)


def _tier(tier: str) -> list[str]:
    return [d["id"] for d in FL.REGISTRY if d["tier"] == tier and not d["memory"] and d["id"] != "GATE_E"]


ACTIVE = _tier("active")
SHADOW = _tier("shadow")
# context shown with a score; none of them changes the verdict
INFO = [
    i
    for i in (
        "P1-SWARM-SCRIPTED-v1",
        "N-MMAAS-MSTX",
        "N-MMAAS-DUSTHOLD",
        "SH-WASH-1",
        "N-ANAT-FADE",
        "CC-TOPDIST-v1",
        "LC-XFERSUP-v1",
        "N-ANAT-LOCKSTEP",
    )
    if i in FL.BY_ID and not FL.BY_ID[i]["memory"]
]

# Vietnamese label and how the raw value reads, per filter id.
LABELS: dict[str, tuple[str, str]] = {
    "SH-DEV-1": ("Dev + creator còn giữ ≥ 3% cung", "pct"),
    "N-MMAAS-WAVE-STREAM": ("Sóng mua cùng cỡ: ≥ 4 ví trong một slot, lệch ≤ 2%", "wallets"),
    "SH-SG-1": ("Nhóm tạo mua ≥ 20 SOL rồi bán ≥ 50%, hoặc ≥ 5 ví mua cùng cỡ", "sol"),
    "N-MMAAS-SPLDIST": ("≥ 5 ví bán trước khi mua (hàng đến qua transfer)", "wallets"),
    "N-MMAAS-WAVE": ("Sóng mua cùng cỡ chặt: lệch ≤ 0,5%, các giao dịch liền nhau", "wallets"),
    "CLD-ORPHAN-v1": ("Insider đã rút, ít người giữ: ≥ 0,5 SOL thật mỗi holder", "sol_per"),
    "P1-SWARM-SCRIPTED-v1": ("Farm script: người mua đầu né cỡ preset; nếu xả thường xả trong 1 slot", "z"),
    "N-MMAAS-MSTX": ("Có giao dịch bán nhiều chữ ký (một người bấm bán cho nhiều ví)", "count"),
    "N-MMAAS-DUSTHOLD": ("≥ 20 ví bụi chỉ mua 1 lần (thổi số holder)", "wallets"),
    "SH-WASH-1": ("Wash: ví đổi chiều ≥ 3 lần chiếm ≥ 30% volume", "pct"),
    "N-ANAT-FADE": ("Đã rơi ≥ 30% từ đỉnh", "pct"),
    "CC-TOPDIST-v1": ("Top-10 đã bán ≥ 35% hàng của họ trong 60 giây qua", "pct"),
    "LC-XFERSUP-v1": ("Hàng nhận qua transfer đã bán ≥ 5,5% cung", "pct"),
    "N-ANAT-LOCKSTEP": ("Cặp ví mua đồng bộ giữ ≥ 10% float", "pct"),
}

# --- founding pool (in-sample) ------------------------------------------------------------------
POOL_TEXT = (
    "Kho sáng lập 06/10 20:53Z–07/10 23:03Z (26 giờ, mẫu 5%): 206 dòng, 55 mint bẫy, 11 mint thắng. "
    "Số trong mẫu, chưa kiểm forward. Bẫy = vé 0,5 SOL vào ngay lúc chấm, lỗ ≥ 50% sau 30 phút."
)
# (rows, trap rows) by real SOL at the decision slot x decision time; "all" pools the three times.
BASE: dict[str, dict[Any, tuple[int, int]]] = {
    "5-13": {120: (50, 1), 300: (18, 1), 600: (10, 0), "all": (78, 2)},
    "13-30": {120: (47, 33), 300: (21, 18), 600: (15, 8), "all": (83, 59)},
    "30-70": {120: (19, 10), 300: (17, 8), 600: (9, 3), "all": (45, 21)},
}
# (rows flagged above the gate, trap rows, winner rows) per filter, all decision times
FLAGGED: dict[str, tuple[int, int, int]] = {
    "SH-DEV-1": (30, 24, 1),
    "N-MMAAS-WAVE-STREAM": (29, 26, 0),
    "SH-SG-1": (24, 17, 2),
    "N-MMAAS-SPLDIST": (20, 16, 1),
    "N-MMAAS-WAVE": (20, 19, 0),
    "CLD-ORPHAN-v1": (12, 10, 0),
    "P1-SWARM-SCRIPTED-v1": (10, 6, 2),
    "N-MMAAS-MSTX": (7, 4, 0),
    "N-MMAAS-DUSTHOLD": (7, 6, 0),
    "SH-WASH-1": (26, 17, 1),
    "N-ANAT-FADE": (36, 29, 1),
    "CC-TOPDIST-v1": (28, 20, 3),
    "LC-XFERSUP-v1": (28, 18, 1),
    "N-ANAT-LOCKSTEP": (30, 19, 2),
}

VERDICTS = {
    "TRANH": "TRÁNH",
    "THIEU_DU_LIEU": "THIẾU DỮ LIỆU",
    "CANH_GIAC": "CẢNH GIÁC",
    "KHONG_THAY_CO": "KHÔNG THẤY CỜ",
    "IT_HOAT_DONG": "ÍT HOẠT ĐỘNG",
    "DUOI_CONG": "DƯỚI CỔNG",
    "NGOAI_VUNG": "NGOÀI VÙNG ĐO",
    "DA_TOT_NGHIEP": "ĐÃ TỐT NGHIỆP",
    "QUA_NHO": "CHƯA ĐỦ 5 SOL",
    "LOI_DOC": "LỖI ĐỌC",
}


LIGHT_TEXT = {
    "DUOI_CONG": (
        "Dưới cổng 11,66 SOL: vé 0,5 SOL không thể lỗ 50% trên curve, nhưng phí và trượt giá vẫn ăn mòn."
    ),
    "NGOAI_VUNG": "Từ 70 SOL trở lên: sát tốt nghiệp, ngoài vùng bộ lọc đã được đo.",
    "DA_TOT_NGHIEP": "Curve đã hoàn tất (tốt nghiệp): ngoài phạm vi của rây.",
    "QUA_NHO": "Chưa tới 5 SOL thật: chưa phải ứng viên.",
}
SUMMARY = {
    "TRANH": "Có dấu hiệu bẫy: {names}.",
    "THIEU_DU_LIEU": "Thiếu giao dịch nên không chấm được: {unscored}.",
    "CANH_GIAC": "Chỉ có cờ phụ (bằng chứng yếu): {names}.",
    "IT_HOAT_DONG": "Không thấy cờ, nhưng ít giao dịch trong 2 phút qua (ngoài cổng F0).",
    "KHONG_THAY_CO": "Không thấy cờ. Đây KHÔNG phải tín hiệu mua: tỷ lệ bẫy nền của tầng này vẫn áp dụng.",
    "DUOI_CONG": "Dưới cổng 11,66 SOL: vé 0,5 SOL không thể lỗ 50% trên curve.",
    "NGOAI_VUNG": "Từ 70 SOL trở lên: ngoài vùng bộ lọc đã được đo.",
}


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n <= 0:
        return 0.0, 1.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def floor_net(real_e: float, fee: float = FEE) -> float:
    """Worst case on the curve for a 0.5 SOL ticket bought at `real_e` real SOL: every other token is
    sold back while the ticket is held, then the ticket is sold (1.25% fee each side, 0.002 SOL).
    -50% at 11.66 SOL: below that a trap is mechanically impossible."""
    vs = V_SOL0 + max(0.0, real_e) * LAMPORTS
    vt = V_SOL0 * V_TOK0 / vs
    net_in = SIZE * LAMPORTS / (1 + fee)
    dt = vt * net_in / (vs + net_in)
    worst = (1 - fee) * V_SOL0 * dt / (V_TOK0 - dt)
    return (worst / LAMPORTS - FIXED) / SIZE - 1


def band(real: float) -> str | None:
    if real < 5:
        return None
    if real < 13:
        return "5-13"
    if real < 30:
        return "13-30"
    if real < 70:
        return "30-70"
    return None


def d_bucket(age_s: float) -> int:
    """The validated decision time closest to this age."""
    return 120 if age_s < 210 else 300 if age_s < 450 else 600


def risk(real_d: float, age_s: float, fired_active: list[str]) -> dict[str, Any]:
    """The historical trap share that applies: the band x decision-time cell (or the whole band when
    the cell has fewer than 15 rows), or a fired active filter's share when higher."""
    b = band(real_d)
    if b is None:
        return {"pct": None, "basis": "ngoài vùng đã đo", "n": 0}
    D = d_bucket(age_s)
    n, k = BASE[b][D]
    basis = f"tầng {b} SOL lúc {D // 60} phút"
    if n < 15:
        n, k = BASE[b]["all"]
        basis = f"tầng {b} SOL (mọi thời điểm)"
    best = {"pct": k / n, "k": k, "n": n, "basis": basis, "ci": wilson(k, n)}
    for fid in fired_active:
        fn, ft, _ = FLAGGED.get(fid, (0, 0, 0))
        if fn and ft / fn > best["pct"]:
            best = {"pct": ft / fn, "k": ft, "n": fn, "basis": f"khi {fid} bật", "ci": wilson(ft, fn)}
    best["base"] = {"band": b, "D": D, "n": n, "k": k}
    if b == "5-13":
        best["note"] = "Tầng 5–13 SOL ít dữ liệu trên cổng: 2/78 dòng là bẫy, cả hai sát cổng."
    return best


def _raw_text(kind: str, raw: Any) -> str:
    if raw is None:
        return "—"
    try:
        x = float(raw)
    except (TypeError, ValueError):
        return str(raw)
    if kind == "pct":
        return f"{x * 100:.1f}%"
    if kind == "sol":
        return f"{x:.2f} SOL"
    if kind == "sol_per":
        return f"{x:.2f} SOL/holder"
    if kind == "z":
        return f"z = {x:.1f}"
    return f"{int(x)}"


def _flag(fid: str, fired: bool, raw: Any, scored: bool) -> dict[str, Any]:
    d = FL.BY_ID[fid]
    label, kind = LABELS.get(fid, (d["definition"], "count"))
    fn, ft, fw = FLAGGED.get(fid, (0, 0, 0))
    return {
        "id": fid,
        "tier": d["tier"],
        "label": label,
        "fired": bool(fired) and scored,
        "scored": scored,
        "raw": raw,
        "raw_text": _raw_text(kind, raw),
        "thr": d["thr"],
        "needs_all_trades": bool(d["complete"]),
        "pool": {"flagged": fn, "traps": ft, "winners": fw} if fn else None,
    }


def f0_activity(cand: Any) -> dict[str, Any]:
    """Gate F0's activity part at the decision slot: a trade in the last 60 s, >= 5 trades and >= 3
    distinct buyers in the last 120 s."""
    vis = cand.vis
    if not vis:
        return {"n120": 0, "buyers120": 0, "recent": False, "ok": False}
    dslot = cand.dslot
    lo120, lo60 = dslot - FL.W120, dslot - FL.W60
    n = 0
    buyers = set()
    for t in reversed(vis):
        if int(t[FL.SLOT]) <= lo120:
            break
        n += 1
        if t[FL.BUY]:
            buyers.add(t[FL.USER])
    recent = int(vis[-1][FL.SLOT]) > lo60
    return {
        "n120": n,
        "buyers120": len(buyers),
        "recent": recent,
        "ok": recent and n >= 5 and len(buyers) >= 3,
    }


def header(info: dict[str, Any], D: int | None, age_s: float, now: float) -> dict[str, Any]:
    return {
        "mint": info["mint"],
        "symbol": info.get("symbol") or "",
        "name": info.get("name") or "",
        "dev": info.get("dev"),
        "creator": info.get("creator"),
        "t0": info.get("create_ts"),
        "key": f"D{D}" if D else "now",
        "D": D,
        "age_s": round(age_s, 1),
        "at": round(now, 3),
        "frozen_ok": not FROZEN_PROBLEMS,
    }


def light_score(
    info: dict[str, Any], real: float, D: int | None, age_s: float, now: float, verdict: str
) -> dict[str, Any]:
    """A verdict that needs no history: below the gate, beyond the studied band, graduated, small.
    A graduated curve shows the highest real SOL seen (none when it was never seen trading): the
    curve is emptied into the AMM pool at migration, and there is no floor on a curve that is gone."""
    out = header(info, D, age_s, now)
    if verdict == "DA_TOT_NGHIEP":
        real_shown = round(real, 4) if real and real > 0 else None
        floor = None
    else:
        real_shown = round(real, 4)
        floor = floor_net(real) if real >= 0 else None
    text = LIGHT_TEXT.get(verdict, "")
    out.update(
        verdict=verdict,
        verdict_vi=VERDICTS.get(verdict, verdict),
        summary=text,
        real=real_shown,
        real_d=real_shown,
        floor=round(floor, 4) if floor is not None else None,
        risk={"pct": None, "basis": text, "n": 0},
        active=[],
        shadow=[],
        info=[],
        f0=None,
        data=None,
    )
    return out


def score_row(
    row: dict[str, Any],
    dslot: int,
    entry: tuple[float, float],
    *,
    D: int | None,
    age_s: float,
    now: float,
    data: dict[str, Any],
) -> dict[str, Any]:
    """Score a census-format row at `dslot` with the curve at `entry` (v_sol, v_tokens) now."""
    info = row
    out = header(info, D, age_s, now)
    cand = FL.Cand(row, dslot, None, entry=(float(entry[0]), float(entry[1])))
    ev: dict[str, tuple[bool, Any]] = {}
    errors = {}
    for fid in ACTIVE + SHADOW + INFO:
        try:
            fired, raw = FL.BY_ID[fid]["fn"](cand)
            ev[fid] = (bool(fired), raw)
        except Exception as exc:  # noqa: BLE001 - one filter failing must not sink the score
            ev[fid] = (False, None)
            errors[fid] = f"{type(exc).__name__}: {exc}"[:160]
    gaps = FL.check_ordered(row, dslot)["gaps"]
    chain_ok = gaps == 0 and not data.get("truncated") and not data.get("synthetic_tx_index")
    groups: dict[str, list[dict[str, Any]]] = {"active": [], "shadow": [], "info": []}
    for group, members in (("active", ACTIVE), ("shadow", SHADOW), ("info", INFO)):
        for fid in members:
            fired, raw = ev[fid]
            d = FL.BY_ID[fid]
            scored = (
                fid not in errors
                and (chain_ok or not d["complete"])
                and not (raw is None and d["none_unscored"])
            )
            groups[group].append(_flag(fid, fired, raw, scored))
    f0 = f0_activity(cand)
    real_d, real_e = cand.real_d, cand.real_e
    fired_active = [f["id"] for f in groups["active"] if f["fired"]]
    unscored_active = [f["id"] for f in groups["active"] if not f["scored"]]
    fired_shadow = [f["id"] for f in groups["shadow"] if f["fired"]]
    if real_e < GATE_E:
        verdict = "DUOI_CONG"
    elif real_d >= F0_MAX:
        verdict = "NGOAI_VUNG"
    elif fired_active:
        verdict = "TRANH"
    elif unscored_active:
        verdict = "THIEU_DU_LIEU"
    elif fired_shadow:
        verdict = "CANH_GIAC"
    elif not f0["ok"]:
        verdict = "IT_HOAT_DONG"
    else:
        verdict = "KHONG_THAY_CO"
    rk = risk(real_d, age_s, fired_active)
    names = [f["label"] for f in groups["active"] + groups["shadow"] if f["fired"]]
    summary = SUMMARY[verdict].format(names="; ".join(names), unscored=", ".join(unscored_active))
    out.update(
        verdict=verdict,
        verdict_vi=VERDICTS[verdict],
        summary=summary,
        slot=int(dslot),
        real=round(real_e, 4),
        real_d=round(real_d, 4),
        floor=round(floor_net(real_e, FL.fee_of(row)), 4),
        risk=rk,
        **groups,
        f0=f0,
        data={**data, "chain_gaps": gaps, "chain_ok": chain_ok, "trades": cand.n, "filter_errors": errors},
    )
    return out


def registry() -> list[dict[str, Any]]:
    """What the dashboard explains about each filter it shows."""
    out = []
    for fid in ACTIVE + SHADOW + INFO:
        d = FL.BY_ID[fid]
        fn, ft, fw = FLAGGED.get(fid, (0, 0, 0))
        out.append(
            {
                "id": fid,
                "tier": d["tier"],
                "label": LABELS.get(fid, (d["definition"], ""))[0],
                "definition": d["definition"],
                "evidence": d["evidence"],
                "needs_all_trades": bool(d["complete"]),
                "pool": {"flagged": fn, "traps": ft, "winners": fw},
            }
        )
    return out
