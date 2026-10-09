import sys
from pathlib import Path

import pytest
from helpers import Launch, pk, row_of

from app.outcome import label_of, ticket_net

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "research" / "sieve"))
import journal  # noqa: E402 - the research's labels, the reference


def test_the_ticket_is_valued_as_the_research_values_it():
    la = Launch(800)
    dev_tok = la.buy(la.dev, 3.0, la.s0, la.t0, in_create=True)
    for i in range(40):
        la.buy(pk(3_000 + i), 0.4 + 0.02 * i, la.s0 + 10 + 5 * i, la.t0 + 3 + i)
    la.sell(la.dev, dev_tok, la.s0 + 260, la.t0 + 70)
    for i in range(10):
        la.buy(pk(4_000 + i), 1.5, la.s0 + 300 + 3 * i, la.t0 + 80 + i)
    p = journal.Curve(row_of(la))
    checked = 0
    for entry_slot, exit_s in ((la.s0 + 100, 30), (la.s0 + 100, 1800), (la.s0 + 250, 60), (la.s0 + 280, 20)):
        net, _, _ = journal.ticket(p, entry_slot, exit_s)
        i0 = p.last(entry_slot)
        j = max(p.last(entry_slot + round(exit_s / journal.SPS)), i0)
        mine = ticket_net((p.vs[i0], p.vt[i0]), (p.vs[j], p.vt[j]), p.fee)
        assert mine == pytest.approx(net, abs=1e-12)
        checked += 1
    assert checked == 4


def test_the_labels_are_the_research_s():
    assert (journal.TRAP_LEVEL, journal.WIN_LEVEL) == (-0.5, 1.0)
    assert [label_of(x) for x in (-0.5, -0.49, 0.99, 1.0)] == ["trap", "neutral", "neutral", "winner"]
