import asyncio

import pytest
from helpers import Cfg, FakeRpc, Launch, TrustAll, pk

from app.chain import MINT_AUTHORITY
from app.engine import Engine, OnDemandLimit, ScoreBook, day_of, read_jsonl
from app.outcome import HOLD_S, INDEX_WAIT_S
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
    eng.rules = TrustAll()  # the filters decide by their tiers here (tests/test_live_rules.py: the rule)
    return la, rpc, clock, eng


def _drain(eng: Engine):
    """Score what the decision times queued, as a worker would."""
    out = []
    while not eng.queue.empty():
        _, _, mint, D, anchor = eng.queue.get_nowait()
        tok = eng.tracker.get(mint)
        sc = run(eng.score_token(tok, D, anchor=anchor))
        eng._record(tok, sc)
        eng._settled(tok)
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
    # its trades up to the last decision went to the row archive, once
    rows = read_jsonl(tmp_path / "ray" / f"rows-{day_of(T0)}.jsonl.gz")
    assert [r["mint"] for r in rows] == [la.mint] and set(rows[0]["scored"]) == {"D120", "D300", "D600"}
    last = max(e["slot"] for e in rows[0]["scored"].values())
    assert rows[0]["trades"] and all(t[0] <= last for t in rows[0]["trades"])


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


def _scored_at_120(tmp_path):
    la, rpc, clock, eng = _setup(tmp_path)
    run(eng.census_once())
    clock.t = T0 + 121
    run(eng.poll_once())
    sc = _drain(eng)[0]
    assert sc["entry"]["slot"] == rpc.slot and eng.outcomes.pending() == 1
    return la, rpc, clock, eng, sc


def _dump(la: Launch, slot: int, ts: int, share: float = 0.9):
    la.sell(pk(77), int((1_073_000_000_000_000 - la.vt) * share), slot, ts)


def test_a_score_gets_its_30_minute_outcome_from_the_curve_account(tmp_path):
    la, rpc, clock, eng, sc = _scored_at_120(tmp_path)
    _dump(la, rpc.slot + 500, T0 + 400)  # the crowd's tokens sold back: a trap for the ticket
    clock.t = sc["entry"]["at"] + HOLD_S - 1
    assert run(eng.outcomes.run_once()) == 0  # not yet
    clock.t = sc["entry"]["at"] + HOLD_S + 2
    assert run(eng.outcomes.run_once()) == 1
    o = sc["outcome"]
    assert o["label"] == "trap" and o["net"] <= -0.5 and (o["how"], o["why"]) == ("account", "time")
    line = read_jsonl(tmp_path / "ray" / f"outcomes-{day_of(sc['entry']['at'])}.jsonl")[0]
    assert line["verdict"] == "TRANH" and line["fired"]["active"] == ["SH-DEV-1"] and line["label"] == "trap"
    assert line["band"] == "13-30" and eng.outcomes.pending() == 0


def test_a_curve_that_graduated_is_sold_at_its_completion(tmp_path):
    la, rpc, clock, eng, sc = _scored_at_120(tmp_path)
    la.finish(pk(88), 60.0, rpc.slot + 900, T0 + 700)
    completed = (la.vs, la.vt)
    la.migrate()
    due = sc["entry"]["at"] + HOLD_S
    clock.t = due + 1
    run(eng.outcomes.run_once())  # the account reads complete: the history is read once indexed
    assert "outcome" not in sc and eng.outcomes.pending() == 1
    clock.t = due + INDEX_WAIT_S + 1
    assert run(eng.outcomes.run_once()) == 1
    o = sc["outcome"]
    assert (o["how"], o["why"], o["label"]) == ("history", "grad", "winner")
    assert o["real_exit"] == pytest.approx((completed[0] - 30_000_000_000) / 1e9, abs=1e-4)


def test_an_outcome_a_restart_interrupted_is_read_from_the_history_at_its_due_time(tmp_path):
    la, rpc, clock, eng, sc = _scored_at_120(tmp_path)
    _dump(la, rpc.slot + 500, T0 + 400)
    due = sc["entry"]["at"] + HOLD_S
    la.buy(pk(99), 80.0, rpc.slot + 9_000, int(due) + 100)  # after the due time: not the exit
    clock.t = due + 3_600  # the app was down at the due time
    book = ScoreBook(tmp_path)
    assert book.load(clock.t) >= 1
    eng2 = Engine(Cfg(), rpc, book, clock=clock)
    assert eng2.outcomes.pending() == 1
    assert run(eng2.outcomes.run_once()) == 1
    o = book.latest[la.mint]["outcome"]
    assert (o["how"], o["why"], o["label"]) == ("history", "time", "trap")
    # settled outcomes come back with their scores and are not read again
    book3 = ScoreBook(tmp_path)
    book3.load(clock.t)
    assert book3.latest[la.mint]["outcome"]["label"] == "trap"
    assert Engine(Cfg(), rpc, book3, clock=clock).outcomes.pending() == 0
