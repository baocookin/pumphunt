# PREREG-RAY-L3: mô hình rủi ro chạy shadow và quét ứng viên (đăng ký 09/10/2026)

Văn bản này ghi lại hai thứ: mô hình rủi ro của Rây, và luật quyết định khi nào nó được thay tỷ lệ bẫy đang hiển thị. Nó cũng ghi lại bản quét ứng viên bộ lọc tự chạy mỗi giờ. Mọi chi tiết dưới đây được cố định trước khi có dữ liệu dùng để chấm chúng.

## 1. Vì sao

- **Rủi ro đang hiển thị:** tỷ lệ bẫy của cùng tầng SOL × mốc trên nhật ký 7 ngày.
  - Thời gian và tầng là hai yếu tố mạnh nhất đã đo.
  - Nhưng trong cùng một ô, 20 đặc trưng lúc chấm của đợt B (PREREG-RAY-L2) còn mang thêm thông tin.
- **Bộ lọc và mô hình khác nhau:**
  - một bộ lọc chỉ đọc một đặc trưng ở một ngưỡng, và cho ra một nhãn;
  - một mô hình cân mọi đặc trưng cùng lúc, và cho ra một xác suất.
- **Thử trên 837 dòng ngày 09/10** (chia 60/40 theo giờ vào lệnh như L2):

| Thước đo trên 40% sau | Mô hình | Tầng × mốc |
|---|---|---|
| Log-loss | 0,616 | 0,678 |
| Log-loss lúc 2 phút | 0,635 | 0,671 |
| Log-loss lúc 5 phút | 0,612 | 0,694 |
| Log-loss lúc 10 phút | 0,584 | 0,669 |

- **Phần tốt hơn:** 0,061 log-loss, khoảng tin cậy 95% theo mint 0,028…0,095.
- **Hiệu chỉnh trên 40% sau:**

| Mô hình báo | Bẫy thực tế |
|---|---|
| 32% | 32% |
| 51% | 52% |
| 69% | 70% |
| 83% | 81% |

- **Vì sao chưa dùng ngay:** mức phạt L2 được chọn trên chính phép chia đó (thử từ 1 đến 300, tốt nhất ở 10–30). Vì vậy đây chưa phải phép kiểm sạch. Mô hình chạy shadow, và chỉ được dùng theo luật ở mục 4, trên dữ liệu về sau.

## 2. Mô hình (cố định)

Mã ở `ray/app/model.py`.

- **Mục tiêu:** xác suất vé 0,5 SOL mua lúc chấm là bẫy (lỗ ≥ 50%) sau 30 phút.
- **Đầu vào:**
  - 20 đặc trưng của `ray/app/features.py`. Các số đếm (giao dịch 2 phút, giao dịch 1 phút, ví 2 phút, ví mua sớm, số coin trước của dev) lấy log(1 + x).
  - Tỷ lệ bẫy của dev tách thành giá trị và cờ "đã biết".
  - Tầng SOL dạng one-hot, 5–13 SOL làm gốc.
  - Mốc dạng one-hot, 2 phút làm gốc.
  - Tổng cộng 25 đầu vào cộng hệ số chặn.
- **Chuẩn hoá:** mỗi đầu vào bị cắt về phân vị 1–99% của dữ liệu học, rồi chuẩn hoá về trung bình 0, độ lệch 1.
- **Ước lượng:**
  - hồi quy logistic, phạt L2 với λ = 30 trên các đầu vào đã chuẩn hoá;
  - hệ số chặn không bị phạt;
  - giải bằng phương pháp Newton.
- **Dữ liệu học:**
  - các dòng ở mốc đã có kết quả 30 phút, có đặc trưng, trong 7 ngày gần nhất;
  - cần ≥ 300 dòng, trong đó ≥ 50 bẫy và ≥ 50 không bẫy.
- **Học lại mỗi giờ** (`RAY_MODEL_REFIT_S`). Mô hình mới nhất lưu ở `<data>/ray/model.json`, và được đọc lại khi khởi động.

## 3. Bản ghi ngoài mẫu

- Mỗi lần chấm ở mốc ghi vào nhật ký hai số:
  - `model_p`: xác suất của mô hình đang có lúc đó;
  - `base_risk`: tỷ lệ Rây hiển thị khi không có mô hình (tầng × mốc, hoặc tỷ lệ của bộ lọc chính đã xác nhận nếu cao hơn).
