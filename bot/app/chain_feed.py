"""Primary data source: Solana RPC `logsSubscribe`.

Why not PumpPortal as primary: its stream has no slot number and is known to
drop events (see docs/RESEARCH.md). The RPC log stream is free on any provider,
carries the slot, and decodes to the same events.

`logsSubscribe` accepts exactly one `mentions` address per subscription, so we
open one subscription per address on a single connection. Subscribing to the
migration authority alone costs a few MB/day; the whole pump.fun program is a
firehose (see Settings.chain_scope).
"""

import asyncio
import json
import time
from collections.abc import AsyncIterator

import websockets

from .anchor import ChainEvent, parse_logs_notification


class SolanaLogsFeed:
    def __init__(self, ws_url: str, mentions: list[str], commitment: str = "confirmed"):
        if not mentions:
            raise ValueError("at least one address to watch is required")
        self.ws_url = ws_url
        self.mentions = mentions
        self.commitment = commitment

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

    async def events(self) -> AsyncIterator[ChainEvent]:
        backoff = 1.0
        while True:
            try:
                async with websockets.connect(
                    self.ws_url, ping_interval=20, max_queue=8192, max_size=8 * 1024 * 1024
                ) as ws:
                    backoff = 1.0
                    for msg in self.subscribe_messages():
                        await ws.send(msg)
                    async for raw in ws:
                        ts = time.time()
                        for ev in parse_logs_notification(json.loads(raw), ts):
                            yield ev
            except (TimeoutError, websockets.ConnectionClosed, OSError) as exc:
                print(f"[chain] disconnected: {exc}; reconnecting in {backoff:.0f}s")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)
