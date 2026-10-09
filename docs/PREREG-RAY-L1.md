# PREREG-RAY-L1: vòng sống 1 của Rây (đăng ký 09/10/2026)

Văn bản này ghi lại vì sao hai bộ lọc mới được thêm vào chuỗi rây, chúng được tìm và kiểm trên dữ liệu nào, và luật nào quyết định chúng có được dùng hay không trên dữ liệu về sau.

## 1. Bối cảnh

- Rây chấm mọi launch classic quote SOL ở mốc 2, 5 và 10 phút.
- Từ 09/10 15:05 UTC, mỗi lần chấm có kết quả 30 phút, với định nghĩa của nghiên cứu: vé 0,5 SOL, bẫy khi lỗ ≥ 50%, thắng khi lãi ≥ 100% (`ray/app/outcome.py`).
- Trên 226 kết quả đầu, các bộ lọc của vòng sáng lập không đúng trên coin mới. Bảng dưới so mỗi bộ lọc với các coin cùng tầng SOL và cùng mốc mà nó không bật:

| Bộ lọc | Số lần bật | Bẫy khi bật | Bẫy kỳ vọng | Ghi chú |
|---|---|---|---|---|
| SH-DEV-1 | 43 | 60% | 66% | |
| N-MMAAS-WAVE-STREAM | 33 | 61% | 57% | thắng nhiều gấp đôi |
| N-MMAAS-SPLDIST | 44 | 39% | 63% | |

- Từ đó Rây chỉ cho một bộ lọc quyết định nhãn khi coin mới xác nhận nó. Đây là luật sống ở `ray/app/live_rules.py`, xem mục 5.

## 2. Dữ liệu

- **Nhật ký kết quả của Rây:** các lần chấm có `entry_at` từ 1791558353 đến 1791568465 (09/10, 15:05–17:54 UTC). Gồm 396 kết quả ở các mốc, của 229 mint.
- **Đặc trưng:** tính từ kho giao dịch đã lưu (`rows-2026-10-09.jsonl.gz`), chỉ dùng giao dịch có slot ≤ slot của lúc chấm. Có 387 dòng tính được, 8 dòng chưa có kho giao dịch.

## 3. Tìm và kiểm

- **Chia theo thời gian vào lệnh:**
  - tìm trên 60% đầu: 232 dòng, 132 mint;
  - kiểm trên 40% sau: 155 dòng, 91 mint.
- **Luật thử:** khoảng 37 đặc trưng. Ngưỡng là phân vị 20/33% (hướng ≤) và 67/80% (hướng ≥) trên phần tìm. Tổng cộng 148 luật có ít nhất 25 dòng bật.
- **Chuẩn qua phần tìm:**
  - bẫy khi bật cao hơn ít nhất 12 điểm so với các dòng cùng tầng × mốc không bật;
  - tỷ lệ thắng không cao hơn kỳ vọng.
  - 11 luật qua.
- **Trên phần kiểm** (ngưỡng giữ nguyên):
  - **Giữ được:** số giao dịch 120 giây trước lúc chấm (n120 ≥ 324: +17 → +18 điểm), số giao dịch 60 giây (+12 → +16), và wash ≥ 0,30 (+16 → +17).
  - **Đảo chiều:** số sniper 10 giây đầu, tỷ trọng mua của ví lớn nhất hoặc 5 ví lớn nhất, cỡ lệnh mua trung vị, và tăng SOL trong 120 giây. Các luật này rơi về −22 đến 0 điểm.
- **Kiểm thêm cho hai tín hiệu giữ được:**
  - **Tính theo mint:** chỉ lấy mốc đầu của mỗi mint thì vẫn +12 và +11 điểm.
  - **Theo mốc:** "curve nóng" đúng ở 2 và 5 phút; wash yếu ở 10 phút (+3 điểm, 30 dòng).
  - **Độ đầy đủ dữ liệu:** 85 trên 88 dòng "nóng" có chuỗi reserve đầy đủ và khớp tài khoản curve.
  - **Định nghĩa wash:** khớp đúng 62/62 dòng với định nghĩa đã đóng băng của SH-WASH-1.

## 4. Đăng ký

Hai bộ lọc thêm vào `research/sieve/filters.py`, đều ở tầng shadow (cho nhãn CẢNH GIÁC). Các định nghĩa cũ không bị sửa.

| Id | Định nghĩa | Hash |
|---|---|---|
| RAY-HOT-v1 | ≥ 300 giao dịch trên curve trong 120 s tới slot lúc chấm. Ngưỡng là phân vị 80% trên phần tìm (324), làm tròn xuống. | `5e0698bae2b2c6fb` |
| RAY-WASH-v1 | Đúng phép đo của SH-WASH-1 (ví đổi chiều ≥ 3 lần mang ≥ 30% volume, real_d ≥ 11,73), xếp ở tầng shadow. Ngưỡng đã đóng băng từ 08/10, không chỉnh. | `d3abfd51b48ed38f` |

- `python3 -I research/sieve/filters.py --check` in `frozen check: OK`.
- File `filters.py` giờ có sha256 khác với bảng ở PREREG-SIEVE-R1 mục 9, vì chỉ thêm định nghĩa mới. Hash của mọi định nghĩa cũ giữ nguyên.

## 5. Luật về sau (không chỉnh sau khi thấy dữ liệu)

- **Phạm vi:** hai bộ lọc chỉ được quyết định nhãn trong Rây theo luật sống, tính trên nhật ký 7 ngày gần nhất. Trước khi deploy chúng chưa tồn tại, nên mọi bằng chứng của chúng đều là dữ liệu sau đăng ký.
- **Được dùng** khi đạt cả ba:
  - bật ≥ 30 dòng, trên ≥ 10 mint;
  - tỷ lệ bẫy khi bật cao hơn ít nhất 10 điểm so với các dòng cùng tầng × mốc không bật, và cận dưới khoảng Wilson 95% không thấp hơn tỷ lệ đó;
  - tỷ lệ thắng không cao hơn.
- **Tiếp tục được dùng** khi còn cao hơn ít nhất 5 điểm và tỷ lệ thắng không cao hơn.
- **Tạm ngưng:** không đạt thì bộ lọc vẫn được tính, vẫn hiện, vẫn được ghi, nhưng không quyết định nhãn.
- **Luật áp như nhau** cho mọi bộ lọc chính và phụ, kể cả của vòng sáng lập.
- **Không chỉnh ngưỡng** của RAY-HOT-v1 hay RAY-WASH-v1. Một ngưỡng mới là một id mới, ví dụ RAY-HOT-v2, với bằng chứng mới.

## 6. Giới hạn

- Hai giờ rưỡi dữ liệu của một buổi chiều. Mức tách vừa phải: khoảng 70% bẫy khi bật, so với 50–57% kỳ vọng.
- Đây là cảnh báo, không phải phân loại chắc chắn. Coin không bật cờ vẫn phần lớn là bẫy.
- Rây không bao giờ đưa ra tín hiệu mua.
