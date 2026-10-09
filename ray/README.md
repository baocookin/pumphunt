# Rây — chấm rủi ro coin pump.fun theo thời gian thực

**Rây chỉ cảnh báo, không bao giờ báo mua.** Nó theo dõi mọi launch pump.fun (curve classic, quote SOL), và tại các mốc 2, 5 và 10 phút sau khi tạo, chạy bộ lọc đã đóng băng của nghiên cứu (`research/sieve/filters.py`) trên toàn bộ giao dịch của curve, rồi trả về một nhãn (TRÁNH, CẢNH GIÁC…) kèm tỷ lệ bẫy lịch sử. Dùng riêng (mật khẩu), không chia sẻ tín hiệu, không đặt lệnh.

Không có thí nghiệm nào chạy trong Rây: không giả thuyết, không mẫu census, không forward test. Các con số rủi ro là số **trong mẫu** của kho sáng lập (26 giờ, 06–07/10/2026; xem `docs/TONG-KET-NGHIEN-CUU.md`), chưa được kiểm trên dữ liệu mới. Nhóm làm giá thay đổi cách làm hàng tuần, nên "không thấy cờ" chỉ có nghĩa là không thấy kiểu bẫy đã biết.

## Cách chạy

```
census   mỗi 60 s   lệnh tạo mới từ lịch sử của mint authority (getTransactionsForAddress)
curve    mỗi 5 s    reserve của mọi curve còn sống, 100 curve một lần gọi (getMultipleAccounts):
                    curve ≥ 2 SOL hoặc dưới 45 s tuổi mỗi 5 s, còn lại mỗi 30 s
mốc D    2/5/10 ph  lần đọc curve đầu tiên tới mốc D quyết định:
                      < 5 SOL       bỏ qua
                      5–11,66 SOL   DƯỚI CỔNG (không đọc lịch sử)
                      ≥ 70 SOL      NGOÀI VÙNG ĐO
                      đã hoàn tất   ĐÃ TỐT NGHIỆP
                      còn lại       đọc lịch sử curve rồi chấm
chấm               đọc mọi giao dịch thành công của curve (cũ trước, 100/trang), đọc lại phần đuôi
                    tới khi phát lại đúng reserve của lần đọc quyết định (chỉ mục giao dịch trễ
                    tài khoản 15–30 s trên RPC công khai), chạy bộ lọc, ghi điểm
kết quả  +30 phút   vé 0,5 SOL mua lúc chấm được định giá lại 30 phút sau: bẫy, thắng hay không
```

Một mốc D chỉ được quyết định trong 45 s sau D; curve phát hiện muộn hơn thì mốc đó bị bỏ (đếm là `missed`). Ngoài ra có thể chấm bất kỳ mint nào ngay lập tức (nút **Chấm ngay** trên bảng điều khiển, hoặc Telegram), tối đa 60 lần/giờ.

## Nhãn

| Nhãn | Nghĩa |
|---|---|
| **TRÁNH** | Một bộ lọc chính bật **và đã được coin mới xác nhận** (xem *Luật sống* bên dưới). Các bộ lọc chính: dev + creator còn giữ ≥ 3% cung (SH-DEV-1), sóng mua cùng cỡ ≥ 4 ví trong một slot (N-MMAAS-WAVE-STREAM). |
| **THIẾU DỮ LIỆU** | Một bộ lọc chính đã được xác nhận cần đủ mọi giao dịch, nhưng chuỗi reserve bị hở, lịch sử bị cắt (quá `RAY_HISTORY_MAX_TX`) hoặc thiếu vị trí giao dịch. |
| **CẢNH GIÁC** | Chỉ cờ phụ đã được coin mới xác nhận bật (bằng chứng yếu hơn). Các cờ phụ: SH-SG-1, N-MMAAS-SPLDIST, N-MMAAS-WAVE, CLD-ORPHAN-v1; từ vòng sống 1 RAY-HOT-v1 (curve quá nóng: ≥ 300 giao dịch trong 2 phút) và RAY-WASH-v1 (wash ≥ 30% volume); từ vòng sống 2 RAY-CROWD-v1 (≥ 100 ví giao dịch trong 2 phút), RAY-PEAK-v1 (SOL thật cách đỉnh ≤ 4%) và RAY-SERIAL-v1 (ví mua sớm chuyên nghiệp mang ≥ 50% tiền mua sớm). |
| **ÍT HOẠT ĐỘNG** | Không thấy cờ, nhưng 2 phút qua dưới 5 giao dịch, dưới 3 ví mua, hoặc không có giao dịch trong 60 s (ngoài cổng F0). |
| **KHÔNG THẤY CỜ** | Không bộ lọc nào đã xác nhận bật (cờ chưa xác nhận hay tạm ngưng vẫn được ghi trong phần tóm tắt). **Không phải tín hiệu mua**: tỷ lệ bẫy của tầng trên coin mới vẫn áp dụng (13–30 SOL lúc 2 phút: 79% ngày 09/10). |
| **DƯỚI CỔNG** | Dưới 11,66 SOL thật: vé 0,5 SOL không thể lỗ 50% trên curve (phí và trượt giá vẫn ăn mòn). Bộ lọc không áp dụng. |
| **NGOÀI VÙNG ĐO** | Từ 70 SOL trở lên: sát tốt nghiệp, ngoài vùng bộ lọc đã được đo. |
| **ĐÃ TỐT NGHIỆP** | Curve đã hoàn tất. |

