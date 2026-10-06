# Sniper trên pump.fun: bằng chứng và giả thuyết S (đăng ký trước, 07/10/2026)

Câu hỏi: mua token mới trên pump.fun trong vài phần giây sau khi nó ra đời ("snipe") rồi bán theo một luật đơn giản thì có dương EV sau chi phí không? Và "ăn x100" thường xuyên tới mức nào?

Tài liệu gồm năm phần:
1. Cơ chế hiện tại.
2. Bằng chứng đã công bố.
3. Phép đo của dự án trên 77 nghìn launch tháng 9/2026.
4. Bộ dữ liệu forward chính xác tới từng slot, đang được ghi.
5. **Giả thuyết S**, cố định trước khi có dữ liệu kiểm định.

Mã tương ứng nằm ở `bot/app/sniper.py`. Kết quả xem ở dashboard (mục "Sniper") và ở `/api/sniper/summary`.

Ký hiệu nguồn:
- **[OC]**: đo trực tiếp on‑chain trong dự án ngày 06/10/2026.
- **[V]**: số liệu của vendor, chưa kiểm chứng.
- **[S]**: chỉ thấy qua đoạn trích của kết quả tìm kiếm.

Nhiều trang bị proxy chặn, nên một số con số lấy từ phần tóm tắt của bài báo. Hãy đọc bản gốc trước khi trích dẫn lại.

## Tóm tắt

**1. Lợi thế nằm ở vị trí trong hàng đợi, và vị trí tốt nhất thuộc về người tạo token.**

Trên cùng 77.043 launch với cùng luật thoát (mục 3), EV trung bình mỗi vé thay đổi theo thời điểm vào:

| Vị trí vào | EV mỗi vé |
|---|---|
| Ngay sau lệnh mua của dev | +5% đến +12% |
| Khoảng 1 giây sau (3–4 slot) | −7% đến −10% |
| 10–60 giây sau | −3% đến −8% |

Kết quả gần như nhau trên cả ba ngày.

**2. Người ngoài không mua được vị trí ngay sau dev.**
- 22% lệnh tạo nằm trong Jito bundle của chính dev, kèm các lệnh mua trung vị 1,66 SOL [OC].
- `jitodontfront` chặn tx khác chen lên trước.
- Người ngoài vào được slot 0 phải trả trung vị 1,35× giá khởi điểm vì đứng sau dev và bundle [OC].

**3. Không bộ lọc đơn giản nào cứu được vé vào ở mốc ~1 giây.**
- Các bộ lọc đã thử gồm: dev mua bao nhiêu, bao nhiêu SOL vào trước mình, số ví bundle, số lần tạo token và tỷ lệ tốt nghiệp của creator.
- Mọi nhóm đều âm, cả trên ngày dùng để thăm dò lẫn ngày giữ lại để kiểm tra.
- Các nhóm "trông như sẽ thành công" lại âm nhất: dev mua lớn, nhiều ví bundle, nhiều SOL vào trước. Đó là nơi insider đã ngồi sẵn để bán cho người đến sau.

**4. x100 không xảy ra trên bonding curve.**
- Giá lúc tốt nghiệp chỉ khoảng 14,7× giá khởi điểm.
- Muốn x100, token phải tốt nghiệp rồi tăng thêm ~7× trên PumpSwap.
- Ước lượng thô: khoảng 1/600 vé ở vị trí tốt nhất *chạm* x100. "Chạm" là đỉnh của một cây nến, không phải giá bán được.
- Ở mốc ~1 giây, tỷ lệ này còn thấp hơn: chỉ 0,3% vé từng chạm x10.

**5. Các bằng chứng đã công bố đều cùng chiều.**
- Lợi nhuận snipe đo được thuộc về các ví do creator nạp tiền và mua cùng block (Pine Analytics: 87% có lãi, khoảng 1 SOL mỗi launch).
- Không tìm thấy nghiên cứu nào cho thấy sniper bên ngoài có lãi ngoài mẫu (out-of-sample) sau chi phí.

**6. Giả thuyết S (mục 7) kiểm định lại trên dữ liệu forward chính xác tới từng slot.**
Luật thoát nhanh (chốt x2 / cắt lỗ 50% / bán sau 60 giây) không mô phỏng được bằng dữ liệu theo launch.

