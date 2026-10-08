# Sổ filter sống của bot "rây": vòng sáng lập (08/10/2026)

> "không bắt bẫy chưa từng tồn tại. crews evolve tuần-đến-tuần (MMaaS công nghiệp hóa) — nên filter chain là sinh vật: tuần nào cũng đọc journal, filter nào bắt thiếu thì vá. công việc duy trì là nghề, không phải bug."

Tài liệu này biến câu trên thành một quy trình chạy được. Nội dung gồm:
- mọi filter đã tìm, đã kiểm và đã vá trong hai ngày 07–08/10/2026, mỗi filter có định nghĩa và số liệu;
- **sổ đăng ký** sau vòng sáng lập: active, shadow, info, theo dõi, nghỉ hưu;
- **sổ theo dõi**: các kiểu bẫy chưa đủ bằng chứng;
- **quy trình bảo trì hằng tuần**;
- **lịch kiểm forward** đầu tiên.

Tài liệu đi kèm:
- [`SIEVE.md`](SIEVE.md): năm luật và đặc tả bot v1;
- [`PREREG-SIEVE-R1.md`](PREREG-SIEVE-R1.md): khối đăng ký trước của vòng này;
- [`research/sieve/`](../research/sieve/): code chấm đã đóng băng.

**Trạng thái của các con số.** Mọi số liệu đến từ khoảng 26 giờ dữ liệu (06/10 20:53Z → 07/10 23:03Z), gồm 55 mint bẫy và 11 mint thắng.
- Phần "holdout" ở mục 2 đã bị chính các agent kiểm chứng xem, nên từ đây nó chỉ còn là dữ liệu tìm tòi.
- Bằng chứng thật đầu tiên là các tuần forward: các launch sau 07/10 23:03Z, chưa ai xem kết quả.

## Tóm tắt

1. **Triết lý thành luật.**
   - "Không bắt bẫy chưa từng tồn tại" thành **luật đếm**: một kiểu bẫy chỉ thành ứng viên khi có ≥ 3 mint bẫy, của ≥ 2 creator, trong ≥ 2 ngày.
   - "Filter chain là sinh vật" thành **vòng đời có version**: theo dõi → shadow → active ("cờ chưa kiểm") → TRÁNH, rồi giáng hạng hoặc nghỉ hưu.
   - "Tuần nào cũng đọc journal" thành **lịch tuần cố định**: chấm một lần, đọc hồ sơ, vá, red team, chủ bot duyệt.
2. **Vòng tìm và vòng kiểm** (19 filter, 5 lăng kính): chỉ hai filter đứng được, cả hai đều có lý do từ trước khi xem holdout.
   - **SH-DEV-1**: dev + creator giữ ≥ 3%.
   - **N-MMAAS-WAVE-STREAM**: ≥ 4 ví mua cùng slot, cỡ lệnh lệch ≤ 2%. Đây là filter duy nhất còn ý nghĩa sau hiệu chỉnh kiểm định bội.
   - Các filter cấu trúc đơn giản đứng được. Các filter "thông minh" (flippers, top-10, trí nhớ ví) sập khi ra khỏi mẫu.
3. **Chain active trung thực** = cổng 11,66 SOL + (DEV hoặc WAVE-STREAM). Trên holdout nó bắt 16/32 bẫy và không giết coin thắng nào.
4. **Vòng vá 1** đọc 40 dòng bẫy (31 mint) mà chain active bỏ sót và xếp chúng thành 6 kiểu đạt luật đếm. Có 10 bản vá được đề xuất:
   - **2 đăng ký shadow:** CLD-ORPHAN-v1 (vòng kín: insider đã đi, curve đắt so với số người giữ) và N-WM-EXIT2-v2b (lượng hàng mà ví "exit công nghiệp" bán ra);
   - 5 thành info hoặc theo dõi;
   - 3 nghỉ hưu, cộng một biến thể chọn sau khi đã thấy kết quả, cũng cho nghỉ và không bao giờ được chấm.
5. **Những điều vòng vá học được quý hơn các filter:**
   - Đám đông xả dây chuyền là chuỗi **cắt lỗ** của người mua gần hoà vốn, không phải hàng rẻ bị xả, nên không thấy được trước D.
   - Sụp muộn là lỗi của **giờ thoát**: 22/28 vé kiểu này từng lời ≥ 30%.
   - Farm script nhận ra được, nhưng kết cục hai đầu (bẫy hoặc tốt nghiệp). Nó là **nhãn thông tin** ("nếu xả thì xả trong 1 slot"), không phải veto.
   - Có một luật **phân loại ví** không cần nêu tên ví và một phép **kiểm đủ lệnh** dùng được trên luồng sống.
6. **Dấu hiệu "crew tiến hoá" đầu tiên** (yếu, p = 0,07). Ở khối cuối, farm lọt lưới vì dev giữ 1,9–2,75%, ngay dưới ngưỡng 3%, và không còn sóng cùng cỡ chính xác. Đầu dò "cận ngưỡng" sẽ theo dõi điều này từ tuần forward đầu tiên.
7. **Không vá nào phân biệt được với may rủi trong mẫu** (p 0,087 và 0,11). Đăng ký shadow chỉ có nghĩa là đưa đi kiểm forward.
   - Lần chấm đầu: 15/10.
   - Quyết định thăng hạng hoặc huỷ đầu tiên: 22/10.
8. **Vẫn không có tín hiệu mua.** Cộng mọi shadow vào active, phần còn lại có mean −1,7%/vé, và đó là số trong mẫu. Bot vẫn chỉ là công cụ phủ quyết riêng tư.

## 1. Triết lý thành quy trình

| Câu của chủ bot | Thành luật gì | Ở đâu |
|---|---|---|
| "không bắt bẫy chưa từng tồn tại" | **Luật đếm**: ≥ 3 mint bẫy, ≥ 2 creator, ≥ 2 ngày. Dưới mức đó → sổ theo dõi, kèm hồ sơ. Ngưỡng chỉ đặt theo cơ chế hoặc theo phân phối không nhìn nhãn, viết ra trước khi chấm. | mục 7 (bước 0 và 4); sổ theo dõi ở mục 5 |
| "crews evolve tuần-đến-tuần" | **Đầu dò né** cho từng filter active: canary tỷ lệ cờ, tỷ lệ bẫy lọt nằm cận ngưỡng, đầu dò riêng (dev chuyển hàng, sóng có jitter…). | mục 7 (bước 8) |
| "filter chain là sinh vật" | **Vòng đời có version**: theo dõi → shadow → active → TRÁNH; giáng và nghỉ hưu theo luật viết sẵn. Không bao giờ sửa ngưỡng tại chỗ: mỗi bản vá là một id mới. | mục 7 (bước 4–7) |
| "tuần nào cũng đọc journal, filter nào bắt thiếu thì vá" | **Lịch tuần**: khoá tuần → chấm → viết hồ sơ bẫy lọt → đề xuất vá, red team soát, chủ bot duyệt. | mục 7 (bước 3) |
| "công việc duy trì là nghề" | Người phân tích, red team tách biệt, và chủ bot duyệt là ba vai khác nhau. Bot không tự sửa mình. | mục 7 (bước 2) |

Điều mà triết lý này **không** được trở thành: đào bới dữ liệu. Nếu tuần nào cũng vá cho khớp những bẫy vừa thấy rồi chấm trên chính tuần đó, chuỗi lọc sẽ đẹp trên giấy và chết ở tuần sau. Vòng sáng lập đã cho thấy rõ điều này:
- SH-FLIP-1 đứng thứ ba trên explore (p = 0,021) nhưng sập trên holdout;
- chuỗi do agent chọn trên holdout trông tốt hơn 50% so với khi chọn trung thực.

## 2. Vòng tìm và vòng kiểm (round 0)

### Dữ liệu