- Mô hình đó chỉ học từ các kết quả đã chốt trước lúc chấm. Vì vậy mọi `model_p` trong nhật ký là dự báo trên dữ liệu mô hình chưa thấy.
- **Thước đo:** log-loss của từng số trên các dòng đã có kết quả, với xác suất bị kẹp trong [0,0001; 0,9999].
- **Phần tốt hơn** của một dòng = log-loss của `base_risk` − log-loss của `model_p`.

## 4. Luật chuyển (không chỉnh sau khi thấy dữ liệu)

Xét các dòng trong 7 ngày gần nhất có cả `model_p` lẫn `base_risk`.

**Mô hình được dùng** khi đạt cả ba:
- có ≥ 2 ngày UTC trọn, mỗi ngày ≥ 300 dòng như vậy;
- phần tốt hơn trung bình lớn hơn 0, và cận dưới khoảng tin cậy 95% (theo mint) cũng lớn hơn 0;
- phần tốt hơn của ngày trọn gần nhất trong số đó lớn hơn 0.

**Khi được dùng:**
- tỷ lệ bẫy hiển thị là xác suất của mô hình;
- tỷ lệ tầng × mốc vẫn đi kèm để đối chiếu;
- nhật ký vẫn ghi `base_risk`, nên phép so sánh vẫn tiếp tục.

**Khi một điều kiện không còn đạt,** Rây quay về tỷ lệ tầng × mốc. Luật được tính lại mỗi giờ.

**Nhãn không bao giờ phụ thuộc mô hình.** TRÁNH, CẢNH GIÁC và các nhãn khác vẫn chỉ do bộ lọc đã được luật sống xác nhận quyết định. Mô hình không bao giờ đưa ra tín hiệu mua.

## 5. Quét ứng viên bộ lọc

Mã ở `ray/app/candidates.py`. Đây là phương pháp của L2, tự chạy mỗi giờ trên nhật ký 7 ngày.

- **Dữ liệu:** các dòng ở mốc đã có kết quả, có đặc trưng. Cần ≥ 200 dòng.
- **Chia theo giờ vào lệnh:** 60% đầu để tìm, 40% sau để kiểm.
- **Luật thử:** mỗi đặc trưng ở phân vị 20% và 33% (hướng ≤), 67% và 80% (hướng ≥) của phần tìm.
- **Qua phần tìm:** bật ≥ 25 dòng, và vé kém hơn ≥ 10 điểm so với cùng tầng × mốc không bật.
- **Qua phần kiểm,** ngưỡng giữ nguyên:
  - chuẩn vào của luật sống (≥ 30 dòng, ≥ 10 mint, kém hơn ≥ 10 điểm, cận dưới khoảng tin cậy > 0);
  - Benjamini–Hochberg q = 0,10 trên mọi phép kiểm ở phần kiểm.
- **Chỉ tìm cảnh báo** (vé kém hơn). Bản quét không tìm và không hiện bất cứ dấu hiệu "tốt hơn" nào.
- **Mỗi ứng viên hiện kèm:**
  - số đo ở hai phần;
  - phần dòng của nó đã có bộ lọc chính hay phụ bật;
  - bộ lọc đã đăng ký đo cùng đặc trưng, nếu có. Ví dụ RAY-CROWD-v1 cho số ví trong 2 phút.

## 6. Đăng ký một ứng viên

- **Ứng viên chỉ để xem:** nó không đổi nhãn, cũng không đổi rủi ro.
- **Chỉ đăng ký khi chủ sở hữu đồng ý.** Khi đó:
  - bộ lọc mới mang **mã mới**, được đóng băng bằng hash, ở tầng shadow;
  - một văn bản PREREG-RAY-Ln ghi số đo của bản quét lúc đó;
  - như mọi bộ lọc, nó chỉ quyết định nhãn khi luật sống xác nhận nó trên dữ liệu sau khi đăng ký.
- **Ngưỡng làm tròn** về số đơn giản theo hướng bật nhiều hơn, và cũng phải qua phần kiểm (như L2).

## 7. Giới hạn

- **Một trạng thái thị trường:** mô hình học trên đúng trạng thái đang diễn ra. Khi thị trường đổi, nó có thể kém đi. Luật chuyển đánh giá lại mỗi giờ, nên mô hình có thể bị thay ra.
- **Log-loss đo chất lượng xác suất, không đo tiền.** Một xác suất tốt hơn không có nghĩa là có lợi thế giao dịch.
- **Bộ nhớ ví:** một phần đặc trưng dựa vào bộ nhớ ví. Nếu mất file, bộ nhớ được dựng lại từ 2 ngày kho giao dịch, nên trong lúc đó các đặc trưng này yếu hơn.
- **Rây chỉ đọc dữ liệu công khai và cảnh báo rủi ro,** không bao giờ đưa ra tín hiệu mua.
