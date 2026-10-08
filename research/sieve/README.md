# research/sieve — gói chấm rây, đóng băng

Code chấm hằng tuần của bot "rây" (docs/SIEVE.md mục 2–5, 7). Chỉ dùng thư viện chuẩn của Python 3.11,
không cần numpy/pandas, cũng không cần cài bot. Kết quả tất định: mọi phép ngẫu nhiên đều có seed cố định.
Chạy được từ repo, không cần thư mục scratch.

> "Không bắt bẫy chưa từng tồn tại." Crew đổi cách làm theo tuần, nên chuỗi lọc phải được bảo trì:
> tuần nào cũng đọc journal, filter nào bắt thiếu thì vá bằng một định nghĩa **mới**. Bảo trì là việc
> thường kỳ của nghề, không phải sửa lỗi.

## Các file

| File | Việc |
|---|---|
| `filters.py` | Sổ đăng ký (`REGISTRY`): mỗi id/version là một hàm `(fired, raw)`, kèm tier (active / shadow / info / watch / retired), dữ liệu cần có, bằng chứng lúc thành lập và lịch xét lại. Gồm luôn phần kiểm đủ lệnh (`check_chain` không cần thứ tự, `check_ordered`), bộ nhớ chéo-launch đọc theo đúng thứ tự thời gian, và `FROZEN` (hash của từng định nghĩa). `--list` liệt kê, `--check` báo định nghĩa nào đã bị sửa tại chỗ. |
| `journal.py` | Dựng journal từ file census. Gồm: cổng F0; D = 120/300/600 giây (tập J), thêm lưới 60..900 giây nếu có `--dense` (tập G, chỉ để mô tả); vé 0,5 SOL; nhãn bẫy/thắng; net ở 10/30/60 phút và giữ tới cuối, cho ba điểm vào (dslot+1, T+45, T+90 giây); SOL thật ở dslot, lúc vào, T+45, T+90; ngày, tuần ISO, khối sáng lập; kết quả kiểm đủ lệnh; cờ và raw của mọi filter. |
| `score.py` | Bảng điểm (chi tiết ở mục "Bảng điểm có gì" bên dưới). `--diff A B` liệt kê cờ bị lật giữa hai journal. |
| `archetype.py` | Gắn **kiểu thoát** cho từng dòng bẫy (mô tả phía kết quả, chỉ để lập hồ sơ, không bao giờ là filter), rồi in bảng luật đếm trên các mint bẫy lọt. |

Cờ trong journal là cờ **chưa qua cổng**. Mọi phủ quyết và mọi con số đều áp GATE_E (`real_e >= 11.66`):
dưới mức đó, vé 0,5 SOL không thể lỗ 50%. Hàm của filter chỉ đọc lệnh có slot <= dslot. Filter có bộ nhớ
chỉ đọc các launch được tạo trước ứng viên, và chỉ các sự kiện có block time <= t_dec. Router
`BwWK17cb…` bị loại khỏi mọi feature ví.

## Tải census

Không cần, và cũng không được dùng, bí mật nào. Census nằm trên volume của bot:

```bash
BASE=https://mc-5hwosgxjn6.bunny.run
mkdir -p /tmp/census-W1 && cd /tmp/census-W1      # mỗi tuần một thư mục mới, ngoài repo
curl -sf "$BASE/api/files" | python3 -I -c 'import json,sys; print("\n".join(f["name"] for f in json.load(sys.stdin)["files"] if f["name"].startswith("sniper-")))'
curl -sfO "$BASE/api/export/file/sniper-2026-10-12.jsonl"      # hoặc .jsonl.gz, đúng tên /api/files trả về
```

- Mỗi launch chỉ được ghi khoảng 2 giờ sau lệnh tạo. Vì vậy hãy tải file của mọi ngày trong tuần **và
  của ngày kế tiếp**. `journal.py` tự bỏ mọi dòng có `create_ts > --to-t0`, và bỏ ngay từ dòng thô,
  trước khi parse JSON.
