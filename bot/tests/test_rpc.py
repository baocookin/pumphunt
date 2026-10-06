from helpers import PK_A, PK_B, fake_migrate_tx, fake_pubkey

from app.rpc import account_keys, find_migrate_ix, http_url_from_ws, migration_from_tx

WA = fake_pubkey(777)


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
    assert acc["withdraw_authority_static"] is True


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
    tx = fake_migrate_tx(PK_A, PK_B, WA)
    tx["meta"]["logMessages"] = ["Program log: nothing here"]
    assert migration_from_tx(tx) is None
    # event present but no recognisable migrate instruction: still usable, accounts unknown
    tx = fake_migrate_tx(PK_A, PK_B, WA)
    tx["transaction"]["message"]["instructions"] = []
    info = migration_from_tx(tx)
    assert info["event"]["pool"] == PK_B and info["accounts"] is None