**Tỷ lệ bẫy** đi kèm mỗi điểm: số dòng bẫy / số dòng của ô (tầng SOL × mốc D) trong nhật ký 7 ngày của coin mới, hoặc của cả tầng khi ô dưới 30 dòng; chỉ khi chưa đủ cả hai mới dùng kho sáng lập (ghi rõ "trong mẫu"). Khi một bộ lọc chính đã xác nhận bật mà tỷ lệ của nó cao hơn thì dùng tỷ lệ đó. Kèm khoảng tin cậy Wilson 95%. "Bẫy" = vé 0,5 SOL vào lúc chấm, lỗ ≥ 50% sau 30 phút. Cờ ngữ cảnh (FADE, TOPDIST, WASH…) chỉ để đọc, không đổi nhãn.

Điểm nào cũng ghi chất lượng dữ liệu: số giao dịch đã đọc, chuỗi reserve có liền không, lịch sử có khớp tài khoản curve lúc quyết định không, và phải chờ chỉ mục bao lâu. Một điểm "chưa khớp" được chấm tới giao dịch cuối đọc được, tức là sớm hơn lúc quyết định.

## Nhật ký kết quả và báo cáo tuần

Mỗi lần chấm đầy đủ (ở các mốc, và chấm tay) được đối chiếu 30 phút sau theo đúng định nghĩa của nghiên cứu (`research/sieve/journal.py`):
- **Vé:** 0,5 SOL mua ở reserve lúc chấm, phí của curve mỗi chiều (1,25%) và 0,002 SOL chi phí cố định.
- **Bán ra:** định giá trên curve 30 phút sau; curve tốt nghiệp trước đó thì coi như bán lúc tốt nghiệp.
- **Nhãn:** **bẫy** khi lỗ ≥ 50%, **thắng** khi lãi ≥ 100%.

Hai khác biệt nhỏ so với nghiên cứu: Rây mua ngay ở lần đọc quyết định (nghiên cứu mua sau đó một slot), và 30 phút tính theo đồng hồ (nghiên cứu đếm slot). Kết quả không đổi nhãn nào; nó chỉ được ghi lại.

Cách đọc:
- **Đúng giờ:** đọc tài khoản curve, gộp 100 curve một lần gọi (1 credit).
- **Curve đã tốt nghiệp, hoặc đọc trễ** (ví dụ app vừa khởi động lại): đọc lịch sử giao dịch tới đúng thời điểm đó (10 credit), lấy giao dịch cuối cùng làm điểm bán.

Phần chưa có kết quả được đọc lại sau mỗi lần khởi động.

**Báo cáo** (mục *Nhật ký kết quả* trên bảng điều khiển, hoặc `/api/report?days=7`) chỉ tính các lần chấm ở mốc, đặt cạnh số của kho sáng lập:
- **Theo phán quyết:** tỷ lệ bẫy thực tế so với tỷ lệ Rây đã báo.
- **Theo tầng SOL và mốc.**
- **Theo từng bộ lọc:** khi bật thì bao nhiêu là bẫy, bao nhiêu thắng.
- **Bẫy lọt lưới:** nhãn KHÔNG THẤY CỜ, ÍT HOẠT ĐỘNG, CẢNH GIÁC hoặc THIẾU DỮ LIỆU nhưng là bẫy.
- **Báo động nhầm:** TRÁNH nhưng thắng.