- File tải về là dữ liệu: để ở thư mục riêng và chạy bằng `python3 -I`. Journal tái dựng được từ census
  cộng với code đã đóng băng, nên đừng commit dữ liệu.

## Lệnh hằng tuần

Ví dụ: tuần forward W1 của `docs/PREREG-SIEVE-R1.md`, gồm các launch tạo trong
(1791414202, 1792019002], tức (07/10 23:03Z, 14/10 23:03Z]. Mỗi tuần dài 604.800 giây và nối tiếp tuần trước.

```bash
A=1791414203; B=1792019002                              # W2: A=1792019003; B=1792623802
R=/home/user/pumphunt/research/sieve; J=~/sieve-journals; mkdir -p $J
python3 -I $R/filters.py --check                       # phải in "frozen check: OK"
# 1. journal: ứng viên trong tuần. Bộ nhớ (EXIT2-v2b/VET/XIN) đọc mọi file truyền vào và là kho TÍCH LUỸ:
#    theo PREREG-SIEVE-R1, luôn đưa mọi file census từ kho sáng lập tới tuần đang chấm (W2: pool + W1 + W2)
python3 -I $R/journal.py /tmp/census-pool/sniper-* /tmp/census-W1/sniper-* \
    --from-t0 $A --to-t0 $B --dense --out $J/W1.json.gz
# 2. bảng điểm, có canary so với các tuần trước (tuần đầu: so với kho sáng lập)
python3 -I $R/score.py $J/W1.json.gz --blocks day --ref $J/pool-e.json.gz $J/pool-h.json.gz \
    --json $J/W1.card.json --out $J/W1.card.txt
# 3. độ bền (cho mọi đề xuất và mọi filter active): nhìn trước, và mất 5% lệnh nhỏ
python3 -I $R/journal.py ...cùng tham số... --lookahead-test --out $J/W1.la.json.gz
python3 -I $R/journal.py ...cùng tham số... --drop-small 0.05 --out $J/W1.d05.json.gz
python3 -I $R/score.py --diff $J/W1.json.gz $J/W1.la.json.gz    # phải là 0 cờ lật
python3 -I $R/score.py --diff $J/W1.json.gz $J/W1.d05.json.gz
```

Bước 1 tốn khoảng 2 GB RAM và chưa tới một phút cho một tuần, cộng thêm kho sáng lập và các tuần trước làm bộ nhớ. Thứ tự
của journal (D, rồi t0) cố định thứ tự hoán vị, nên chạy lại sẽ ra đúng các con số cũ.

Sau khi chấm, gắn kiểu thoát cho bẫy lọt:

```bash
python3 -I $R/archetype.py $J/W1.json.gz /tmp/census-pool/sniper-* /tmp/census-W1/sniper-* --out $J/W1.arch.txt
#   mặc định --chain active; có thêm --chain active+shadow; kho sáng lập dùng thêm --blocks founding
```

`archetype.py` gán cho mỗi dòng bẫy một **kiểu thoát**, tức cách crew rút tiền. Luật đầu tiên khớp được chọn, theo thứ tự: SWARM-EXIT, INSIDER-XFER-EXIT, WHALE-DUMP, CLOSED-LOOP-DRAIN, LATE-COLLAPSE, CROWD-CASCADE. Định nghĩa đầy đủ nằm ở docstring.
- Đây là mô tả phía kết quả: nó đọc lệnh sau dslot, tới mốc 30 phút, nên chỉ dùng để lập hồ sơ.
- Tool in từng dòng bẫy (ACT/MISS trùng với danh sách bẫy lọt của `score.py`, kèm kiểu và số đo), rồi in bảng luật đếm theo kiểu.
- Kiểu `meets` (≥ 3 mint, ≥ 2 creator, ≥ 2 ngày hoặc khối) mới được đề xuất thành filter mới. Filter mới chỉ đọc lệnh có slot ≤ dslot và vào shadow.
- Kiểu `watch` ghi vào sổ theo dõi, kèm hồ sơ.
- Trên kho sáng lập, kết quả khớp bản scratch trên 82/82 dòng bẫy.