- **Census**: mẫu băm 5% các launch, đủ mọi giao dịch trên curve trong 2 giờ đầu.
- **Journal**: mỗi dòng là một ứng viên (mint, D) ở D = 120/300/600 giây, qua cổng F0 (5 ≤ SOL thật < 70; ≥ 5 giao dịch và ≥ 3 ví mua trong 120 giây gần nhất).
  - Vé 0,5 SOL ở slot dslot+1, phí 1,25% mỗi chiều, 0,002 SOL.
  - **Bẫy**: lỗ ≥ 50% sau 30 phút. **Thắng**: lời ≥ 100% sau 30 phút.
- **Kho**: 206 dòng, các launch tạo từ 06/10 20:53Z đến 07/10 23:03Z, khoảng 26 giờ.
  - Explore (trước 07/10 15:15Z): 111 dòng, 50 bẫy, 8 thắng.
  - Holdout: 95 dòng, 32 bẫy (22 mint), 8 thắng (5 mint).
- **Lưới dày**: D = 60…900 giây, cách nhau 60 giây; 461 dòng explore, 370 dòng holdout. Các dòng của cùng một mint tương quan rất mạnh, nên lưới chỉ dùng để mô tả.

### Vòng tìm

Workflow `wf_888a2d8b-3ba` chỉ dùng nhãn explore. Năm agent, mỗi agent một lăng kính:
- **sharpen**: mài lại các cờ v1;
- **anatomy**: mổ xẻ cách bẫy xả hàng;
- **early**: sổ creator, "nhà máy coin";
- **wallet memory**: trí nhớ ví qua các launch;
- **MMaaS**: dấu vết của dịch vụ market-making/bundle công nghiệp.

Kết quả: 19 filter, cộng các biến thể.

### Vòng kiểm

Workflow `wf_6385b300-44f` gồm ba bước:
1. Mỗi họ filter có một verifier tự viết lại code từ định nghĩa chữ. Tất cả tái lập được số explore; riêng FACTORY lệch, nhưng lệch vô hại.
2. Verifier chấm trên holdout, rồi một agent lắp chuỗi.
3. Một agent red team tấn công toàn bộ, kiểm:
   - nhìn trước;
   - proxy ẩn (odds ratio Mantel-Haenszel trong tầng, placebo khớp số cờ);
   - mất lệnh trên luồng sống;
   - nhãn mong manh;
   - kiểm định bội (p hoán vị theo mint, hiệu chỉnh BH).

Bảng dưới là số holdout, chỉ là cái nhìn đầu tiên:
- **cờ / B / T**: số dòng có cờ / số bẫy / số thắng trong các dòng đó;
- **tỷ lệ bẫy**: tỷ lệ bẫy trong các dòng có cờ ở tầng 13–70 SOL. Nền của tầng là 0,54;
- **p**: p hoán vị theo mint của U = bẫy − 3 × thắng;
- **red team**: đứng / nghi / bác.

| Filter | Định nghĩa ngắn | cờ / B / T | tỷ lệ bẫy | p | red team | tầng mới |
|---|---|---|---|---|---|---|
| **N-MMAAS-WAVE-STREAM** | ≥ 4 ví (trừ dev) mua cùng một slot, cỡ lệnh cả cụm lệch ≤ 2% | 12 / 10 / 0 | 0,83 | **0,0027** (q = 0,071) | đứng | **active** |
| **SH-DEV-1** | dev + creator giữ ròng ≥ 3% cung, SOL thật ≥ 11,73 | 12 / 11 / 0 | 0,91 | 0,028 | đứng | **active** |
| SH-SG-1 | nhóm tạo (dev, creator, ví mua ở slot tạo/+1) mua ≥ 20 SOL, và đã bán ≥ 50% hoặc có ≥ 5 ví cùng cỡ | 18 / 10 / 0 | 0,67 | 0,042 | nghi | shadow, có cổng |
| N-MMAAS-WAVE | như WAVE-STREAM nhưng lệch ±0,5% và tx_index cách ≤ 64 | 4 / 4 / 0 | 1,00 | 0,030 | nghi | shadow, cần tx_index |
| N-MMAAS-SPLDIST | ≥ 5 ví có sự kiện đầu tiên là **bán** (hàng đến qua transfer) | 10 / 6 / 0 | 0,86 | 0,10 | nghi | shadow, cần kiểm đủ lệnh |
| N-WM-EXIT2 | ≥ 2 ví "chỉ bán, không mua" đã thấy ở launch trước | 33 / 14 / 1 | 0,58 | 0,13 | **bác** | sửa thành EXIT2-v2 |
| SH-WASH-1 | ví đổi chiều ≥ 3 lần chiếm ≥ 30% volume | 14 / 9 / 1 | 0,67 | 0,33 | bác | info |
| N-ANAT-FADE | SOL thật ≥ 13 và đã rơi ≥ 30% từ đỉnh trước D | 13 / 11 / 1 | 0,85 | 0,21 | bác: proxy của tầng curve | info |
| N-ANAT-LOCKSTEP | cặp ví mua đồng bộ ≥ 2 lần giữ ≥ 10% float | 9 / 4 / 1 | 0,67 | 0,62 | bác | info |
| N-LTE-FACTORY | creator có ≥ 5 launch trong 30 ngày, curve 13–30 SOL | 12 / 9 / 1 | 0,75 | 0,35 | bác: proxy tầng 13–30 | info |
| N-WM-XIN | hàng transfer-in bị ví exit đã biết bán | 46 / 20 / 2 | 0,66 | 0,075 | đứng ở mức info | info |
| N-MMAAS-MSTX | một giao dịch chứa lệnh bán của ≥ 2 ví | 3 / 1 / 0 | – | – | mới thấy 2 mint | theo dõi |
| N-MMAAS-DUSTHOLD | ≥ 20 ví chỉ mua bụi (< 0,005 SOL) đúng 1 lần | 2 / 1 / 0 | – | – | 3 mint explore | theo dõi |
| N-ANAT-DUSTFARM | ≥ 20 lệnh mua bụi, chiếm ≥ 50% số lệnh mua trong 120 giây | 0 / 0 / 0 | – | – | cả bằng chứng chỉ là 1 mint | nghỉ, giữ field |
| SH-TOP10-1 | top-10 ≥ 20% khi insider đã rời | 35 / 18 / 3 | 0,53 | 0,36 | REJECT | nghỉ |
| SH-TIN-1 | transfer-in bán ≥ 0,5% cung trong 60 giây | 19 / 7 / 3 | 0,55 | 0,78 | REJECT | nghỉ |
| SH-FLIP-1 | ≥ 8 ví lướt đã thoát | 10 / 3 / 0 | 0,38 | 0,48 | REJECT | nghỉ |
| S1_spike | +10 SOL thật trong 60 giây | 12 / 5 / 2 | 0,42 | 0,71 | REJECT | chỉ làm ngữ cảnh |
| N-WM-TDINV | ví từng xả vào bẫy trước đang giữ hàng | 60 / 21 / 8 | 0,49 | 0,90 | REJECT: gắn cờ cả 5/5 mint thắng | nghỉ |
| N-WM-BL3 | ví bán-quá-mua lặp lại đang giữ hàng | 10 / 3 / 3 | 0,33 | 0,95 | REJECT | nghỉ, giữ danh sách ví |
| S1_early_hold | ví ở slot tạo còn giữ ≥ 5% | 33 / 13 / 3 | 0,60 | 0,47 | nghiêng về coin thắng | info |

Bài học rút ra từ bảng:
- Các filter **cấu trúc, đơn giản** đứng được: dev giữ hàng, sóng mua cùng cỡ, bundle ở slot tạo.
- Các filter "**thông minh**" sập khi ra khỏi mẫu: flippers, top-10, transfer-in, trí nhớ ví.
- SH-FLIP-1 là bài học rõ nhất: trên explore nó đứng thứ ba (p = 0,021), trên holdout chỉ 3/10.

### Chuỗi lọc trên holdout

Cột "tiết kiệm" là số SOL không mất nhờ bỏ qua các vé bị phủ quyết, tính trên toàn bộ vé 0,5 SOL.