Số của kho sáng lập là số trong mẫu; số trong báo cáo là trên coin mới.

**File nhật ký** nằm trong `<data>/ray/`, mỗi ngày (UTC) một file, tải ở mục *Tải nhật ký* hoặc `/api/journal/<tên>` (cần mật khẩu):

| File | Nội dung |
|---|---|
| `scores-YYYY-MM-DD.jsonl` | Mọi lần chấm, đầy đủ cờ và giá trị thô. |
| `outcomes-YYYY-MM-DD.jsonl` | Kết quả 30 phút, mỗi dòng kèm phán quyết, cờ đã bật, tầng SOL, tỷ lệ Rây đã báo (`risk`), tỷ lệ khi không có mô hình (`base_risk`), xác suất của mô hình (`model_p`), các đặc trưng lúc chấm (`features`) và reserve lúc mua (theo ngày của lần chấm). |
| `rows-YYYY-MM-DD.jsonl.gz` | Toàn bộ giao dịch tới mốc cuối của mỗi coin được chấm ở mốc, cùng định dạng census của nghiên cứu (khoảng 20 MB/ngày; tắt bằng `RAY_ARCHIVE_ROWS=false`). |
| `wallets.json.gz` | Bộ nhớ ví (xem *Bộ nhớ ví* bên dưới). Mất file thì Rây dựng lại từ `rows-*` và `outcomes-*` của 2 ngày gần nhất. |
| `rules.json`, `model.json` | Bộ lọc đang được dùng, và mô hình rủi ro học gần nhất; giữ qua lần khởi động lại. |

**Vá bộ lọc mỗi tuần:**
1. Mở báo cáo 7 ngày và đọc các bẫy lọt lưới trước: cờ nào suýt bật, giống kiểu nào đã biết.
2. Bộ lọc mới luôn mang **mã mới** trong `research/sieve/filters.py` và được đóng băng bằng hash; không bao giờ sửa bộ lọc cũ.
3. Đo bộ lọc mới trên `rows-*.jsonl.gz` với nhãn trong `outcomes-*.jsonl` của các tuần trước, không cần đọc lại chain.
4. Thêm nhãn tiếng Việt và số đo vào `app/sieve.py`, rồi deploy.

## Luật sống của bộ lọc (từ 09/10/2026)

Trên 226 kết quả đầu tiên (09/10, 15:05–17:05 UTC), các bộ lọc chính **không đúng trên coin mới**. Số "kỳ vọng" dưới đây là tỷ lệ của các coin cùng tầng SOL và cùng mốc mà bộ lọc không bật.

| Bộ lọc | Số lần bật | Bẫy khi bật | Bẫy kỳ vọng | Ghi chú |
|---|---|---|---|---|
| SH-DEV-1 | 43 | 60% | 66% | |
| N-MMAAS-WAVE-STREAM | 33 | 61% | 57% | thắng nhiều gấp đôi |
| N-MMAAS-SPLDIST | 44 | 39% | 63% | đảo ngược hẳn, 30% thắng |

Tỷ lệ 80–90% mà Rây hiện trước đó là số trong mẫu của kho sáng lập, nên Rây đã báo TRÁNH cho nhiều coin rồi vẫn tăng giá. Từ nay:

- **Một bộ lọc chỉ quyết định nhãn khi coin mới xác nhận nó, và được chấm bằng tiền.** Trong 7 ngày qua, nó phải đạt cả hai điều:
  - bật ≥ 30 lần, trên ≥ 10 coin;
  - ở những coin nó bật, vé 0,5 SOL lãi/lỗ trung bình **kém hơn ít nhất 10 điểm** so với các coin cùng tầng SOL, cùng mốc mà nó không bật; cận dưới khoảng tin cậy 95% (tính theo coin) cũng phải trên 0.
