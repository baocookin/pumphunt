# Đăng ký trước (pre-registration), 06/10/2026

Văn bản này cố định *trước* khi có dữ liệu để kiểm định: định nghĩa cái gì được đo, đo trên mẫu nào, và kết luận theo tiêu chí nào. Mã tương ứng nằm ở `bot/app/prereg.py`; kết quả hiện trên dashboard (bảng "Giả thuyết đăng ký trước") và ở `/api/survivor/summary` → `prereg`.

## Thời điểm

* Đăng ký: commit đầu tiên chứa file này, trước 16:00 UTC ngày 06/10/2026.
* **Mẫu kiểm định**: các migration có thời điểm on‑chain từ `2026-10-06 16:00:00 UTC` trở đi (`PREREG_TS = 1791302400`). Harvester chỉ tính một dòng khoảng 25 giờ sau migration, nên lúc đăng ký chưa có kết quả nào của mẫu này.
* Dữ liệu trước thời điểm đó đã được xem (một phần) khi thiết kế; nó chỉ là thăm dò, không phải bằng chứng.

## Đại lượng đo (chung cho mọi giả thuyết)

* Ô: vào lúc T+30 phút sau migration, giữ 1 giờ, vị thế 1 SOL.
* Net = SOL nhận về / SOL bỏ ra − 1, khớp lệnh trên reserve thật của pool PumpSwap (fills v2): mô hình *replay* khi có đủ mọi swap từ lúc vào tới lúc ra, nếu không thì *ghost* (bi quan); phí pool thật cả hai chiều, 0.001 SOL phí giao dịch mỗi chiều, độ trễ 3 giây từ quyết định tới khớp.
* Chỉ pool quote bằng SOL; mỗi token tính một lần (lần harvest mới nhất); chỉ dòng tính bằng phiên bản fills ≥ 2.

## Tiêu chí kết luận (giữ nguyên như giả thuyết C)

* Cần n ≥ 300.
* **KILL** nếu median net ≤ −1.25%, hoặc 2% token tốt nhất chiếm ≥ 50% tổng lãi.
* **PASS** nếu median net > +2% và tỉ lệ thắng ≥ 45%.
* Còn lại: **INCONCLUSIVE**.
* Khoảng tin cậy 95% của median (từ thống kê thứ tự, không giả định phân phối) được báo kèm để tham khảo; nó không thay đổi tiêu chí của C và C2.

## Giả thuyết

| Tên | Tập con | Mẫu |
|---|---|---|
| C | Mọi graduate quote SOL (đăng ký từ đầu dự án) | Toàn bộ |
| C* | Như C | Mẫu kiểm định (để so với C2) |
| C2 | Tại đúng T+30 (trước độ trễ): pool có **≥ 10 SOL thật** trong vault **và** có **ít nhất một swap trong 60 giây** trước đó | Mẫu kiểm định |

Lý do chọn C2: lệnh 1 SOL không vượt 1/10 lượng SOL thật trong vault, và pool còn được giao dịch. Ngưỡng đặt theo cơ chế thị trường, không theo kết quả. Cả hai điều kiện đều đo ở thời điểm quyết định, không phải lúc khớp lệnh 3 giây sau.

## Luật dựa trên đặc trưng (C3 trở đi)

* Chỉ dùng đặc trưng đã công khai trước T+30: trạng thái pool tại T+30, order flow 5 phút trước T+30, snapshot holder T+30, lịch sử bonding curve, nguồn tiền của các ví.
* **Khám phá**: migration trong khoảng `[06/10 16:00, 20/10 16:00)` UTC, trên quần thể C2. Chọn tối đa **3 luật**, mỗi luật là điều kiện đơn giản trên tối đa 3 đặc trưng.
* **Đăng ký luật**: một commit thêm luật vào `RULES` trong `bot/app/prereg.py`, với `since` bằng giờ tròn kế tiếp sau commit. Mẫu kiểm định của luật là các migration từ `since` trở đi. Luật không được sửa sau khi đăng ký; sửa nghĩa là một luật mới với mẫu mới.
* **Kiểm định**: một lần, khi n ≥ 300, theo đúng tiêu chí trên. Vì có nhiều luật, thêm một điều kiện để PASS: cận dưới khoảng tin cậy 95% của median phải > 0.

## Không được làm

* Đổi ô, cỡ lệnh, mô hình khớp lệnh, chi phí hay ngưỡng sau khi thấy kết quả của mẫu kiểm định.
* Bỏ dòng khỏi mẫu, trừ các trường hợp đã định nghĩa ở trên.
* Coi bảng chia tầng thăm dò trên dashboard, hay dữ liệu trước `PREREG_TS`, là bằng chứng.
* Nếu phép đo thay đổi (tăng `FILLS_VERSION`), mẫu kiểm định vẫn chỉ gồm các dòng tính bằng phiên bản từ phiên bản lúc đăng ký (2) trở lên, và mọi thay đổi được ghi lại ở đây.