| Chuỗi | Bẫy bắt | Thắng bị giết | Tiết kiệm | Ghi chú |
|---|---|---|---|---|
| Không phủ quyết | 0/32 | 0/8 | 0 | phần qua có mean −12,2%/vé |
| Cổng trần (chặn mọi coin ≥ 11,73 SOL) | 32/32 | 7/8 | +1,73 SOL | coin thắng duy nhất được tha nằm dưới cổng |
| v1, có cổng | 31/32 | 6/8 | +3,70 SOL | ngang cổng trần: v1 nghỉ hưu |
| Cổng + DEV \| SG \| EXIT2 \| WAVE-STREAM (agent lắp chuỗi chọn) | 28/32 | 1/8 | +8,76 SOL | **đã chọn trên chính holdout** |
| Cùng quy trình, nhưng chỉ chọn trên explore | 25/32 | 3/8 | +5,85 SOL | ước lượng trung thực của quy trình |
| **Cổng + DEV \| WAVE-STREAM (active trung thực)** | 16/32 | **0/8** | +4,80 SOL | cả hai có lý do từ trước khi xem holdout |

Ngay cả chuỗi tốt nhất, phần được qua vẫn có KTC theo mint chứa 0: +0,114/vé, KTC −0,23 đến +0,50. **Không có tín hiệu mua.**

### Red team nói gì về cả quy trình

1. **Holdout đã bị tiêu.** Các verifier và agent lắp chuỗi đều đã xem kết quả, nên từ giờ chỉ dữ liệu sau 07/10 23:03Z là sạch.
2. **Luật PROMOTE cũ quá lỏng.** Một filter ngẫu nhiên cùng số cờ cũng đạt 17–66% số lần, nên khoảng 7,7/26 filter "đạt" chỉ do may rủi. Sau hiệu chỉnh BH chỉ còn WAVE-STREAM.
3. **Đơn vị bằng chứng là mint.** Holdout chỉ có 22 mint bẫy và 5 mint thắng. Hơn thua giữa các chuỗi chủ yếu do 3–4 mint thắng được tha.
4. **Nhãn mong manh.** Vào ở T+90 giây (tốc độ người thật) thì chỉ 21/32 bẫy holdout còn là bẫy.
5. **Luồng sống khác census.**
   - Mất ngẫu nhiên 5% lệnh nhỏ, mức mà dung sai lệch reserve không thấy được, làm EXIT2 bật thêm 248 cờ, 30 trong đó trên coin thắng.
   - Các filter "bán nhiều hơn mua" (EXIT2, SPLDIST, TIN, XIN) cần kiểm đủ lệnh.
6. **Proxy trá hình.**
   - EXIT2 và XIN thực chất là "coin đông ví".
   - FADE và FACTORY là "đang ở tầng 13–30".
   - WASH gần với động lượng.
7. **Ví hạ tầng.** ARu4n5mF xuất hiện trong 6,1% launch classic và bán 1,33 lần số đã mua. Một mình nó tạo 8/33 cờ EXIT2 trên holdout và cả 4 lần EXIT2 giết coin thắng trên lưới dày.
8. **Không có nhìn trước.** Cắt lệnh ở dslot không đổi cờ nào trên 576 dòng.
9. **Chưa kiểm được tiền đề "crew tiến hoá theo tuần"**, vì dữ liệu mới có 26 giờ.

## 3. Vòng vá 1: đọc journal

Workflow `wf_9d08da03-2d3` gồm ba bước:
- một agent mổ xẻ mọi bẫy mà chain active trung thực (cổng + DEV + WAVE-STREAM) còn lọt;
- mỗi kiểu bẫy đạt luật đếm có một agent thiết kế bản vá;
- red team chấm các bản vá.

**Kho** là explore + holdout cũ: 206 dòng, các launch tới 07/10 23:03Z. Holdout đã bị xem, nên theo quy trình nó nhập vào kho tìm tòi. **Forward** là các launch sau 07/10 23:03Z; chưa ai xem kết quả của chúng.

Vì mới có 26 giờ dữ liệu, luật đếm vòng này dùng **khối thời gian** thay cho ngày:
- B1: trước 07/10 06:00Z (49 dòng, 21 bẫy);
- B2: 06:00–15:15Z (62 dòng, 29 bẫy);
- B3: 15:15–23:03Z (95 dòng, 32 bẫy).

Một kiểu bẫy thành ứng viên khi có ≥ 3 mint bẫy, ≥ 2 creator và ≥ 2 khối.

### Chain active lọt gì

| Khối | Mint bẫy được active bắt | WAVE-STREAM | DEV | Mint thắng bị giết |
|---|---|---|---|---|
| B1 | 7/12 (58%) | 42% | 25% | 0/2 |
| B2 | 9/21 (43%) | 19% | 29% | 1/4 |
| B3 | 10/22 (45%) | 23% | 32% | 0/5 |

Chain active lọt 40 dòng bẫy của 31 mint. Mint thắng duy nhất nó giết là ukjpAvka@120 (+255%), qua DEV: dev mua 5,86 SOL lúc tạo và giữ 17,5%, đúng kiểu sắp rug, nhưng dev không xả.

### Các kiểu bẫy (theo cơ chế xả sau D)

| Kiểu | Cơ chế | Mint lọt / creator / khối | Luật đếm | Shadow bắt |
|---|---|---|---|---|
| **Đám đông xả dây chuyền** (crowd-cascade) | Curve đông: 104–453 ví, nhiều bot và lệnh cỡ preset của terminal. Holder sớm và top-10 bán bằng rất nhiều lệnh nhỏ riêng lẻ (3–7 người mỗi slot); tiền mới không đỡ nổi. | 11 / 11 / B1–B3 | đạt (về số) | SG 3, SPLDIST 3 |
| **Thoát đồng loạt nhiều ví** (swarm-exit) | Một người điều khiển cho nhiều ví holder bán **trong cùng một slot**. Hai cỡ: farm vài trăm ví, và crew 30–70 ví. | 8 / 8 / B1–B3 | đạt | SG 3 |
| ↳ farm lớn (swarm-mega) | 207–535 holder, gần hết là ví dùng một lần. Bẫy cắt mức −50% sau 28–59 giây; một slot có 225–423 người bán, thường qua giao dịch nhiều chữ ký. | 4 / 4 / **chỉ B3** | **không đạt** → theo dõi | SG 1 |
| ↳ crew nhỏ (swarm-crew) | 17–48 holder ôm curve 12–25 SOL; sau D có 10–25 holder bán cùng một slot. | 4 / 4 / B1–B3 | đạt | SG 2 |
| **Sụp muộn sau sóng 2** (late-collapse) | Vé sống qua 5 phút. Sóng tiền mới đẩy curve lên 25–154%, rồi sụp trước mốc thoát 30 phút. Lúc D trông y hệt coin thắng. | 7 / 7 / B1–B3 | đạt về số, nhưng **không phải mục tiêu veto**: đây là lỗi của giờ thoát | SPLDIST 1 |
| **Vòng kín rút cạn** (closed-loop-drain) | 22–35 holder, sau D gần như không có tiền mới; chính holder bán dần tới 0. 5/6 vào ở 13–17 SOL, sát cổng. | 6 / 6 / B1–B3 | đạt | 0 |
| Rút cạn sát cổng (near-gate-drain) | Thẻ ghép: vào ở 11,7–14,7 SOL, curve bị rút về ≤ 0,03 SOL. Ở dải này 8/13 dòng "không bẫy" cũng lỗ 38–49%: ranh giới bẫy chỉ là vài % độ sâu. | 6 / 6 / B1–B3 | mô tả mép cổng, không phải cơ chế crew | 0 |
| Thoát nhiều chữ ký (multisig-exit) | Một giao dịch chứa lệnh bán của ≥ 2 ví (nút "bán tất cả ví"). | 4 / 4 / chỉ B3 | không đạt → theo dõi | SG 2 |
| Insider thoát qua ví transfer | 53ny3h2z@300: nhóm tạo 19 ví (12 ví mua đúng 2,8 SOL) xả 80 SOL qua 37 ví mới sau 29 phút. | 1 | theo dõi | SG |
| Cá voi xả một lệnh | 51y19mwC@120: một ví sớm giữ 8,4% bán 15 SOL trong một lệnh. | 1 | theo dõi | SG |
| Bán bậc thang (ladder-sell) | Ví sớm bán 40–50 lần, rải đúng sau lệnh mua của người khác. | 2 / 2 / chỉ B2 | theo dõi | SG 1 |