Tiếp theo:
- Lập hồ sơ cho từng dòng `MISSED` và `KILLED`, xếp mỗi dòng vào một kiểu đã biết hoặc đánh dấu "mới".
- **Luật đếm:** một kiểu bẫy chỉ thành ứng viên filter khi thấy ở ≥ 3 mint bẫy, của ≥ 2 creator, trong
  ≥ 2 ngày. Riêng khối sáng lập dùng 2 trong 3 khối thay cho 2 ngày. Cột `Tm Tc Tb R` của bảng điểm đếm
  sẵn các con số này. Kiểu nào chưa đạt thì ghi vào sổ theo dõi, kèm hồ sơ.
- Tuần đã chấm sẽ nhập vào kho tìm tòi. Từ đó mọi con số trên tuần ấy là **in-sample**, và tập ấy không
  bao giờ được gọi là holdout hay forward nữa.

## Bảng điểm có gì

- Tỷ lệ bẫy nền theo tầng (5–13, 13–30, 30–70 SOL thật ở dslot) và theo D, kèm KTC Wilson.
- Với mỗi filter, tính trên các dòng đã qua cổng:
  - số cờ; bẫy và thắng theo dòng và theo mint; số creator và số khối của các mint bẫy;
  - tỷ lệ bẫy có cờ / không cờ, kèm KTC Wilson, và theo từng tầng;
  - odds ratio Mantel–Haenszel trong tầng real_e × D;
  - U = T − 3W, p hoán vị theo mint (N 2000, seed 9), q BH trên mọi filter không retired, không reference;
  - placebo khớp số cờ tốt nhất, chọn trong các biến n_trades, uniq_buyers, d_real_60s, real_e,
    buyers120, n120, an_dd_pre. Dấu `*` nghĩa là filter thắng placebo. Không có `*` thì filter
    **không phân biệt được** với một proxy hoạt động hoặc mức curve;
  - SOL tiết kiệm riêng: với thành viên active là phần mất đi khi bỏ nó khỏi chuỗi; với filter khác là
    phần thêm vào khi cộng nó vào chuỗi active;
  - mô tả trên lưới dày G.
- Các chuỗi đặt cạnh nhau, trên J và trên G: không phủ quyết, cổng trần, v1 (đúng như bản dựng, không
  cổng), v1 có cổng, active (GATE_E và (SH-DEV-1 hoặc N-MMAAS-WAVE-STREAM)), active + shadow. Mỗi
  chuỗi có: số dòng bị chặn, bẫy và mint bẫy bắt được, thắng và mint thắng bị giết, SOL tiết kiệm
  (KTC theo mint), mean của tập lọt qua (KTC cụm theo mint).
- Danh sách bẫy lọt và coin thắng bị giết, để lập hồ sơ.
- Canary của từng filter:
  - tỷ lệ cờ theo tầng; nếu giảm hơn 50% so với trung bình của `--ref` trong khi tỷ lệ bẫy nền không
    giảm thì cảnh báo DROP (bị né hoặc mất dữ liệu: kiểm dữ liệu trước);
  - số bẫy lọt có raw nằm trong khoảng 70–100% ngưỡng;
  - ví hoặc mint chiếm nhiều cờ nhất (luật huỷ của v2b: một ví đứng sau quá 30% số cờ).
- Một filter cần đủ lệnh thì không được chấm ở dòng không qua `check_chain`. Nếu trong một ngày có hơn
  5% ứng viên hỏng chuỗi, cả ngày đó không được chấm cho các filter ấy.

## Quy tắc không được phá

1. **Định nghĩa có version và không bao giờ sửa tại chỗ.** Đổi ngưỡng, cửa sổ hay luật ví thì phải
   thêm một hàm và một id/version mới vào `REGISTRY`, chạy `filters.py --hashes` rồi chỉ thêm dòng của
   id mới vào `FROZEN`. Không bao giờ sửa hash cũ cho `--check` qua. `score.py` sẽ cảnh báo nếu một
   journal được dựng bằng định nghĩa khác.
