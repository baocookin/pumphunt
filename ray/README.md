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
```

Một mốc D chỉ được quyết định trong 45 s sau D; curve phát hiện muộn hơn thì mốc đó bị bỏ (đếm là `missed`). Ngoài ra có thể chấm bất kỳ mint nào ngay lập tức (nút **Chấm ngay** trên bảng điều khiển, hoặc Telegram), tối đa 60 lần/giờ.

## Nhãn

| Nhãn | Nghĩa |
|---|---|
| **TRÁNH** | Bộ lọc chính bật: dev + creator còn giữ ≥ 3% cung (SH-DEV-1), hoặc sóng mua cùng cỡ ≥ 4 ví trong một slot (N-MMAAS-WAVE-STREAM). Trong kho sáng lập: 24/30 và 26/29 dòng bị cờ là bẫy. |
| **THIẾU DỮ LIỆU** | Bộ lọc chính cần đủ mọi giao dịch nhưng chuỗi reserve bị hở, lịch sử bị cắt (quá `RAY_HISTORY_MAX_TX`) hoặc thiếu vị trí giao dịch. |
| **CẢNH GIÁC** | Chỉ cờ phụ bật (bằng chứng yếu hơn): SH-SG-1, N-MMAAS-SPLDIST, N-MMAAS-WAVE, CLD-ORPHAN-v1. |
| **ÍT HOẠT ĐỘNG** | Không thấy cờ, nhưng 2 phút qua dưới 5 giao dịch, dưới 3 ví mua, hoặc không có giao dịch trong 60 s (ngoài cổng F0). |
| **KHÔNG THẤY CỜ** | Không thấy dấu hiệu nào. **Không phải tín hiệu mua**: tỷ lệ bẫy nền của tầng vẫn áp dụng (13–30 SOL lúc 2 phút: 33/47 = 70%). |
| **DƯỚI CỔNG** | Dưới 11,66 SOL thật: vé 0,5 SOL không thể lỗ 50% trên curve (phí và trượt giá vẫn ăn mòn). Bộ lọc không áp dụng. |
| **NGOÀI VÙNG ĐO** | Từ 70 SOL trở lên: sát tốt nghiệp, ngoài vùng bộ lọc đã được đo. |
| **ĐÃ TỐT NGHIỆP** | Curve đã hoàn tất. |

**Tỷ lệ bẫy** đi kèm mỗi điểm: số dòng bẫy / số dòng của ô (tầng SOL × mốc D) trong kho sáng lập, hoặc của cả tầng khi ô dưới 15 dòng; khi một bộ lọc chính bật mà tỷ lệ của nó cao hơn thì dùng tỷ lệ đó. Kèm khoảng tin cậy Wilson 95%. "Bẫy" = vé 0,5 SOL vào lúc chấm, lỗ ≥ 50% sau 30 phút. Cờ ngữ cảnh (FADE, TOPDIST, WASH…) chỉ để đọc, không đổi nhãn.

Điểm nào cũng ghi chất lượng dữ liệu: số giao dịch đã đọc, chuỗi reserve có liền không, lịch sử có khớp tài khoản curve lúc quyết định không, và phải chờ chỉ mục bao lâu. Một điểm "chưa khớp" được chấm tới giao dịch cuối đọc được, tức là sớm hơn lúc quyết định.

## Cấu hình (biến môi trường)

Đủ dùng chỉ với `RAY_PASSWORD`; mọi thứ khác có mặc định. Biến danh sách viết dạng JSON, ví dụ `RAY_TELEGRAM_PUSH=["TRANH"]`.

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `RAY_PASSWORD` | (không) | Mật khẩu HTTP Basic cho bảng điều khiển và API (tên người dùng tuỳ ý). Chưa đặt thì mọi trang riêng trả 503. |
| `RAY_RPC_URL` | | URL HTTPS của RPC có `getTransactionsForAddress` (Helius, kèm key). Không đặt thì lấy `PH_SOLANA_WS_URL` (biến cũ trên Bunny) đổi sang https; không có cả hai thì dùng RPC công khai `api.mainnet-beta.solana.com` (miễn phí, chậm hơn). URL không bao giờ xuất hiện trong log hay lỗi. |
| `RAY_RPC_RPS` | 10 (riêng), 2,5 (công khai) | Số yêu cầu mỗi giây. RPC công khai trả 429 từ khoảng 3/s. |
| `RAY_DAILY_CREDITS` | 200000 | Trần credit Helius mỗi ngày (UTC). Tới trần thì ngừng chấm; census và đọc curve được vượt 25%. |
| `RAY_CHECKPOINTS_S` | `[120,300,600]` | Các mốc quyết định (giây). |
| `RAY_HISTORY_MAX_TX` | 6000 | Trần giao dịch đọc cho một curve (~600 credit). |
| `RAY_SYNC_WAITS_S` | `[3,5,8,10,14]` | Các lần chờ trước khi đọc lại phần đuôi lịch sử (tổng tối đa 40 s). |
| `RAY_WORKERS` | 4 | Số curve chấm song song. |
| `RAY_SCORE_BELOW_GATE` | false | Chấm cả curve dưới cổng (đọc thêm ~1.000 lịch sử/ngày, vô ích vì không có phủ quyết dưới cổng). |
| `RAY_ONDEMAND_PER_HOUR` | 60 | Số lần "Chấm ngay" mỗi giờ. |
| `RAY_DATA_DIR` / `PH_DATA_DIR` | `/data` trong image | Điểm ghi vào `<data>/ray/scores-YYYY-MM-DD.jsonl`. |
| `RAY_TELEGRAM_BOT_TOKEN`, `RAY_TELEGRAM_CHAT_ID` | | Bot Telegram riêng (xem dưới). |
| `RAY_TELEGRAM_PUSH` | `[]` | Nhãn tự đẩy về Telegram, ví dụ `["TRANH","KHONG_THAY_CO"]`. |
| `RAY_PUBLIC_URL` | | Link bảng điều khiển gắn vào tin Telegram. |

## Chi phí credit (Helius)

`getTransactionsForAddress` tính 10 credit cho mỗi 100 giao dịch trả về (tối thiểu 10), `getMultipleAccounts` 1 credit cho tối đa 100 curve. Ước tính: census ~14k/ngày, đọc curve ~17–35k/ngày, lịch sử các curve được chấm ~75k/ngày; tổng ~110–130k/ngày, khoảng 3,3–3,9 triệu/tháng. Số đã tiêu hiện trên bảng điều khiển ("credit hôm nay") và trong `/api/state`.

Không có Helius thì Rây chạy bằng RPC công khai (đã kiểm 09/10/2026 là có `getTransactionsForAddress`): miễn phí nhưng 2,5 yêu cầu/giây, chỉ mục trễ 15–30 s nên điểm ra muộn hơn mốc khoảng 20–40 s, và có thể bị chặn nếu IP dùng chung bị giới hạn. Trần credit vẫn được đếm như Helius để không lạm dụng.

## Telegram (tuỳ chọn)

1. Nhắn [@BotFather](https://t.me/BotFather) `/newbot` → lấy token → đặt `RAY_TELEGRAM_BOT_TOKEN`.
2. Nhắn một tin bất kỳ cho bot, mở `https://api.telegram.org/bot<token>/getUpdates` để lấy `chat.id` → đặt `RAY_TELEGRAM_CHAT_ID`.
3. Gửi `/score <mint>` hoặc dán mint. Bot chỉ trả lời đúng chat đó, mọi chat khác bị bỏ qua. Tin nhắn tối đa 1 tin/2 s, 300 tin/ngày, không bao giờ có chữ "mua".

