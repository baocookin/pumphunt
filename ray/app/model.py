"""Risk model, in shadow until it earns its place (registered 09/10/2026, docs/PREREG-RAY-L3.md).

What it gives: the probability that a 0.5 SOL ticket bought at a decision is a trap 30 minutes later
(net <= -50%), from the decision-time features (app/features.py), the SOL band and the decision time.

The model. Logistic regression with an L2 penalty (LAMBDA on standardised inputs, intercept free),
fitted by Newton's method every hour on the settled decision-time rows of the last 7 days that carry
features (>= 300 rows, >= 50 traps and >= 50 others). Inputs: the 20 features (counts as log1p,
dev_traps as a value and a known flag), the band and the decision time as one-hot columns; each
clipped to its training 1st-99th percentile and standardised.

Every score records the model's probability (`model_p`) next to the risk Ray showed without it
(`base_risk`). Each prediction comes from a model fitted only on outcomes settled before it, so the
journal keeps a held-out record of both.

The switch. The model's probability replaces the band x decision time share as the risk shown when,
on the journal rows of the last 7 days that carry both:
  - at least 2 complete UTC days have >= 300 such rows each,
  - the mean log-loss gain (base - model) is above zero, the lower end of its 95% interval (clustered
    by launch) too, and
  - the gain on the latest such day is above zero.
Whenever these stop holding, the risk shown is the band x decision time share again. Verdicts never
depend on the model; it never gives a buy signal.
"""

import datetime
import math
from collections import defaultdict
from operator import mul
from typing import Any

from .live_rules import WINDOW_S, clustered_mean, journal_rows

CURVE = (
    "n120",
    "trades60",
    "wallets120",
    "per_wallet120",
    "cadence_cv120",
    "same_size_share",
    "dust_buyers",
    "sell_sol_share60",
    "wash_share",
    "top5_buy_share",
    "d_real_60s",
    "dd_pre",
)
MEMORY = (
    "n_early",
    "serial_share",
    "serial_vol",
    "dumper_share",
    "dumper_vol",
    "trapw_vol",
    "dev_prior",
    "dev_traps",
)
FEATURES = CURVE + MEMORY
COUNTS = frozenset({"n120", "trades60", "wallets120", "n_early", "dev_prior"})
BANDS = ("13-30", "30-70")  # one-hot; 5-13 SOL is the reference
TIMES = (300, 600)  # one-hot; 2 minutes is the reference
LAMBDA = 30.0
MIN_ROWS, MIN_CLASS = 300, 50
MAX_ITER, TOL = 30, 1e-7
CLIP_P = 1e-4
SWITCH_DAYS, SWITCH_DAY_ROWS = 2, 300

# what each input means, for the dashboard
VI = {
    "n120": "giao dịch trong 2 phút",
    "trades60": "giao dịch trong 1 phút",
    "wallets120": "ví giao dịch trong 2 phút",
    "per_wallet120": "giao dịch mỗi ví",
    "cadence_cv120": "nhịp giao dịch không đều",
    "same_size_share": "lệnh mua cùng cỡ",
    "dust_buyers": "ví mua bụi",
    "sell_sol_share60": "tỷ trọng bán trong 1 phút",
    "wash_share": "wash",
    "top5_buy_share": "tỷ trọng mua của 5 ví lớn nhất",
    "d_real_60s": "SOL thật tăng trong 1 phút",
    "dd_pre": "khoảng cách tới đỉnh",
    "n_early": "số ví mua sớm",
    "serial_share": "tỷ lệ ví mua sớm chuyên nghiệp",
    "serial_vol": "tiền của ví mua sớm chuyên nghiệp",
    "dumper_share": "tỷ lệ ví từng xả sớm",
    "dumper_vol": "tiền của ví từng xả sớm",
    "trapw_vol": "tiền của ví hay vào bẫy",
    "dev_prior": "số coin trước của dev",
    "dev_traps": "tỷ lệ bẫy các coin trước của dev",
    "dev_known": "dev có coin trước đã có kết quả",
    "band_13-30": "tầng 13–30 SOL",
    "band_30-70": "tầng 30–70 SOL",
    "D300": "mốc 5 phút",
    "D600": "mốc 10 phút",
}


