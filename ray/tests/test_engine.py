import asyncio

import pytest
from helpers import Cfg, FakeRpc, Launch, pk

from app.chain import MINT_AUTHORITY
from app.engine import Engine, OnDemandLimit, ScoreBook
from app.rpc import CreditMeter

T0 = 1_800_000_000


class Clock:
    def __init__(self, t: float):
        self.t = t

    def __call__(self) -> float:
        return self.t


def run(coro):
    return asyncio.run(coro)


def _crowd(la: Launch, n: int, start_slot: int):
    sizes = (0.21, 0.33, 0.27, 0.38, 0.23, 0.41, 0.29)
    for i in range(n):
        la.buy(
            pk(2_000 + la.s0 % 97 + i), sizes[i % len(sizes)], start_slot + 3 * i, la.t0 + 10 + (3 * i) // 4
        )


def _setup(tmp_path, dev_sol=5.0, crowd=30, at=30, **cfg):
    la = Launch(700, t0=T0)
    la.buy(la.dev, dev_sol, la.s0, la.t0, in_create=True)
    _crowd(la, crowd, la.s0 + 30)
    rpc = FakeRpc()
    rpc.add(la)
    rpc.history[MINT_AUTHORITY] = [la.create_tx]
    rpc.slot = la.s0 + 400
    clock = Clock(T0 + at)
    eng = Engine(Cfg(**cfg), rpc, ScoreBook(tmp_path), clock=clock)
    return la, rpc, clock, eng


def _drain(eng: Engine):
    """Score what the decision times queued, as a worker would."""
    out = []
    while not eng.queue.empty():
        _, _, mint, D, anchor = eng.queue.get_nowait()
        tok = eng.tracker.get(mint)
        sc = run(eng.score_token(tok, D, anchor=anchor))
        eng._settled(tok)
        eng._record(tok, sc)
        out.append(sc)
    return out


def test_a_launch_is_found_read_and_scored_at_its_decision_time(tmp_path):
    la, rpc, clock, eng = _setup(tmp_path)
    assert run(eng.census_once()) == 1
    tok = eng.tracker.get(la.mint)
    run(eng.poll_once())
    assert tok.state["real"] == pytest.approx(la.real)
    assert eng.queue.empty() and not tok.done  # 30 s old: no decision time yet
    clock.t = T0 + 121
    run(eng.poll_once())
    assert tok.done == {120: "score"}
    scores = _drain(eng)
    assert len(scores) == 1
    sc = scores[0]
    assert sc["D"] == 120 and sc["key"] == "D120" and sc["verdict"] == "TRANH"
    assert sc["data"]["synced"] and sc["data"]["chain_ok"]
    assert eng.book.recent[0]["mint"] == la.mint
    assert list((tmp_path / "ray").glob("scores-*.jsonl"))
    # the five- and ten-minute reads only ask for what is new, the last one after the launch retired
    for D in (300, 600):
        calls = len(rpc.calls)
        clock.t = T0 + D + 1
        run(eng.poll_once())
        _drain(eng)
        assert len([c for c in rpc.calls[calls:] if c == ("gtfa", la.curve)]) == 1
    assert tok.scores.keys() == {"D120", "D300", "D600"}
    assert la.mint not in eng.tracker.live and tok.history is None and tok.pending == 0


def test_a_launch_found_late_misses_the_decision_times_it_passed(tmp_path):
    la, rpc, clock, eng = _setup(tmp_path, at=200)
    run(eng.census_once())
    run(eng.poll_once())
    tok = eng.tracker.get(la.mint)
    assert tok.done == {120: "missed"} and eng.queue.empty()


def test_below_the_gate_is_recorded_without_reading_the_history(tmp_path):
    la, rpc, clock, eng = _setup(tmp_path, dev_sol=1.0, crowd=20)
    assert 5 <= la.real < 11.66
    run(eng.census_once())
    clock.t = T0 + 121
    run(eng.poll_once())
    tok = eng.tracker.get(la.mint)
    assert tok.done == {120: "below_gate"} and eng.queue.empty()
    assert tok.scores["D120"]["verdict"] == "DUOI_CONG"
    assert not [c for c in rpc.calls if c == ("gtfa", la.curve)]


def test_a_score_is_anchored_on_the_read_that_reached_its_decision_time(tmp_path):
    la, rpc, clock, eng = _setup(tmp_path)
    run(eng.census_once())
    clock.t = T0 + 121
    run(eng.poll_once())
    decided_slot, decided_real = rpc.slot, la.real
    for i in range(5):  # the curve moves on before a worker gets to it
        la.buy(pk(9_000 + i), 1.0, rpc.slot + 10 + i, T0 + 124)
    rpc.slot += 50
    clock.t = T0 + 126
    run(eng.poll_once())
    assert eng.tracker.get(la.mint).state["real"] > decided_real
    sc = _drain(eng)[0]
    assert sc["data"]["synced"] and sc["slot"] == decided_slot
    assert sc["real"] == pytest.approx(decided_real, abs=1e-4) and sc["age_s"] == 121


