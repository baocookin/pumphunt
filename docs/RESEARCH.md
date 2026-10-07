# Nghiên cứu: giao dịch tự động trên pump.fun (10/2026)

Tài liệu này tóm tắt những gì tìm được, kết luận chiến lược, và vì sao kiến trúc được chọn như hiện tại. Nhiều trang bị proxy chặn nên một số số liệu lấy từ trích dẫn trong kết quả tìm kiếm; chỗ nào chưa kiểm chứng trực tiếp sẽ ghi rõ.

## Sniper (07/10/2026)

Nghiên cứu riêng về snipe token mới, phép đo trên 77.043 launch tháng 9/2026, bộ dữ liệu forward chính xác tới slot, và giả thuyết S đăng ký trước: [`SNIPER.md`](SNIPER.md). Kết luận chính: trên cùng các launch, vé đứng ngay sau lệnh mua của dev có EV +12% (KTC 95% +10,9…+13,2%), vé vào ~1 giây sau có EV −8% (−8,1…−7,7%), không bộ lọc đơn giản nào đổi dấu; vị trí có lãi là vị trí bundle của người tạo token.

## Giả thuyết G và GS (07/10/2026)

Mua một bonding curve đã có 60 SOL thật, giữ tới khi tốt nghiệp, bán 3 giây sau migration ([`SNIPER.md`](SNIPER.md), mục 8–9).
- Trên dữ liệu thăm dò, 30% số curve chạm 60 SOL đã hoàn tất ngay trong phút đầu (phần lớn là bundle trong 2 giây). Người ngoài không vào kịp, nên kỳ vọng +21% ban đầu bị thổi phồng.
- Curve chạm 60 SOL sau giây 60: +8,6% mỗi vé (KTC +4,5…+12,7%), dương ở cả hai nửa thời gian. Đây là GS, đăng ký thêm với cùng mẫu kiểm định của G, phán quyết một lần trên 300 vé đầu.
- Mua ngay sau migration rồi bán lúc T+5 phút (ăn theo lệnh mua lại của BOOST): −5,7% (KTC −10,0…−1,4%, 725 token ngày 4–5/10). Người nắm token từ curve xả vào lệnh mua của BOOST.

## Thăm dò luật đặc trưng (06/10/2026, trước cửa sổ thăm dò)

**Dữ liệu dùng để thăm dò:**
- Các dòng được harvest trước `PREREG_TS`, tức migration ngày 4–5/10. Đây chỉ là thăm dò, không phải bằng chứng.
- 307 pool C2: ≥ 10 SOL thật, và có swap trong 60 giây trước T+30.
- Ô đo: vào T+30, giữ 1 giờ, 1 SOL, khớp lệnh thật.
- Bảng đầy đủ: `/api/survivor/explore` → mẫu `before`.

**Kết quả:**

| Nhóm | n | Trung vị | Trung bình | Thắng | Mất ≥ 90% |
|---|---|---|---|---|---|
| Toàn bộ C2 | 307 | −41,7% | −32,4% | 29% | 26% |
| Token tự tốt nghiệp: dev mua ≥ 80 SOL ngay trong lệnh tạo (40% của C2) | 123 | −1,4% | −45% | 34% | 47% |
| Token mà người khác lấp đầy curve | 184 | −42,5% | −24% | 26% | 12% |
| Giá tại T+30 bằng 0,7–1,15 lần giá migration, kèm mua ròng ≥ 1 SOL trong 5 phút trước | 52 | +2,8% (KTC +1,6% … +5,4%) | −5,6% | 75% | 13% |

Về nhóm token tự tốt nghiệp: sau migration, dev nắm khoảng 79% cung nên có thể rút cạn pool bất cứ lúc nào. Trung vị của nhóm này ở nửa đầu là −0,6%, ở nửa sau là −98,7%.

Về nhóm cuối:
- Trung vị như nhau ở cả hai nửa, và không đổi khi xê dịch ngưỡng.
- Nhưng toàn bộ các ca về 0 đều là token tự tốt nghiệp. Bỏ chúng đi thì chỉ còn n = 11.

Không nhóm nào có trung bình dương ổn định.

