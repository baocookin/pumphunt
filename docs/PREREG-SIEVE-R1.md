# PREREG-SIEVE-R1: chuỗi lọc rây, vòng sáng lập (đăng ký 08/10/2026)

Văn bản này cố định những điều sau trước khi xem bất kỳ kết quả forward nào:
- bộ lọc nào chạy thật (active) và bộ lọc nào chạy bóng (shadow);
- định nghĩa và ngưỡng của từng bộ lọc;
- luật thăng, giáng và huỷ.

Mọi con số trên pool là trong mẫu (in-sample), chỉ để mô tả, không phải bằng chứng.

## 1. Dữ liệu và thời điểm

- **Pool (đã xem, chỉ là khám phá):**
  - Gồm các launch classic có `t0 ≤ 1791414202` (06/10 20:53Z → 07/10 23:03Z, khoảng 26 giờ).
  - Journal: J_explore + J_holdout, 206 dòng, trong đó 137 dòng qua GATE_E; 55 mint bẫy, 11 mint winner.
  - Lưới dày G_* chỉ để mô tả, vì các dòng của cùng một mint tự tương quan.
  - Khối thời gian: B1 có `t0 < 1791352800`; B2 có `1791352800 ≤ t0 < 1791386123`; B3 là phần còn lại.
- **Forward (chưa ai xem kết quả):**
  - Gồm các launch classic có `t0 > 1791414202` trong census mẫu băm 5%, dùng cùng mã thu thập và cùng mã journal.
  - Lọc `t0 > 1791414202` trước mọi bước khác. Mayhem bị loại.
  - 9 dòng forward đã có trong file census ngày 08/10 chưa bị đọc kết quả.
- **Tuần forward:**
  - W1: `t0 ∈ (1791414202, 1792019002]`.
  - W2: `(1792019002, 1792623802]`.
  - Các tuần sau nối tiếp nhau, mỗi tuần 604 800 s.
  - Mỗi tuần chấm **đúng một lần**, sau khi mọi launch của tuần đã đủ 2 giờ giao dịch và đã được đọc.
- **Đăng ký:** commit gồm file này và mã đóng băng (mục 9), thực hiện trước lần chấm forward đầu tiên.

## 2. Định nghĩa chung (không đổi)

- **Ứng viên (cổng F0)**, xét tại D ∈ {120, 300, 600} s:
  - 5 ≤ SOL thật < 70;
  - ≥ 5 giao dịch và ≥ 3 ví mua khác nhau trong 120 s gần nhất;
  - curve chưa hoàn tất ở slot vào.
- **Vé, bẫy, winner:**
  - Vé 0,5 SOL, mua ở trạng thái curve cuối slot `dslot+1`; phí 1,25% mỗi chiều; 0,002 SOL cố định.
  - **Bẫy:** net ở 30 phút ≤ −50%.
  - **Winner:** net ở 30 phút ≥ +100%.
- **GATE_E:** `real_e` (SOL thật ở trạng thái vào) ≥ 11,66.
  - Dưới mức này, vé 0,5 SOL không thể lỗ 50% (tính giải tích).
  - Mọi bộ lọc chỉ được chấm trên các dòng qua GATE_E ("band").
- **Router:** ví `BwWK17cbHxwWBKZkUYvzxLcNQ1YVyaFezduWbtm2de6s` bị loại khỏi mọi đặc trưng ví, nhưng giao dịch của nó vẫn làm đổi trạng thái curve.
- **Không nhìn trước:**
  - Chỉ dùng giao dịch của ứng viên có `slot ≤ dslot`.
  - Danh tiếng ví chỉ lấy từ các launch tạo trước `t0` của ứng viên, và chỉ từ giao dịch có `ts ≤ t_dec = t0 + round((dslot − s0) × 0,269)`.
- **Đơn vị bằng chứng: mint.** Các thống kê:
  - **U** = số dòng band là bẫy bị chặn − 3 × số dòng band là winner bị chặn.
  - **p:** hoán vị gom theo mint, 4000 lần. Mỗi lần chọn mint ngẫu nhiên, lấy mọi dòng band của mint đó, cho tới khi đủ k dòng.
  - **MH OR:** tính trong tầng `real_e` (< 20 / 20–30 / 30–45 / ≥ 45) × D (≤ 180 / > 180).
  - **BH:** hiệu chỉnh trên cả họ shadow của lần chấm đó.