- **Đã được dùng thì giữ** khi vẫn còn kém hơn ít nhất 5 điểm. Hai mức "vào" và "giữ" khác nhau để bộ lọc không bật/tắt theo vài dòng dữ liệu: ngày 09/10, SH-SG-1 được xác nhận rồi tạm ngưng chỉ trong một giờ, khi mới có 30–40 dòng.
- **Vì sao chấm bằng tiền mà không bằng tỷ lệ bẫy** (đổi tối 09/10): đếm bẫy xếp hạng bộ lọc sai cả hai chiều. Trên 387 dòng:
  - N-MMAAS-WAVE-STREAM bật nhiều hơn 7 điểm bẫy, nhưng vé ở coin nó chặn lại lời hơn 11 điểm, vì nó chặn cả coin thắng lớn;
  - SH-SG-1 chỉ hơn 6 điểm bẫy, nhưng coin nó chặn lỗ thêm 21 điểm.

  Tỷ lệ bẫy và thắng vẫn được tính và hiện để tham khảo.
- **Bộ lọc chưa đủ dữ liệu hoặc không đạt** vẫn được tính, vẫn hiện (ghi "chưa xác nhận" hoặc "tạm ngưng") và vẫn được ghi vào nhật ký, nhưng không quyết định nhãn. Khi số liệu của nó đạt chuẩn, nó tự được dùng lại.
- **Tầng của bộ lọc giữ nguyên:** bộ lọc chính cho TRÁNH, bộ lọc phụ cho CẢNH GIÁC, bộ lọc ngữ cảnh không bao giờ quyết định. Luật này không thăng hạng bộ lọc nào (thăng hạng theo PREREG-SIEVE-R1 mục 5).
- **Tỷ lệ bẫy hiển thị** lấy từ nhật ký 7 ngày của coin mới, cùng tầng SOL và cùng mốc (cần ≥ 30 dòng; không đủ thì lấy cả tầng). Chưa đủ cả hai thì mới dùng kho sáng lập, và ghi rõ là số trong mẫu. Đi kèm là lãi/lỗ trung bình của vé ở tầng đó, và **rủi ro của cùng tầng theo từng mốc**. Thời gian là yếu tố mạnh nhất đo được: tối 09/10, ở tầng 13–30 SOL, mốc 2 phút có 73% bẫy và vé lỗ trung bình −26%, còn mốc 10 phút (coin còn trụ) có 44% bẫy, vé khoảng −2%.
- Danh sách bộ lọc đang được dùng được lưu ở `<data>/ray/rules.json` mỗi lần tính lại. Khi khởi động lại hay deploy, các bộ lọc này vẫn chỉ cần mức "giữ", không phải chứng minh lại từ đầu.
- Luật được tính lại mỗi 10 phút (`RAY_RULES_REFRESH_S`). Trạng thái từng bộ lọc nằm ở mục *Nhật ký kết quả → Theo bộ lọc*; mã ở `app/live_rules.py`.

Lúc 18:20 UTC ngày 09/10, trên 391 dòng, không còn bộ lọc chính hay phụ nào đạt: không có nhãn TRÁNH, không có CẢNH GIÁC. Mọi coin là KHÔNG THẤY CỜ, kèm tỷ lệ bẫy thực tế của tầng (ví dụ 13–30 SOL lúc 2 phút: khoảng 76–79%). Coin "không thấy cờ" vẫn phần lớn là bẫy; bộ lọc chỉ giúp được ở rìa.

**Vòng sống 1** ([docs/PREREG-RAY-L1.md](../docs/PREREG-RAY-L1.md)). Trên 387 kết quả, mình tìm luật ở 60% đầu và kiểm nguyên ngưỡng ở 40% sau. Trong 148 luật thử, chỉ hai loại tín hiệu giữ được:
- **Curve quá nóng:** rất nhiều giao dịch ngay trước lúc chấm, khoảng +16 điểm bẫy ở cả hai phần.
- **Wash:** ví đổi chiều liên tục, khoảng +13 điểm bẫy, rất ít coin thắng.

Chúng được thêm thành RAY-HOT-v1 và RAY-WASH-v1 (tầng phụ, mã mới, đóng băng). Chúng cũng phải qua luật sống trên dữ liệu *sau khi deploy* mới được quyết định nhãn. Đến 21:10 UTC, chỉ trên dữ liệu sau deploy:
- **RAY-WASH-v1** được xác nhận theo luật tiền: bật 48 lần, coin nó chặn lỗ thêm 28 điểm, khoảng tin cậy +4…+53.
- **RAY-HOT-v1** suýt đạt: bật 67 lần, +23 điểm, khoảng tin cậy −1…+47.