**Cam kết quy trình** (ghi lại trước khi xem dữ liệu của cửa sổ thăm dò):
1. Tiêu chí của C, C2 và của các luật dựa trên trung vị, và được giữ nguyên (`PREREG.md`). Trung vị không thấy đuôi rug, nên mọi bảng báo thêm trung bình và tỷ lệ mất ≥ 90% (`mean`, `rug_share`).
2. Một luật chỉ được đăng ký nếu trên cửa sổ thăm dò, trung bình của nó dương ở cả hai nửa (chia theo thời gian), chứ không chỉ trung vị.
3. Nếu một luật PASS theo tiêu chí nhưng trung bình trên mẫu kiểm định ≤ 0, kết luận ghi là "PASS theo trung vị, EV không dương". Đó không phải chiến lược có lãi.
4. Lần chọn luật kế tiếp diễn ra khi cửa sổ có ≥ 600 dòng C2 kèm snapshot holder, dự kiến khoảng 10/10. Chọn trên 2/3 đầu, kiểm tra trên 1/3 sau, và chỉ đăng ký những luật qua được.
   - Hướng thử theo cơ chế thứ nhất: loại token tự tốt nghiệp.
   - Hướng thử thứ hai: tỷ trọng của ví dev và ví bundle trong snapshot holder tại T+30.

**Sniper (S2):**
- Bảng thăm dò theo đặc trưng lúc vào: `/api/sniper/explore`.
- Chọn luật khi cửa sổ S có ≥ 1.500 vé classic (dự kiến khoảng 9/10), cùng quy tắc trung bình dương ở cả hai nửa.
- Phép đo lịch sử (`SNIPER.md`, mục 3) không cho nhóm nào dương, nên hiện chưa có ứng viên.

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

## Sửa đổi phương pháp (06/10/2026): thước đo chính là khớp lệnh thật

Kill criteria giữ nguyên (n≥300; KILL nếu median net ≤ −1.25% hoặc top‑2% ≥ 50% lãi; PASS nếu median > +2% và win rate ≥ 45%), nhưng đại lượng "net" được đo lại:

* **Trước**: close nến (1 rồi 5 phút) tại T+d và T+d+h, trừ 3.5% round‑trip cố định.
* **Sau**: mô phỏng vị thế S SOL trên reserve thật của pool PumpSwap đọc từ event swap on‑chain (reserve trước swap, virtual quote reserve, phí lp/protocol/creator thực tế), vào ở trạng thái 3 giây sau quyết định, ra tương tự, trừ phí pool hai chiều và 0.001 SOL phí tx mỗi chiều. Ô chính: S = 1 SOL, T+30m, giữ 1h. Các cỡ 0.5/2/5 SOL báo kèm để thấy chi phí thanh khoản.

Lý do: xác minh trên mainnet cho thấy pool có virtual quote reserve và thanh khoản thật có thể bị rút gần hết, khiến trượt giá thực tế cao hơn nhiều so với 3.5%. Thước đo theo nến vẫn được tính và hiển thị để đối chiếu, không dùng làm verdict.

## Đo trên pool PumpSwap (06/10/2026): thực thi quyết định kết quả, và đo nó khó hơn tưởng

**Số liệu sơ bộ (fills v1, 186 token đã harvest, 112 có khớp lệnh; lệnh 1 SOL, vào T+30, giữ 1h).** Sẽ được tính lại toàn bộ bằng fills v2 bên dưới; xem như định hướng, chưa phải kết luận.

| Nhóm pool lúc vào | Tỉ lệ | Kết quả |
|---|---|---|
| Lúc tốt nghiệp nạp < 1 SOL thật vào pool | 20% số migration | Gần như không có thanh khoản, lỗ ~99% |
| Pool bình thường nhưng không còn giao dịch | 41% pool bình thường | Chỉ mất phí |
| Pool bình thường còn giao dịch | 59% | Giá trung vị −7.8%; 5/36 tăng quá phí khứ hồi 2.7% |

Với pool bình thường, verdict không đổi theo cách mô hình hóa: bi quan (tác động giá của mình biến mất trước khi bán) trung vị −12.4%, thắng 5%; lạc quan (tác động giá giữ nguyên) −2.8%, thắng 8%. Cả hai là KILL.

