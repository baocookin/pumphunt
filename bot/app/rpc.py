"""Solana JSON-RPC over HTTP: confirm a migration by signature and learn the fixed accounts.

PumpPortal hands us the migration's signature. One `getTransaction` (1 credit on
Helius) gives the slot, the full logs (so the CompletePumpAmmMigrationEvent with
the pool address decodes exactly like the websocket path) and the account list
of the `migrate` / `migrate_v2` instruction. The IDL does not pin
`withdraw_authority` to a fixed address, so we read it from real transactions
instead of guessing; the recorder re-subscribes the websocket feed to it.
"""

from typing import Any

import httpx

from .anchor import PUMP_PROGRAM, b58decode, parse_logs

# Account order copied from pump-fun/pump-public-docs idl/pump.json.
_MIGRATE_ACCOUNTS = [
    "global",
    "withdraw_authority",
    "mint",
    "bonding_curve",
    "associated_bonding_curve",
    "user",
    "system_program",
    "token_program",
    "pump_amm",
    "pool",
    "pool_authority",
    "pool_authority_mint_account",
    "pool_authority_wsol_account",
    "amm_global_config",
    "wsol_mint",
    "lp_mint",
    "user_pool_token_account",
    "pool_base_token_account",
    "pool_quote_token_account",
    "token_2022_program",
    "associated_token_program",
    "pump_amm_event_authority",
    "event_authority",
    "program",
    "rent",
]
_MIGRATE_V2_ACCOUNTS = [
    "global",
    "withdraw_authority",
    "base_mint",
    "quote_mint",
    "bonding_curve",
    "associated_base_bonding_curve",
    "associated_quote_bonding_curve",
    "user",
    "system_program",
    "pump_amm",
    "pool",
    "pool_authority",
    "pool_authority_mint_account",
    "pool_authority_quote_account",
    "amm_global_config",
    "lp_mint",
    "user_pool_token_account",
    "pool_base_token_account",
    "pool_quote_token_account",
    "base_token_program",
    "quote_token_program",
    "token_2022_program",
    "associated_token_program",
    "pump_amm_event_authority",
    "rent",
    "event_authority",
    "program",
]
MIGRATE_IX: dict[bytes, tuple[str, list[str]]] = {
    bytes([155, 234, 231, 146, 236, 158, 162, 30]): ("migrate", _MIGRATE_ACCOUNTS),
    bytes([187, 203, 18, 31, 206, 237, 254, 41]): ("migrate_v2", _MIGRATE_V2_ACCOUNTS),
}


def http_url_from_ws(ws_url: str) -> str:
    if ws_url.startswith("wss://"):
        return "https://" + ws_url[len("wss://") :]
    if ws_url.startswith("ws://"):
        return "http://" + ws_url[len("ws://") :]
    return ws_url


class SolanaRpc:
    def __init__(self, client: httpx.AsyncClient, url: str):
        self.c = client
        self.url = url

    async def get_transaction(self, signature: str) -> dict[str, Any] | None:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTransaction",
            "params": [
                signature,
                {"encoding": "json", "commitment": "confirmed", "maxSupportedTransactionVersion": 0},
            ],
        }
        r = await self.c.post(self.url, json=payload)
        r.raise_for_status()
        return r.json().get("result")


def account_keys(tx: dict[str, Any]) -> tuple[list[str], int]:
    """All account keys (static first, then address-table loaded) and the static count."""
    msg = tx["transaction"]["message"]
    static = [k if isinstance(k, str) else k.get("pubkey") for k in msg.get("accountKeys", [])]
    loaded = (tx.get("meta") or {}).get("loadedAddresses") or {}
    return static + list(loaded.get("writable") or []) + list(loaded.get("readonly") or []), len(static)


def find_migrate_ix(tx: dict[str, Any]) -> dict[str, Any] | None:
    """IDL account name -> pubkey for the migrate instruction in this tx (top-level or inner)."""
    keys, n_static = account_keys(tx)
    msg = tx["transaction"]["message"]
    candidates = list(msg.get("instructions") or [])
    for inner in (tx.get("meta") or {}).get("innerInstructions") or []:
        candidates.extend(inner.get("instructions") or [])
    for ix in candidates:
        pidx = ix.get("programIdIndex", -1)
        if not (0 <= pidx < len(keys)) or keys[pidx] != PUMP_PROGRAM:
            continue
        try:
            data = b58decode(ix.get("data", ""))
        except ValueError:
            continue
        hit = MIGRATE_IX.get(data[:8])
        if hit is None:
            continue
        name, names = hit
        idxs = ix.get("accounts") or []
        out: dict[str, Any] = {"ix": name}
        for nm, i in zip(names, idxs, strict=False):
            out[nm] = keys[i] if i < len(keys) else None
        # logsSubscribe `mentions` only matches static keys; an authority loaded via an
        # address lookup table cannot be subscribed to.
        out["withdraw_authority_static"] = len(idxs) > 1 and idxs[1] < n_static
        return out
    return None


def migration_from_tx(tx: dict[str, Any] | None) -> dict[str, Any] | None:
    """Decoded migrate event + slot + instruction accounts, or None if not a successful migrate tx."""
    if not tx or (tx.get("meta") or {}).get("err"):
        return None
    events = parse_logs((tx.get("meta") or {}).get("logMessages") or [])
    ev = next((e for e in events if e["kind"] == "migrate"), None)
    if ev is None:
        return None
    return {
        "event": ev,
        "slot": tx.get("slot"),
        "block_time": tx.get("blockTime"),
        "accounts": find_migrate_ix(tx),
    }