## Bảng điều khiển và API

`/` (cần mật khẩu): trạng thái, ô **Chấm ngay**, các curve đang sống (≥ 2 SOL), điểm gần đây có lọc theo nhãn (DƯỚI CỔNG ẩn mặc định), bấm vào một dòng để xem chi tiết: cờ nào bật với giá trị thô, bằng chứng trong kho sáng lập, chất lượng dữ liệu, link pump.fun và Solscan.

| Đường dẫn | Quyền | |
|---|---|---|
| `GET /api/health` | công khai | `app`, `build_sha`, `rpc` (public/helius/private), `filters_frozen`; 503 khi vòng đọc curve đứng quá 3 phút (dùng cho health probe của Bunny). |
| `GET /api/state` | mật khẩu | Trạng thái, curve sống, điểm gần đây. |
| `GET /api/token/<mint>` | mật khẩu | Mọi điểm của một mint. |
| `POST /api/score/<mint>` | mật khẩu | Chấm ngay. |
| `GET /api/registry` | mật khẩu | Định nghĩa và bằng chứng của từng bộ lọc. |
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
| `app/engine.py` | Vòng lặp, hàng chờ chấm, sổ điểm JSONL. |
| `app/api.py`, `app/static/index.html` | API và bảng điều khiển. |
| `app/telegram.py` | Bot Telegram riêng. |

## Pháp lý

Nghị định 284/2026/NĐ‑CP (hiệu lực 1/9/2026) phạt cá nhân giao dịch tài sản mã hoá không qua tổ chức được cấp phép. Rây chỉ đọc dữ liệu công khai on‑chain, không đặt lệnh, không có ví, và chỉ chủ sở hữu xem được điểm. Không chia sẻ hay bán điểm của Rây.
