"""Primary data source: Solana RPC `logsSubscribe`.

Why not PumpPortal as primary: its stream has no slot number and is known to
drop events (see docs/RESEARCH.md). The RPC log stream is free on any provider,
carries the slot, and decodes to the same events.

`logsSubscribe` accepts exactly one `mentions` address per subscription, so we
open one subscription per address on a single connection. Subscribing to the
migration authority alone costs a few MB/day; the whole pump.fun program is a
firehose (see Settings.chain_scope). `set_mentions` swaps the watched addresses
at runtime (the recorder learns the real withdraw authority from confirmed
transactions) by closing the socket so the reconnect loop re-subscribes.
"""

import asyncio
import json
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any

import websockets

from .anchor import ChainEvent, parse_logs_notification


@dataclass
class ChainNotification:
    """One `logsNotification`, whether or not its logs decoded to anything.

    Solana cuts logs at 10 KB, so a chatty transaction (a migrate creates the PumpSwap
    pool through CPI) often arrives with its event line missing; the recorder then
    confirms it by signature over HTTP.
    """

    ts: float
    slot: int
    signature: str
    mention: str | None  # the watched address whose subscription delivered it
    err: Any
    kinds: list[str] = field(default_factory=list)  # event kinds decoded from the logs
    logs_truncated: bool = False


class SolanaLogsFeed:
    def __init__(self, ws_url: str, mentions: list[str], commitment: str = "confirmed"):
        if not mentions:
            raise ValueError("at least one address to watch is required")
        self.ws_url = ws_url
        self.mentions = list(mentions)
        self.commitment = commitment
        self._ws = None
        self._subs: dict[int, str] = {}  # subscription id -> watched address
        self.on_notification: Callable[[ChainNotification], None] | None = None
        self.stats: dict[str, Any] = {
            "connected": False,
            "connects": 0,
            "subscribed": 0,
            "notifications": 0,
            "events": 0,
            "last_msg_ts": 0.0,
            "last_error": None,
            "mentions": self.mentions,
        }

    def subscribe_messages(self) -> list[str]:
        return [
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": i + 1,
                    "method": "logsSubscribe",
                    "params": [{"mentions": [addr]}, {"commitment": self.commitment}],
                }
            )
            for i, addr in enumerate(self.mentions)
        ]

    async def set_mentions(self, mentions: list[str]) -> None:
        if list(mentions) == self.mentions:
            return
        self.mentions = list(mentions)
        self.stats["mentions"] = self.mentions
        self.stats["subscribed"] = 0
        self._subs = {}
        if self._ws is not None:
            await self._ws.close()  # the events() loop reconnects and re-subscribes

    def _on_message(self, msg: dict[str, Any], ts: float) -> list[ChainEvent]:
        self.stats["last_msg_ts"] = ts
        if "id" in msg and "result" in msg:
            self.stats["subscribed"] += 1
            i = int(msg["id"]) - 1
            if 0 <= i < len(self.mentions):
                self._subs[msg["result"]] = self.mentions[i]
            return []
        if msg.get("method") == "logsNotification":
            self.stats["notifications"] += 1
            evs = parse_logs_notification(msg, ts)
            self.stats["events"] += len(evs)
            if self.on_notification is not None:
                self.on_notification(self._notification(msg, ts, evs))
            return evs
        if "error" in msg:
            self.stats["last_error"] = str(msg["error"])
        return []

    def _notification(self, msg: dict[str, Any], ts: float, evs: list[ChainEvent]) -> ChainNotification:
        params = msg.get("params") or {}
        res = params.get("result") or {}
        value = res.get("value") or {}
        logs = value.get("logs") or []
        return ChainNotification(
            ts=ts,
            slot=int((res.get("context") or {}).get("slot", 0)),
            signature=str(value.get("signature", "")),
            mention=self._subs.get(params.get("subscription")),
            err=value.get("err"),
            kinds=[ev.kind for ev in evs],
            logs_truncated=any("Log truncated" in line for line in logs),
        )

    async def events(self) -> AsyncIterator[ChainEvent]:
        backoff = 1.0
        while True:
            try:
                async with websockets.connect(
                    self.ws_url, ping_interval=20, max_queue=8192, max_size=8 * 1024 * 1024
                ) as ws:
                    self._ws = ws
                    self.stats["connected"] = True
                    self.stats["connects"] += 1
                    backoff = 1.0
                    for msg in self.subscribe_messages():
                        await ws.send(msg)
                    async for raw in ws:
                        for ev in self._on_message(json.loads(raw), time.time()):
                            yield ev
            except (TimeoutError, websockets.ConnectionClosed, OSError) as exc:
                self.stats["last_error"] = f"{type(exc).__name__}: {exc}"
                print(f"[chain] disconnected: {exc}; reconnecting in {backoff:.0f}s")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)
            finally:
                self._ws = None
                self.stats["connected"] = False