def test_the_score_waits_for_the_index_to_reach_the_decision_read(tmp_path):
    la, rpc, clock, eng = _setup(tmp_path)
    rpc.hidden_after[la.curve] = T0 + 15  # the index has not caught up with the last trades yet
    rpc.reveal_after[la.curve] = 1  # ... and has on the next read
    run(eng.census_once())
    clock.t = T0 + 121
    run(eng.poll_once())
    sc = _drain(eng)[0]
    assert sc["data"]["synced"] and sc["data"]["reads"] == 2 and sc["slot"] == rpc.slot
    assert sc["verdict"] == "TRANH" and eng.stats["unsynced"] == 0


def test_an_index_that_never_catches_up_is_scored_up_to_its_last_trade(tmp_path):
    la, rpc, clock, eng = _setup(tmp_path)
    rpc.hidden_after[la.curve] = T0 + 15
    run(eng.census_once())
    clock.t = T0 + 121
    run(eng.poll_once())
    sc = _drain(eng)[0]
    assert not sc["data"]["synced"] and eng.stats["unsynced"] == 1
    assert sc["data"]["reads"] == 1 + len(eng.cfg.sync_waits_s) and sc["slot"] < rpc.slot
    assert sc["data"]["lag_s"] > 100  # the last trade read is from T0 + 15, the decision read T0 + 121


def test_any_mint_can_be_scored_now_within_the_hourly_allowance(tmp_path):
    la, rpc, clock, eng = _setup(tmp_path, ondemand_per_hour=1, at=150)
    sc = run(eng.score_mint(la.mint))
    assert sc["key"] == "now" and sc["D"] is None and sc["verdict"] == "TRANH"
    assert eng.tracker.get(la.mint) is not None
    with pytest.raises(OnDemandLimit):
        run(eng.score_mint(la.mint))


def test_an_unknown_mint_is_not_found(tmp_path):
    la, rpc, clock, eng = _setup(tmp_path)
    with pytest.raises(LookupError):
        run(eng.score_mint(pk(999_999)))


def test_the_credit_cap_stops_scoring_reads_before_the_cheap_ones():
    clock = Clock(T0)
    m = CreditMeter(100, clock=clock)
    m.add(100, "history")
    assert not m.allows("history") and not m.allows("ondemand")
    assert m.allows("poll") and m.allows("census")
    m.add(30, "poll")
    assert not m.allows("poll")
    clock.t = T0 + 86_400  # a new UTC day
    assert m.allows("history") and m.snapshot()["spent"] == 0


def test_the_score_book_comes_back_after_a_restart(tmp_path):
    la, rpc, clock, eng = _setup(tmp_path)
    run(eng.census_once())
    clock.t = T0 + 121
    run(eng.poll_once())
    _drain(eng)
    book = ScoreBook(tmp_path)
    assert book.load(T0 + 130) == 1 and book.latest[la.mint]["verdict"] == "TRANH"


def test_the_latest_score_per_mint_is_bounded(tmp_path):
    book = ScoreBook(tmp_path, keep=2)
    for i in range(3):
        book.add({"mint": f"m{i}", "at": T0 + i, "verdict": "TRANH"})
    assert list(book.latest) == ["m1", "m2"] and len(book.recent) == 2


def test_the_day_s_credit_count_survives_a_restart(tmp_path):
    la, rpc, clock, eng = _setup(tmp_path)
    run(eng.census_once())
    spent = rpc.meter.snapshot()["spent"]
    assert spent > 0
    rpc2 = FakeRpc()
    Engine(Cfg(), rpc2, ScoreBook(tmp_path), clock=clock)
    assert rpc2.meter.snapshot()["spent"] == spent


def test_a_graduated_curve_shows_its_peak_not_the_emptied_account(tmp_path):
    la, rpc, clock, eng = _setup(tmp_path)
    run(eng.census_once())
    run(eng.poll_once())
    peak = la.real
    la.complete, la.vs, la.vt = True, 0, 0  # migrated: reserves moved to the AMM pool
    clock.t = T0 + 121
    run(eng.poll_once())
    tok = eng.tracker.get(la.mint)
    sc = tok.scores["D120"]
    assert tok.done == {120: "graduated"} and sc["verdict"] == "DA_TOT_NGHIEP"
    assert sc["real"] == pytest.approx(peak, abs=1e-4) and sc["floor"] is None