**Cơ chế pool phải mô hình đúng:**
* Giá tính trên Q+V (SOL thật trong vault + virtual quote reserve có dấu, ~17.5 SOL ở pool mới) nhưng lệnh bán **không bao giờ nhận quá Q** (lỗi 6063 `InsufficientRealQuoteReserves`): pool bị rút hết SOL thật vẫn báo giá mà không ai thoát được. Mọi lệnh bán mô phỏng đều bị chặn ở Q.
* Ba biến thể lệnh mua ghi event khác nhau. `buy`: `quote_amount_in` là SOL vào curve. `buy_exact_quote_in`: `quote_amount_in` là tổng người dùng trả, `user_quote_amount_in` mới là SOL vào curve, và token ra được tính trên đầu vào − 1 lamport. `buy_exact_quote_in_v2`: giữ lại trong vault mọi khoản phí trừ phần buyback; số phí này về sau bị rút ra ngoài bằng giao dịch không phải swap. Công thức chung: SOL vào curve = `quote_amount_in_with_lp_fee − lp_fee`. Đọc sai, mỗi lệnh mua exact‑in làm SOL của pool lệch thêm một khoản bằng tổng phí (~1.2% giá trị lệnh ở pool đo được), cộng dồn theo từng lệnh (đo: 40/53 lệnh mua ở một pool lớn là exact‑in).
* Kiểm tra trên cửa sổ đầy đủ: phía token, swap sau luôn bắt đầu đúng ở trạng thái swap trước để lại (0 lệch trên mọi cửa sổ đã đo); phía SOL có những lần rút phí ngoài swap. Bộ đếm `chain_breaks` (phía token, nghĩa là thiếu swap) và `quote_gaps` (phía SOL, nghĩa là phí bị rút) tách hai chuyện này; mô hình replay áp cùng khoản rút đó vào pool giả định (thiếu bước này replay lạc quan giả ~1% ở pool 50 SOL).

**Bot MEV làm "giao dịch cuối cùng trước thời điểm T" vô nghĩa.** Ở pool sôi động, 95/100 giao dịch thành công chạm pool là bot đọc giá rồi thoát, không swap; chúng tham chiếu cả pool, hai vault, mint và vault phí creator, nên không địa chỉ nào lọc được. Hệ quả với fills v1: trạng thái tại mốc vào/ra có thể là của một swap cũ hàng phút (một pool đang có ~3 swap/giây bị ghi "idle 242s"). Fills v2 quét lùi từ mỗi mốc đến khi gặp swap thật.

**Phân bố số giao dịch** trong cửa sổ T+25 → T+121 phút (40 pool ngẫu nhiên): trung vị 13, p75 389, p90 7,041, lớn nhất > 31,000. Đa số pool gần như chết; chi phí đọc tập trung ở ~10–15% pool sôi động, cũng là nhóm duy nhất có thể giao dịch được. Trần 15,000 tx/cửa sổ đọc trọn ~93% pool, trung bình ~200 credit/pool (Helius: 0.1 credit/tx). Bộ lọc `tokenTransfer` của Helius (giữ giao dịch có chuyển token của pool) bỏ được nhiễu bot; recorder chỉ bật nó sau khi so cạnh nhau với trang không lọc và thấy nó giữ đủ mọi swap (RPC công khai bỏ qua bộ lọc này; Helius chỉ nhận nó ở commitment `finalized`). Trên production nó vẫn bỏ sót **1 swap trong ~210,000** (243 cửa sổ có lọc): một lệnh mua đi qua router trong giao dịch phiên bản 1. Chỗ đứt phía token lộ ra ngay, nên từ nay mỗi chỗ đứt trong cửa sổ có lọc được đọc lại không lọc để lấy swap bị thiếu; cửa sổ không lọc có 0 chỗ đứt trên ~37,000 swap.

**Thay đổi phương pháp (fills v2, mọi dòng được tính lại):** trạng thái ở mốc vào/ra = swap mới nhất trước mốc (quét lùi); cửa sổ đầy đủ quanh T+30→T+90 và T+60→T+120 khi vừa trần, cho mô hình replay và order flow 5 phút trước khi vào; ba mô hình ghost/persist/replay báo song song, replay là ước lượng chính khi có. Verdict vẫn theo tiêu chí đã đăng ký.

