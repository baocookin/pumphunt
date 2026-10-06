import base64

from helpers import PK_A, PK_B, disc_for, fake_migrate_tx, fake_pubkey, migrate_event_log

from app.anchor import PUMP_PROGRAM, b58encode
from app.rpc import (
    EVENT_IX_TAG,
    PUMP_AMM,
    account_keys,
    find_migrate_ix,
    http_url_from_ws,
    migration_from_tx,
    tx_diagnostics,
)

WA = fake_pubkey(777)


class _Resp:
    status_code = 200

    def __init__(self, result):
        self._r = result

    def raise_for_status(self):
        pass

    def json(self):
        return {"jsonrpc": "2.0", "id": 1, "result": self._r}


class _Client:
    def __init__(self, result):
        self.result = result
        self.calls = []

    async def post(self, url, json):
        self.calls.append((url, json))
        return _Resp(self.result)


def test_get_signatures_request_shape_and_empty_result():
    import asyncio

    from app.rpc import SolanaRpc

    c = _Client(None)
    rpc = SolanaRpc(c, "https://rpc.example")
    assert asyncio.run(rpc.get_signatures("ADDR", limit=50, before="B", until="U")) == []
    url, body = c.calls[0]
    assert url == "https://rpc.example" and body["method"] == "getSignaturesForAddress"
    assert body["params"] == ["ADDR", {"limit": 50, "commitment": "confirmed", "before": "B", "until": "U"}]
    c.result = [{"signature": "s1", "err": None, "blockTime": 5}]
    assert asyncio.run(rpc.get_signatures("ADDR"))[0]["signature"] == "s1"
    assert c.calls[-1][1]["params"][1] == {"limit": 1000, "commitment": "confirmed"}
    # getTransaction must accept every transaction version, v1 included
    c.result = {"slot": 1}
    assert asyncio.run(rpc.get_transaction("SIG")) == {"slot": 1}
    assert c.calls[-1][1]["params"] == [
        "SIG",
        {"encoding": "json", "commitment": "confirmed", "maxSupportedTransactionVersion": 255},
    ]


def test_http_url_from_ws():
    assert (
        http_url_from_ws("wss://mainnet.helius-rpc.com/?api-key=k")
        == "https://mainnet.helius-rpc.com/?api-key=k"
    )
    assert http_url_from_ws("ws://localhost:8899") == "http://localhost:8899"
    assert http_url_from_ws("https://x") == "https://x"


def test_migration_from_tx_decodes_event_and_accounts():
    tx = fake_migrate_tx(PK_A, PK_B, WA, slot=42)
    info = migration_from_tx(tx)
    assert info is not None
    assert info["slot"] == 42 and info["event"]["mint"] == PK_A and info["event"]["pool"] == PK_B
    acc = info["accounts"]
    assert acc["ix"] == "migrate_v2" and acc["withdraw_authority"] == WA
    assert acc["withdraw_authority_static"] is True and acc["user_static"] is True


def test_legacy_migrate_variant_and_lookup_table_authority():
    tx = fake_migrate_tx(PK_A, PK_B, WA, variant="migrate", authority_in_lookup_table=True)
    keys, n_static = account_keys(tx)
    assert WA in keys and keys.index(WA) >= n_static
    acc = find_migrate_ix(tx)
    assert acc["ix"] == "migrate" and acc["withdraw_authority"] == WA
    assert acc["withdraw_authority_static"] is False


def test_failed_or_foreign_tx_is_ignored():
    assert migration_from_tx(None) is None
    assert migration_from_tx(fake_migrate_tx(PK_A, PK_B, WA, err={"InstructionError": [0, "Custom"]})) is None
    # neither an event nor a migrate instruction: some other pump.fun transaction
    tx = fake_migrate_tx(PK_A, PK_B, WA)
    tx["meta"]["logMessages"] = ["Program log: nothing here"]
    tx["transaction"]["message"]["instructions"] = []
    assert migration_from_tx(tx) is None
    # event present but no recognisable migrate instruction: still usable, accounts unknown
    tx = fake_migrate_tx(PK_A, PK_B, WA)
    tx["transaction"]["message"]["instructions"] = []
    info = migration_from_tx(tx)
    assert info["event"]["pool"] == PK_B and info["event"]["via"] == "log" and info["accounts"] is None


def _truncate_logs(tx):
    """What Solana returns once a chatty tx passes the 10 KB log limit: the event line is gone."""
    tx["meta"]["logMessages"] = [f"Program {PUMP_PROGRAM} invoke [1]", "Log truncated"]


