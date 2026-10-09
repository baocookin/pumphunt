import base64

from helpers import V_TOK0, Launch, pk

from app import chain


def test_a_create_reads_as_the_census_header():
    la = Launch(10)
    create = chain.create_of(la.create_tx)
    info = chain.launch_info(create, la.create_tx, chain.signature_of(la.create_tx))
    assert info["mint"] == la.mint and info["curve"] == la.curve and info["dev"] == la.dev
    assert info["create_ts"] == la.t0 and info["create_slot"] == la.s0
    assert info["v_sol0"] == 30_000_000_000 and info["v_tokens0"] == V_TOK0
    assert chain.classic_sol(info)
    mayhem = Launch(20, mayhem=True)
    m = chain.launch_info(chain.create_of(mayhem.create_tx), mayhem.create_tx, "s")
    assert not chain.classic_sol(m)


def test_trades_come_out_in_chain_order_and_their_reserves_chain():
    la = Launch(30)
    la.buy(la.dev, 1.0, la.s0, la.t0, in_create=True)
    la.buy(pk(101), 0.7, la.s0 + 3, la.t0 + 1, idx=2)
    la.buy(pk(100), 0.5, la.s0 + 3, la.t0 + 1, idx=7)
    tok = la.buy(pk(102), 2.0, la.s0 + 9, la.t0 + 3)
    la.sell(pk(102), tok // 2, la.s0 + 12, la.t0 + 4)
    # the index hands transactions back in any order within a second
    shuffled = [la.txs[0], la.txs[2], la.txs[1], la.txs[4], la.txs[3]]
    path = chain.curve_trades(shuffled, la.mint)
    trades = path["trades"]
    chain.chain_order(trades)
    assert [t[4] for t in trades] == [la.dev, pk(101), pk(100), pk(102), pk(102)]
    assert chain.chain_breaks(trades, V_TOK0) == 0
    assert dict(path["fees"]) == {125: 5}
    # a trade missing from the read breaks the chain
    assert chain.chain_breaks(trades[:2] + trades[3:], V_TOK0) == 1


def test_a_transaction_without_an_index_gets_a_stand_in_and_is_counted():
    la = Launch(40)
    la.buy(pk(200), 1.0, la.s0 + 2, la.t0 + 1, idx=None)
    path = chain.curve_trades(la.txs, la.mint)
    assert path["synthetic_tx_index"] == 1
    assert path["trades"][0][1] >= chain.SYNTH_TX


def test_a_curve_account_parses_and_anything_else_does_not():
    la = Launch(50)
    la.buy(pk(300), 3.0, la.s0 + 1, la.t0 + 1)
    acc = chain.parse_curve_account(la.account())
    assert acc["v_sol"] == la.vs and acc["v_tokens"] == la.vt and acc["complete"] is False
    assert acc["creator"] == la.dev
    bad = la.account()
    bad["data"][0] = "AAAA" + bad["data"][0][4:]
    assert chain.parse_curve_account(bad) is None
    assert chain.parse_curve_account(None) is None


def test_events_mirrored_by_self_cpi_are_read_once():
    la = Launch(60)
    la.buy(pk(400), 1.0, la.s0 + 1, la.t0 + 1)
    tx = la.txs[-1]
    raw = base64.b64decode(tx["meta"]["logMessages"][0][len("Program data: ") :])
    keys = tx["transaction"]["message"]["accountKeys"]
    tx["meta"]["innerInstructions"] = [
        {
            "index": 0,
            "instructions": [
                {
                    "programIdIndex": keys.index(chain.PUMP_PROGRAM),
                    "data": chain.b58encode(chain.EVENT_IX_TAG + raw),
                }
            ],
        }
    ]
    evs = chain.pump_events(tx)
    assert len([e for e in evs if e["kind"] == "trade"]) == 1 and evs[0]["via"] == "cpi"