**Vòng sống 2** ([docs/PREREG-RAY-L2.md](../docs/PREREG-RAY-L2.md)). Trên 837 kết quả, mình thử 20 đặc trưng lúc chấm, kể cả bộ nhớ ví, thành 80 luật. Mình tìm ở 60% đầu và kiểm nguyên ngưỡng ở 40% sau, chấm bằng tiền như luật sống. Có 8 luật qua chuẩn vào của luật sống ở phần sau; kiểm đa so sánh Benjamini–Hochberg giữ đúng 8 luật đó. Sau khi gộp các phép đo trùng nhau, còn ba bộ lọc mới (tầng phụ, đóng băng):
- **RAY-CROWD-v1:** ≥ 100 ví giao dịch trong 2 phút trước lúc chấm. Phần kiểm: vé kém hơn 36 điểm, khoảng tin cậy +19…+53.
- **RAY-PEAK-v1:** đang ở sát đỉnh, SOL thật cách đỉnh trước đó ≤ 4%. Phần kiểm: +35 điểm (+24…+45), 0 coin thắng trong 70 dòng.
- **RAY-SERIAL-v1:** ví mua sớm ở ≥ 2 coin trước mang ≥ 50% tiền mua trong 60 s đầu. Phần kiểm: +20 điểm (+6…+33).

Ba bộ lọc này cũng chỉ quyết định nhãn sau khi luật sống xác nhận chúng trên dữ liệu sau deploy.

## Bộ nhớ ví và đặc trưng lúc chấm (từ vòng sống 2)

- **Đặc trưng lúc chấm:** mỗi lần chấm ở mốc tính 20 đặc trưng, chỉ từ giao dịch có slot ≤ slot lúc chấm (`app/features.py`). Chúng được ghi vào `scores-*` và `outcomes-*` (khoá `features`), để mô hình rủi ro và các bộ lọc sau này học lại trên dữ liệu đã có.
- **Bộ nhớ ví** (`app/wallets.py`):
  - Mỗi coin được ghi một lần, ở lần chấm đầu: ví nào mua trong 60 s đầu, ví nào trong số đó đã bán ≥ 50% hàng mua sớm trước lúc chấm.
  - Khi có kết quả 30 phút đầu tiên của coin, kết quả đó được cộng vào hồ sơ của từng ví mua sớm và của dev.
  - Đặc trưng của một coin không bao giờ tính chính nó: khi chấm lại ở 5 hay 10 phút, phần của chính nó được trừ ra.
  - Ví chỉ mua sớm một lần bị quên sau 1 ngày; ví khác sau 7 ngày không thấy lại.
  - Bộ nhớ được lưu mỗi 15 phút (`RAY_WALLETS_SAVE_S`).
  - Trạng thái hiện ở `/api/state` (khoá `wallets`).
- **Bộ lọc gốc của Rây** (`app/native.py`): bộ lọc đọc bộ nhớ ví không nằm được trong gói nghiên cứu, nên được định nghĩa ở đây. Chúng cùng kỷ luật đóng băng: hash phủ cả hàm lẫn các định nghĩa đặc trưng và cách bộ nhớ đếm. Sửa tại chỗ sẽ hiện trên health check.

## Mô hình rủi ro (shadow) và ứng viên bộ lọc (từ 09/10/2026)

Đăng ký ở [docs/PREREG-RAY-L3.md](../docs/PREREG-RAY-L3.md).

- **Mô hình rủi ro** (`app/model.py`):
  - Tính xác suất vé 0,5 SOL mua lúc chấm là bẫy sau 30 phút, từ 20 đặc trưng lúc chấm cùng tầng SOL và mốc. Đây là hồi quy logistic, phạt L2 (λ = 30).
  - Học lại mỗi giờ trên nhật ký 7 ngày, cần ≥ 300 dòng có đặc trưng.
  - Mỗi lần chấm ghi lại xác suất của mô hình (`model_p`) bên cạnh tỷ lệ Rây hiển thị khi không có mô hình (`base_risk`). Mô hình chỉ học từ kết quả đã có trước lúc chấm, nên đây là bản ghi trên dữ liệu nó chưa thấy.
