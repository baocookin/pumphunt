"""Primary data source: Solana RPC `logsSubscribe` on the pump.fun program.

Why not PumpPortal as primary: its stream has no slot number and is known to
drop events (see docs/RESEARCH.md). The RPC log stream is free on any provider
(Helius free tier is fine), carries the slot, and decodes to the same events.
PumpPortal stays as a *secondary* feed to measure coverage.
"""

import asyncio
import json
import time
from collections.abc import AsyncIterator

import websockets

from .anchor import PUMP_PROGRAM, ChainEvent, parse_logs_notification
from .jsonl import JsonlWriter


class SolanaLogsFeed:
    def __init__(
        self,
        ws_url: str,
        commitment: str = "confirmed",
        program: str = PUMP_PROGRAM,
        record: JsonlWriter | None = None,
    ):
        self.ws_url = ws_url
        self.commitment = commitment
        self.program = program
        self.record = record

    async def events(self) -> AsyncIterator[ChainEvent]:
        backoff = 1.0
        while True:
            try:
                async with websockets.connect(
                    self.ws_url, ping_interval=20, max_queue=8192, max_size=8 * 1024 * 1024
                ) as ws:
                    backoff = 1.0
                    await ws.send(
                        json.dumps(
                            {
                                "jsonrpc": "2.0",
                                "id": 1,
                                "method": "logsSubscribe",
                                "params": [{"mentions": [self.program]}, {"commitment": self.commitment}],
                            }
                        )
                    )
                    async for raw in ws:
                        ts = time.time()
                        msg = json.loads(raw)
                        if self.record and msg.get("method") == "logsNotification":
                            self.record.write({"ts": ts, "src": "chain", "msg": msg["params"]["result"]})
                        for ev in parse_logs_notification(msg, ts):
                            yield ev
            except (TimeoutError, websockets.ConnectionClosed, OSError) as exc:
                print(f"[chain] disconnected: {exc}; reconnecting in {backoff:.0f}s")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)
