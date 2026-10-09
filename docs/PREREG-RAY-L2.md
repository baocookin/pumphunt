# PREREG-RAY-L2: vòng sống 2 của Rây (đăng ký 09/10/2026)

Văn bản này ghi lại ba bộ lọc mới của vòng 2: chúng đo gì, được tìm và kiểm trên dữ liệu nào, và luật nào quyết định chúng có được dùng trên dữ liệu về sau. Văn bản cũng ghi một thay đổi so với PREREG-RAY-L1 (mục 7).

## 1. Bối cảnh

- Vòng 1 tìm ra hai tín hiệu giữ được: curve quá nóng (RAY-HOT-v1) và wash (RAY-WASH-v1).
- Đợt A (baocookin/pumphunt#34) đổi luật sống: bộ lọc được chấm bằng tiền (lãi/lỗ của vé 0,5 SOL), không bằng tỷ lệ bẫy. Xem mục 7.
- Vòng 2 thêm hai nguồn tín hiệu mà vòng 1 không có:
  - **Đặc trưng lúc chấm** (`ray/app/features.py`): đo trên giao dịch của chính coin, chỉ dùng giao dịch có slot ≤ slot lúc chấm. Từ vòng này, mỗi điểm và mỗi dòng kết quả lưu kèm các đặc trưng (`features`).
  - **Bộ nhớ ví** (`ray/app/wallets.py`): những ví mua trong 60 giây đầu của một coin đã làm gì ở các coin Rây chấm trước đó, và các coin đó ra sao.

## 2. Dữ liệu

- **Nhật ký kết quả của Rây ngày 09/10:**
  - 854 kết quả 30 phút đã chốt ở các mốc 2, 5 và 10 phút;
  - 837 dòng có kho giao dịch (`rows-2026-10-09.jsonl.gz`), của 466 mint;
  - vào lệnh từ 15:05 đến 20:43 UTC (`entry_at` 1791558353 … 1791578631);
  - 58% bẫy, 10% thắng.
- **Cách tính đặc trưng:**
  - chạy đúng mã Rây dùng khi chạy thật, theo thứ tự thời gian vào lệnh;
  - bộ nhớ ví chỉ biết các coin đã được chấm trước dòng đó;
  - kết quả của một coin chỉ vào bộ nhớ từ lúc nó đến hạn (30 phút sau lúc vào lệnh).
- **Kết quả:** vé 0,5 SOL mua lúc chấm, bán sau 30 phút, theo định nghĩa của nghiên cứu. Bẫy là lỗ ≥ 50%, thắng là lãi ≥ 100%.

## 3. Đặc trưng thử (20)

| Nhóm | Đặc trưng |
|---|---|
| Hoạt động trên curve | số giao dịch 120 s và 60 s; số ví giao dịch trong 120 s; số giao dịch mỗi ví; độ đều của nhịp giao dịch (hệ số biến thiên của khoảng cách slot) |
| Lệnh mua | tỷ lệ lệnh mua cùng cỡ lặp ≥ 3 lần; tỷ lệ ví mua bụi (< 0,01 SOL); tỷ trọng mua của 5 ví lớn nhất |
| Dòng tiền | tỷ trọng SOL bán trong 60 s; wash (phép đo của SH-WASH-1); SOL thật tăng trong 60 s; khoảng cách tới đỉnh trước lúc chấm (`dd_pre`) |
| Bộ nhớ ví | số ví mua sớm; tỷ lệ và tỷ trọng SOL của ví mua sớm "chuyên nghiệp" (mua sớm ở ≥ 2 coin trước); của ví từng xả sớm (bán ≥ 50% hàng mua sớm trước lúc chấm đầu tiên của coin đó); của ví mà các coin trước ≥ 70% là bẫy; số coin trước của dev và tỷ lệ bẫy của chúng |

## 4. Tìm và kiểm

**Chia theo thời gian vào lệnh:**
- tìm trên 60% đầu: 502 dòng, 283 mint, 15:05–18:40 UTC;
- kiểm trên 40% sau: 335 dòng, 188 mint, 18:41–20:43 UTC.

**Luật thử:**
- mỗi đặc trưng ở phân vị 20% và 33% (hướng ≤), 67% và 80% (hướng ≥) của phần tìm: 80 luật;
- thước đo là thước của luật sống. Lấy lãi/lỗ trung bình của vé ở dòng luật bật, so với dòng không bật cùng tầng SOL × mốc. Số dương là số điểm vé kém hơn ("chặn được").
- khoảng tin cậy 95% tính theo mint (ba mốc của một coin đi cùng nhau).

**Chuẩn:**

| Bước | Chuẩn | Số luật qua |
|---|---|---|
| Phần tìm | bật ≥ 25 dòng, kém hơn ≥ 10 điểm | 29 / 80 |
| Phần kiểm, ngưỡng giữ nguyên | chuẩn vào của luật sống: ≥ 30 dòng, ≥ 10 mint, kém hơn ≥ 10 điểm, cận dưới khoảng tin cậy > 0 | 8 / 29 |
| Kiểm đa so sánh | Benjamini–Hochberg q = 0,10 trên 29 phép kiểm ở phần kiểm | đúng 8 luật trên |

**Tám luật qua phần kiểm** (điểm vé kém hơn, phần tìm → phần kiểm, cận dưới phần kiểm trong ngoặc):

| Luật | Phần tìm | Phần kiểm |
|---|---|---|
| `dd_pre` ≤ 0,038 (sát đỉnh) | +12 | +33 (+21) |
| ví giao dịch 120 s ≥ 108 | +23 | +30 (+13) |
| giao dịch 60 s ≥ 138 | +17 | +27 (+11) |
| ví mua sớm ≤ 45 | +15 | +20 (+7) |
| tỷ trọng SOL ví mua sớm chuyên nghiệp ≥ 0,506 | +18 | +20 (+6) |
| giao dịch 120 s ≥ 195 | +21 | +24 (+6) |
| giao dịch 60 s ≥ 89 | +16 | +23 (+3) |
| ví giao dịch 120 s ≥ 170 | +22 | +25 (+2) |

**Đảo chiều ở phần kiểm:**
- tỷ trọng mua của 5 ví lớn nhất: +19/+20 → −18/−29;
- số ví mua sớm ≥ 123: +11 → −13;
- nhịp giao dịch đều: +29 → −2;
- tỷ lệ ví mua sớm chuyên nghiệp tính theo số ví: +28 → +4. Tính theo SOL thì giữ được.

**Chọn để đăng ký:**
- Mỗi phép đo chỉ một luật.
- Ngưỡng được làm tròn về số đơn giản, theo hướng bật nhiều hơn. Ngưỡng làm tròn cũng phải qua chuẩn của phần kiểm.
- Phép đo có ≥ 85% số dòng trùng với một bộ lọc đã đăng ký thì không đăng ký lại.

| Luật | Quyết định |
|---|---|
| ví giao dịch 120 s ≥ 108 → 100 | **RAY-CROWD-v1** |
| tỷ trọng SOL ví mua sớm chuyên nghiệp ≥ 0,506 → 0,50 | **RAY-SERIAL-v1** |
| `dd_pre` ≤ 0,038 → 0,04 | **RAY-PEAK-v1** |
| ví mua sớm ≤ 45 → 50 | Không đăng ký: ở ngưỡng 50, phần kiểm chỉ còn +13 (−3…+29). Kết quả không đứng được khi làm tròn. |
| giao dịch 60 s ≥ 138 hoặc ≥ 89 | Không đăng ký: 97% số dòng của nó là dòng RAY-CROWD-v1. |
| giao dịch 120 s ≥ 195 | Không đăng ký: cùng phép đo với RAY-HOT-v1, mà RAY-HOT-v1 vẫn đang kiểm forward. Một ngưỡng mới sẽ là RAY-HOT-v2, với bằng chứng mới. |
| ví giao dịch 120 s ≥ 170 | Cùng phép đo với RAY-CROWD-v1. |

## 5. Đăng ký

Cả ba bộ lọc ở tầng shadow: khi được xác nhận, chúng cho nhãn CẢNH GIÁC. Không định nghĩa cũ nào bị sửa.

| Id | Định nghĩa | Nơi | Hash |
|---|---|---|---|
| RAY-CROWD-v1 | ≥ 100 ví khác nhau giao dịch trên curve trong 120 s tới slot lúc chấm. | `research/sieve/filters.py` | `c8322b63559427f7` |
| RAY-PEAK-v1 | SOL thật lúc chấm cách đỉnh trước đó ≤ 4% (`dd_pre` của nhóm ANATOMY ≤ 0,04). | `research/sieve/filters.py` | `dd0c7915f60326f0` |
| RAY-SERIAL-v1 | Ví mua sớm ở ≥ 2 coin trước mà Rây đã chấm mang ≥ 50% số SOL mà người mua sớm của coin này bỏ ra trong 60 s đầu. Không có ví mua sớm thì không chấm. | `ray/app/native.py` | `ea22fbee3198ff9c` |

**Số đo ở ngưỡng đã đăng ký:**

| Id | Phần tìm | Phần kiểm |
|---|---|---|
| RAY-CROWD-v1 | 181 dòng, 141 mint, +25 (+6…+45); bẫy 67% so với 48%; thắng 11% so với 20% | 104 dòng, 83 mint, +36 (+19…+53); bẫy 73% so với 50%; thắng 6% so với 18% |
| RAY-PEAK-v1 | 104 dòng, 79 mint, +12 (−7…+31); bẫy 53% so với 58%; thắng 8% so với 16% | 70 dòng, 62 mint, +35 (+24…+45); bẫy 73% so với 53%; thắng 0 trên 70 dòng |
| RAY-SERIAL-v1 | 174 dòng, 99 mint, +15 (−5…+35); bẫy 61% so với 55% | 172 dòng, 96 mint, +20 (+6…+33); bẫy 61% so với 53%; thắng 5% so với 11% |

**Trùng nhau:**
- RAY-CROWD-v1 chứa mọi dòng của RAY-HOT-v1.
- 29% số dòng RAY-PEAK-v1 là dòng RAY-CROWD-v1. Chỉ xét các dòng RAY-CROWD-v1 không bật, RAY-PEAK-v1 vẫn kém hơn 24 điểm trên cả ngày (+9…+39).
- 39% số dòng RAY-SERIAL-v1 là dòng RAY-CROWD-v1.

**Bộ lọc gốc của Rây (native):**
- Bộ nhớ ví không nằm trong gói nghiên cứu đóng băng, nên RAY-SERIAL-v1 được định nghĩa trong `ray/app/native.py`.
- Nó cũng được đóng băng bằng hash, cùng kỷ luật với gói nghiên cứu. Hash phủ:
  - hàm của bộ lọc;
  - các định nghĩa nó đọc: `early_slot`, `early_activity` và `memory_features` trong `features.py`;
  - cách bộ nhớ đếm: `WalletBook.features`, `note_launch`, `_note`, `note_outcome`;
  - các hằng số.
- Sửa tại chỗ bất kỳ phần nào ở trên sẽ hiện trên health check (`filters_frozen`) và trên bảng điều khiển.

**Kiểm tra:**
- `python3 -I research/sieve/filters.py --check` in `frozen check: OK`.
- Hash của mọi định nghĩa cũ giữ nguyên.

## 6. Luật về sau (không chỉnh sau khi thấy dữ liệu)

- **Luật sống:** ba bộ lọc chỉ quyết định nhãn trong Rây theo luật sống bằng tiền của đợt A (`ray/app/live_rules.py`), trên nhật ký 7 ngày gần nhất.
  - **Vào:** bật ≥ 30 dòng, trên ≥ 10 mint. Vé ở các dòng nó bật kém hơn ≥ 10 điểm so với dòng không bật cùng tầng × mốc, và cận dưới khoảng tin cậy 95% (theo mint) > 0.
  - **Giữ:** khi còn kém hơn ≥ 5 điểm.
- **Dữ liệu tính cho chúng:**
  - Trước khi deploy, ba bộ lọc chưa tồn tại, nên mọi dòng chúng bật đều là dữ liệu sau đăng ký.
  - Các dòng trước deploy chỉ vào nhóm so sánh, như dòng không bật. Nếu bộ lọc tốt thật, điều này làm nhóm so sánh xấu đi và số "chặn được" nhỏ lại, tức là nghiêng về phía khó xác nhận.
- **Không chỉnh ngưỡng.** Một ngưỡng mới là một id mới, với bằng chứng mới.
- **Bộ nhớ ví:**
  - lưu ở `<data>/ray/wallets.json.gz`, cắt tỉa và ghi mỗi 15 phút;
  - mất file thì dựng lại từ kho giao dịch 2 ngày gần nhất và nhật ký kết quả;
  - ví chỉ mua sớm một lần bị quên sau 1 ngày, ví khác sau 7 ngày không thấy lại.
- **Mô hình rủi ro (đợt C):** các đặc trưng được lưu để làm mô hình rủi ro hiệu chỉnh ở chế độ shadow. Mô hình đó không quyết định gì cho tới khi thắng tầng × mốc trên những ngày nó chưa thấy, và sẽ có văn bản đăng ký riêng.

## 7. Thay đổi so với PREREG-RAY-L1

- **Thay đổi:** PREREG-RAY-L1 mục 5 chấm bộ lọc bằng tỷ lệ bẫy. Tối 09/10, đợt A đổi sang chấm bằng tiền với chuẩn ở mục 6.
- **Lý do:** trên 387 dòng, đếm bẫy xếp hạng sai cả hai chiều.
  - N-MMAAS-WAVE-STREAM bật nhiều hơn 7 điểm bẫy, nhưng vé ở coin nó chặn lại lời hơn 11 điểm, vì nó chặn cả coin thắng lớn.
  - SH-SG-1 chỉ hơn 6 điểm bẫy, nhưng coin nó chặn lỗ thêm 21 điểm.
- **Đây là thay đổi sau khi đã thấy dữ liệu,** nên được ghi rõ ở đây. Văn bản L1 giữ nguyên.
- **Phạm vi:** luật mới áp như nhau cho mọi bộ lọc chính và phụ, kể cả RAY-HOT-v1 và RAY-WASH-v1.
- **Kết quả đầu tiên:** đến 21:10 UTC, chỉ trên dữ liệu sau deploy của chúng:
  - RAY-WASH-v1 đạt luật tiền: 48 dòng, +28 điểm, +4…+53;
  - RAY-HOT-v1 chưa đạt: 67 dòng, +23 điểm, −1…+47.

## 8. Giới hạn

- **Một buổi chiều và tối** (khoảng 5 giờ 40 phút vào lệnh), cùng một trạng thái thị trường. Phần tìm và phần kiểm chỉ cách nhau theo giờ trong cùng một ngày.
- **RAY-PEAK-v1 không đều giữa hai phần:**
  - ở phần tìm, coin sát đỉnh ít bẫy hơn kỳ vọng (53% so với 58%) nhưng hầu như không thắng;
  - ở phần kiểm, chúng nhiều bẫy hơn hẳn (73% so với 53%).
  - Tín hiệu có thể phụ thuộc trạng thái thị trường. Luật sống là phép kiểm thật.
- **RAY-SERIAL-v1:** bộ nhớ ví bắt đầu rỗng lúc 15:05, nên phần tìm đo một bộ nhớ còn đang đầy dần.
- **80 luật được thử.** BH giữ cùng 8 luật, nhưng đây vẫn là thử nhiều lần trên một ngày. Luật sống trên dữ liệu mới mới là phép kiểm.
- **Đây là cảnh báo, không phải phân loại chắc chắn.** Coin không bật cờ vẫn phần lớn là bẫy (58% cả ngày).
- **Rây không bao giờ đưa ra tín hiệu mua.**