## 1. Cơ chế (10/2026)

**Bonding curve.**
- Là AMM hằng số tích trên reserve ảo 30 SOL / 1,073 tỷ token.
- 793,1 triệu token được bán trên curve. Curve hoàn tất ở khoảng 85,005 SOL thật: giá lúc đó ≈ 14,7× giá đầu, vốn hoá ≈ 410 SOL.
- Sau khi X SOL đi vào, giá bằng ((30+X)/30)² lần giá đầu. Ví dụ: 1 SOL đẩy giá +6,8%, 5 SOL +36%, 10 SOL +78%.
- Hệ quả: người mua đầu tiên lỗ rất ít khi mọi người khác rút ra hết. Người mua sau lỗ phần chênh giá họ đã trả.

**Phí.**
- 1,25% mỗi chiều, gồm 0,95% cho protocol và 0,30% cho creator.
- Từ 28/4/2026, một nửa phần protocol dùng để mua lại PUMP. Đây là chia lại phần phí cũ, không phải phí thêm.
- Event giao dịch on‑chain xác nhận các số này: `fee_basis_points` 95, `creator_fee_basis_points` 30, `buyback_fee_basis_points` 5000 (tức 50% của phần protocol) [OC].

**Không có cơ chế chống sniper hay chặn block đầu tiên.**
- Không thấy trong IDL hay fee config [OC, pump-public-docs].
- "Fair Launch Shield" mà bex.co nhắc tới (20/4/2026) không thấy on‑chain [S].

**Slot.**
- Khoảng 0,25 giây từ ~18/9/2026 (SIMD‑0525).
- Đo được trung bình 0,272 giây; mỗi leader giữ 4 slot liên tiếp [OC].

**Jito bundle.**
- Tối đa 5 tx, thực thi nguyên tử.
- Trong 112 launch SOL quan sát trong 4,4 phút [OC]:
  - 22% lệnh tạo nằm trong bundle (trung vị 4 tx, tip 0,0008 SOL).
  - Các bundle đó chở thêm 70 lệnh mua, trung vị 1,66 SOL.
- `jitodontfront` cho phép đánh dấu để không tx nào chen lên trước tx của mình.

**Mayhem mode** (từ 11/2025).
- Agent của pump.fun tự giao dịch token trong 24 giờ; cung 2 tỷ.
- Chiếm 26–28% số launch.
- Gần như không bao giờ tốt nghiệp: 0,02% [loopholetape].

**BOOST** (từ 21/7/2026).
- Lúc migration, khoảng 17,58 SOL thanh khoản chuyển vào vault. Pool nhận reserve ảo tương đương nên giá không đổi.
- Authority của pump.fun dùng số đó mua dần token trong khoảng 5 phút rồi đốt [OC, The Block].
- Tỷ lệ tốt nghiệp tăng từ 0,26% (giữa 6/2026) lên 2,5–4,7%.
- Ở pool tháng 9 (5.473 pool "đầy"), giá hiếm khi sập trong phút đầu: chỉ 4%. Trung vị thời điểm giá về ≤10% giá mở là 8 phút. Tới phút 30, 58,5% pool đã mất ≥90% [loopholetape].

**Quy mô** [OC].
- Khoảng 57.000 lệnh tạo mỗi ngày on‑chain.
- Khoảng 1/3 trong số đó không dùng SOL làm quote (USDC, cổ phiếu token hoá, RACE…).
- PumpPortal chỉ chuyển khoảng 29.000/ngày, và ghi sai địa chỉ bonding curve cho launch mayhem.

## 2. Bằng chứng đã công bố

**Ai kiếm được tiền**
- **Pine Analytics, "Exit Liquidity Machines"** (4/2025):
  - Tìm ra 15.000+ launch có ví do creator nạp tiền mua ngay trong block tạo token, tổng 15.000+ SOL đã chốt (khoảng 1 SOL mỗi launch).
  - 87% các ví đó có lãi; 85% thoát trong 5 phút.
  - Hơn 50% token bị snipe ngay trong block tạo. Bài không đo lãi lỗ của sniper không liên quan tới creator.
