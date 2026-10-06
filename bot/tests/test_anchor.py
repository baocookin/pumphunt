"""Decoder tests: we encode with the IDL schema and decode back, so the layout is pinned."""

import base64

from app import anchor
from app.anchor import (
    COMPLETE,
    CREATE,
    MIGRATE,
    TRADE,
    b58decode,
    b58encode,
    decode_event,
    parse_logs,
    parse_logs_notification,
)

PK_A = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
PK_B = "So11111111111111111111111111111111111111112"


def enc(schema, values: dict, disc: bytes) -> bytes:
    out = bytearray(disc)
    for name, ty in schema:
        v = values[name]
        if ty == "u64":
            out += int(v).to_bytes(8, "little")
        elif ty == "i64":
            out += int(v).to_bytes(8, "little", signed=True)
        elif ty == "bool":
            out += bytes([1 if v else 0])
        elif ty == "pubkey":
            out += b58decode(v).rjust(32, b"\0")
        elif ty == "string":
            b = v.encode()
            out += len(b).to_bytes(4, "little") + b
    return bytes(out)


def disc_for(kind: str) -> bytes:
    return next(d for d, (k, _) in anchor.DISCRIMINATORS.items() if k == kind)


def test_base58_roundtrip_and_known_vectors():
    assert b58decode("11111111111111111111111111111111") == bytes(32)
    raw = b58decode(PK_A)
    assert len(raw) == 32 and b58encode(raw) == PK_A
    assert b58encode(bytes(32)) == "1" * 32


def test_trade_event_decodes_with_units():
    vals = dict.fromkeys([n for n, _ in TRADE], 0)
    vals.update(
        mint=PK_A,
        user=PK_B,
        fee_recipient=PK_B,
        creator=PK_B,
        sol_amount=1_500_000_000,
        token_amount=25_000_000_000_000,
        is_buy=True,
        timestamp=1_700_000_000,
        virtual_sol_reserves=31_500_000_000,
        virtual_token_reserves=1_020_000_000_000_000,
        ix_name="buy",
        track_volume=True,
        mayhem_mode=False,
    )
    payload = enc(TRADE, vals, disc_for("trade")) + b"\x00" * 40  # trailing unknown fields
    ev = decode_event(payload)
    assert ev["kind"] == "trade" and ev["is_buy"] is True and ev["mint"] == PK_A
    assert ev["sol_amount_sol"] == 1.5
    assert ev["token_amount_ui"] == 25_000_000
    assert ev["virtual_sol_reserves_sol"] == 31.5
    assert ev["ix_name"] == "buy"
    assert ev["truncated"] is False


def test_create_event_truncated_prefix_still_decodes():
    vals = dict.fromkeys([n for n, _ in CREATE], 0)
    vals.update(
        name="Test",
        symbol="TST",
        uri="https://x",
        mint=PK_A,
        bonding_curve=PK_B,
        user=PK_B,
        creator=PK_B,
        timestamp=1,
        virtual_token_reserves=1_073_000_000_000_000,
        virtual_sol_reserves=30_000_000_000,
        real_token_reserves=793_100_000_000_000,
        token_total_supply=1_000_000_000_000_000,
        token_program=PK_B,
        quote_mint=PK_B,
    )
    full = enc(CREATE, vals, disc_for("create"))
    # Simulate an older program version that stopped after token_total_supply
    cut = enc(CREATE[:12], vals, disc_for("create"))
    ev = decode_event(cut)
    assert ev["kind"] == "create" and ev["truncated"] is True
    assert ev["symbol"] == "TST" and ev["virtual_sol_reserves_sol"] == 30.0
    assert ev["token_total_supply_ui"] == 1_000_000_000
    assert decode_event(full)["truncated"] is False


def test_migrate_and_complete():
    m = dict(
        user=PK_B,
        mint=PK_A,
        mint_amount=200_000_000_000_000,
        sol_amount=85_000_000_000,
        pool_migration_fee=15_000_000,
        bonding_curve=PK_B,
        timestamp=5,
        pool=PK_B,
        quote_mint=PK_B,
    )
    ev = decode_event(enc(MIGRATE, m, disc_for("migrate")))
    assert ev["kind"] == "migrate" and ev["pool"] == PK_B and ev["sol_amount_sol"] == 85.0
    assert ev["pool_migration_fee_sol"] == 0.015
    c = dict(user=PK_B, mint=PK_A, bonding_curve=PK_B, timestamp=7, quote_mint=PK_B)
    assert decode_event(enc(COMPLETE, c, disc_for("complete")))["kind"] == "complete"


def test_unknown_discriminator_ignored_and_logs_parsed():
    c = dict(user=PK_B, mint=PK_A, bonding_curve=PK_B, timestamp=7, quote_mint=PK_B)
    good = base64.b64encode(enc(COMPLETE, c, disc_for("complete"))).decode()
    junk = base64.b64encode(b"\xff" * 40).decode()
    logs = [
        "Program 6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P invoke [1]",
        "Program log: Instruction: Buy",
        f"Program data: {junk}",
        f"Program data: {good}",
        "Program data: not-base64!!",
        "Program 6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P success",
    ]
    evs = parse_logs(logs)
    assert [e["kind"] for e in evs] == ["complete"]
    assert evs[0]["raw_b64"] == good


def test_logs_notification_to_chain_events_skips_failed_tx():
    c = dict(user=PK_B, mint=PK_A, bonding_curve=PK_B, timestamp=7, quote_mint=PK_B)
    good = base64.b64encode(enc(COMPLETE, c, disc_for("complete"))).decode()
    msg = {
        "jsonrpc": "2.0",
        "method": "logsNotification",
        "params": {
            "result": {
                "context": {"slot": 123456},
                "value": {"signature": "sig", "err": None, "logs": [f"Program data: {good}"]},
            },
            "subscription": 1,
        },
    }
    evs = parse_logs_notification(msg, ts=1.0)
    assert len(evs) == 1 and evs[0].slot == 123456 and evs[0].kind == "complete"
    msg["params"]["result"]["value"]["err"] = {"InstructionError": [0, "Custom"]}
    assert parse_logs_notification(msg, ts=1.0) == []
    assert parse_logs_notification({"jsonrpc": "2.0", "id": 1, "result": 1}, ts=1.0) == []