- **Khi nào mô hình được dùng:** nó thay tỷ lệ tầng × mốc khi trên ≥ 2 ngày trọn (mỗi ngày ≥ 300 dòng):
  - log-loss của nó thấp hơn, và khoảng tin cậy 95% của phần tốt hơn nằm trên 0;
  - ngày gần nhất cũng tốt hơn.
  
  Không đạt thì Rây quay về tỷ lệ tầng × mốc. Nhãn không bao giờ phụ thuộc mô hình.
- **Kết quả thử** trên 837 dòng ngày 09/10 (60% đầu học, 40% sau kiểm): log-loss 0,616 so với 0,678 của tầng × mốc. Hiệu chỉnh khớp: báo 32% thì thực tế 32%, báo 69% thì thực tế 70%.
- **Ứng viên bộ lọc** (`app/candidates.py`): mỗi giờ, Rây tự chạy lại phương pháp của vòng sống 2 trên nhật ký 7 ngày:
  - tìm ở 60% đầu, kiểm nguyên ngưỡng ở 40% sau;
  - ứng viên phải qua chuẩn vào của luật sống và kiểm đa so sánh Benjamini–Hochberg (q = 0,10);
  - chỉ tìm cảnh báo.
  
  Ứng viên hiện ở cuối mục *Nhật ký kết quả* và không đổi gì. Một ứng viên chỉ thành bộ lọc khi bạn đồng ý: nó được đăng ký với mã mới, đóng băng, rồi phải qua luật sống như mọi bộ lọc.

## Cấu hình (biến môi trường)

Đủ dùng chỉ với `RAY_PASSWORD`; mọi thứ khác có mặc định. Biến danh sách viết dạng JSON, ví dụ `RAY_TELEGRAM_PUSH=["TRANH"]`.

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `RAY_PASSWORD` | (không) | Mật khẩu HTTP Basic cho bảng điều khiển và API (tên người dùng tuỳ ý). Chưa đặt thì mọi trang riêng trả 503. |
| `RAY_RPC_URL` | | URL HTTPS của RPC có `getTransactionsForAddress` (Helius, kèm key). Không đặt thì lấy `PH_SOLANA_WS_URL` (biến cũ trên Bunny) đổi sang https; không có cả hai thì dùng RPC công khai `api.mainnet-beta.solana.com` (miễn phí, chậm hơn). URL không bao giờ xuất hiện trong log hay lỗi. |
| `RAY_RPC_RPS` | 10 (riêng), 2,5 (công khai) | Số yêu cầu mỗi giây. RPC công khai trả 429 từ khoảng 3/s. |
| `RAY_DAILY_CREDITS` | 300000 | Trần credit Helius mỗi ngày (UTC). Tới trần thì ngừng chấm; census, đọc curve và kết quả được vượt 25%. 300k/ngày nằm trong 10 triệu/tháng của gói Helius Developer. |
| `RAY_CHECKPOINTS_S` | `[120,300,600]` | Các mốc quyết định (giây). |
| `RAY_HISTORY_MAX_TX` | 6000 | Trần giao dịch đọc cho một curve (~600 credit). |
| `RAY_SYNC_WAITS_S` | `[3,5,8,10,14]` | Các lần chờ trước khi đọc lại phần đuôi lịch sử (tổng tối đa 40 s). |
| `RAY_WORKERS` | 4 | Số curve chấm song song. |
| `RAY_SCORE_BELOW_GATE` | false | Chấm cả curve dưới cổng (đọc thêm ~1.000 lịch sử/ngày, vô ích vì không có phủ quyết dưới cổng). |
| `RAY_ONDEMAND_PER_HOUR` | 60 | Số lần "Chấm ngay" mỗi giờ. |
| `RAY_DATA_DIR` / `PH_DATA_DIR` | `/data` trong image | Nhật ký ghi vào `<data>/ray/` (xem mục trên). |
| `RAY_OUTCOME_TICK_S` | 5 | Bao lâu kiểm tra các kết quả 30 phút đến hạn một lần. |
| `RAY_ARCHIVE_ROWS` | true | Lưu giao dịch của các coin được chấm (`rows-*.jsonl.gz`). |
| `RAY_RULES_REFRESH_S` | 600 | Bao lâu tính lại luật sống của bộ lọc từ nhật ký. |
| `RAY_WALLETS_SAVE_S` | 900 | Bao lâu cắt tỉa và lưu bộ nhớ ví (`wallets.json.gz`). |
| `RAY_MODEL_REFIT_S` | 3600 | Bao lâu học lại mô hình rủi ro và quét lại ứng viên bộ lọc. |
| `RAY_TELEGRAM_BOT_TOKEN`, `RAY_TELEGRAM_CHAT_ID` | | Bot Telegram riêng (xem dưới). |
| `RAY_TELEGRAM_PUSH` | `[]` | Nhãn tự đẩy về Telegram, ví dụ `["TRANH","KHONG_THAY_CO"]`. |
| `RAY_PUBLIC_URL` | | Link bảng điều khiển gắn vào tin Telegram. |