- **Placebo chung**, khớp số cờ k trên dòng band:
  - k dòng có `d_real_60s` thấp nhất;
  - k dòng có `an_dd_pre` cao nhất;
  - k dòng có `real_e` thấp nhất;
  - top-k theo `n_trades` (cả hai chiều);
  - top-k theo `uniq_buyers` (cả hai chiều);
  - dòng ngẫu nhiên khớp số đếm của từng tầng `real_e × D` (2000 lần).
- **Giá trị biên:** SOL tiết kiệm = −0,5 × net_b30m, cộng trên các dòng chỉ thành viên đó chặn còn ACTIVE thì không. Kèm KTC 95% bootstrap theo mint.

## 3. Chuỗi active (không đổi)

**ACTIVE = GATE_E ∧ (SH-DEV-1 ∨ N-MMAAS-WAVE-STREAM).**

Chủ bot thấy chuỗi này dưới dạng "cờ (chưa kiểm)" cho tới khi đạt chuẩn TRÁNH của SIEVE §5.

- **SH-DEV-1:** dev + creator giữ ròng trên curve ≥ 3% cung (và SOL thật ≥ 11,73).
- **N-MMAAS-WAVE-STREAM:**
  - có một slot sau slot tạo chứa lệnh mua của ≥ 4 ví khác nhau (trừ dev, creator, router);
  - mỗi lệnh ≥ 0,01 SOL;
  - cả cụm có (max − min)/max ≤ 2%.

Trên pool, ACTIVE chặn 51 dòng band (42 bẫy, 1 winner); 26/55 mint bẫy, 1/11 mint winner.

## 4. Shadow sau vòng này

Có 5 thành viên (trần 8). Vòng này đăng ký mới 2 (trần 4).

Shadow được tính và ghi sổ cho mọi ứng viên, nhưng **không hiển thị** cho chủ bot và không chặn gì.

### 4.1 N-WM-EXIT2-v2b (MỚI, thay N-WM-EXIT2 v1)

**Kho danh tiếng**
- Gồm mọi launch classic của census: pool trước, rồi forward, theo thứ tự thời gian.
- Chỉ lấy launch tạo trước `t0_c` và giao dịch có `ts ≤ t_dec`.
- Mỗi launch bị cắt ở chỗ hổng reserve đầu tiên.
- Kho **tích luỹ**: gồm mọi launch như vậy kể từ đầu kho sáng lập (06/10 20:53Z). Trong bài kiểm forward không dùng cửa sổ trượt; vì thế mỗi lần chấm phải đưa vào journal toàn bộ file census từ kho sáng lập tới tuần đang chấm. `U` = số launch như vậy.
- Bản live sẽ dùng cửa sổ trượt 7 ngày. Đó là một biến thể phải đo riêng: theo §5 điều 7, phải đo tỷ lệ cờ trên luồng đầy đủ một tuần trước khi thăng hạng.

**Số liệu của mỗi ví w (trừ router)**
- `nL` = số launch có giao dịch của w.
- `nB` = số launch có lệnh mua của w.
- **XFER_SELL** trong launch L: tại một thời điểm nào đó, token w đã bán trên curve vượt token w đã mua quá 1e12 raw.
- `nXS` = số launch có XFER_SELL.
- `over_share` = Σ_L max(0, bán_L − mua_L) / Σ_L bán_L.

**Phân loại WTYPE-v1** (lấy loại khớp đầu tiên)
- **INFRA:** có mặt ở ≥ 25% số launch classic hoặc mayhem, với n ≥ 20.
- **INDUSTRIAL:** `nXS ≥ 3`, `1000·nXS/U ≥ 1,75`, `nXS/nL ≥ 0,5` và `over_share ≥ 0,5`.
- **CUSTODIAL:** `nXS ≥ 3`, `1000·nL/U ≥ 10`, `nB/nL ≥ 0,5`, và (`nXS/nL ≥ 0,1` hoặc `over_share ≥ 0,1`).
- **GENERIC:** còn lại.

**Đại lượng và cờ**
- `ind_over(c)` = Σ, trên các ví INDUSTRIAL đã giao dịch c tới `dslot`, của max(0, token bán − token mua trên c) / 1e15.
- **Cờ:** GATE_E ∧ `ind_over ≥ 0,02`.

