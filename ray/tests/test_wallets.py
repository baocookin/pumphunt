import asyncio

import pytest
from helpers import Cfg, FakeRpc, Launch, TrustAll, pk, row_of

from app import native, sieve
from app.chain import MINT_AUTHORITY
from app.engine import Engine, ScoreBook
from app.features import curve_features, early_activity, early_slot
from app.wallets import WalletBook

T0 = 1_800_000_000
CREW = [pk(9_000 + i) for i in range(6)]  # wallets that buy early in launch after launch


def _launch(seed, t0, crew=CREW, others=4):
    la = Launch(seed, t0=t0)
    la.buy(la.dev, 1.0, la.s0, la.t0, in_create=True)
    for i, u in enumerate(crew):
        la.buy(u, 1.0, la.s0 + 10 + i, la.t0 + 3)
    for i in range(others):
        la.buy(pk(seed * 100 + i), 0.5, la.s0 + 20 + i, la.t0 + 6)
    return la


def _first(la):
    row = row_of(la)
    return row, int(row["trades"][-1][0])


def test_early_buyers_and_early_dumpers_are_read_up_to_the_decision():
    la = Launch(10)
    la.buy(la.dev, 1.0, la.s0, la.t0, in_create=True)
    tok = la.buy(pk(1), 1.0, la.s0 + 10, la.t0 + 3)
    la.buy(pk(2), 0.5, la.s0 + 11, la.t0 + 3)
    la.sell(pk(1), tok // 2 + 1, la.s0 + 100, la.t0 + 27)  # sold over half of its early tokens
    la.buy(pk(3), 2.0, early_slot(row_of(la)) + 5, la.t0 + 62)  # after the first 60 s
    row = row_of(la)
    early, dumpers = early_activity(row, int(row["trades"][-1][0]))
    assert set(early) == {la.dev, pk(1), pk(2)} and early[pk(1)] == pytest.approx(1.0) and dumpers == {pk(1)}
    early, dumpers = early_activity(row, la.s0 + 50)  # the sale is after this decision
    assert dumpers == set()


def test_a_launch_never_counts_itself_and_outcomes_reach_its_early_buyers():
    book = WalletBook()
    for k in range(2):
        row, dslot = _first(_launch(20 + k, T0 + 100 * k))
        assert book.note_launch(row, dslot, T0 + 100 * k + 120)
        assert not book.note_launch(row, dslot, T0 + 999)  # once per launch
        book.note_outcome(row["mint"], "trap")
    row, dslot = _first(_launch(30, T0 + 300))
    f = book.features(row, dslot)
    # the crew were early in 2 earlier launches, both traps; 6 of 11 early buyers, 6 of 9 SOL
    assert f["n_early"] == 11 and f["serial_share"] == pytest.approx(6 / 11)
    assert f["serial_vol"] == pytest.approx(6 / 9) and f["trapw_vol"] == pytest.approx(6 / 9)
    book.note_launch(row, dslot, T0 + 420)
    book.note_outcome(row["mint"], "winner")
    assert book.features(row, dslot) == f  # scored again at 5 minutes: its own record taken out
    assert book.wallets[CREW[0]][:4] == [3, 0, 3, 2]


def test_the_dev_s_earlier_launches_are_counted():
    book = WalletBook()
    dev = pk(77)
    for k in range(3):
        row, dslot = _first(_launch(40 + k, T0 + 100 * k, crew=[]))
        row["dev"] = dev
        f = book.features(row, dslot)
        assert f["dev_prior"] == k
        book.note_launch(row, dslot, T0 + 100 * k + 120)
        book.note_outcome(row["mint"], "trap" if k == 0 else "neutral")
    assert f["dev_traps"] == 0.5


def test_the_memory_is_saved_pruned_and_rebuilt_the_same(tmp_path):
    book = WalletBook()
    rows, outcomes = [], []
    for k in range(3):
        la = _launch(50 + k, T0 + 100 * k)
        row, dslot = _first(la)
        at = T0 + 100 * k + 120
        book.note_launch(row, dslot, at)
        row["scored"] = {"D120": {"at": at, "slot": dslot}}
        rows.append(row)
        o = {"mint": row["mint"], "D": 120, "status": "ok", "entry_at": at, "due": at + 1800}
        outcomes.append({**o, "label": "trap"})
    for o in outcomes:
        book.note_outcome(o["mint"], o["label"])
    again = WalletBook.rebuild(iter(rows), outcomes)
    assert again.wallets == book.wallets and again.devs == book.devs
    book.save(tmp_path / "w.json.gz")
    loaded = WalletBook.load(tmp_path / "w.json.gz")
    assert loaded.wallets == book.wallets and loaded.launches.keys() == book.launches.keys()
    assert WalletBook.load(tmp_path / "missing.json.gz") is None
    one_shots = sum(1 for w in book.wallets.values() if w[0] == 1)
    assert book.prune(T0 + 2 * 86_400) == one_shots and all(w[0] >= 2 for w in book.wallets.values())


def test_the_native_filter_is_frozen_and_reads_the_memory():
    assert native.check_frozen() == [] and "RAY-SERIAL-v1" in native.IDS
    flags = native.evaluate({"n_early": 10, "serial_vol": 0.6})
    assert flags[0]["fired"] and flags[0]["tier"] == "shadow" and flags[0]["raw_text"] == "60.0%"
    assert not native.evaluate({"n_early": 0, "serial_vol": 0.9})[0]["scored"]
    assert not native.evaluate(None)[0]["fired"]


def test_a_crowded_curve_fires_ray_crowd():
    la = Launch(60)
    la.buy(la.dev, 2.0, la.s0, la.t0, in_create=True)
    for i in range(110):  # 110 wallets in the last 110 slots (~30 s)
        la.buy(pk(20_000 + i), 0.05, la.s0 + 600 + i, la.t0 + 165 + i // 4)
    row = row_of(la)
    dslot = int(row["trades"][-1][0])
    sc = sieve.score_row(row, dslot, (la.vs, la.vt), D=300, age_s=305, now=la.t0 + 305, data={})
    flag = next(f for f in sc["shadow"] if f["id"] == "RAY-CROWD-v1")
    assert flag["fired"] and flag["raw"] == 110
    cand = sieve.FL.Cand(row, dslot, None, entry=(float(la.vs), float(la.vt)))
    f = curve_features(cand)
    assert f["wallets120"] == 110 and f["n120"] == 110 and f["per_wallet120"] == 1.0


def test_a_curve_at_its_peak_fires_ray_peak():
    la = Launch(65)
    la.buy(la.dev, 2.0, la.s0, la.t0, in_create=True)
    for i in range(12):
        la.buy(pk(40_000 + i), 1.5, la.s0 + 50 + 20 * i, la.t0 + 15 + 5 * i)
    row = row_of(la)
    dslot = int(row["trades"][-1][0])
    sc = sieve.score_row(row, dslot, (la.vs, la.vt), D=120, age_s=125, now=la.t0 + 125, data={})
    peak = next(f for f in sc["shadow"] if f["id"] == "RAY-PEAK-v1")
    assert peak["fired"] and peak["raw"] == pytest.approx(0.0)
    tok = la.buy(pk(40_100), 1.0, la.s0 + 400, la.t0 + 110)
    la.sell(pk(40_100), tok, la.s0 + 401, la.t0 + 111)
    la.sell(pk(40_000), la.vt // 40, la.s0 + 402, la.t0 + 112)
    row = row_of(la)
    dslot = int(row["trades"][-1][0])
    sc = sieve.score_row(row, dslot, (la.vs, la.vt), D=120, age_s=125, now=la.t0 + 125, data={})
    peak = next(f for f in sc["shadow"] if f["id"] == "RAY-PEAK-v1")
    assert not peak["fired"] and peak["raw"] > 0.04


def test_the_engine_scores_with_the_memory_and_remembers_the_launch(tmp_path):
    la = _launch(70, T0)
    for i in range(30):  # enough activity to pass the F0 gate
        la.buy(pk(30_000 + i), 0.3, la.s0 + 300 + 3 * i, la.t0 + 90 + i)
    rpc = FakeRpc()
    rpc.add(la)
    rpc.history[MINT_AUTHORITY] = [la.create_tx]
    rpc.slot = la.s0 + 500
    clock = type("C", (), {"t": T0 + 30, "__call__": lambda self: self.t})()
    eng = Engine(Cfg(), rpc, ScoreBook(tmp_path), clock=clock)
    eng.rules = TrustAll()
    for u in CREW:  # the crew were early in two earlier launches
        eng.wallets.wallets[u] = [2, 1, 0, 0, T0 - 100]
    asyncio.run(eng.census_once())
    clock.t = T0 + 121
    asyncio.run(eng.poll_once())
    _, _, mint, D, anchor = eng.queue.get_nowait()
    tok = eng.tracker.get(mint)
    sc = asyncio.run(eng.score_token(tok, D, anchor=anchor))
    assert sc["features"]["serial_vol"] > 0.5 and sc["features"]["dumper_share"] > 0
    serial = next(f for f in sc["shadow"] if f["id"] == "RAY-SERIAL-v1")
    assert serial["fired"] and serial["deciding"] and serial["label"] in sc["summary"]
    assert mint in eng.wallets.launches and eng.wallets.wallets[CREW[0]][0] == 3
    eng._outcome(sc, {"status": "ok", "label": "trap", "net": -0.7})
    assert eng.wallets.wallets[CREW[0]][2:4] == [1, 1]


def test_a_restart_loads_the_memory_and_the_outcomes_settled_since(tmp_path):
    book = WalletBook()
    row, dslot = _first(_launch(80, T0))
    book.note_launch(row, dslot, T0 + 120)
    sb = ScoreBook(tmp_path)
    book.save(sb.dir / "wallets.json.gz")
    # settled after the file was saved (the app stopped before its next save)
    sb.add_outcome({"mint": row["mint"], "D": 120, "status": "ok", "label": "trap", "entry_at": T0 + 120})
    eng = Engine(Cfg(), FakeRpc(), sb, clock=lambda: T0 + 2_000)
    assert asyncio.run(eng.load_wallets()) == len(book)
    assert eng.wallets.launches[row["mint"]]["label"] == "trap"
    assert eng.wallets.wallets[CREW[0]][2:4] == [1, 1]
    # no file: rebuilt from the row archive and the journal
    (sb.dir / "wallets.json.gz").unlink()
    row["scored"] = {"D120": {"at": T0 + 120, "slot": dslot}}
    sb.add_row(row, T0 + 120)
    eng = Engine(Cfg(), FakeRpc(), sb, clock=lambda: T0 + 2_000)
    asyncio.run(eng.load_wallets())
    assert eng.wallets.launches[row["mint"]]["label"] == "trap"
    assert eng.wallets.wallets.keys() == book.wallets.keys() and eng.wallets.wallets[CREW[0]][2:4] == [1, 1]