## Đặc trưng tại thời điểm quyết định (06/10/2026)

Mục tiêu: những gì đã công khai *trước* lúc vào lệnh ở T+30, để một bộ lọc đăng ký trước có thể dùng. Ba nguồn, đều đo trên dữ liệu thật trước khi viết code:

* **Cách bonding curve được lấp đầy** (100 giao dịch đầu của curve). Ví dụ: một token có cả vòng đời curve chỉ 9 giao dịch — bốn ví mua ngay trong slot tạo token (~79 SOL), tốt nghiệp trong cùng giây; pool PumpSwap của nó giảm 98.6% trong giờ đầu. Một token khác tốt nghiệp nhờ chính dev mua 85 SOL trong slot tạo. Token "tự nhiên" hơn: 8–160 phút để tốt nghiệp, 33–39 ví mua chỉ trong 20–30 giây đầu, và dev đã bán 6–11 SOL ngay trong khoảng đó.
* **Nguồn tiền của ví** (giao dịch đầu tiên của ví). Ở token bị mua gom trong slot tạo: cả 5 ví (dev + 4 ví bundle) được tạo ~20 phút trước khi token ra đời, 4/5 được nạp từ *cùng một ví*. Ở các token tự nhiên: ví dev và người mua sớm đã tồn tại 6–430 ngày, không có cụm chung người nạp. Ví sàn cũng nạp cho nhiều ví không liên quan, nên địa chỉ người nạp được lưu nguyên để lọc offline (người nạp xuất hiện ở rất nhiều token không liên quan = sàn).
* **Holder lúc T+30/T+60** (chụp trực tiếp): tỷ trọng top holder ngoài pool, dev/bundle còn giữ bao nhiêu, và *khả năng thoát* — SOL top‑10 rút được nếu bán hết vào pool đúng lúc đó. Lưu ý: event pump.fun xuất hiện hai lần trong một giao dịch (log + self‑CPI); số liệu chưa khử trùng lặp bị nhân đôi.

**Quan sát thăm dò từ production (06/10, 42 token đầu có lịch sử curve, chưa phải bằng chứng):** 16/42 token (38%) tốt nghiệp trong vòng 5 giây sau khi được tạo, 13 trong số đó vì chính dev mua ≥ 80 SOL ngay trong giao dịch tạo (curve chỉ có 2 giao dịch). Lúc T+30, pool của nhóm "tự tốt nghiệp" này chỉ còn trung vị 0.5 SOL thật: dev rút lại gần hết ngay sau migration. Nhiều khả năng đây là cày ưu đãi graduation (tỉ lệ graduation tăng vọt sau thay đổi BOOST), giải thích con số ~1,200 graduation/ngày và nhóm "pool < 1 SOL" ở trên. Chúng không phải thị trường thật; C2 (≥ 10 SOL thật lúc quyết định) loại chúng ra theo định nghĩa.

Những đặc trưng này chỉ được dùng theo quy trình đăng ký trước (mục tiếp theo): chọn luật trên một phần dữ liệu, kiểm định trên phần sau, không chỉnh luật sau khi thấy kết quả.

## Đăng ký trước C2 (06/10/2026 14:39 UTC)

Toàn văn ở [`PREREG.md`](PREREG.md). Tóm tắt: mẫu kiểm định là các migration từ 16:00 UTC 06/10/2026; C2 = pool có ≥ 10 SOL thật và có swap trong 60 giây trước T+30, đo đúng tại T+30; tiêu chí như C. Lúc đăng ký, C trên 98 dòng fills v2 (dữ liệu cũ, thăm dò) có median −3.2%, thắng 7%, khoảng tin cậy 95% của median [−10.9%, −2.7%]: cận trên đã dưới ngưỡng KILL dù chưa đủ n = 300. Bảng chia tầng thăm dò cho thấy pool lớn (≥ 20 SOL thật lúc vào) lại thua nặng hơn (median −53.6%, n = 24), vì đó thường là những pool vừa được bơm rồi xả. Vì vậy C2 có thể cũng bị KILL; kết quả đó vẫn có giá trị nếu được kiểm định đúng quy trình.
