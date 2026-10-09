from app import report
from app.sieve import BASE

NOW = 10 * 86_400.0
NETS = {"trap": -0.8, "winner": 1.5, "neutral": 0.1, None: None}


def _line(mint, verdict, label, ago, fired=(), D=120, risk=0.7):
    return {
        "mint": mint,
        "symbol": mint.upper(),
        "key": f"D{D}" if D else "now",
        "D": D,
        "score_at": NOW - ago,
        "entry_at": NOW - ago,
        "verdict": verdict,
        "real": 20.0,
        "real_d": 20.0,
        "band": "13-30",
        "risk": risk,
        "fired": {"active": list(fired), "shadow": [], "info": []},
        "unscored": [],
        "status": "ok" if label else "unresolved",
        "net": NETS[label],
        "label": label,
        "why": "time",
    }


def test_the_report_puts_new_outcomes_next_to_the_founding_pool():
    lines = [
        _line("a", "TRANH", "trap", 100, fired=["SH-DEV-1"]),
        _line("b", "TRANH", "winner", 200, fired=["SH-DEV-1"]),
        _line("c", "KHONG_THAY_CO", "trap", 300),
        _line("d", "KHONG_THAY_CO", "neutral", 400),
        _line("e", "KHONG_THAY_CO", None, 500),  # could not be read
        _line("old", "TRANH", "trap", 8 * 86_400, fired=["SH-DEV-1"]),  # outside the 7 days
        _line("f", "KHONG_THAY_CO", "trap", 50, D=None),  # asked by hand: counted apart
        {**_line("d", "KHONG_THAY_CO", "neutral", 400)},  # the same outcome written twice
    ]
    r = report.build(lines, NOW, 7, pending=3)
    totals = {"settled": 4, "unresolved": 1, "pending": 3, "traps": 2, "winners": 1, "by_hand": 1}
    assert r["totals"] == totals
    v = {x["verdict"]: x for x in r["verdicts"]}
    assert (v["TRANH"]["traps"]["k"], v["TRANH"]["traps"]["n"], v["TRANH"]["winners"]) == (1, 2, 1)
    assert v["KHONG_THAY_CO"]["traps"]["pct"] == 0.5 and v["KHONG_THAY_CO"]["risk_mean"] == 0.7
    dev = next(f for f in r["filters"] if f["id"] == "SH-DEV-1")
    assert (dev["traps"]["k"], dev["traps"]["n"], dev["winners"]) == (1, 2, 1) and dev["pool"]["n"] == 30
    cell = next(b for b in r["bands"] if b["band"] == "13-30" and b["D"] == 120)
    assert cell["traps"]["n"] == 4 and (cell["pool"]["n"], cell["pool"]["k"]) == BASE["13-30"][120]
    assert [x["mint"] for x in r["missed"]["rows"]] == ["c"]
    assert [x["mint"] for x in r["false_alarms"]["rows"]] == ["b"]
    assert (r["pool"]["k"], r["pool"]["n"]) == (82, 206)


def test_an_empty_journal_reads_as_nothing_yet():
    r = report.build([], NOW, 1, pending=0)
    assert r["totals"]["settled"] == 0 and r["overall"]["pct"] is None and r["missed"]["rows"] == []
