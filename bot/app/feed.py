"""Secondary feed: PumpPortal websocket (free channels only).

Used to measure how much the chain feed and PumpPortal disagree (coverage) and
as a fallback source of migration events. `subscribeNewToken` and
`subscribeMigration` are free; we deliberately do not use the metered trade
stream. One persistent connection only — PumpPortal bans multi-connection clients.

PumpPortal has been seen to go silent for hours with the socket still open and
answering pings, so a stale timer closes and reopens it: new tokens arrive every
few seconds, and `stale_s` of silence means the stream is dead, not quiet.
"""

import asyncio
import json
import time
from collections.abc import AsyncIterator
from typing import Any

import websockets

from .events import Event, parse_event


class PumpPortalFeed:
    def __init__(self, url: str, api_key: str | None = None, stale_s: float = 120, backoff_s: float = 1.0):
        self.url = url if not api_key else f"{url}?api-key={api_key}"
        self.stale_s = stale_s
        self.backoff_s = backoff_s
        self.stats: dict[str, Any] = {
            "connected": False,
            "connects": 0,
            "stale_reconnects": 0,
            "messages": 0,
            "last_msg_ts": 0.0,
            "last_error": None,
        }

    async def events(self) -> AsyncIterator[Event]:
        backoff = self.backoff_s
        while True:
            try:
                async with websockets.connect(self.url, ping_interval=20, max_queue=4096) as ws:
                    self.stats["connected"] = True
                    self.stats["connects"] += 1
                    backoff = self.backoff_s
                    await ws.send(json.dumps({"method": "subscribeNewToken"}))
                    await ws.send(json.dumps({"method": "subscribeMigration"}))
                    while True:
                        try:
                            raw = await asyncio.wait_for(ws.recv(), timeout=self.stale_s)
                        except TimeoutError:
                            self.stats["stale_reconnects"] += 1
                            raise TimeoutError(f"no message for {self.stale_s:.0f}s") from None
                        ts = time.time()
                        self.stats["messages"] += 1
                        self.stats["last_msg_ts"] = ts
                        ev = parse_event(json.loads(raw), ts)
                        if ev:
                            yield ev
            except (TimeoutError, websockets.ConnectionClosed, OSError) as exc:
                self.stats["last_error"] = f"{type(exc).__name__}: {exc}"
                print(f"[portal] disconnected: {exc}; reconnecting in {backoff:.0f}s")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)
            finally:
                self.stats["connected"] = False
