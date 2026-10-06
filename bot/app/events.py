"""Typed view over PumpPortal websocket messages (secondary feed).

Unknown/missing fields default to 0 so a schema drift on PumpPortal's side
degrades gracefully instead of crashing the recorder. Migration messages have
no stable documented schema, so we only rely on `txType`/`mint`.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Event:
    ts: float
    tx_type: str  # "create" | "buy" | "sell" | "migrate" | other
    mint: str
    trader: str
    signature: str
    sol_amount: float
    token_amount: float
    v_sol: float
    v_tokens: float
    market_cap_sol: float
    pool: str = "pump"
    name: str = ""
    symbol: str = ""
    uri: str = ""
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def is_create(self) -> bool:
        return self.tx_type == "create"

    @property
    def is_migration(self) -> bool:
        return self.tx_type in ("migrate", "migration")


def _f(d: dict[str, Any], key: str) -> float:
    v = d.get(key)
    try:
        return float(v) if v is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def parse_event(msg: dict[str, Any], ts: float) -> Event | None:
    tx_type = msg.get("txType")
    mint = msg.get("mint")
    if not tx_type or not mint:
        return None
    return Event(
        ts=ts,
        tx_type=str(tx_type),
        mint=str(mint),
        trader=str(msg.get("traderPublicKey", "")),
        signature=str(msg.get("signature", "")),
        sol_amount=_f(msg, "solAmount"),
        token_amount=_f(msg, "tokenAmount") or _f(msg, "initialBuy"),
        v_sol=_f(msg, "vSolInBondingCurve"),
        v_tokens=_f(msg, "vTokensInBondingCurve"),
        market_cap_sol=_f(msg, "marketCapSol"),
        pool=str(msg.get("pool", "pump")),
        name=str(msg.get("name", "")),
        symbol=str(msg.get("symbol", "")),
        uri=str(msg.get("uri", "")),
        raw=msg,
    )