**Phạm vi chấm**
- Áp dụng cho launch classic, ở mọi D.
- Census forward là đọc đầy đủ, nên mọi dòng đều được chấm; báo kèm tỷ lệ dòng qua kiểm tra chuỗi reserve.
- Khi chạy live: nếu ứng viên có hổng reserve tới `dslot`, phải đọc bù (trả phí) rồi mới chấm; nếu không thì ghi "THIẾU DỮ LIỆU".

**Placebo riêng (ràng buộc):** các placebo chung, cộng k dòng có `v1_transfer_in` cao nhất (khối transfer-in không dùng danh tiếng).

**Điều kiện huỷ riêng**
- Một ví đứng sau > 30% số cờ.
- Canary xoay ví: số sự kiện của roster trên 1000 launch giảm > 50% trong khi khối XFER_SELL dưới ngưỡng vẫn giữ nguyên.
- Khi live: > 50% ứng viên không chấm được trong 2 tuần liền mà không đọc bù.

**Ghi kèm (không phán quyết):**
- `n_ind` (v2a);
- cỡ roster;
- số ví CUSTODIAL và khoảng cách của chúng tới ngưỡng INDUSTRIAL;
- khối XFER_SELL dưới ngưỡng trên 1000 launch.

**Pool (trong mẫu):**
- 35 dòng band, 24 bẫy, 1 winner (dòng winner này SH-DEV-1 đã chặn); 16 mint bẫy từ 16 creator, ở cả 3 khối.
- p = 0,087; MH 1,42.
- Placebo sụt-từ-đỉnh ngang hoặc hơn (U 22 so với 21).

### 4.2 CLD-ORPHAN-v1 (MỚI)

**Định nghĩa**
- Chỉ dùng giao dịch có `slot ≤ dslot`. Mỗi ví (trừ router) có sổ: token mua `bt`, token bán `st`, slot của lệnh mua đầu.
- **Tập tạo** = dev, creator, và mọi ví có lệnh mua đầu ở slot tạo hoặc slot kế tiếp.
- `creation_out` = Σ_tập tạo min(st, bt) / Σ_tập tạo bt. Bằng 0 nếu tập tạo không mua gì.
- `ins_share` = Σ_{dev, creator} (bt − st) / cung. Nếu dev trùng creator thì chỉ tính một lần.
- `real_d` = SOL thật sau giao dịch cuối cùng có `slot ≤ dslot`.
- `holders` = số ví có bt − st > 0 (tính cả dev và creator).
- `raw = real_d / holders`.

**Cờ:** GATE_E ∧ `creation_out ≥ 0,5` ∧ `ins_share < 0,03` ∧ `raw ≥ 0,50`.

**Phạm vi chấm**
- Áp dụng cho launch classic, ở mọi D.
- **Chỉ chấm trên dòng có giao dịch đầy đủ, đã kiểm chuỗi reserve.** Không bao giờ chạy trên luồng PumpPortal thô.
- Khi chạy live: cần một lần đọc lịch sử curve trả phí cho mỗi ứng viên band (khoảng 20–30 credit).

**Placebo riêng (ràng buộc)**, lấy trong tập con `creation_out ≥ 0,5 ∧ ins_share < 0,03`, cùng k:
- k dòng ít ví mua nhất;
- k dòng ít giao dịch nhất;
- k dòng có `real_e` thấp nhất.

**Điều kiện huỷ riêng:** có một winner bị chặn mà giá trị của nó nằm trong 5% của bất kỳ ngưỡng nào (0,5 / 0,03 / 0,50).

**Ghi kèm:**
- biến thể v1d: chỉ đếm holder ≥ 0,1% cung, ngưỡng 0,65;
- khoảng cách từ mỗi cờ và mỗi winner tới từng ngưỡng;
- số holder < 0,1% cung;
- số ví bán-trước.

**Pool:**
- 12 dòng band, 10 bẫy, 0 winner; 9 mint bẫy từ 9 creator, ở cả 3 khối.
- p = 0,110; MH 2,90.
- Điểm ngưỡng (0,50; 0,5) đứng lẻ trên lưới ngưỡng, và lưới dày đã chặn 2 mint winner trên 15 mint bẫy, nên dự kiến luật winner sẽ là điều kiện ràng buộc.

### 4.3 Giữ nguyên