def names() -> list[str]:
    out: list[str] = []
    for k in FEATURES:
        out += ["dev_traps", "dev_known"] if k == "dev_traps" else [k]
    return out + [f"band_{b}" for b in BANDS] + [f"D{d}" for d in TIMES]


def inputs(feats: dict[str, Any] | None, band: str | None, D: int | None) -> list[float] | None:
    """The raw inputs of one score, before clipping and standardising; None when it has no features
    or is outside the measured bands."""
    if not feats or band is None or D is None:
        return None
    x: list[float] = []
    for k in FEATURES:
        v = feats.get(k)
        if v is None:
            return None
        v = float(v)
        if k == "dev_traps":
            x += [max(v, 0.0), 1.0 if v >= 0 else 0.0]
        elif k in COUNTS:
            x.append(math.log1p(max(v, 0.0)))
        else:
            x.append(v)
    x += [1.0 if band == b else 0.0 for b in BANDS]
    x += [1.0 if int(D) == d else 0.0 for d in TIMES]
    return x


def _sigmoid(s: float) -> float:
    if s >= 0:
        return 1.0 / (1.0 + math.exp(-s))
    e = math.exp(s)
    return e / (1.0 + e)


def _scaled(x: list[float], m: dict[str, Any]) -> list[float]:
    lo, hi, mu, sd = m["lo"], m["hi"], m["mu"], m["sd"]
    return [1.0] + [(min(max(v, lo[j]), hi[j]) - mu[j]) / sd[j] for j, v in enumerate(x)]


def _solve(a: list[list[float]], b: list[float]) -> list[float]:
    """a x = b by Gaussian elimination with partial pivoting (a is small and positive definite)."""
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for c in range(n):
        piv = max(range(c, n), key=lambda r: abs(m[r][c]))
        m[c], m[piv] = m[piv], m[c]
        for r in range(c + 1, n):
            f = m[r][c] / m[c][c]
            if f:
                mr, mc = m[r], m[c]
                for k in range(c, n + 1):
                    mr[k] -= f * mc[k]
    x = [0.0] * n
    for r in range(n - 1, -1, -1):
        x[r] = (m[r][n] - sum(m[r][k] * x[k] for k in range(r + 1, n))) / m[r][r]
    return x


def _newton(z: list[list[float]], y: list[float], lam: float) -> list[float]:
    q = len(z[0])
    k = sum(y)
    w = [0.0] * q
    w[0] = math.log(k / (len(y) - k))
    for _ in range(MAX_ITER):
        g = [0.0] * q
        h = [[0.0] * q for _ in range(q)]
        for zi, yi in zip(z, y, strict=True):
            p = _sigmoid(sum(map(mul, w, zi)))
            d, v = p - yi, p * (1.0 - p)
            for a in range(q):
                za = zi[a]
                g[a] += d * za
                vza = v * za
                if vza:
                    ha = h[a]
                    for b in range(a, q):
                        ha[b] += vza * zi[b]
        for a in range(q):
            for b in range(a):
                h[a][b] = h[b][a]
        for a in range(1, q):
            g[a] += lam * w[a]
            h[a][a] += lam
        step = _solve(h, g)
        w = [a - b for a, b in zip(w, step, strict=True)]
        if max(abs(s) for s in step) < TOL:
            break
    return w


def _logloss(p: float, trap: bool) -> float:
    p = min(max(float(p), CLIP_P), 1 - CLIP_P)
    return -math.log(p if trap else 1 - p)


def fit(lines: list[dict[str, Any]], now: float) -> dict[str, Any] | None:
    """The model from the settled decision-time rows of the last 7 days that carry features; None
    while there are too few of them."""
    data: list[tuple[list[float], float]] = []
    for r in journal_rows(lines, now - WINDOW_S):
        x = inputs(r.get("features"), r.get("band"), r.get("D"))
        if x is not None and r.get("label"):
            data.append((x, 1.0 if r["label"] == "trap" else 0.0))
    n = len(data)
    traps = int(sum(t for _, t in data))
    if n < MIN_ROWS or traps < MIN_CLASS or n - traps < MIN_CLASS:
        return None
    lo, hi, mu, sd = [], [], [], []
    for j in range(len(data[0][0])):
        col = sorted(x[j] for x, _ in data)
        a, b = col[int(0.01 * (n - 1))], col[int(0.99 * (n - 1))]
        c = [min(max(v, a), b) for v in col]
        m = sum(c) / n
        s = math.sqrt(sum((v - m) ** 2 for v in c) / n)
        lo.append(a)
        hi.append(b)
        mu.append(m)
        sd.append(s if s > 1e-12 else 1.0)
    model: dict[str, Any] = {"lo": lo, "hi": hi, "mu": mu, "sd": sd}
    z = [_scaled(x, model) for x, _ in data]
    y = [t for _, t in data]
    w = _newton(z, y, LAMBDA)
    loss = sum(_logloss(_sigmoid(sum(map(mul, w, zi))), yi == 1.0) for zi, yi in zip(z, y, strict=True)) / n
    model.update(
        version=1,
        trained_at=now,
        n=n,
        traps=traps,
        lam=LAMBDA,
        names=names(),
        w=w,
        train_logloss=loss,
    )
    return model


