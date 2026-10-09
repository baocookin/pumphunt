import asyncio

import httpx

from app.rpc import describe_error
from app.telegram import HELP, TelegramBot, format_score

MINT = "So11111111111111111111111111111111111111112"
SCORE = {
    "mint": MINT,
    "symbol": "TST",
    "verdict": "TRANH",
    "verdict_vi": "TRÁNH",
    "D": 120,
    "age_s": 125,
    "real": 15.3,
    "floor": -0.58,
    "summary": "Có dấu hiệu bẫy: Dev + creator còn giữ ≥ 3% cung.",
    "risk": {"pct": 0.8, "ci": [0.63, 0.9], "basis": "khi SH-DEV-1 bật", "n": 30},
    "active": [{"label": "Dev + creator còn giữ ≥ 3% cung", "raw_text": "14.2%", "fired": True}],
    "shadow": [],
    "info": [],
}


class FakeHttp:
    def __init__(self):
        self.sent = []

    async def post(self, url, json):
        self.sent.append(json["text"])

        class R:
            def raise_for_status(self):
                return None

        return R()


def _bot(push=()):
    http = FakeHttp()

    async def score(mint):
        assert mint == MINT
        return SCORE

    return TelegramBot(http, "TOKEN", "42", score, list(push)), http


def test_a_score_reads_as_a_warning_never_a_buy():
    text = format_score(SCORE, "https://example/#" + MINT)
    assert text.startswith("TRÁNH · TST") and "80%" in text and "Dev + creator" in text
    assert "MUA" not in text


def test_the_owner_asks_by_mint_and_gets_the_score():
    bot, http = _bot()
    asyncio.run(bot.handle(f"/score {MINT}"))
    asyncio.run(bot.handle("hello"))
    asyncio.run(bot.handle("/help"))
    assert http.sent[0].startswith("TRÁNH") and "mint" in http.sent[1] and http.sent[2] == HELP


def test_only_the_chosen_verdicts_are_pushed():
    bot, http = _bot(push=["KHONG_THAY_CO"])
    asyncio.run(bot.push(SCORE))
    assert http.sent == []
    asyncio.run(bot.push({**SCORE, "verdict": "KHONG_THAY_CO"}))
    asyncio.run(bot.push({**SCORE, "verdict": "KHONG_THAY_CO", "D": None}))  # a score asked by hand
    assert len(http.sent) == 1


def test_a_failed_score_never_shows_a_key():
    http = FakeHttp()
    url = "https://rpc.example/?api-key=SECRET"

    async def score(mint):
        req = httpx.Request("POST", url)
        resp = httpx.Response(503, request=req)
        raise httpx.HTTPStatusError(f"Server error '503' for url '{url}'", request=req, response=resp)

    asyncio.run(TelegramBot(http, "TOKEN", "42", score, []).handle(MINT))
    assert "503" in http.sent[0] and "SECRET" not in http.sent[0]
    assert "SECRET" not in describe_error(ValueError(f"bad {url}&x=1"))
    assert "123:ABC" not in describe_error(RuntimeError("https://api.telegram.org/bot123:ABC/getUpdates"))