- **SH-SG-1 (gated):** GATE_E ∧ tập tạo mua ≥ 20 SOL ∧ (tập tạo đã bán ≥ 50% token của mình, hoặc ≥ 5 ví mua cùng cỡ).
- **N-MMAAS-SPLDIST:** GATE_E ∧ ≥ 5 ví (trừ dev, creator, router) có sự kiện curve đầu tiên là lệnh bán. Cần giao dịch đầy đủ.
- **N-MMAAS-WAVE (strict):** như WAVE-STREAM, nhưng dung sai 0,5% và khoảng tx_index ≤ 64. Cần tx_index.

## 5. Luật thăng, giáng, huỷ (chỉ dùng dữ liệu forward)

**Shadow → active** (vào chuỗi veto, hiển thị "cờ (chưa kiểm)"): sau ≥ 2 tuần forward, phải đạt **tất cả** các điều kiện sau.
1. ≥ 20 cờ band, từ ≥ 8 mint bẫy và ≥ 3 creator, trải trên ≥ 2 tuần.
2. p (hoán vị gom mint) < 0,05 sau hiệu chỉnh BH trên họ shadow, gộp các tuần.
3. MH OR > 1 ở từng tuần, và ≥ 1,5 khi gộp.
4. U lớn hơn U của mọi placebo (chung và riêng) ở cùng k.
5. ≤ 1 mint winner bị chặn trên mỗi 10 mint bẫy bị chặn, đếm ở D = 120/300/600.
6. Thêm được ≥ 3 mint bẫy so với ACTIVE, và SOL tiết kiệm biên có cận dưới KTC 95% > 0.
7. Với thành viên cần giao dịch đầy đủ: chỉ tính dòng đã kiểm chuỗi reserve. Riêng với thành viên dựa danh tiếng (v2b): phải đo trước tỷ lệ cờ trên luồng đầy đủ trong một tuần.

**Active → nhãn TRÁNH:** theo SIEVE §5.
- ≥ 200 cờ forward ở tầng ≥ 5 SOL.
- Chênh trung bình (có cờ − không cờ) ≤ −10 điểm, với KTC bootstrap không chứa 0.
- Cận dưới Wilson của lift > 1.
- Tỷ lệ winner/bẫy bị chặn không vượt tỷ lệ chung của tầng.

**Active → shadow (giáng):** xảy ra khi trong 2 tuần liên tiếp có một trong các điều sau.
- U ≤ U của placebo tốt nhất ở cùng k.
- Hơn 1 mint winner trên 10 mint bẫy.
- MH OR < 1, với ≥ 20 cờ trong tuần.

**Shadow → nghỉ hưu (huỷ):** khi có bất kỳ điều nào sau đây.
- Sau 2 tuần, U ≤ U của placebo tốt nhất ở cùng k.
- Sau 2 tuần, trong band, tỷ lệ bẫy khi có cờ ≤ tỷ lệ bẫy khi không có cờ.
- Trong một tuần có ≥ 2 mint winner bị chặn mà không thêm được mint bẫy biên nào.
- Các điều kiện huỷ riêng ở mục 4.

Sau 4 tuần, shadow nào không được thăng mà cũng không bị huỷ thì chuyển xuống INFO.

**Không chỉnh ngưỡng trên dữ liệu forward.** Mỗi lần sửa định nghĩa là một id mới (v2), với đồng hồ shadow mới, và chỉ được chấm trên các tuần chưa xem.

## 6. Từ watch thành ứng viên

Từ nay áp dụng luật đếm thường, thay cho bản dùng khối của vòng sáng lập. Một archetype chỉ thành bộ lọc ứng viên khi trên dữ liệu forward:
- thấy ở ≥ 3 mint bẫy;
- từ ≥ 2 creator;
- trong ≥ 2 ngày UTC khác nhau.

Mỗi tuần đọc journal, gắn archetype cho từng bẫy lọt bằng `research/sieve/archetype.py` (đóng băng như mục 9), rồi cập nhật watch list.

## 7. INFO (ghi raw, không phán quyết, không chiếm chỗ shadow)