### Dấu hiệu "crew tiến hoá" đầu tiên (chưa đủ mạnh)

1. **Kiểu farm tăng dần qua các khối.** Thoát đồng loạt chiếm 1/12 mint bẫy ở B1, 5/21 ở B2 và 7/22 ở B3.
   - Ở B2, chain active bắt 4/5 farm: dev giữ ≥ 3,3%, hoặc có sóng mua cùng cỡ chính xác.
   - Ở B3 nó **lọt 6/7**: dev chỉ giữ **1,9–2,75%**, ngay dưới ngưỡng 3% (dev mua 0,54–0,79 SOL), và không còn sóng cùng cỡ chính xác.
2. **Sóng cùng cỡ chính xác (≤ 0,5%) giảm dần** trong các mint bẫy: 5/12 → 4/21 → 2/22.
3. **Nhưng có thể chỉ là nhiễu.**
   - Fisher p = 0,07 cho cả hai thay đổi trên.
   - Dải dev 1,5–3% cũng tăng ở mint **không** bẫy (1/6 → 2/8 → 4/14), nên đó là thay đổi của cả quần thể, không riêng crew.
   - Sóng "có jitter" (lệch 2–10%) phổ biến ở mint không bẫy ngang mint bẫy, nên chưa thấy crew thay sóng chính xác bằng sóng jitter.
   - 26 giờ không đủ để chứng minh crew tiến hoá.

   Đây đúng là thứ mà đầu dò "cận ngưỡng" (mục 8 của quy trình) phải theo dõi từ tuần đầu forward.

### Các bản vá được đề xuất

**Luật chung cho mọi agent thiết kế:**
- Chỉ dùng giao dịch tới dslot.
- Ngưỡng đặt theo lý do cơ học, hoặc theo một luật viết ra **trước khi** chấm. Luật dùng nhiều nhất: số tròn gần phân vị 80% của feature trên các dòng qua cổng, không nhìn nhãn.
- Mọi đề xuất chấm theo cùng một bộ:
  - p hoán vị theo mint;
  - odds ratio Mantel-Haenszel trong tầng;
  - 8 placebo khớp số cờ;
  - giá trị thêm vào chain active;
  - mất lệnh 5% và 20%;
  - nhìn trước.

Mọi số dưới đây là **trong mẫu**, trên 26 giờ.

| Kiểu bẫy | Đề xuất | Định nghĩa | Kho: cờ / B / T | Thêm so với active | p | Agent tự xét |
|---|---|---|---|---|---|---|
| Đám đông xả dây chuyền | CC-CHEAPLOAD-v1 | holder còn hoà vốn ở mức −50% của vé có đủ hàng để tự đẩy giá xuống đó | 36 / 17 / 6 | +4 mint bẫy, giết 6 mint thắng, −4,0 SOL | 0,90 | bỏ |
| | CC-TOPDIST-v1 | top-10 đã bán ≥ 35% số họ giữ trong 60 giây trước D | 28 / 20 / 3 | +8 / giết 3 / −1,7 SOL | 0,37 | theo dõi |
| Thoát đồng loạt | P1-SWARM-SCRIPTED-v1 | người mua đầu là script: tỷ lệ lệnh đầu đúng cỡ preset ≤ 0,185 (z ≤ −3), và ≥ 50% ví đó còn ôm | 10 / 6 / 2 | +4 / giết 2 / −0,45 SOL | 0,76 | theo dõi; **dùng làm nhãn thông tin** |
| | P2-SWARM-VET-v1 | ≥ 10 holder từng bán chung một slot ở một launch trước | 2 / 1 / 0 | +1 / 0 | 0,68 | theo dõi |
| Sụp muộn | LC-XFERSUP-v1 | hàng transfer-in đã bán ≥ 5,5% cung trước D | 28 / 18 / 1 | +9 / giết 1 / +3,1 SOL | 0,19 | theo dõi |
| | LC-REPUMP-v1 | đã xả sâu ≥ 70% rồi bơm lại ≥ 50% | 16 / 12 / 1 | +4 / giết 1 | 0,29 | bỏ |
| Vòng kín | **CLD-ORPHAN-v1** | nhóm tạo đã bán ≥ 50% số mua, dev + creator < 3%, SOL thật / số holder ≥ 0,50 | 12 / 10 / **0** | **+9 mint bẫy (9 creator, cả 3 khối), 0 thắng, +3,3 SOL** | 0,11 | **đăng ký shadow** |
| | CLD-REACTFLOAT-v1 | ≥ 60% float trong tay ví đã mua lại hoặc đã bán bớt | 21 / 12 / 1 | +8 / giết 1 | 0,37 | bỏ |
| Sửa EXIT2 | N-WM-EXIT2-v2a | ≥ 2 ví loại INDUSTRIAL (theo luật phân loại ví WTYPE-v1) có mặt | 20 / 13 / 0 | +6 / 0 / +3,7 SOL | 0,15 | theo dõi |
| | **N-WM-EXIT2-v2b** | ví INDUSTRIAL đã bán ≥ 2% cung mà không mua trên curve này | 35 / 24 / 1 | **+12 mint bẫy (12 creator), 0 thắng mới, +6,6 SOL** | 0,087 | **đăng ký shadow** |

### Red team chấm vòng vá

Red team tự viết lại 5 đề xuất chỉ từ định nghĩa chữ: hai đề xuất được đề nghị shadow, cộng P1, TOPDIST và XFERSUP.
- Bốn đề xuất khớp với code của người thiết kế trên 1.037/1.037 dòng.
- TOPDIST lệch, vì định nghĩa chưa nói rõ có chặn lượng bán theo từng ví hay không. Điểm này nay đã được ghi rõ vào định nghĩa.

| Đề xuất | Quyết định | Phản bác mạnh nhất |
|---|---|---|
| **CLD-ORPHAN-v1** | **shadow** | Kết quả "0 coin thắng" nằm trên lưỡi dao: 3 coin thắng cách ngưỡng < 1%. Hạ một nấc ngưỡng là giết 2–3 coin thắng; đặt ngưỡng trên hai khối rồi chấm khối thứ ba thì giết 1. Mất 5% lệnh nhỏ thì 6/10 lần bật cờ trên một coin thắng. Trong cùng tập "insider đã đi", thay "SOL mỗi holder" bằng "ít ví mua nhất" cho đúng kết quả đó. Vẫn được đăng ký, vì đây là đề xuất duy nhất chạm tới kiểu vòng kín và crew nhỏ, và shadow thì không chặn gì. |
| **N-WM-EXIT2-v2b** | **shadow** | Trong mẫu không tách được khỏi placebo "curve đã sụt từ đỉnh" (U 22 so với 21); trong tầng real × D × sụt, MH chỉ còn 1,19. Nó thắng được "khối transfer-in không dùng danh tiếng" và "coin đông ví", nên roster không phải proxy của coin đông. Tỷ lệ cờ trên luồng sống chưa biết: trong census nó tăng từ 0,10 lên 0,26 khi kho danh tiếng tăng từ 25% lên 100%. |
| N-WM-EXIT2-v2a | info | Khớp số ví mua thì không thêm bẫy nào; ưu điểm duy nhất là ít dòng thắng hơn, trên 11 mint thắng. |
| P1-SWARM-SCRIPTED-v1 | info (nhãn) | Kết cục hai đầu; placebo "giá vừa giảm" thắng nó. |
| P2-SWARM-VET-v1 | theo dõi | Chỉ 1 mint bẫy trong 1 khối; cần luồng có slot cho toàn chương trình. |
| CC-TOPDIST-v1 | info | Giết 3 mint thắng; placebo thắng nó. |
| LC-XFERSUP-v1 | info | Chính là `v1_transfer_in` cắt cao hơn 11 lần; nhạy với mất lệnh. |
| CC-CHEAPLOAD-v1, POSTHOC-CC-FRAGILE-v0, LC-REPUMP-v1, CLD-REACTFLOAT-v1 | nghỉ hưu | Âm tính; FRAGILE là chọn sau khi thấy kết quả, không bao giờ được chấm. |