- **Luo et al., WWW'26** (arXiv 2601.08641, khoảng 6.000 coin): bot sniper và bundle *phân phối lại* lợi nhuận của dự án chứ không làm nó nhỏ đi. "Smart money" trung bình +14% mỗi lệnh, nhưng người copy chỉ còn +3% mỗi coin sau ma sát. Đây là backtest lịch sử, chưa thử với đối thủ biết thích nghi. Bài đi kèm (SSRN 5953738) cho thấy người thắng lớn phần nhiều là creator hoặc sniper.
- **MELT** (arXiv 2602.13480, 41.470 token đã migrate, 12/2024–3/2025): tài khoản phối hợp nắm trung bình 36,5% cung. Dữ liệu cùng giai đoạn: 98,7% token tốt nghiệp có dev mua ngay lúc tạo.
- **Mongardini & Mei, USENIX Security'26** (arXiv 2507.01963): 82,89% token lời trên 100% có dấu hiệu tăng trưởng nhân tạo.
- **Meme Coin Factories, CCS'26** (arXiv 2609.10246; 15,2 triệu coin, 1/2024–1/2026):
  - Wash trade chiếm ít nhất 17% số giao dịch và làm xác suất "thành công" tăng tới 10 lần.
  - 1% nhóm creator lớn nhất tạo ra 58,6% số coin.

**Có ai thắng bằng dự đoán không**
- **Kamat:**
  - Nghiên cứu graduation (SSRN 6915560, arXiv 2607.02823) đã bị tác giả rút vì nhãn "graduation" sai.
  - Bản thay thế được đăng ký trước: AUROC 0,859 trên dữ liệu phát triển, chỉ còn 0,464 trên 14 ngày tiếp theo, tức ngang đoán mò.
  - Bài "sniper cohorts" (arXiv 2607.02795) tìm ra 1.012 nhóm ví lặp lại trong 10 người mua đầu. Nhóm làm số người mua tăng +16%, nhưng SOL đổ vào chỉ +6% và khoảng tin cậy chứa 0.
  - Đây là một tác giả độc lập, nên coi là kết quả tạm.
- **Marino et al.** (arXiv 2602.14860; 655.770 token, 9/2025): 0,63% tốt nghiệp. Dấu hiệu dự báo tốt nhất là SOL dồn vào nhanh trong ít giao dịch; token nhiều bot tốt nghiệp ít hơn. Bài mô hình hoá xác suất tốt nghiệp chứ không mô hình hoá lợi nhuận, và không có test ngoài mẫu.
- **Người làm thật:**
  - jmenzler (GitHub `pumpfun-retrospective`, tự báo cáo) đưa 7 SOL lên khoảng 1.000 SOL trong 2–4/2024 bằng cách đoán trước sniper lớn sẽ mua gì. Lợi thế đó chết từ cuối 4/2024.
  - Bot của Kamat (arXiv 2606.08232, 190 lệnh, giao dịch giấy) lãi +0,039 SOL; bỏ 3 lệnh tốt nhất là lỗ.

**Thống kê ví**
- Dune (Adam Tehc, 1/2025): 0,41% trong 13,55 triệu ví lãi trên $10k. Ngày 9/6/2025, 93/100 ví lãi nhất là bot.
- CoinGecko (2026) báo tới 73% ví có lãi vào 4/2026. Nhưng đó là lãi đã chốt, không lọc bot, và chỉ tính ví còn hoạt động (từ 5,2 triệu xuống 1,8 triệu ví/tháng). Dashboard Dune cùng thời điểm cho thấy 49–50,6% lỗ.

## 3. Phép đo của dự án: 77.043 launch, 27–29/9/2026

**Dữ liệu**

Lấy từ `loopholetape/pumpfun-launches` (Hugging Face), phần `launches`: từ 27/9 00:18 UTC, bộ giải mã đầy đủ, đặc trưng sớm được dựng lại cho mọi launch.

Chọn launch:
- Classic (không phải mayhem), quote SOL, đã có kết quả.
- Dev mua < 84,5 SOL. 45,5% token classic tốt nghiệp trong ba ngày này là *tự tốt nghiệp*: dev mua cả curve ngay trong lệnh tạo, không ai kịp vào.

