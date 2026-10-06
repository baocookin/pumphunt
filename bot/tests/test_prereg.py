"""Pre-registered hypotheses: who is in each sample, and what they are tested on."""

from app.prereg import C2_MAX_IDLE_S, C2_MIN_REAL_SOL, PREREG_TS, c2_member, evaluate, median_ci
from app.survivor import FILLS_VERSION

WSOL = "So11111111111111111111111111111111111111112"


def row(mint, t, net, real_sol=None, idle=None, quote=WSOL, version=FILLS_VERSION):
    r = {
        "mint": mint,
        "fills_t0": t,
        "quote_mint": quote,
        "fills_version": version,
        "fills": {"d30_h60": {"1": {"net": net}}},
    }
    if real_sol is not None:
        r["decision"] = {"d30": {"real_sol": real_sol, "last_trade_age_s": idle}}
    return r


def test_c2_needs_real_sol_and_a_recent_swap_at_the_decision_time():
    assert c2_member(row("a", 0, 0, real_sol=C2_MIN_REAL_SOL, idle=C2_MAX_IDLE_S))
    assert not c2_member(row("b", 0, 0, real_sol=C2_MIN_REAL_SOL - 0.01, idle=1))
    assert not c2_member(row("c", 0, 0, real_sol=50, idle=C2_MAX_IDLE_S + 1))
    assert not c2_member(row("d", 0, 0, real_sol=50, idle=None))  # never traded before the decision
    assert not c2_member(row("e", 0, 0))  # harvested before decision states existed


def test_only_rows_after_registration_are_confirmatory():
    rows = [row(f"old{i}", PREREG_TS - 10, 0.5, real_sol=50, idle=5) for i in range(5)]
    rows += [row(f"in{i}", PREREG_TS + i, -0.1, real_sol=50, idle=5) for i in range(3)]
    rows += [row("thin", PREREG_TS + 9, 0.9, real_sol=2, idle=5)]
    rows += [
        row(
            "usdc",
            PREREG_TS + 9,
            0.9,
            real_sol=50,
            idle=5,
            quote="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        )
    ]
    rows += [row("v1", PREREG_TS + 9, 0.9, real_sol=50, idle=5, version=1)]
    h = {x["name"]: x for x in evaluate(rows)["hypotheses"]}
    assert h["C"]["n"] == 9 and h["C*"]["n"] == 4 and h["C*"]["eligible"] == 4
    assert h["C2"]["n"] == 3 and h["C2"]["members"] == 3 and h["C2"]["median"] == -0.1
    assert h["C2"]["verdict"]["status"] == "INSUFFICIENT" and h["C2"]["since"] == PREREG_TS


def test_median_interval_is_distribution_free():
    assert median_ci([1.0] * 5) is None
    lo, hi = median_ci([float(i) for i in range(101)])
    assert lo < 50 < hi and (lo, hi) == (40.0, 60.0)