### Những gì vòng vá dạy

1. **Đám đông xả dây chuyền không phải hàng rẻ bị xả.**
   - Đo bằng công thức curve: tới lúc D, holder mua rẻ đã đi hết. Ở các dòng bẫy kiểu này, phần hàng của người còn lời chỉ bằng 2,6% lượng cần bán để kéo vé xuống −50%. Con số đó là 44% ở dòng không bẫy và 70% ở coin thắng.
   - Bẫy ở đây là một **chuỗi cắt lỗ** của người mua gần hoà vốn, phần lớn bằng các nút preset của terminal. Trước D không thấy được.
2. **Farm script có dấu nhận ra được, nhưng kết cục hai đầu.**
   - Trong 16 mint farm trên lưới dày, 12 xả trong một slot, 7–60 giây sau khi vào; 4 tốt nghiệp.
   - Dùng nó làm veto thì lỗ tiền. Dùng làm **nhãn thông tin** thì có ích: *"farm script: nếu xả thì xả trong 1 slot, dưới 1 phút; người thật không kịp thoát"*.
   - Farm cũng không chỉ có ở B3: nó đã xuất hiện ở B2, nhưng xả trước mốc D = 120 nên journal không thấy.
3. **Sụp muộn là lỗi của giờ thoát, không phải của lúc vào.**
   - 22/28 vé thuộc kiểu này từng lời ≥ 30% trong 30 phút (trung vị +84%) rồi mới sụp.
   - Đòn bẩy là một luật thoát hoặc chốt lời. Muốn dùng phải đăng ký riêng trên mọi dòng, vì nó cũng cắt phần lời của coin thắng.
4. **Vòng kín không phân biệt được với một curve nhỏ, yên tĩnh sát cổng.** Ở dải 13–17 SOL, vé chỉ lỗ 50% khi curve bị rút 76–91%, tức là mọi holder đều đi và không ai vào. CLD-ORPHAN là phép thử duy nhất có lý do cơ chế ("insider đã đi, curve đắt so với số người giữ").
5. **EXIT2 sửa được một nửa.**
   - Luật phân loại ví WTYPE-v1 không cần nêu tên ví nào mà vẫn xếp ARu4n5mF là ví **gom hàng** ở mọi cửa sổ dữ liệu.
   - Có 28 ví **exit công nghiệp**. Chúng không bao giờ mua trên curve, mỗi lần bán khoảng 0,9 SOL, khoảng 13 giây sau lệnh tạo, và mỗi ví làm cho 3–22 creator khác nhau.
   - Bản v2b đo **lượng hàng** những ví này bán, không đếm số ví. Nó không còn là proxy "coin đông ví", nhưng vẫn ngang placebo "curve đang giảm" (p trong tầng 0,12).
6. **Kiểm đủ lệnh dùng được.**
   - Phép kiểm: mỗi lệnh phải giải thích đúng thay đổi reserve, sai số 1 lamport, không cần tx_index.
   - Kết quả trên kho:
     - 0/1.698 launch classic hỏng;
     - bắt được 1.055/1.055 lần rút ngẫu nhiên một lệnh;
     - 0 báo động giả trên 400 launch bị xáo thứ tự.
   - Nhưng nếu luồng sống mất 5% lệnh nhỏ:
     - khoảng 30% launch có lỗ hổng;
     - **85/95 dòng journal của holdout** không qua được phép kiểm, vì ứng viên thường là curve đông lệnh.
   - Mọi filter cần đủ lệnh (DEV, SG, SPLDIST, v2b, ORPHAN) khi đó phải đọc bù (21–51 credit mỗi launch), hoặc ghi "THIẾU DỮ LIỆU". Chỉ WAVE-STREAM gần như không bị ảnh hưởng: mất 1/12 cờ.
   - Launch mayhem không chấm được: reserve của chúng đổi ngoài sự kiện giao dịch.

## 4. Sổ đăng ký sau vòng sáng lập

Số "kho" là trong mẫu, trên các dòng qua cổng. B / T là số dòng bẫy / thắng; p là p hoán vị theo mint.

### Active: hiện cho chủ bot dưới dạng "cờ (chưa kiểm)"

| Filter | Định nghĩa | Cần dữ liệu gì | Kho | Bước tiếp |
|---|---|---|---|---|
| **GATE_E** | SOL thật ở trạng thái vào ≥ 11,66. Dưới mức này vé 0,5 SOL không thể lỗ 50% (giải tích). Mọi veto chỉ áp dụng phía trên cổng. | vSol trong luồng (miễn phí) | 82/82 dòng bẫy ở trên cổng | Chỉ tính lại khi pump.fun đổi phí hoặc tham số curve |
| **SH-DEV-1** | dev + creator giữ ròng ≥ 3% cung | giao dịch từ lúc tạo | 30 dòng, 24 B / 1 T; 16 mint bẫy, 1 mint thắng; holdout p 0,028 | TRÁNH khi ≥ 200 cờ forward (khoảng 8 ngày census) |
| **N-MMAAS-WAVE-STREAM** | ≥ 4 ví (trừ dev, creator, router) mua trong cùng một slot sau slot tạo, mỗi lệnh ≥ 0,01 SOL, cả cụm (max − min)/max ≤ 2% | slot và lượng của mỗi lệnh | 29 dòng, 26 B / 0 T; 14 mint bẫy; holdout q 0,071 | TRÁNH khi ≥ 200 cờ (khoảng 7,5 ngày). **Theo dõi suy giảm**: tỷ lệ mint bẫy bắt được 42% → 19% → 23% |

Trên kho, ACTIVE chặn 51 dòng (42 bẫy, 1 thắng) và để qua 155 dòng (40 bẫy, 15 thắng), mean −10,8%/vé.

### Shadow: 5/8 chỗ, chỉ ghi sổ, không hiện, không chặn

| Filter | Định nghĩa | Cần dữ liệu gì | Kho | Điều kiện riêng |
|---|---|---|---|---|
| SH-SG-1 (có cổng) | nhóm tạo mua ≥ 20 SOL, và (đã bán ≥ 50% hoặc ≥ 5 ví cùng cỡ) | slot của lệnh mua đầu (đọc trả phí khi live) | 24 dòng, 17 B / 2 T; p 0,31 | luật coin thắng nhiều khả năng sẽ loại nó |
| N-MMAAS-SPLDIST | ≥ 5 ví có sự kiện đầu tiên là bán | đủ lệnh, đã kiểm reserve | 20 dòng, 16 B / 1 T; p 0,15 | chỉ chấm dòng đã kiểm reserve |
| N-MMAAS-WAVE (strict) | như WAVE-STREAM, lệch ±0,5%, khoảng tx_index ≤ 64 | tx_index (không có trên PumpPortal) | 20 dòng, 19 B / 0 T; p 0,005 | về info nếu tỷ lệ bắt < 10% hai tuần liền (đang 42% → 14% → 9%) |
| **N-WM-EXIT2-v2b** (mới) | các ví INDUSTRIAL (theo WTYPE-v1) đã bán ≥ 2% cung mà không mua trên curve này | trí nhớ ví tích luỹ từ kho sáng lập (live: 7 ngày), tỷ lệ tính trên 1.000 launch; đủ lệnh | 35 dòng, 24 B / 1 T; 16 mint bẫy của 16 creator; p 0,087 | phải thắng placebo sụt-từ-đỉnh, giá-vừa-giảm, real thấp, transfer-in thô, đông ví; huỷ nếu một ví gây > 30% số cờ |
| **CLD-ORPHAN-v1** (mới) | nhóm tạo đã bán ≥ 50% số đã mua, dev + creator < 3%, SOL thật / holder ≥ 0,50 | đủ lệnh, đã kiểm reserve, slot lệnh mua đầu (20–30 credit mỗi ứng viên khi live) | 12 dòng, 10 B / 0 T; 9 mint bẫy của 9 creator; p 0,11 | phải thắng placebo "ít ví mua nhất / ít lệnh nhất / real thấp nhất" trong cùng tập insider-đã-đi; huỷ nếu giết một coin thắng nằm trong 5% của bất kỳ ngưỡng nào |

