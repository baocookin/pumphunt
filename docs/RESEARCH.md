# Nghiên cứu: giao dịch tự động trên pump.fun (10/2026)

Tài liệu này tóm tắt những gì tìm được, kết luận chiến lược, và vì sao kiến trúc được chọn như hiện tại. Nhiều trang bị proxy chặn nên một số số liệu lấy từ trích dẫn trong kết quả tìm kiếm; chỗ nào chưa kiểm chứng trực tiếp sẽ ghi rõ.

## 0. Vòng 2 (10/2026): 6 agent phản biện — kết luận thay thế toàn bộ mục 4 bên dưới

Bốn agent nghiên cứu (ai kiếm tiền thật · adverse selection 60s đầu · sân chơi ít chen chúc · kiểm toán bằng chứng), một agent fact‑check, một agent red‑team. Những gì sống sót:

**Chiến lược v1 (scalp momentum trên curve) bị falsify, không cần test thêm.**
- Người mua organic vào 2–25 slot sau trade đầu: +3.9% gross → **−2.7% net** (230 coin); 72/72 biến thể momentum âm (167 token); paper bot sống thật WR 24%, PF 0.7.
- 45–51% tx chạm curve **fail**; Python + PumpPortal event→fill 1.5–3s; slot‑0 vs slot‑2 chênh 20–60%; một bot đo chi phí all‑in 9.5%.
- Backtest "$4k/ngày" mà v1 dựa vào: **1 giờ dữ liệu**, best‑of‑270 lưới, fill latency 0, đăng dưới tag vendor. Trust 1/5.
- "≥4 ví khác nhau mua" là thứ bị làm giả rẻ nhất: 1,012 sniper ring cố định (Kamat 2607.02795); ví phối hợp giữ **36.5% supply lúc migration** (MELT 2602.13480); wash trade trong 17% tx (CCS'26). Ring làm tăng *số* người mua +16% nhưng SOL inflow chỉ +6% (CI chứa 0).
- Graduation được *chế tạo*: dev mua >5 SOL → 8% graduate, 0 SOL → 0.34%. Filter "dev ≤3 SOL" của v1 lọc ngược chiều.

**Mô hình dự đoán không generalize.** Kamat (SSRN 6915560 / arXiv 2607.02823): claim "Telegram 8.94×, hazard" **bị chính tác giả rút** (collector chỉ nhìn mỗi token ~6 phút); bài thay thế: AUROC 0.859 in‑sample → **0.464** trên 14 ngày kế tiếp. Marino et al. (2602.14860, 655k token, 9/2025): feature thật duy nhất là tỷ lệ trader qua UI pump.fun (non‑bot) + tốc độ gom vSOL; chưa có OOS.

**Số liệu thị trường (fact‑check):** graduation 0.2% (May–Jun 26, lower bound) → **2.6–3.1% tháng 8/2026** sau BOOST, ~1,000/ngày — *không* "đang rơi". Revenue pump.fun 2026 YTD ≈ −57% vs TB tháng 2025, Q3/2026 là quý mạnh nhất năm. LetsBonk 58% là snapshot 7/2025; đối thủ hiện tại: Pons, Stonkfun. Phí 2024 toàn hệ: Raydium 56%, bot/terminal 24%, Jito 11%, pump.fun 8% — "người bán xẻng" thật là terminal thu 1%/giao dịch, và pump.fun đang nuốt lớp đó (Padre→Terminal, Kolscan). Retail: ~6% trader có lãi, median −$120; 93/100 ví PnL cao nhất là bot.

**"Bán verdict rug/bundle" không phải lỗ hổng:** Axiom Pulse, Padre, GMGN, BullX Neo, RugCheck, Bubblemaps, SolanaTracker đều hiện bundle/sniper/insider/dev trên pair mới; gRPC rẻ nhất tử tế $199/tháng (Shyft). Hội tụ của nhiều agent LLM về "sell shovels" = cùng một prior đọc cùng vài trang marketing, không phải bằng chứng độc lập.

**Pháp lý:** Nghị định 284/2026/NĐ‑CP (16/7/2026, hiệu lực 1/9/2026) — cá nhân VN giao dịch không qua tổ chức được Bộ Tài chính cấp phép: phạt 30–50 triệu; bán dữ liệu tài khoản trái phép 150–200 triệu. Kéo audience VN vào bot offshore để ăn referral = xúi giục hành vi bị phạt.

**Hai thứ chưa bị falsify (khác "đã chứng minh"):**
1. **C — survivor entry trên token đã graduate**: trong 15,548 graduate (May–Sep 2026) 43.8% còn ≥$5k liquidity sau 30 phút, 19.7% sau 24h; liquidity median rơi 57% từ phút 5→30 rồi gần như đứng yên. Chưa có backtest công khai cho entry T+30. Red‑team: 4/10 — rủi ro là "survivor" chỉ là bundler chưa xả.
2. **D — copy ví "chậm" đã lọc bot**: WWW'26 (arXiv 2601.08641, code `lyc0603/copytrading`) +14%/lệnh **in‑sample**; ví bị copy nhìn thấy copier để bán vào họ. Red‑team: 3/10.

**Quyết định:** repo chuyển thành bộ ghi dữ liệu on‑chain có slot + harness kiểm định C với tiêu chí giết đăng ký trước (README). Vốn 1–5 SOL đứng ngoài cho tới khi có kết quả OOS dương *và* có khung pháp lý. Thứ khan hiếm có bằng chứng là dữ liệu sạch kéo dài >24h (API pump.fun không backfill quá ~24h; paper 832k launch phải rút vì collector 6 phút).

Nguồn vòng 2: [Kamat audit 2607.02823](https://arxiv.org/abs/2607.02823) · [Sniper rings 2607.02795](https://arxiv.org/abs/2607.02795) · [MELT 2602.13480](https://arxiv.org/abs/2602.13480) · [Marino 2602.14860](https://arxiv.org/abs/2602.14860) · [Meme Coin Factories 2609.10246](https://arxiv.org/abs/2609.10246) · [Copy trading WWW'26 2601.08641](https://arxiv.org/abs/2601.08641) · [Pine Analytics – Exit Liquidity Machines](https://pineanalytics.substack.com/p/exit-liquidity-machines) · [Graduate liquidity decay (15,548 token)](https://trader.scorplabs.online/blog/pump-fun-graduation-raydium-migration) · [Graduation sau BOOST – The Block](https://www.theblock.co/post/409815/pump-fun-token-graduation-rate-jumps-boost-changes-launch-incentives) · [Launchpad share 9/2026 – CoinGecko](https://www.coingecko.com/learn/memecoin-launchpad-wars-pumpfun-stonkfun-ponsfamily) · [Fee pie 2024](https://www.chaincatcher.com/en/article/2162793) · [DefiLlama pump.fun](https://defillama.com/protocol/pump.fun) · [Axiom Pulse docs](https://docs.axiom.trade/axiom/finding-tokens/pulse) · [Shyft gRPC](https://shyft.to/solana-yellowstone-grpc) · [NĐ 284/2026 – VnEconomy](https://vneconomy.vn/phat-den-50-trieu-dong-voi-ca-nhan-giao-dich-tai-san-ma-hoa-khong-qua-don-vi-duoc-cap-phep.htm) · [NĐ 284/2026 – LuatVietnam](https://luatvietnam.vn/linh-vuc-khac/nghi-dinh-284-2026-nd-cp-quy-dinh-xu-phat-vi-pham-ve-tai-san-ma-hoa-nhu-the-nao-883-112958-article.html) · [pump.fun IDL](https://github.com/pump-fun/pump-public-docs)

---

*Phần dưới đây là vòng 1 (giữ nguyên để thấy đã sai ở đâu). Mục 4 "Early‑Momentum Scalp" đã bị thay thế bởi mục 0.*

## 1. Bối cảnh thị trường

| Số liệu | Giá trị | Nguồn |
|---|---|---|
| Tỷ lệ ví có lời trên pump.fun | 50.1 % (1/2026) → 56.8 % (2) → 70.0 % (3) → **73.3 % (4/2026)**, cao nhất lịch sử | CoinGecko Research |
| Nhưng lời bao nhiêu | 65.1 % ví có lời chỉ lời **$1–500**; chỉ 5.4 % lời >$1 000 | CoinGecko Research |
| Ví hoạt động/tháng | 5.2 M (5/2025) → 1.8 M (12/2025): retail non‑tay rời đi, còn lại trader kinh nghiệm + bot | CoinGecko Research |
| Token graduate | ~1 % (nhiều nguồn); một bài ghi 0.26 % đầu 2026 | dextools, cryptomemecoin, j.tools |
| Token bị bỏ hoặc rug | **98.6 %** | solbundler, bex.co |
| Thời điểm rug | đa số **5–15 phút** đầu (dev + ví bundle xả cùng lúc trên curve) | solbundler |
| Bundler | creator có thể chia initial buy cho tới 17 ví, gom 30–40 % supply ở giá sàn | smithii, bex.co |

Kết luận 1: xác suất một token *bất kỳ* đi xa gần bằng 0; EV của bot nằm ở **thời gian giữ cực ngắn** và **tránh được bẫy dev/bundle**, không nằm ở "chọn đúng runner".

## 2. Phí và cơ chế curve

* Bonding curve là constant‑product trên reserve ảo: khởi đầu ≈30 SOL ảo / ≈1.073 B token ảo, supply 1 B; mcap khởi điểm ≈28 SOL.
* Phí curve **1.25 %** mỗi giao dịch (0.95 % protocol + 0.30 % creator), tính trên SOL. Hoàn tất curve khi gom ≈85 SOL thật → chuyển sang PumpSwap, phí graduate 0.015 SOL. PumpSwap: 0.20 % LP + 0.05 % protocol + creator fee theo bậc. (soltokencreator, blofin, pump.fun/docs/fees — trang docs bị chặn, chưa đọc trực tiếp.)
* Ý nghĩa: một vòng mua‑bán mất ≈2.5 % phí + price impact 2 chiều + priority fee. Với lệnh 0.1 SOL trên curve ~30 SOL, price impact nhỏ; với 1 SOL thì đáng kể. `curve.py` mô hình đúng điều này, `test_curve.py` kiểm chứng roundtrip mất đúng phí.

## 3. Bằng chứng về chiến lược

### 3.1 Backtest công khai duy nhất có số liệu
Bài "My pump.fun bot makes $4,000 a day – here are the 4 numbers" (dev.to, trang bị chặn, số lấy từ trích dẫn): **270 cấu hình exit trên 2.5 M event**, fill tính qua bonding curve thật.

| Cấu hình | Win rate | Net | Số lệnh |
|---|---|---|---|
| dev buy 1 SOL, TP +30 %, SL −30 %, hold 120 s | 52.7 % | **+40.26 SOL** | 1 034 |
| dev buy 1 SOL, TP +30 %, SL −15 %, hold 120 s | 49.3 % | +38.11 SOL | – |
| dev buy 3 SOL, TP +200 % | 14.1 % | **−10.97 SOL** | 555 lỗ |

Bài học: *runner có thật nhưng không đủ nhiều để trả cho 555 lệnh lỗ*. TP nhỏ, hold ngắn, lọc theo dev buy vừa phải → dương.

### 3.2 Ba cách tiếp cận phổ biến
1. **Snipe block‑0** (mua ngay khi create, AutoSell): rủi ro cao nhất, chỉ hợp lệnh nhỏ rải nhiều token. Đây là cuộc đua latency với bot Rust/Jito/Geyser — Python + PumpPortal **không thắng được**, không nên chọn.
2. **Copy‑trade ví thông minh**: hiệu quả phụ thuộc hoàn toàn vào chất lượng danh sách ví, và ví tốt bị copy nhiều sẽ bị front‑run; cần dữ liệu lịch sử để tìm ví → chưa có ở ngày 0.
3. **Momentum/volume sớm**: chờ vài giây để thấy nhiều ví *khác nhau* mua thật, vào theo nhịp kế, thoát nhanh. Không đòi hỏi latency cực thấp; phù hợp paper‑first.

### 3.3 Checklist rug (gộp từ j.tools, solbundler, rpcfast)
* Dev + 3 ví sniper > 35 % supply → bỏ. Dev & ví liên quan > 20–25 % → rủi ro xả rất cao.
* Dev không mua gì → không có skin in the game; dev mua quá nhiều → sẽ xả.
* Dev bán trong cửa sổ đầu → rời ngay.
* Có socials (X/TG/web) tăng xác suất graduate (SSRN "social‑presence effect", 832 941 launch — chưa đọc được bản full).

## 4. Chiến lược được chọn: Early‑Momentum Scalp

Mặc định (tất cả chỉnh được qua `.env`, xem `bot/app/config.py`):

| Bước | Luật | Lý do |
|---|---|---|
| Lọc `create` | 0.3 ≤ dev buy ≤ 3 SOL; dev ≤ 20 % supply | §3.1 (1 SOL hoạt động tốt, 3 SOL lỗ), §3.3 |
| Cửa sổ xác nhận | tối đa 20 s; cần ≥4 ví mua khác dev; net buy ≥ 1 SOL; mcap ≤ 60 SOL | tránh block‑0, tránh đu đỉnh; dev bán trong cửa sổ → huỷ |
| Vào | 0.1 SOL, tối đa 5 vị thế | rải nhỏ như §3.2‑1 khuyên |
| Thoát | TP +30 %, SL −20 %, hold ≤120 s, dev bán → thoát ngay | §3.1 |
| Định giá | PnL tính trên **giá trị thoát thật** (bán hết qua curve, trừ phí) chứ không trên giá mark | tránh ảo tưởng lời khi thanh khoản mỏng |
| Paper realism | phí 1.25 %, haircut 1 % mỗi fill, 0.001 SOL/tx | phí, slippage/latency, priority fee |

Những con số TP/SL/hold lấy từ backtest của người khác trên dữ liệu đầu 2026; **không được coi là đã kiểm chứng** cho hiện tại. Bước đầu của bạn là thu dữ liệu vài ngày (bot tự ghi JSONL) rồi chạy `python -m app.backtest` theo grid.

## 5. Hạ tầng

### Vì sao PumpPortal cho v1
* WS `wss://pumpportal.fun/api/data`: `subscribeNewToken` (miễn phí), `subscribeTokenTrade`, `subscribeAccountTrade`, `subscribeMigration`. Event có `txType, mint, traderPublicKey, solAmount, tokenAmount, vSolInBondingCurve, vTokensInBondingCurve, marketCapSol, bondingCurveKey, pool`; create thêm `name, symbol, uri, initialBuy`.
* `subscribeTokenTrade` **có phí** (≈0.01 SOL/10k event, cần API key + ví ≥0.02 SOL) → bot chỉ subscribe mint đang quan tâm. Một kết nối duy nhất (mở nhiều → ban 1 giờ).
* Trading: `POST /api/trade-local` trả transaction đã build (`publicKey, action, mint, amount, denominatedInSol, slippage, priorityFee, pool`) → tự ký bằng `solders` → gửi RPC riêng. Đây là đường đi cho `LiveBroker` sau này; không dùng Lightning API (giữ key ở PumpPortal).

### RPC là gì và cần gì
RPC node là máy chủ bạn gọi để đọc chain và gửi giao dịch. Public RPC (`api.mainnet-beta.solana.com`) chậm và rate‑limit, không dùng để trade. Khi sang live: Helius / QuickNode / Triton có gói free đủ cho vài tx/phút; Jito bundle giúp tx vào block nhanh và chống bị kẹp. Paper không cần RPC.

### Vì sao FastAPI + Redis + Next.js
Bạn đang cân nhắc template `mc-template-fastapi-with-redis` của Bunny. Nó khớp tốt: worker async Python nghe WS, Redis giữ vị thế/lệnh/thống kê (sống qua restart, chia sẻ giữa worker và API), Next.js đọc API. `bunny.json`, `docker-compose.yml`, workflow deploy đều mô phỏng cấu trúc template. Trade‑off: Python đủ cho chiến lược chờ‑xác‑nhận; nếu sau này cần block‑0 phải sang Rust/TS + Geyser.

## 6. Việc tiếp theo (ưu tiên)
1. Chạy paper 3–7 ngày, thu JSONL. Kiểm tra feed hoạt động từ máy bạn (môi trường này bị chặn pumpportal.fun nên chưa test kết nối thật).
2. Grid backtest TP ∈ {15,20,30}, SL ∈ {10,15,20,30}, hold ∈ {60,90,120,180}, min_unique_buyers ∈ {3,4,6}. Chọn theo **net SOL sau phí**, không theo win‑rate.
3. Thêm lọc metadata (socials) và bundle detection; đo lại.
4. `LiveBroker` với giới hạn rủi ro cứng; bắt đầu 0.02–0.05 SOL/lệnh.

## Nguồn
* [CoinGecko – Pump.fun Traders Are Making a Comeback](https://www.coingecko.com/research/publications/pump-fun-traders-are-making-a-comeback)
* [Bitget – Profitability hits ATH](https://www.bitget.com/news/detail/12560605404343) · [blockchain.news](https://blockchain.news/news/pump-fun-traders-profitability-surge)
* [odin.tools – 3 ways to trade memecoins with a bot (2026)](https://odin.tools/blog/pump-fun-bot-strategy-solana-2026)
* [dev.to – My pump.fun bot makes $4,000 a day: the 4 numbers](https://dev.to/gengengen/my-pumpfun-bot-makes-4000-a-day-here-are-the-4-numbers-51oa)
* [j.tools – 7‑point rug checklist](https://j.tools/en/blog/pump-fun-token-visibility-crisis-2026) · [solbundler – avoid rug pulls 2026](https://solbundler.app/blog/how-to-avoid-pump-fun-rug-pull-2026) · [rpcfast – sniping infra guide](https://rpcfast.com/blog/how-to-launches-snipe-pump) · [bex.co – Meme Launchpad 2.0](https://bex.co/blog/2026/04/20/meme-launchpad-2-pump-fun-letsbonk-anti-sniper-reputation) · [smithii – bundler](https://smithii.io/en/pump-fun-bundler-bot/)
* [dextools – graduation rate collapses to 0.26 %](https://www.dextools.io/news/pump-fun-graduation-collapse-solana-fees-2026) · [cryptomemecoin – graduation explained](https://cryptomemecoin.com/blog/pump-fun-graduation-explained)
* [soltokencreator – fees](https://www.soltokencreator.io/blog/pump-fun-fees-explained) · [blofin – fees explained](https://blofin.com/en/academy/education/pumpfun/pump-fun-fees-explained) · [pump.fun/docs/fees](https://pump.fun/docs/fees) · [cryptoslate review](https://cryptoslate.com/decentralized-exchanges/pump-fun-review/)
* [PumpPortal real‑time docs](https://pumpportal.fun/data-api/real-time/) · [PumpPortal FAQ](https://pumpportal.fun/FAQ/) · [thetateman/Trading-API](https://github.com/thetateman/Trading-API) · [pumpdevio – WS streaming](https://medium.com/@pumpdevio/pump-fun-api-real-time-websocket-streaming-with-python-token-launches-trades-whale-tracking-2b3979fc26bb)
* Học thuật: [Marino et al. 2026 – Predicting the success of new cryptotokens: the Pump.fun case (arXiv:2602.14860)](https://arxiv.org/abs/2602.14860) · [Kamat – Graduation Regime Windows, survival analysis of 832 941 launches (SSRN)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6915560) · [arXiv:2607.02823 – auditing graduation labels](https://arxiv.org/pdf/2607.02823) · [arXiv:2512.11850 – Solana memecoin phenomenon](https://arxiv.org/pdf/2512.11850)
* Tham chiếu mã nguồn mở: [TreeCityWes/Pump-Fun-Trading-Bot-Solana](https://github.com/TreeCityWes/Pump-Fun-Trading-Bot-Solana) (TP bậc 25 %/25 %, SL −10 %, moon‑bag 25 %), [Tinuz/solsniperbot](https://github.com/Tinuz/solsniperbot)
* Template hạ tầng: [jamie-at-bunny/mc-template-fastapi-with-redis](https://github.com/jamie-at-bunny/mc-template-fastapi-with-redis)
