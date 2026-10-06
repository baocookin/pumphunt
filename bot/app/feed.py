"""Secondary feed: PumpPortal websocket (free channels only).

Used to measure how much the chain feed and PumpPortal disagree (coverage),
not as a source of truth. `subscribeNewToken` and `subscribeMigration` are
free; we deliberately do not use the metered trade stream.
One persistent connection only — PumpPortal bans multi-connection clients.
"""

import asyncio
import json
import time
from collections.abc import AsyncIterator

import websockets

from .events import Event, parse_event
from .jsonl import JsonlWriter


class PumpPortalFeed:
    def __init__(self, url: str, api_key: str | None = None, record: JsonlWriter | None = None):
        self.url = url if not api_key else f"{url}?api-key={api_key}"
        self.record = record

    async def events(self) -> AsyncIterator[Event]:
        backoff = 1.0
        while True:
            try:
                async with websockets.connect(self.url, ping_interval=20, max_queue=4096) as ws:
                    backoff = 1.0
                    await ws.send(json.dumps({"method": "subscribeNewToken"}))
                    await ws.send(json.dumps({"method": "subscribeMigration"}))
                    async for raw in ws:
                        ts = time.time()
                        msg = json.loads(raw)
                        if self.record:
                            self.record.write({"ts": ts, "src": "portal", "msg": msg})
                        ev = parse_event(msg, ts)
                        if ev:
                            yield ev
            except (TimeoutError, websockets.ConnectionClosed, OSError) as exc:
                print(f"[portal] disconnected: {exc}; reconnecting in {backoff:.0f}s")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)