Còn 77.043 launch, trong đó 1.322 tốt nghiệp (1,7%).

**Mô hình**
- Vé 0,5 SOL, phí 1,25% mỗi chiều, cộng 0,002 SOL phí ưu tiên/tip cho mỗi vòng mua–bán.
- Dòng token của mọi trader khác giữ nguyên. Vì curve là hằng số tích, giá trị của vé tại mọi thời điểm tính đúng từ reserve lịch sử.
- Luật thoát: chốt lời ở mức m. Nếu không chạm thì bán lúc tốt nghiệp. Nếu không tốt nghiệp thì giữ tới khi curve ngừng giao dịch.
- Giả định bán đúng ở mức m là **lạc quan**.

**Vị trí vào**
- *Ngay sau dev*: reserve bằng lệnh mua của dev, tức chỗ của bundle.
- *~1 giây*: reserve ở snapshot đầu tiên dưới 10 giây (trung vị 1,02 giây, p90 3 giây).
- *10–60 giây*.

**EV trung bình mỗi vé**

| Vị trí vào | chốt 1,5× | chốt 2× | chốt 3× | chốt 5× | chốt 10× | giữ tới tốt nghiệp |
|---|---|---|---|---|---|---|
| ngay sau dev | +5,6% | +6,1% | +5,5% | +5,5% | +8,8% | **+12,0%** |
| ~1 giây | −6,8% | **−7,9%** | −9,0% | −9,5% | −8,9% | −8,5% |
| 10–60 giây | −2,7% | −5,5% | −7,8% | −8,4% | −8,1% | −8,0% |

Ổn định qua các ngày:
- "Ngay sau dev, giữ": +12,3% / +12,2% / +11,7%. KTC 95% gộp ba ngày: **+10,9% … +13,2%**.
- "~1 giây, chốt 2×": −7,5% / −7,9% / −8,3%. KTC 95%: **−8,1% … −7,7%**.

Trung vị luôn âm. Tỷ lệ vé có lãi ở mốc ~1 giây: 13% khi chốt 1,5×, chỉ 1,5% khi giữ.

**Bộ lọc thăm dò** (vào ~1 giây, chốt 2×; chọn trên 27–28/9, kiểm tra trên 29/9)

| Nhóm | n | EV 27–28/9 | EV 29/9 |
|---|---|---|---|
| dev không mua | 12.958 | −2,7% | −3,1% |
| dev mua < 0,5 SOL | 26.268 | −4,0% | −4,8% |
| dev mua 0,5–1,5 SOL | 17.557 | −6,0% | −7,5% |
| dev mua 1,5–3 SOL | 10.948 | −14,1% | −16,0% |
| dev mua 3–10 SOL | 6.387 | −22,6% | −24,8% |
| dev mua ≥ 10 SOL | 626 | −28,8% | −14,0% |
| không ai mua trước mình | 28.977 | −4,0% | −3,8% |
| ≥ 5 SOL mua trước mình | 11.546 | −18,2% | −18,1% |
| 0 ví bundle | 28.488 | −3,8% | −3,7% |
| ≥ 5 ví bundle | 11.025 | −15,9% | −16,8% |
| creator lần đầu tạo token | 28.472 | −4,9% | −6,8% |
| creator đã tạo ≥ 100 token | 16.017 | −14,3% | −13,8% |
| creator từng có token tốt nghiệp | 10.752 | −18,5% | −19,0% |

Nhóm ít âm nhất là các launch không ai quan tâm: vé chỉ mất đúng phí. Nhóm âm nhất là các launch trông có triển vọng. Tỷ lệ tốt nghiệp của chúng cao hơn (dev ≥ 10 SOL: 11,7%; ≥ 5 ví bundle: 5,4%), nhưng giá vào cũng cao hơn và người vào trước bán vào tay mình.

**Đuôi phân phối**
- Vé ~1 giây chạm ≥ 10× ở 0,3% số trường hợp; vé ngay sau dev ở 1,6%.
- Sau tốt nghiệp, theo dữ liệu Slinky21 (6–7/2026, trước BOOST), đỉnh chia cho giá lúc tốt nghiệp có:
  - trung vị 1,05×, p90 7,3×, p99 115×;
  - 10,7% token đạt ≥ 6,8×.