def predict(
    model: dict[str, Any] | None, feats: dict[str, Any] | None, band: str | None, D: int | None
) -> float | None:
    if not model:
        return None
    x = inputs(feats, band, D)
    if x is None or len(x) != len(model["mu"]):
        return None
    return _sigmoid(sum(map(mul, model["w"], _scaled(x, model))))


def factors(model: dict[str, Any] | None, top: int = 6) -> dict[str, list[dict[str, Any]]]:
    """The inputs that move the probability most (weights on standardised inputs), both ways."""
    if not model:
        return {"up": [], "down": []}
    ws = [
        {"name": n, "vi": VI.get(n, n), "w": round(w, 3)}
        for n, w in zip(model["names"], model["w"][1:], strict=False)
    ]
    up = sorted((f for f in ws if f["w"] > 0), key=lambda f: -f["w"])[:top]
    down = sorted((f for f in ws if f["w"] < 0), key=lambda f: f["w"])[:top]
    return {"up": up, "down": down}


def day_of(ts: float) -> str:
    return datetime.datetime.fromtimestamp(float(ts), datetime.UTC).strftime("%Y-%m-%d")


def held_out(lines: list[dict[str, Any]], now: float) -> dict[str, Any]:
    """The model's record against the risk shown without it, on the journal rows of the last 7 days
    that carry both, and whether the switch rule holds."""
    rows = [
        r
        for r in journal_rows(lines, now - WINDOW_S)
        if r.get("model_p") is not None and r.get("base_risk") is not None and r.get("label")
    ]
    today = day_of(now)
    per_day: dict[str, list[tuple[float, float]]] = defaultdict(list)
    pairs: list[tuple[Any, float]] = []
    buckets = [[0, 0.0, 0, 0.0] for _ in range(5)]  # rows, predicted, traps, base predicted
    for r in rows:
        trap = r["label"] == "trap"
        lm, lb = _logloss(r["model_p"], trap), _logloss(r["base_risk"], trap)
        per_day[day_of(r["entry_at"])].append((lm, lb))
        pairs.append((r.get("mint"), lb - lm))
        bk = buckets[min(int(float(r["model_p"]) * 5), 4)]
        bk[0] += 1
        bk[1] += float(r["model_p"])
        bk[2] += trap
        bk[3] += float(r["base_risk"])
    days = []
    for d in sorted(per_day):
        items = per_day[d]
        n = len(items)
        lm = sum(a for a, _ in items) / n
        lb = sum(b for _, b in items) / n
        days.append({"day": d, "n": n, "complete": d < today, "model": lm, "base": lb, "gain": lb - lm})
    gain, lo, hi = clustered_mean(pairs)
    qualified = [d for d in days if d["complete"] and d["n"] >= SWITCH_DAY_ROWS]
    active = (
        len(qualified) >= SWITCH_DAYS
        and gain is not None
        and gain > 0
        and lo is not None
        and lo > 0
        and qualified[-1]["gain"] > 0
    )
    return {
        "rows": len(rows),
        "days": days,
        "gain": gain,
        "gain_ci": None if lo is None else [lo, hi],
        "qualified_days": len(qualified),
        "active": active,
        "calibration": [
            {
                "lo": i / 5,
                "hi": (i + 1) / 5,
                "n": b[0],
                "predicted": b[1] / b[0],
                "observed": b[2] / b[0],
                "base": b[3] / b[0],
            }
            for i, b in enumerate(buckets)
            if b[0]
        ],
    }