Trên kho, ACTIVE + 5 shadow chặn 93 dòng (70 bẫy, 4 thắng; 46/55 mint bẫy, 4/11 mint thắng) và để qua 113 dòng (12 bẫy, 12 thắng), mean −1,7%/vé. Đây là số trong mẫu và nhiều khả năng quá lạc quan.

### Info: ghi giá trị thô, không phán quyết

- **N-WM-EXIT2-v2a**: số ví INDUSTRIAL có mặt.
- **P1-SWARM-SCRIPTED-v1**: nhãn thông tin *"farm script: nếu xả thì xả trong 1 slot, dưới 1 phút"*. Ghi kèm p_hat, z, số lệnh mua đầu, NP_hold và lượng lamport chính xác.
- **CC-TOPDIST-v1**: ngưỡng 0,35 đóng băng; lượng bán của mỗi ví bị chặn trên bằng số nó giữ tại w0.
- **LC-XFERSUP-v1**: chính là `v1_transfer_in`, cắt ở 0,055.
- **CLD-ORPHAN-v1d**: ORPHAN chỉ đếm holder ≥ 0,1% cung, ngưỡng 0,65. Dùng để đo crew né bằng ví bụi.
- **REF-DRAIN75**: mốc so sánh mức curve.
- Các cờ cũ: SH-WASH-1, N-ANAT-LOCKSTEP, N-LTE-FACTORY (+REPEAT1), N-WM-XIN, N-MMAAS-MSTX, N-MMAAS-DUSTHOLD.
- N-ANAT-FADE: dùng làm **thước placebo**, không làm thành viên.
- Các cờ v1 tầng 0 và tầng 1.

### Theo dõi

P2-SWARM-VET-v1 và các kiểu bẫy ở mục 5.

### Nghỉ hưu

- N-WM-EXIT2 v1 (thay bằng v2b), CC-CHEAPLOAD-v1, POSTHOC-CC-FRAGILE-v0, LC-REPUMP-v1, CLD-REACTFLOAT-v1.
- Từ vòng 0: SH-TOP10-1, SH-TIN-1, SH-FLIP-1, N-WM-TDINV, N-WM-BL3, N-ANAT-DUSTFARM, SH-CHAIN-v2, và chuỗi v1 với vai trò chuỗi veto.

## 5. Sổ theo dõi: những bẫy chưa đủ bằng chứng

Sau vòng này, 9/55 mint bẫy trong kho vẫn **không bị gì bắt** (tính cả active và shadow):
- 3 farm lớn ở B3: AVaDpFQ9, Ak2GeCR9, B7SwdKF7;
- 4 đám đông xả dây chuyền: 4qYxeZrV, EZZC2MCZ, Fb7zu3wV, HmAfq5i1;
- 1 sụp muộn: A8TaVU44;
- 1 vòng kín: CweohnTZ.

| Mục theo dõi | Nền hiện có | Thành ứng viên khi forward cho thấy |
|---|---|---|
| **Farm lớn né DEV/WAVE**: dev 1,9–2,75%, không sóng cùng cỡ chính xác | 4 mint, 4 creator, chỉ B3. Cơ chế này đã có ở B2 nhưng xả trước D = 120. | ≥ 3 mint bẫy farm, ≥ 2 creator, ≥ 2 ngày, với dev < 3% và không sóng chính xác, **và** một dấu hiệu trước D tha được farm tốt nghiệp (B3E8PKcE, FtHBuzmn, XQwBHMVg, 9jDLpAu1) |
| **Thoát nhiều chữ ký** | 4 mint lọt ở B3; 2 mint ở B2 đã bị bắt | lệnh bán nhiều chữ ký **trước D** ở ≥ 3 mint bẫy, ≥ 2 creator, ≥ 2 ngày (live phải gom theo chữ ký) |
| **Ví farm tái dùng** (P2-VET) | 4MJMKMXK: 35 holder đến từ một launch 8 phút trước | ≥ 3 mint bẫy trên luồng đầy đủ, thắng placebo khớp số holder |
| Insider thoát qua ví transfer | 53ny3h2z@300 | ≥ 2 mint nữa, từ creator khác |
| Cá voi xả một lệnh | 51y19mwC@120 | ≥ 2 mint nữa |
| Bán bậc thang | 53ny3h2z, 26dXHm8K (chỉ B2) | có dấu hiệu trước D ở một khối hoặc ngày thứ ba |
| Đám đông xả dây chuyền (phần còn lại) | đạt luật đếm, nhưng không có dấu hiệu trước D | **chỉ qua luật thoát**: phút sụp bắt đầu 0–235 giây sau khi vào. Cần một luật thoát/cảnh báo đăng ký riêng, có độ trễ T+45/T+90. |
| Sụp muộn | 22/28 vé từng lời ≥ 30% | chỉ qua luật thoát, hoặc ảnh chụp holder tầng 2 (3 credit) thấy hàng transfer đang nằm chờ |
| Vòng kín (phần còn lại) | CweohnTZ | một định nghĩa mới trên dữ liệu forward |
| Rút cạn sát cổng (11,66–17,4 SOL) | mép cổng, không phải crew | một nghiên cứu về cổng, không phải filter |

**Độ trôi cần đo mỗi tuần**:
- tỷ phần farm trong các mint bẫy (1/12 → 5/21 → 7/22);
- tỷ lệ bắt của WAVE strict (42% → 14% → 9%);
- phân phối dev 1,5–3%, trong cả mint bẫy lẫn mint không bẫy.

Né chỉ thành phát hiện khi 2 tuần forward lặp lại mẫu hình của B3.

## 6. Kế hoạch forward

**Dữ liệu.** Các launch classic có `t0 > 1791414202` (sau 07/10 23:03Z) trong census 5%. Điều kiện này được lọc trước mọi bước khác.

| Tuần | Launch | Chấm |
|---|---|---|
| W1 | t0 ≤ 1792019002 (14/10 23:03Z) | khoảng 15/10 02:00Z. Chỉ đếm và kiểm các điều kiện huỷ, chưa thăng. |
| W2 | t0 ≤ 1792623802 (21/10 23:03Z) | khoảng 22/10 02:00Z. Quyết định thăng/huỷ đầu tiên trên W1 + W2, hiệu chỉnh BH trên 5 shadow. |

**Khối lượng dự kiến**, theo tỷ lệ của kho (sai số ±30–50%):
- mỗi ngày: khoảng 1.560 launch, 189 dòng journal, 126 dòng qua cổng, khoảng 50 mint bẫy và 10 mint thắng;
- số cờ band mỗi ngày: DEV 27,5; WAVE-STREAM 26,6; SG 22; SPLDIST 18; WAVE strict 18; EXIT2-v2b 32; ORPHAN 11;
- mức đếm (≥ 20 cờ band từ ≥ 8 mint bẫy) đạt sau 1–2 ngày;
- nhãn TRÁNH (≥ 200 cờ) xét sớm nhất cuối W2 cho DEV, WAVE-STREAM và v2b; ORPHAN cần khoảng 3 tuần.

**Phép thử sắc nhất là luật coin thắng**: tối đa 1 mint thắng bị giết trên mỗi 10 mint bẫy bắt được.
- ORPHAN có khoảng 58 mint bẫy mỗi tuần, nên chỉ được giết tối đa 5 mint thắng.
- SG theo tỷ lệ trong mẫu (khoảng 13 mint thắng trên 71 mint bẫy mỗi tuần) nhiều khả năng sẽ trượt.