- Ghép lại: khoảng 1,7% × 10% ≈ 0,17% số vé ở vị trí tốt nhất từng chạm x100. Đó là đỉnh nến, không phải giá bán được.

**Giới hạn**
- Dữ liệu theo launch, không có đường giá, nên không mô phỏng được cắt lỗ hay bán theo thời gian.
- Giả định chốt lời đúng mức là lạc quan.
- "~1 giây" là trạng thái ở snapshot, không phải một slot chính xác.
- Sniper thật còn gặp tx lỗi (mục 4).

Vì vậy, các số âm ở trên là **cận trên** cho người ngoài: thực tế chỉ có thể tệ hơn.

**Tái lập:** `research/sniper_launches.py` (cần `duckdb` và các file parquet của dataset).

## 4. Thị trường ở slot 0

Đo trên 112 launch SOL, 06/10/2026 [OC].

**Ai vào và trả giá bao nhiêu**
- Người ngoài mua được trong slot 0 ở 32% số launch, trung vị ở vị trí 130 tx sau lệnh tạo.
- Họ trả trung vị 1,35× giá đầu (p90 2,7×).
- Hết slot 0, giá trung vị ở 1,23×; các slot +1 đến +3 cộng thêm trung vị 0%.

**Mức độ cạnh tranh**
- 54% launch không có người mua bên ngoài nào trong slot 0–3.
- Launch có tranh chấp: trung vị 2 ví.
- Sniper chọn launch có dev mua lớn hơn: trung vị 0,79 SOL, so với 0,09 SOL ở các launch họ bỏ qua.
- Chỉ có 173 ví mua sớm; 2 ví vào ≥ 5 launch.
- Theo một thống kê thị phần terminal (6/2026): Axiom ~70%, Terminal (của pump.fun) 12,5%, GMGN 11,1%.

**Cách họ thoát**
- 79% người mua sớm bán trong khoảng 55 giây, ở giá trung vị 0,96× so với cuối slot 0 (p25 0,74×).
- Creator hoặc ví bundle bán trong vòng 3 slot ở 22% launch có tranh chấp, trong khoảng 11 giây ở 49%.

**Tỷ lệ tx lỗi**
- Tx chạm vào mint mới thất bại 38% ở slot 0, 58% ở slot +1, 68% ở slot +2, 77% ở slot +3. Phần lớn là lỗi trượt giá của pump.fun (6042/6002).
- Tính chung, 57% giao dịch của program pump.fun thất bại.
- Ví dụ một curve đã đọc: 911 chữ ký, chỉ 24 thành công.

## 5. Chi phí và hạ tầng để có mặt ở slot 0–2

**Phí**
- Phí curve 2 × 1,25%.
- Bot hoặc terminal thu thêm 0,7–1% mỗi chiều [V].
- Sniper thật trả trung vị khoảng 0,001 SOL phí ưu tiên, cộng 0,0006–0,0012 SOL tip mỗi tx [OC].
- Với vé 0,1 SOL, riêng tip và phí ưu tiên đã là 3–7% mỗi chiều.

**Phát hiện launch**
- Yellowstone gRPC: Helius LaserStream từ $499/tháng; Shyft $199–349/tháng.
- Shred stream: Helius $1.000/IP/tháng. Jito ShredStream ngừng từ 5/9/2026 và chuyển sang DoubleZero.

**Gửi lệnh**
- Jito block engine (Frankfurt, Amsterdam, …).
- Helius Sender (tip tối thiểu 0,001 SOL).
- bloXroute `submit-snipe`.

**Vị trí máy chủ**
- Gần Frankfurt hoặc Amsterdam: Đức nắm 34% stake, Hà Lan 20%.
- Vendor nói co‑location giúp vào slot 0 ở 89% lượt snipe migration [V]. Dự án không đo được độ trễ thật.

## 6. Dữ liệu forward (đang ghi)

**Census**
- Mọi lệnh tạo đều nhắc tới mint authority của pump.fun (`TSLvdd1pWpHVjahSpsvCXUbgwsL3JAcvokwaKt1eokM`). Đo được 190/190 tx thành công là lệnh tạo.
- Vì vậy, danh sách chữ ký của địa chỉ này là census đầy đủ các launch.
- Recorder gọi `getSignaturesForAddress` mỗi 60 giây (1 credit), lưu cursor trong Redis. Sau khi khởi động lại, nó quét ngược tối đa ~12 giờ.