## Chi phí credit (Helius)

`getTransactionsForAddress` tính 10 credit cho mỗi 100 giao dịch trả về (tối thiểu 10), `getMultipleAccounts` 1 credit cho tối đa 100 curve. Ước tính: census ~14k/ngày, đọc curve ~17–35k/ngày, lịch sử các curve được chấm ~75k/ngày; tổng ~110–130k/ngày, khoảng 3,3–3,9 triệu/tháng. Nhật ký kết quả thêm vài chục credit/ngày, cộng khoảng 10 credit cho mỗi coin tốt nghiệp trong 30 phút sau khi chấm. Số đã tiêu hiện trên bảng điều khiển ("credit hôm nay") và trong `/api/state`.

Không có Helius thì Rây chạy bằng RPC công khai (đã kiểm 09/10/2026 là có `getTransactionsForAddress`): miễn phí nhưng 2,5 yêu cầu/giây, chỉ mục trễ 15–30 s nên điểm ra muộn hơn mốc khoảng 20–40 s, và có thể bị chặn nếu IP dùng chung bị giới hạn. Trần credit vẫn được đếm như Helius để không lạm dụng.

## Telegram (tuỳ chọn)

1. Nhắn [@BotFather](https://t.me/BotFather) `/newbot` → lấy token → đặt `RAY_TELEGRAM_BOT_TOKEN`.
2. Nhắn một tin bất kỳ cho bot, mở `https://api.telegram.org/bot<token>/getUpdates` để lấy `chat.id` → đặt `RAY_TELEGRAM_CHAT_ID`.
3. Gửi `/score <mint>` hoặc dán mint. Bot chỉ trả lời đúng chat đó, mọi chat khác bị bỏ qua. Tin nhắn tối đa 1 tin/2 s, 300 tin/ngày, không bao giờ có chữ "mua".

## Bảng điều khiển và API

`/` (cần mật khẩu): trạng thái, ô **Chấm ngay**, các curve đang sống (≥ 2 SOL), điểm gần đây có lọc theo nhãn (DƯỚI CỔNG ẩn mặc định) kèm kết quả 30 phút, bấm vào một dòng để xem chi tiết: cờ nào bật với giá trị thô, bằng chứng trong kho sáng lập, chất lượng dữ liệu, link pump.fun và Solscan. Mục *Nhật ký kết quả* là báo cáo 1, 7 hoặc 30 ngày.

| Đường dẫn | Quyền | |
|---|---|---|
| `GET /api/health` | công khai | `app`, `build_sha`, `rpc` (public/helius/private), `filters_frozen`; 503 khi vòng đọc curve đứng quá 3 phút (dùng cho health probe của Bunny). |
| `GET /api/state` | mật khẩu | Trạng thái, curve sống, điểm gần đây. |
| `GET /api/token/<mint>` | mật khẩu | Mọi điểm của một mint. |
| `POST /api/score/<mint>` | mật khẩu | Chấm ngay. |
| `GET /api/registry` | mật khẩu | Định nghĩa và bằng chứng của từng bộ lọc. |
| `GET /api/report?days=7` | mật khẩu | Báo cáo nhật ký kết quả (1–90 ngày). |
| `GET /api/journal`, `GET /api/journal/<tên>` | mật khẩu | Danh sách và tải các file nhật ký. |
| `GET /api/files`, `GET /api/export/file/<tên>` | công khai | File dữ liệu trên volume, gồm dữ liệu nghiên cứu cũ (`sniper-…jsonl`, `swaps-…`, …), như trước. |

## Deploy (Bunny Magic Containers)

Workflow `deploy.yml` build `ray/Dockerfile` ở mỗi push lên `main` và cập nhật container `pumphunt` của app Bunny cũ (cùng image `ghcr.io/baocookin/pumphunt`). Việc cần làm một lần trên Bunny:

1. Thêm biến `RAY_PASSWORD` cho container `pumphunt`. Chưa có thì bảng điều khiển bị khoá (503).
2. Giữ `PH_SOLANA_WS_URL` (Rây dùng key Helius trong đó) và volume `/data`.
3. Các biến `PH_*` khác và container `redis` không còn dùng; xoá được container `redis` để bớt chi phí.
4. Health probe (nếu bật) vẫn là `/api/health`.

Quay lại bộ ghi nghiên cứu cũ: đặt image của container `pumphunt` về tag `f20df965c218dca3c672191abe123bdd5fc9fad5` (cần lại container `redis`).

## Chạy local

```bash
cd ray
pip install -r requirements-dev.txt
RAY_PASSWORD=pw uvicorn app.api:app --port 8080    # không có RPC URL: dùng RPC công khai
# http://localhost:8080 (tên người dùng tuỳ ý, mật khẩu pw)
ruff check . && ruff format --check . && pytest -q
```

Docker: `docker build -f ray/Dockerfile -t ray .` từ gốc repo. Image chép `research/sieve/filters.py` nguyên vẹn; khi khởi động Rây kiểm hash từng bộ lọc (`filters_frozen` trong `/api/health`). Sửa định nghĩa bộ lọc tại chỗ thì bảng điều khiển báo đỏ: bộ lọc mới phải thêm với id mới trong `research/sieve/`, không sửa cái cũ.

## Mã nguồn

| File | Vai trò |
|---|---|
| `app/chain.py` | Giải mã event pump.fun (create, trade, complete) từ log và bản sao self‑CPI, tài khoản bonding curve, thứ tự chuỗi (slot, vị trí giao dịch, event). |
| `app/rpc.py` | JSON‑RPC có điều tốc, xử lý 429, đếm credit theo ngày. |
| `app/live.py` | Census, lịch đọc curve, các mốc quyết định. |
| `app/history.py` | Lịch sử curve đọc dần, kiểm khớp với tài khoản curve. |
| `app/sieve.py` | Nạp bộ lọc đóng băng, chạy chúng, nhãn, tỷ lệ bẫy. |
| `app/engine.py` | Vòng lặp, hàng chờ chấm, sổ điểm và các file nhật ký. |
| `app/outcome.py` | Kết quả 30 phút: công thức vé của nghiên cứu, đọc đúng giờ hoặc từ lịch sử. |
| `app/report.py` | Báo cáo nhật ký so với kho sáng lập. |
| `app/live_rules.py` | Luật sống: bộ lọc nào được quyết định nhãn, tỷ lệ bẫy từ coin mới. |
| `app/features.py` | Đặc trưng lúc chấm: hoạt động trên curve, lệnh mua, dòng tiền, hồ sơ ví mua sớm. |
| `app/wallets.py` | Bộ nhớ ví: ví mua sớm ở các coin trước và kết quả của các coin đó. |
| `app/native.py` | Bộ lọc gốc của Rây (đọc bộ nhớ ví), đóng băng bằng hash. |
| `app/model.py` | Mô hình rủi ro shadow, bản ghi ngoài mẫu và luật chuyển. |
| `app/candidates.py` | Quét ứng viên bộ lọc mỗi giờ. |
| `app/api.py`, `app/static/index.html` | API và bảng điều khiển. |
| `app/telegram.py` | Bot Telegram riêng. |

## Pháp lý

Nghị định 284/2026/NĐ‑CP (hiệu lực 1/9/2026) phạt cá nhân giao dịch tài sản mã hoá không qua tổ chức được cấp phép. Rây chỉ đọc dữ liệu công khai on‑chain, không đặt lệnh, không có ví, và chỉ chủ sở hữu xem được điểm. Không chia sẻ hay bán điểm của Rây.