**Điều kiện phụ thuộc.**
- Census phải tiếp tục chạy với cùng tỷ lệ mẫu và cùng code.
- Các file census từ 06/10 trở đi phải còn trên volume của bot. Kho danh tiếng của EXIT2-v2b là kho tích luỹ, nên mỗi lần chấm phải đọc lại toàn bộ.
- Trước khi bất kỳ filter dựa danh tiếng nào lên active, phải chạy một tuần trên luồng đầy đủ để đo tỷ lệ cờ thật.
- Kiểm đủ lệnh cho thấy, nếu luồng sống mất khoảng 5% lệnh nhỏ thì khoảng 30% launch có lỗ hổng. Các launch đó phải đọc bù (21–51 credit mỗi launch) hoặc ghi "THIẾU DỮ LIỆU".

## 7. Quy trình bảo trì hằng tuần: nghề của người giữ rây

Chuỗi lọc là sinh vật: nó phải lớn theo bẫy thật. Nhưng nếu tuần nào cũng "vá" cho khớp những gì vừa thấy, nó thành đào bới dữ liệu và sẽ chết ở tuần sau. Quy trình dưới đây giữ được cả hai điều. Phần lớn lấy từ đề xuất của red team.

### 0. Ba nguyên tắc gốc

1. **Mỗi tuần chỉ được chấm một lần**, sau khi tuần đã khoá. Chấm xong, tuần đó mới nhập vào **kho tìm tòi**. Không bao giờ vừa tìm vừa chấm trên cùng một tuần.
2. **"Không bắt bẫy chưa từng tồn tại" thành luật đếm.**
   - Một kiểu bẫy chỉ thành ứng viên filter khi đã thấy ở ≥ 3 mint bẫy khác nhau, của ≥ 2 creator/dev khác nhau, trong ≥ 2 ngày khác nhau.
   - Ít hơn thì vào **sổ theo dõi**, kèm hồ sơ.
3. **Đơn vị bằng chứng là mint, không phải dòng.** Lưới dày (60–900 giây) chỉ để mô tả.

### 1. Ghi gì (tự động)

- Mỗi ứng viên F0 ở các D chính 120/300/600 giây, cộng lưới dày 60–900 giây.
- Danh tính: mint, creator, dev, phiên bản chương trình pump.fun, phiên bản định nghĩa của từng filter, hash của chuỗi.
- Trạng thái curve: SOL thật ở dslot, ở slot vào, ở T+45 giây và ở T+90 giây.
- Toàn bộ giao dịch thô.
- Chất lượng dữ liệu:
  - khớp reserve sau **mỗi** lệnh; ghi mọi chênh lệch, kể cả nhỏ hơn 0,2 SOL;
  - có tx_index hay không;
  - độ phủ lệnh tạo trong ngày.
- Net thô ở 10, 30, 60 phút và giữ tới cuối, cho cả ba điểm vào. Nhãn bẫy/thắng tính lại từ net thô.
- Giá trị thô của mọi feature, và cờ của mọi filter (active, shadow, info), cờ của chuỗi.
- Dòng cảnh báo bot đã hiện, hành động của chủ bot, và giá khớp thật.
- **Sổ ô**: mọi phép đo đã xem trong tuần (filter × ngưỡng × tầng × D), kể cả những ô bị bỏ. Con số này dùng để hiệu chỉnh kiểm định bội.
- Ngày có độ phủ < 90%, hoặc > 5% ứng viên lệch reserve, bị đánh dấu "không chấm" với các filter cần đủ lệnh (EXIT2, SPLDIST, XIN, WAVE-STREAM).

### 2. Ai làm gì

- **Người phân tích** (Claude) chạy code chấm đã đóng băng trong `research/sieve/` với commit hash cố định, viết hồ sơ bẫy lọt và coin thắng bị giết, rồi soạn đề xuất.
- **Red team**, một agent tách biệt với người đề xuất, soát mọi đề xuất trước khi đăng ký. Nó kiểm:
  - nhìn trước (cắt lệnh ở dslot thì cờ không được đổi);
  - proxy tầng curve: odds ratio trong tầng real × D, so với placebo khớp số cờ;
  - mất 5% lệnh nhỏ;
  - số mint làm nền;
  - ví hạ tầng.
- **Chủ bot** là người duyệt duy nhất cho đăng ký, thăng hạng, giáng hạng và huỷ. Bot không bao giờ tự sửa mình.

### 3. Lịch tuần (UTC)

Mỗi tuần là 604.800 giây, nối tiếp nhau từ mốc của PREREG-SIEVE-R1:
- W1 gồm các launch tạo trong (07/10 23:03Z, 14/10 23:03Z];
- W2 gồm các launch tạo trong (14/10 23:03Z, 21/10 23:03Z];
- các tuần sau nối tiếp như vậy.

| Ngày | Việc |
|---|---|
| Ngày 0, 23:03Z | Khoá tuần W. |
| Ngày 1 (sau khoảng 3 giờ, khi mọi launch đã đủ 2 giờ giao dịch) | Tải census, rồi chấm tuần W bằng code đóng băng. Chi tiết bên dưới. |
| Ngày 2 | Viết hồ sơ cho mọi bẫy lọt và mọi coin thắng bị giết (`archetype.py`). Xếp mỗi hồ sơ vào một kiểu đã biết, hoặc đánh dấu "mới". Đếm theo luật đếm. |
| Ngày 3 | Đề xuất bản vá nếu có, qua red team, chủ bot duyệt, rồi commit một khối PREREG mới. |

Phần chấm ở ngày 1 gồm:
- tỷ lệ bẫy nền theo tầng (5–13, 13–30, 30–70) và theo D;
- mỗi filter:
  - số cờ;
  - bẫy và thắng, theo dòng và theo mint;
  - tỷ lệ bẫy có cờ / không cờ trong từng tầng, kèm KTC Wilson;
  - odds ratio trong tầng;
  - p hoán vị theo mint, hiệu chỉnh BH trên mọi filter được chấm;
  - SOL tiết kiệm riêng (bỏ nó ra khỏi chuỗi active thì mất bao nhiêu);
- các chuỗi đặt cạnh nhau: không phủ quyết, cổng trần, v1, active, active + shadow.

### 4. Một bản vá

- Mỗi bản vá là một **định nghĩa mới có version**. Không bao giờ sửa ngưỡng của định nghĩa cũ tại chỗ.
- Bản vá viết bằng code, kèm:
  - ngưỡng cố định;
  - phạm vi (tầng, D);
  - danh sách mint bẫy làm nền, đạt luật đếm, lấy từ kho tìm tòi;
  - cái giá: số mint thắng bị giết trong kho;
  - tiêu chí thăng, giáng, huỷ viết sẵn.
- Ngưỡng chỉ được đặt theo lý do cơ học (ví dụ sàn −50% ở 11,66 SOL lúc vào), hoặc từ phân phối trong kho tìm tòi. Không bao giờ đặt theo tuần đang chạy shadow.
- Tối đa 2 đề xuất mới mỗi tuần, và tối đa 8 định nghĩa shadow cùng lúc.
- Ví hạ tầng (kiểu ARu4n5mF) chỉ được loại bằng một luật phân loại ví đã đăng ký trước. Không loại tay sau khi đã thấy kết quả.

### 5. Shadow

- Chạy trên mọi ứng viên F0, chỉ ghi, không ảnh hưởng nhãn hiện cho chủ bot.
- Chỉ được xét thăng hạng khi có đủ cả ba:
  - ≥ 2 tuần chưa ai xem lúc đề xuất;
  - ≥ 20 cờ ở tầng ≥ 13 SOL;
  - các cờ đó đến từ ≥ 8 mint bẫy khác nhau.

### 6. Thăng hạng

**Từ shadow lên active**, hiện cho chủ bot dưới dạng "cờ (chưa kiểm)". Phải đạt **tất cả**:
- tỷ lệ bẫy có cờ cao hơn không cờ trong từng tầng đã đăng ký;
- p hoán vị theo mint < 0,05 sau BH;
- giết ≤ 1 mint thắng trên mỗi 10 mint bẫy bắt được;
- SOL tiết kiệm riêng trong chuỗi active > 0 ở cả hai nửa thời gian;
- vẫn đứng khi vào ở T+45 và T+90 giây;
- mất 5% lệnh nhỏ (mô phỏng) không lật quá 20% số cờ.