**Mẫu**
- Chọn `sha256(chữ ký lệnh tạo) mod 10.000 < 200`, tức 2%.
- Cách chọn này xác định trước và không phụ thuộc kết quả của token.
- Khoảng 1.100 launch/ngày, trong đó ~700 là classic quote SOL.

**Đọc dữ liệu**

Hai giờ sau khi launch:
- Đọc lệnh tạo (1 credit) để biết mint, curve, quote, mayhem.
- Nếu quote là SOL: đọc mọi tx thành công của curve trong 2 giờ đó, cũ nhất trước, bằng Helius `getTransactionsForAddress` (10 credit/100 tx, tối đa 5.000 tx).
- Mỗi trade event giữ: slot, vị trí trong block, ví, mua/bán, số SOL, số token, reserve ảo sau lệnh, tên lệnh.
- Reserve phải nối liền từ lệnh này sang lệnh kế. Nếu đứt, tức là thiếu lệnh, và dòng đó được đánh dấu.
- Cửa sổ 2 giờ chứa 95% số lần tốt nghiệp mà sniper vào kịp.

**Ngân sách**
- Tối đa 30.000 credit/ngày (`PH_SNIPER_DAILY_CREDITS`; lúc đầu 20.000, nâng sau khi đo được một curve sôi động tốn ~140 credit cho 1.200 tx).
- Ngân sách fills của giả thuyết C giảm từ 300.000 xuống 270.000, nên trần tổng vẫn như cũ.
- Hết ngân sách trong ngày thì launch chờ tới ngày sau mới được đọc, không bị bỏ khỏi mẫu.

**Lưu trữ**
- Dữ liệu thô: `sniper-YYYY-MM-DD.jsonl` (gzip khi sang ngày).
- Kết quả mô phỏng gọn: Redis.
- `/api/sniper/rows` trả các kết quả đó.

**Lưới mô phỏng (thăm dò)**

Thời điểm vào: cuối slot tạo+k, với k = 0, 1, 2, 4, 8, 20, 40 (khoảng 0 đến 11 giây).

Luật thoát:
- `p`: chốt x2 / cắt lỗ 50% / bán sau 60 giây.
- `tp1.5` … `tp10`: chốt lời ở mức đó, nếu không thì giữ tới tốt nghiệp hoặc hết cửa sổ.
- `t10` … `t300`: bán sau 10–300 giây.
- `hold`: giữ.

Cỡ vé:
- 0,5 SOL cho mọi ô.
- Thêm 0,1 và 1 SOL cho luật chính.

**Giới hạn của mô phỏng**
- Mô hình đối chứng: dòng token của người khác giữ nguyên.
- Không mô hình bot khác phản ứng với vé của mình.
- Không tính tx lỗi.
- Vé vào ở *cuối* slot, sau mọi lệnh trong slot đó. Đây là vị trí bi quan trong slot, nhưng sát với vị trí đo được của người ngoài.
- Lệnh bán khớp ở cuối slot kế tiếp sau khi điều kiện kích hoạt.
- Nếu tốt nghiệp trước khi thoát: bán ở trạng thái cuối của curve. Giả định này lạc quan, vì thực tế phải bán trên PumpSwap.

**Vé xổ số (mô tả, không kiểm định)**
- Giữ vé từ slot +2. Nếu token tốt nghiệp, nhân giá trị lúc tốt nghiệp với đỉnh nến 5 phút của pool trong 24 giờ (`peak_x` của dòng survivor). Ra tỷ lệ chạm x10 và x100.

## 7. Giả thuyết S (đăng ký trước)

**Thời điểm.** Đăng ký bằng commit đầu tiên chứa mục này, trước `2026-10-07 03:00:00 UTC` (`PREREG_S_TS = 1791342000`). Mỗi dòng chỉ được tính hai giờ sau launch. Lúc đăng ký, census chưa chạy trên production, nên chưa có kết quả nào của mẫu kiểm định.

