"""Optional private Telegram bot: answers in one chat only (the owner's), never anyone else.

  /score <mint>  (or a bare mint)  score that launch now
  /help                            what the verdicts mean
Pushes: the verdict codes listed in RAY_TELEGRAM_PUSH (none by default), at most one message every
two seconds and 300 a day. No message ever says "buy": the scorer only warns.
"""

import asyncio
import re
import time
from collections import deque
from typing import Any

import httpx

from .engine import OnDemandLimit
from .rpc import describe_error

MINT_RE = re.compile(r"\b([1-9A-HJ-NP-Za-km-z]{32,44})\b")
API = "https://api.telegram.org"

HELP = (
    "Rây chấm rủi ro một coin pump.fun (curve classic, quote SOL) tại thời điểm hỏi.\n"
    "Gửi /score <mint> hoặc dán mint.\n\n"
    "TRÁNH: bộ lọc chính bật, và coin mới đã xác nhận bộ lọc đó.\n"
    "CẢNH GIÁC: chỉ cờ phụ đã xác nhận bật (bằng chứng yếu hơn).\n"
    "KHÔNG THẤY CỜ: không có cờ đã xác nhận. KHÔNG phải tín hiệu mua: tỷ lệ bẫy của tầng vẫn áp dụng.\n"
    "DƯỚI CỔNG: dưới 11,66 SOL, vé 0,5 SOL không thể lỗ 50% trên curve.\n"
    "Tỷ lệ bẫy lấy từ coin mới 7 ngày qua (kết quả 30 phút sau mỗi lần chấm)."
)


def format_score(sc: dict[str, Any], link: str | None = None) -> str:
    lines = [f"{sc.get('verdict_vi')} · {sc.get('symbol') or '?'} · {sc['mint']}"]
    age = sc.get("age_s")
    real = sc.get("real")
    head = []
    if age is not None:
        head.append(f"tuổi {int(age) // 60}:{int(age) % 60:02d}")
    if real is not None:
        head.append(f"{real:.2f} SOL thật")
    if sc.get("floor") is not None:
        head.append(f"sàn lỗ trên curve {sc['floor'] * 100:.0f}%")
    if head:
        lines.append(" · ".join(head))
    rk = sc.get("risk") or {}
    if rk.get("pct") is not None:
        lo, hi = rk.get("ci") or (None, None)
        ci = f" (KTC {lo * 100:.0f}–{hi * 100:.0f}%)" if lo is not None else ""
        lines.append(f"Tỷ lệ bẫy lịch sử: {rk['pct'] * 100:.0f}%{ci}, {rk.get('basis')}, n={rk.get('n')}")
    if sc.get("summary"):
        lines.append(sc["summary"])
    for f in (sc.get("active") or []) + (sc.get("shadow") or []):
        if f.get("fired"):
            lines.append(f"• {f['label']}: {f['raw_text']}")
    for f in sc.get("info") or []:
        if f.get("fired"):
            lines.append(f"· {f['label']}: {f['raw_text']}")
    if link:
        lines.append(link)
    return "\n".join(lines)


class TelegramBot:
    def __init__(
        self,
        client: httpx.AsyncClient,
        token: str,
        chat_id: str,
        score_mint: Any,
        push_verdicts: list[str],
        public_url: str | None = None,
    ):
        self.c = client
        self.base = f"{API}/bot{token}"
        self.chat_id = str(chat_id)
        self.score_mint = score_mint
        self.push_verdicts = set(push_verdicts)
        self.public_url = public_url
        self.sent: deque[float] = deque()
        self._lock = asyncio.Lock()
        self.stats: dict[str, Any] = {
            "updates": 0,
            "answered": 0,
            "pushed": 0,
            "errors": 0,
            "last_error": None,
        }

    async def send(self, text: str) -> None:
        async with self._lock:
            now = time.time()
            while self.sent and now - self.sent[0] > 86_400:
                self.sent.popleft()
            if len(self.sent) >= 300:
                return
            if self.sent and now - self.sent[-1] < 2:
                await asyncio.sleep(2 - (now - self.sent[-1]))
            self.sent.append(time.time())
            try:
                r = await self.c.post(
                    f"{self.base}/sendMessage",
                    json={"chat_id": self.chat_id, "text": text[:4000], "disable_web_page_preview": True},
                )
                r.raise_for_status()
            except httpx.HTTPError as exc:
                self.stats["errors"] += 1
                self.stats["last_error"] = type(exc).__name__  # never the URL: it holds the bot token

    def link(self, mint: str) -> str | None:
        return f"{self.public_url.rstrip('/')}/#{mint}" if self.public_url else None

    async def push(self, sc: dict[str, Any]) -> None:
        if sc.get("verdict") in self.push_verdicts and sc.get("D"):
            await self.send(format_score(sc, self.link(sc["mint"])))
            self.stats["pushed"] += 1

    async def handle(self, text: str) -> None:
        text = (text or "").strip()
        if text.startswith(("/start", "/help")):
            await self.send(HELP)
            return
        m = MINT_RE.search(text)
        if not m:
            await self.send("Gửi /score <mint> hoặc dán mint của coin cần chấm.")
            return
        try:
            sc = await self.score_mint(m.group(1))
        except Exception as exc:  # noqa: BLE001 - the answer says what went wrong, never a URL
            why = str(exc) if isinstance(exc, LookupError | OnDemandLimit) else describe_error(exc)
            await self.send(f"Không chấm được: {why}"[:300])
            return
        await self.send(format_score(sc, self.link(sc["mint"])))
        self.stats["answered"] += 1

    async def run(self) -> None:
        offset = 0
        while True:
            try:
                r = await self.c.get(
                    f"{self.base}/getUpdates", params={"timeout": 30, "offset": offset}, timeout=40
                )
                r.raise_for_status()
                for upd in r.json().get("result") or []:
                    offset = max(offset, int(upd["update_id"]) + 1)
                    self.stats["updates"] += 1
                    msg = upd.get("message") or {}
                    if str((msg.get("chat") or {}).get("id")) != self.chat_id:
                        continue  # private: other chats get no answer at all
                    await self.handle(msg.get("text") or "")
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - keep polling
                self.stats["errors"] += 1
                self.stats["last_error"] = type(exc).__name__
                await asyncio.sleep(5)
