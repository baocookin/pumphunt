from app.analyze import render, reprice
from app.gecko import Candle
from app.survivor import MIN_N, compute_metrics, summarize, verdict

T0 = 1_700_000_000
DELAYS = [0, 30]
HORIZONS = [60]


def candles(path: dict[int, float], vol: float = 100.0) -> list[Candle]:
    """path: minute offset -> close price. Fills gaps by carrying the price forward."""
    out, price = [], None
    for m in range(0, 25 * 60):
        price = path.get(m, price)
        if price is None:
            continue
        out.append(Candle(T0 + m * 60, price, price * 1.01, price * 0.99, price, vol))
    return out


def test_metrics_net_of_cost():
    cs = candles({0: 1.0, 30: 0.5, 90: 0.6, 60: 0.8})
    m = compute_metrics(cs, T0, DELAYS, HORIZONS, cost_bps=350)
    c = m["cells"]["d30_h60"]
    assert abs(c["gross"] - 0.2) < 1e-9  # 0.5 -> 0.6
    assert abs(c["net"] - ((1.2 * 0.965) - 1)) < 1e-9
    c0 = m["cells"]["d0_h60"]
    assert abs(c0["gross"] - (-0.2)) < 1e-9  # 1.0 -> 0.8
    assert c0["mdd"] < -0.4  # low of the 0.5 candle (0.495) seen inside the hour
    assert c0["exit_stale_s"] == 0  # a candle exists exactly at the exit minute
    assert m["alive_24h"] is True


def test_metrics_missing_data():
    assert compute_metrics([], T0, DELAYS, HORIZONS, 350)["no_data"] is True
    # pool that stops trading after minute 9: the AMM mark carries forward (LP is burned,
    # so it is nominally sellable) but the cell records how stale the exit mark is
    cs = candles({0: 1.0})[:10]
    m = compute_metrics(cs, T0, DELAYS, HORIZONS, 350)
    c = m["cells"]["d30_h60"]
    assert c["gross"] == 0.0 and c["exit_stale_s"] == (90 - 9) * 60
    assert m["cells"]["d0_h60"]["exit_stale_s"] == (60 - 9) * 60
    assert m["alive_24h"] is False
    # no candle at all before the entry time -> no cell
    late = [x for x in candles({0: 1.0}) if x.ts >= T0 + 40 * 60]
    assert compute_metrics(late, T0, DELAYS, HORIZONS, 350)["cells"]["d30_h60"] is None


def _row(net: float, key="d30_h60"):
    return {"cells": {key: {"gross": net, "net": net, "mdd": 0.0}}, "alive_24h": True}


def test_verdict_rules():
    assert verdict({"n": 10})["status"] == "INSUFFICIENT"
    base = {"n": MIN_N, "win_rate": 0.5, "top2pct_share": 0.1}
    assert verdict(dict(base, median=-0.02))["status"] == "KILL"
    assert verdict(dict(base, median=0.05, top2pct_share=0.7))["status"] == "KILL"
    assert verdict(dict(base, median=0.05))["status"] == "PASS"
    assert verdict(dict(base, median=0.0))["status"] == "INCONCLUSIVE"


def test_summarize_lottery_detector():
    # 299 small losers + 1 giant winner: median negative, top-2% share ~100%
    rows = [_row(-0.03) for _ in range(299)] + [_row(50.0)]
    s = summarize(rows, DELAYS, HORIZONS)
    c = s["cells"]["d30_h60"]
    assert c["n"] == 300 and c["top2pct_share"] > 0.99 and c["median"] < 0
    assert s["verdict"]["status"] == "KILL"
    assert s["cells"]["d0_h60"]["n"] == 0


def test_reprice_and_render():
    rows = [_row(0.10) for _ in range(MIN_N)]
    s = summarize(reprice(rows, 1000), DELAYS, HORIZONS)  # 10% cost -> net ≈ -1%
    assert abs(s["cells"]["d30_h60"]["median"] - (1.1 * 0.9 - 1)) < 1e-9
    text = render(s, DELAYS, HORIZONS)
    assert "T+30m" in text and "C (T+30m -> 1h)" in text