- **N-WM-EXIT2-v2a:** `n_ind`.
- **P1-SWARM-SCRIPTED-v1:** p_hat, z, n_fb, NP_hold, và số lamport chính xác của lệnh mua đầu.
- **P2-SWARM-VET-v1:** độ chồng ≥ 3. Cần luồng toàn chương trình.
- **CC-TOPDIST-v1:** ngưỡng 0,35 đóng băng; lượng bán trong cửa sổ của mỗi ví bị chặn trên ở số token ví đó giữ tại w0.
- **LC-XFERSUP-v1:** chính là `v1_transfer_in`, cắt ở 0,055.
- **CLD-ORPHAN-v1d.**
- **REF-DRAIN75:** tham chiếu mức curve.
- **Các cờ cũ:** SH-WASH-1, N-ANAT-FADE, N-ANAT-LOCKSTEP, N-LTE-FACTORY (+REPEAT1), N-WM-XIN, N-MMAAS-MSTX, N-MMAAS-DUSTHOLD.
- **Cờ v1:** tầng 1 (early_hold, top10, flippers, transfer_in, spike, dev_hold, wash) và tầng 0 (selfgrad_fill).

## 8. Nghỉ hưu

- **N-WM-EXIT2 v1:** thay bằng v2b; không sửa tại chỗ.
- **CC-CHEAPLOAD-v1.**
- **POSTHOC-CC-FRAGILE-v0:** không bao giờ chấm.
- **LC-REPUMP-v1.**
- **CLD-REACTFLOAT-v1.**

## 9. Mã đóng băng

Mã chấm là gói `research/sieve/` trong repo, commit cùng file này. Thư mục scratch của phiên làm việc sẽ mất, nên gói này là bản chính thức.

- `filters.py`: mỗi id/version một hàm. Bảng `FROZEN` giữ hash của từng định nghĩa, cùng mọi hàm phụ và hằng số mà nó dùng. `python3 -I research/sieve/filters.py --check` phải in `frozen check: OK`; nếu không, một định nghĩa đã bị sửa tại chỗ và lần chấm đó không hợp lệ.
- `journal.py`, `score.py`, `archetype.py`: dựng journal, chấm, và gắn archetype cho bẫy lọt.
- sha256 (16 ký tự đầu) của từng file lúc đăng ký nằm ở bảng cuối mục này. Lần chấm forward phải chạy đúng các file đó (cùng commit).

Gói này là bản port của mã người thiết kế (scratch `sieve2/verify/*`, `sieve3/patch-*`) và được kiểm từng dòng trên kho sáng lập: 0 lệch trên 1.037 dòng (J + G). Cụ thể:
- cờ của 22 filter cũ, nhãn và feature;
- raw của 13 định nghĩa mới;
- số k/T/W/U/p/MH khớp đúng bảng của red team và của người thiết kế.

Hai bản viết lại độc lập của red team (CLD-ORPHAN-v1, N-WM-EXIT2-v2b) cũng khớp 1.037/1.037 dòng.

| File | sha256 (16 ký tự đầu) |
|---|---|
| `research/sieve/filters.py` | `890d76e5a608f09e` |
| `research/sieve/journal.py` | `48441b097aa3fdbe` |
| `research/sieve/score.py` | `ce7cd03d2e0f075a` |
| `research/sieve/archetype.py` | `96262e1b05c07b07` |

## 10. So sánh hằng tuần

Mỗi tuần, so sánh song song năm chuỗi:
- (a) không veto (chỉ cổng F0);
- (b) GATE_E chặn hết (chỉ mua dưới 11,66);
- (c) v1 tầng 1;
- (d) ACTIVE;
- (e) ACTIVE + 5 shadow.

Với mỗi chuỗi, báo:
- số dòng qua;
- dòng và mint bẫy qua;
- dòng và mint winner qua;
- net trung bình và trung vị của các dòng qua, kèm KTC bootstrap theo mint;
- lỗ chuẩn hoá;
- độ nhạy khi vào ở T+45 và T+90 giây.

Ngoài ra báo sổ của từng thành viên theo mục 5.

## 11. Không được làm

- Xem kết quả forward trước khi commit; dùng pool làm bằng chứng.
- Chỉnh ngưỡng, danh sách placebo, tầng hay tuần sau khi đã thấy forward.
- Bỏ dòng khỏi mẫu, trừ các lý do đã định nghĩa sẵn: mayhem, quote khác SOL, hổng reserve không đọc bù được. Số dòng bị bỏ phải được báo cáo.
- Đưa shadow lên kênh của chủ bot trước khi được thăng.
- Mô tả cơ chế crew vượt quá mức cần để phát hiện; viết hướng dẫn chạy bundle, wash, farm hay launch lừa đảo.

