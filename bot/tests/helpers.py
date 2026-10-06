"""Shared test helpers: encode pump.fun events the way the program does, build fake RPC responses."""

import base64

from app import anchor
from app.anchor import PUMP_PROGRAM, b58decode, b58encode
from app.rpc import MIGRATE_IX, PUMP_AMM

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


def migrate_event_log(mint: str, pool: str, sol_lamports: int = 85_000_000_000, ts: int = 5) -> str:
    vals = dict(
        user=PK_B,
        mint=mint,
        mint_amount=200_000_000_000_000,
        sol_amount=sol_lamports,
        pool_migration_fee=15_000_000,
        bonding_curve=PK_B,
        timestamp=ts,
        pool=pool,
        quote_mint=PK_B,
    )
    return "Program data: " + base64.b64encode(enc(anchor.MIGRATE, vals, disc_for("migrate"))).decode()


def fake_pubkey(seed: int) -> str:
    return b58encode(seed.to_bytes(32, "big"))


def fake_migrate_tx(
    mint: str,
    pool: str,
    withdraw_authority: str,
    slot: int = 123_456,
    variant: str = "migrate_v2",
    authority_in_lookup_table: bool = False,
    err=None,
) -> dict:
    """A getTransaction(json) result with one migrate instruction and its event in the logs."""
    disc = next(d for d, (name, _) in MIGRATE_IX.items() if name == variant)
    names = next(acc for d, (name, acc) in MIGRATE_IX.items() if name == variant)
    # static keys: user, global, (authority), ..., pump program last
    keys = [fake_pubkey(1), fake_pubkey(2)]
    loaded_readonly = []
    if authority_in_lookup_table:
        loaded_readonly.append(withdraw_authority)
    else:
        keys.append(withdraw_authority)
    while len(keys) < len(names):
        keys.append(fake_pubkey(100 + len(keys)))
    keys.append(PUMP_PROGRAM)
    keys.append(PUMP_AMM)
    all_keys = keys + loaded_readonly
    # instruction account indexes follow the IDL order; index 1 must be the withdraw authority
    idx_of = {k: i for i, k in enumerate(all_keys)}
    acct_idx = [1, idx_of[withdraw_authority]] + [
        i for i in range(2, len(names)) if all_keys[i] != withdraw_authority
    ]
    acct_idx = acct_idx[: len(names)]
    return {
        "slot": slot,
        "blockTime": 1_700_000_000,
        "meta": {
            "err": err,
            "logMessages": [
                f"Program {PUMP_PROGRAM} invoke [1]",
                "Program log: Instruction: MigrateV2",
                migrate_event_log(mint, pool),
                f"Program {PUMP_PROGRAM} success",
            ],
            "loadedAddresses": {"writable": [], "readonly": loaded_readonly},
            # the pool creation CPI into PumpSwap that every real migrate carries
            "innerInstructions": [
                {
                    "index": 0,
                    "instructions": [{"programIdIndex": keys.index(PUMP_AMM), "accounts": [], "data": ""}],
                }
            ],
        },
        "transaction": {
            "message": {
                "accountKeys": keys,
                "instructions": [
                    {
                        "programIdIndex": keys.index(PUMP_PROGRAM),
                        "accounts": acct_idx,
                        "data": b58encode(disc),
                    }
                ],
            }
        },
    }