**Mẫu kiểm định.** Mọi launch thoả tất cả các điều kiện:
- lệnh tạo từ `PREREG_S_TS` trở đi;
- nằm trong mẫu băm 2%;
- quote SOL, không phải mayhem;
- đọc được đường giá (`status = ok`);
- curve chưa hoàn tất ở slot vào.

Mỗi mint chỉ tính một lần.

**Vé.** 0,5 SOL (đã gồm phí 1,25%), mua ở cuối slot tạo+2, tức sau mọi giao dịch của slot đó, khoảng 0,5–0,8 giây sau lệnh tạo.

**Thoát.** Điều kiện nào đến trước thì bán theo điều kiện đó:
- (a) giá trị vé ≥ 2× số SOL bỏ ra;
- (b) giá trị vé ≤ 0,5×;
- (c) đủ 60 giây sau lúc vào: bán ở trạng thái lúc đó.

(a) và (b) được xét sau mỗi giao dịch; lệnh bán khớp ở cuối slot kế tiếp. Nếu curve hoàn tất trước đó, vé bán ở trạng thái cuối của curve.

**Chi phí.** Phí curve lấy theo event (1,25% mỗi chiều), cộng 0,002 SOL mỗi vòng. Tx lỗi không được tính, điều này có lợi cho S.

**Đại lượng đo.**
- net = (SOL nhận về − 0,002) / 0,5 − 1.
- EV = trung bình net; khoảng tin cậy 95% theo xấp xỉ chuẩn.
- Ô chính là `k2_p` trong `/api/sniper/summary` → `prereg`.

**Tiêu chí** (chỉ áp dụng khi n ≥ 2.000):
- **KILL** nếu cận trên KTC 95% của EV < 0, hoặc 1% vé tốt nhất chiếm ≥ 50% tổng lãi.
- **PASS** nếu cận dưới KTC 95% > 0 **và** EV vẫn > 0 khi vào ở slot +1 và slot +4 (cùng luật thoát).
- Các trường hợp còn lại: **INCONCLUSIVE**.

**Luật dựa trên đặc trưng (S2 trở đi).**
- Chỉ dùng thông tin có tại lúc vào (cuối slot tạo+k):
  - giá vào so với giá đầu, SOL thật trong curve;
  - dev mua bao nhiêu; số ví và lượng SOL mua trong slot 0;
  - số người mua trước mình; dev đã bán chưa;
  - các cờ của lệnh tạo (mayhem, cashback, holder reward, quote).
- Thăm dò trên `[PREREG_S_TS, PREREG_S_TS + 14 ngày)`, trên mẫu classic.
- Chọn tối đa 3 luật, mỗi luật là điều kiện đơn giản trên tối đa 3 đặc trưng.
- Đăng ký bằng commit, với `since` là giờ tròn kế tiếp. Luật đã đăng ký không được sửa.
- Mỗi luật được kiểm định một lần trên launch từ `since` trở đi, khi n ≥ 2.000, theo tiêu chí trên.

**Không được làm.**
- Đổi slot vào, cỡ vé, luật thoát, chi phí, ngưỡng, hay mô hình đối chứng sau khi thấy dữ liệu kiểm định.
- Bỏ dòng khỏi mẫu, ngoài các điều kiện đã nêu.
- Dòng mà vé chưa thoát hết trong phần đã đọc (cửa sổ bị cắt) được đếm là `unresolved` và báo kèm. Nếu chúng vượt 2% mẫu, kết luận phải nêu điều đó.
- Nếu sửa mô phỏng (tăng `SIM_VERSION`), mẫu kiểm định chỉ dùng dòng tính bằng phiên bản mới, tính lại từ dữ liệu thô `sniper-*.jsonl`, và ghi lại thay đổi ở đây.
- Coi lưới thăm dò, mẫu trước `PREREG_S_TS`, hay phép đo lịch sử ở mục 3 là bằng chứng kiểm định.

**Ý nghĩa của kết luận.**
- KILL nghĩa là snipe từ bên ngoài, ở tốc độ của một bot tốt, là âm EV trên dữ liệu hiện tại.
- PASS chỉ nghĩa là đáng đo tiếp ở quy mô lớn hơn. Dự án không giao dịch thật: theo Nghị định 284/2026, cá nhân Việt Nam giao dịch qua nhà cung cấp chưa được cấp phép có thể bị phạt.
- Vị trí có lãi là vị trí của người tạo token (bundle ngay trong lệnh tạo). Dự án không theo đuổi hướng đó: nó là tạo token để bán cho người đến sau.