2. Định nghĩa mới chỉ được vào **shadow**. Ngưỡng của nó chỉ được đặt theo lý do cơ học, hoặc theo phân
   phối của kho tìm tòi mà không nhìn kết quả. Nó chỉ được chấm trên các tuần chưa ai xem. Tối đa 2 đề
   xuất mỗi tuần.
3. Không bao giờ dựng journal cho dữ liệu sau tuần đã khoá. Không xem kết quả của một tuần forward
   trước khi tới lượt chấm nó.
4. Đơn vị bằng chứng là mint. Lưới G tự tương quan rất mạnh trong một mint, nên chỉ dùng để mô tả.
5. Filter cần đủ lệnh phải khai `complete=True` và qua được `--drop-small 0.05`: không lật quá 20% số
   cờ. Ngưỡng dựa trên danh tiếng ví phải tính trên mỗi 1.000 launch của vũ trụ danh tiếng, vì census
   chỉ là mẫu 5% còn luồng live lớn gấp 10–20 lần.
6. `N-LTE-FACTORY` cần sổ creator ngoài của loopholetape (`--lt-ledger`, dữ liệu bên thứ ba, đọc bằng
   `python -I`). Không có sổ đó thì filter này không được chấm.
7. Đạo đức: mục đích duy nhất là **không làm thanh khoản thoát cho crew**. Chỉ mô tả cơ chế của crew tới
   mức cần để phát hiện. Không bao giờ in chữ "MUA", không chia sẻ tín hiệu.

## Tái lập kho sáng lập (06/10 20:53Z – 07/10 23:03Z, t0 ≤ 1791414202)

```bash
R=/home/user/pumphunt/research/sieve
C=/path/to/census   # sniper-2026-10-06.jsonl.gz, sniper-2026-10-07.jsonl, sniper-2026-10-08.jsonl
python3 -I $R/journal.py $C/sniper-2026-10-0* --from-t0 0 --to-t0 1791386122 --dense --out e.json.gz
python3 -I $R/journal.py $C/sniper-2026-10-0* --from-t0 1791386123 --to-t0 1791414202 --dense --out h.json.gz
python3 -I $R/score.py e.json.gz h.json.gz --blocks founding     # thêm --perm-n 4000: p như người thiết kế
```

Kết quả phải ra:
- J có 206 dòng, 127 mint; 82 dòng bẫy (55 mint) và 16 dòng thắng (11 mint); 137 dòng qua cổng.
- Chuỗi active bắt 42/82 dòng bẫy (26 mint) và giết 1 coin thắng (ukjpAvka@120).
- SH-DEV-1: 30 dòng, 24T/1W, p 0,050, MH 3,45.
- N-MMAAS-WAVE-STREAM: 29 dòng, 26T/0W, p 0,002, MH 13,63.

Số của N-LTE-FACTORY chỉ ra khi thêm `--lt-ledger` vào cả hai lệnh journal.

Ngày 08/10/2026, mọi cờ của 22 filter đã có, cùng nhãn và feature, đều khớp từng dòng với `flags.json`
của scratch trên cả 4 tập (1.037 dòng). Số k/T/W/Tm/Wm/U/p/MH khớp đúng `registry_ev.json` của red team
(N 2000). Raw của 13 định nghĩa mới khớp với code của người thiết kế; số gộp và p (N 4000) khớp với
`score_out` của họ. Nhãn T+45/T+90 khớp với `labels.py` của red team.

Độ bền trên kho sáng lập:
- Cắt ở dslot (`--lookahead-test`) không lật cờ nào.
- Mất 5% lệnh nhỏ thì N-WM-EXIT2 v1 sinh đúng 248 cờ ma trên J_holdout + G_holdout, như red team đã đo.
  Cờ ma của nó đến từ bộ nhớ, nên kiểm chuỗi của ứng viên không chặn được.
- Cũng với mức mất đó, 85/95 dòng J của holdout hỏng `check_chain`, nên mọi filter `complete=True` không
  được chấm ở các dòng ấy. Live phải đọc bù lệnh thiếu (RPC trả phí), nếu không thì phải ghi THIẾU DỮ LIỆU.