**Từ active lên TRÁNH**, theo SIEVE mục 5:
- ≥ 200 cờ forward;
- chênh mean ≤ −10 điểm, KTC không chứa 0;
- cận dưới Wilson của lift > 1.

### 7. Giáng hạng và nghỉ hưu

- **Active xuống shadow** khi có một trong ba:
  - 2 tuần liền SOL tiết kiệm riêng âm;
  - 1 tuần giết ≥ 2 mint thắng mà số bẫy bắt được < 3 lần số đó;
  - 2 tuần liền tỷ lệ bẫy có cờ ≤ không cờ (với ≥ 10 cờ).
- **Shadow xuống info** sau 4 tuần không đạt thăng hạng. Feature vẫn được ghi.
- **Filter miễn phí không bao giờ bị xoá vì im lặng.** Luật 5 cũ ("7 ngày không bắt gì thì cắt") bị bỏ: một filter im lặng có thể chính là lý do crew đổi cách làm.
- **pump.fun đổi chương trình** (phí, thưởng, BOOST, tham số curve): mọi filter active về shadow, rồi chấm lại từ đầu trên dữ liệu sau thay đổi.

### 8. Phát hiện bị né

Crew tiến hoá thì filter sẽ bị né. Mỗi tuần đo cho từng filter active:
- **Canary**: tỷ lệ cờ trong ứng viên F0, theo tầng. Nếu giảm > 50% so với trung bình 4 tuần trong khi tỷ lệ bẫy nền không giảm, thì nghi bị né hoặc mất dữ liệu. Kiểm dữ liệu trước.
- **Cận ngưỡng**: phần bẫy lọt có feature trong khoảng 70–100% ngưỡng. Nếu phần này tăng 2 tuần liền, nghi crew đang đứng sát ngưỡng.
- **Đầu dò né riêng** cho từng filter:
  - DEV: sổ của dev giảm mà không có lệnh bán trên curve, tức là chuyển hàng sang ví mới;
  - WAVE: độ lệch cỡ lệnh trong cụm tăng (sóng có "jitter"), lệnh nằm liền nhau, sóng toàn cỡ preset;
  - SG: lệnh mua rải ra khỏi slot tạo;
  - EXIT2: ví mua bụi trước rồi bán nhiều hơn số đã mua.
- **Kiểu bẫy mới** trong hồ sơ đạt luật đếm → mở đề xuất ở bước 4.

Một lần né đã xác nhận được vá bằng một định nghĩa **mới**, rồi đi lại các bước 4 đến 6.

### 9. Không bao giờ

- Chỉnh ngưỡng hay thành viên chuỗi trên tuần đang dùng để chấm.
- Gọi một tập là "holdout" hay "forward" khi đã có người xem kết quả của nó.
- Vá để bắt đúng cái bẫy vừa lọt, rồi chấm bản vá trên chính tuần đó.
- Thêm filter cho kiểu bẫy mới thấy ở 1–2 mint.
- Loại ví khỏi danh sách sau khi đã thấy kết quả.
- Đổi định nghĩa bẫy/thắng, chân trời 30 phút hay điểm vào mà không tạo version mới và chấm song song với bản cũ.
- Dùng lưới dày làm bằng chứng độc lập.
- Chấm filter bán-quá-mua trên dữ liệu thiếu lệnh.
- Để bot tự "phẫu thuật" chính nó.
- In chữ "MUA", hay chia sẻ tín hiệu.

## 8. Code: `research/sieve/`

Thư mục scratch của phiên làm việc sẽ mất, nên toàn bộ phần chấm đã được đóng gói vào repo. Gói chỉ dùng thư viện chuẩn của Python 3.11, chạy bằng `python3 -I`, cho kết quả tất định.

| File | Việc |
|---|---|
| `filters.py` | Sổ đăng ký `REGISTRY`: mỗi id/version là một hàm trả `(fired, raw)`, kèm tầng và dữ liệu cần có. `FROZEN` giữ hash của từng định nghĩa: `--check` báo ngay khi có định nghĩa bị sửa tại chỗ. Có phép kiểm đủ lệnh `check_chain`, không cần thứ tự lệnh. |
| `journal.py` | Dựng journal từ file census. Tuỳ chọn: `--from-t0` / `--to-t0`; `--dense` (lưới 60–900 giây); `--lookahead-test` (cắt ở dslot); `--drop-small 0.05` (mô phỏng mất lệnh). |
| `score.py` | Bảng điểm tuần. Gồm: tỷ lệ nền; từng filter với p, q, MH, placebo tốt nhất và SOL tiết kiệm riêng; các chuỗi đặt cạnh nhau; danh sách bẫy lọt và coin thắng bị giết; canary. `--diff` liệt kê cờ bị lật giữa hai journal. |
| `archetype.py` | Gắn kiểu bẫy (theo cơ chế xả sau D) cho từng bẫy, rồi in bảng luật đếm cho các bẫy lọt. |

**Kiểm tái lập.** Trên kho sáng lập, gói khớp mã của người thiết kế **0 lệch trên 1.037 dòng**:
- cờ của 22 filter cũ, nhãn và feature;
- raw của 13 định nghĩa mới;
- k/T/W/U/p/MH khớp bảng của red team.

Dựng hai cửa sổ của kho mất khoảng 6 giây. Mất 5% lệnh nhỏ sinh đúng 248 cờ ma cho EXIT2 v1, khớp số red team đã đo.

**Tải census và lệnh hằng tuần:** xem [`research/sieve/README.md`](../research/sieve/README.md). Census tải qua `/api/files` và `/api/export/file/<tên>` của bot; không cần bí mật nào.

## 9. Kết luận

1. Triết lý của chủ bot đúng, và đã thành quy trình. Bẫy thật quả có nhiều kiểu: farm script, crew nhỏ, vòng kín, ví exit công nghiệp, bundle ở slot tạo, dev ôm hàng, sóng mua cùng cỡ. Dấu hiệu đầu tiên của việc crew đứng sát ngưỡng cũng đã xuất hiện ngay trong 26 giờ.
2. Nhưng phần lớn các "bản vá" hấp dẫn đều thua những placebo rẻ tiền như "curve vừa giảm" hay "đang ở tầng 13–30". Vì vậy nghề giữ rây chủ yếu là **từ chối** vá, nhiều hơn là vá:
   - 10 đề xuất → 2 shadow;
   - 19 filter vòng đầu → 2 active.
3. Hai bài học về thiết kế đáng giá hơn mọi filter:
   - **Hai kiểu bẫy lớn nhất (đám đông xả dây chuyền và sụp muộn) không thể phủ quyết trước D.** Chỗ can thiệp là luật thoát hoặc cảnh báo khi đang giữ vé. Đó là một giả thuyết riêng cần đăng ký riêng, chưa có trong dự án.
   - **Mọi filter bán-quá-mua đều cần kiểm đủ lệnh.** Trên luồng sống, điều này tốn credit đọc bù hoặc phải bỏ không chấm.
4. Bot vẫn chỉ là công cụ phủ quyết riêng tư. Không có tín hiệu mua, và không chia sẻ tín hiệu.

## Nguồn

- Workflow `wf_888a2d8b-3ba` (vòng tìm), `wf_6385b300-44f` (vòng kiểm và red team), `wf_9d08da03-2d3` (vòng vá 1: mổ xẻ, 5 agent thiết kế, red team, đóng gói), 07–08/10/2026.
- Dữ liệu: census mẫu băm 5% của bot (`sniper-2026-10-06/07/08`), các launch tạo tới 07/10 23:03Z.
- Định nghĩa đầy đủ và luật thăng/giáng: [`PREREG-SIEVE-R1.md`](PREREG-SIEVE-R1.md). Code: [`research/sieve/`](../research/sieve/).