def test_event_from_self_cpi_when_logs_are_truncated():
    tx = fake_migrate_tx(PK_A, PK_B, WA, slot=7)
    _truncate_logs(tx)
    payload = base64.b64decode(migrate_event_log(PK_A, PK_B)[len("Program data: ") :])
    keys = tx["transaction"]["message"]["accountKeys"]
    tx["meta"]["innerInstructions"] = [
        {
            "index": 0,
            "instructions": [
                {
                    "programIdIndex": keys.index(PUMP_PROGRAM),
                    "accounts": [0],
                    "data": b58encode(EVENT_IX_TAG + payload),
                }
            ],
        }
    ]
    info = migration_from_tx(tx)
    assert info["slot"] == 7 and info["event"]["via"] == "cpi"
    assert (
        info["event"]["mint"] == PK_A
        and info["event"]["pool"] == PK_B
        and info["event"]["sol_amount_sol"] == 85.0
    )
    assert info["accounts"]["ix"] == "migrate_v2"


def test_mint_and_pool_from_instruction_accounts_when_event_is_lost():
    tx = fake_migrate_tx(PK_A, PK_B, WA)
    _truncate_logs(tx)
    info = migration_from_tx(tx)
    acc = find_migrate_ix(tx)
    assert info["event"]["via"] == "accounts"
    assert info["event"]["mint"] == acc["base_mint"] and info["event"]["pool"] == acc["pool"]
    assert info["event"]["timestamp"] == tx["blockTime"] and "sol_amount" not in info["event"]
    assert info["accounts"]["withdraw_authority"] == WA


def test_migrate_that_created_nothing_is_a_noop_not_a_migration():
    tx = fake_migrate_tx(PK_A, PK_B, WA)
    tx["meta"]["logMessages"] = [
        f"Program {PUMP_PROGRAM} invoke [1]",
        "Program log: Instruction: MigrateV2",
        "Program log: Bonding curve already migrated",
        f"Program {PUMP_PROGRAM} success",
    ]
    tx["meta"]["innerInstructions"] = []
    info = migration_from_tx(tx)
    assert info["noop"] is True and info["event"] is None and info["accounts"]["ix"] == "migrate_v2"
    d = tx_diagnostics(tx)
    assert d["already_migrated_log"] is True and d["creates_pool"] is False
    # a decoded event always wins, pool CPI or not (the event itself proves the migration)
    tx2 = fake_migrate_tx(PK_A, PK_B, WA)
    tx2["meta"]["innerInstructions"] = []
    assert migration_from_tx(tx2)["event"]["via"] == "log"


def test_rpc_client_paces_requests_and_backs_off_on_429():
    import asyncio
    import contextlib
    import time

    import httpx

    from app.rpc import SolanaRpc

    class Resp:
        def __init__(self, status):
            self.status_code = status

        def raise_for_status(self):
            if self.status_code >= 400:
                req = httpx.Request("POST", "https://rpc.example")
                raise httpx.HTTPStatusError(
                    "x", request=req, response=httpx.Response(self.status_code, request=req)
                )

        def json(self):
            return {"result": {"ok": 1}}

    class Client:
        def __init__(self):
            # the third call is rate limited 4x: give up; the fourth meets a brief outage and gets through
            self.codes = [200, 200, 429, 429, 429, 429, 503, 200]

        async def post(self, url, json):
            return Resp(self.codes.pop(0))

    async def run():
        rpc = SolanaRpc(Client(), "https://rpc.example", rps=20, penalty_s=0.3)
        t0 = time.monotonic()
        await asyncio.gather(rpc.get_transaction("a"), rpc.get_transaction("b"))
        spaced = time.monotonic() - t0
        with contextlib.suppress(httpx.HTTPStatusError):
            await rpc.get_transaction("c")
        t1 = time.monotonic()
        await rpc.get_transaction("d")
        return spaced, time.monotonic() - t1, rpc.stats

    spaced, after_429, stats = asyncio.run(run())
    assert spaced >= 0.045  # second request waited for its slot at 20 rps
    assert after_429 >= 0.25  # the 429 penalty held the next request back
    assert {k: stats[k] for k in ("calls", "rate_limited", "unavailable", "errors")} == {
        "calls": 8,
        "rate_limited": 4,
        "unavailable": 1,
        "errors": 1,
    }
    assert stats["credits_est"] == 3  # only answered calls are metered  # 3 retries inside _call, then raised


def test_tx_diagnostics_names_what_is_there():
    assert tx_diagnostics(None) == {"found": False}
    tx = fake_migrate_tx(PK_A, PK_B, WA)
    d = tx_diagnostics(tx)
    assert d["found"] and d["log_truncated"] is False
    assert d["events"] == [{"kind": "migrate", "via": "log"}]
    assert d["log_event_discs"] == [disc_for("migrate").hex()]
    assert d["pump_ixs"][0]["name"] == "migrate_v2" and d["pump_ixs"][0]["inner"] is False
    assert d["programs"] == sorted([PUMP_PROGRAM, PUMP_AMM]) and d["n_static"] == d["n_keys"]
    _truncate_logs(tx)
    d = tx_diagnostics(tx)
    assert d["log_truncated"] is True and d["events"] == [] and d["log_event_discs"] == []