## Nguồn

**Dữ liệu**
- [loopholetape/pumpfun-launches](https://huggingface.co/datasets/loopholetape/pumpfun-launches): 982.709 launch, 31/8–29/9/2026, kèm KNOWN_ISSUES.
- [Slinky21/Pumpfun_Memecoin_Corpus](https://huggingface.co/datasets/Slinky21/Pumpfun_Memecoin_Corpus): 6–7/2026, `postgard_outcomes`.

**Tài liệu pump.fun**
- [pump-public-docs](https://github.com/pump-fun/pump-public-docs): IDL, phí, buyback, holder rewards.
- [pump.fun fees](https://pump.fun/docs/fees).

**Bài báo**
- [Meme Coin Factories (CCS'26)](https://arxiv.org/abs/2609.10246)
- [Kamat, sniper cohorts](https://arxiv.org/abs/2607.02795)
- [Kamat, graduation audit](https://arxiv.org/abs/2607.02823)
- [Kamat, bot](https://arxiv.org/abs/2606.08232)
- [Marino et al.](https://arxiv.org/abs/2602.14860)
- [Luo et al. (WWW'26)](https://arxiv.org/abs/2601.08641)
- [MELT](https://arxiv.org/abs/2602.13480)
- [Mongardini & Mei (USENIX'26)](https://arxiv.org/abs/2507.01963)
- [Bot transaction failures (ISSTA'25)](https://arxiv.org/abs/2504.18055)

**Phân tích on‑chain và báo chí**
- [Pine Analytics: Exit Liquidity Machines](https://pineanalytics.substack.com/p/exit-liquidity-machines)
- [Decrypt: Dune, ví lãi > $10k](https://decrypt.co/300403/pump-fun-traders-millionaires)
- [CoinGecko: trader quay lại](https://www.coingecko.com/research/publications/pump-fun-traders-are-making-a-comeback)
- [crypto.news: 49% lỗ tháng 3](https://crypto.news/pump-fun-data-shows-49-of-march-traders-in-the-red-as-platform-locks-fees/)
- [The Block: graduation sau BOOST](https://www.theblock.co/post/409815)
- [The Block: graduation giữa tháng 6](https://theblock.co/post/404806)
- [ChainCatcher: BOOST](https://www.chaincatcher.com/en/article/2277632)
- [CoinDesk: buyback PUMP](https://www.coindesk.com/markets/2026/04/29/pump-fun-burns-36-of-pump-supply-in-usd370-million-wipe-locks-50-revenue-into-ongoing-buybacks)
- [Thị phần terminal 6/2026](https://thelearningpill.substack.com/p/the-state-of-the-trenches-h126)
- [jmenzler/pumpfun-retrospective](https://github.com/jmenzler/pumpfun-retrospective)

**Hạ tầng**
- [Jito: gửi tx độ trễ thấp](https://docs.jito.wtf/lowlatencytxnsend/)
- [Jito tip floor](https://bundles.jito.wtf/api/v1/bundles/tip_floor)
- [Helius Sender](https://www.helius.dev/docs/sending-transactions/sender)
- [Helius getTransactionsForAddress](https://www.helius.dev/docs/rpc/gettransactionsforaddress.md)
- [bloXroute submit-snipe](https://docs.bloxroute.com/solana/trader-api/api-endpoints/transaction-submisson/submit-snipe)
- [SIMD‑0525 (slot ngắn hơn)](https://github.com/solana-foundation/solana-improvement-documents/blob/main/proposals/0525-reduce-slot-times.md)
- [Data center của validator](https://validators.solutions/en/validators/data-centers/)
- [RPCFast: snipe pump](https://rpcfast.com/blog/how-to-launches-snipe-pump) [V]
- [Chorus One: độ trễ tx](https://chorus.one/reports-research/transaction-latency-on-solana-do-swqos-priority-fees-and-jito-tips-make-your-transactions-land-faster)
