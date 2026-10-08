# Tổng kết nghiên cứu pumphunt (06–08/10/2026)

> Viết ngày 08/10/2026, ngay trước khi tắt server, để sau này đọc lại mà không cần server hay dữ liệu
> trên volume. Repo vẫn còn; server, Redis và volume `/data` có thể đã bị xoá.
>
> **Ảnh chụp cuối**: API của server lúc 08/10/2026 khoảng 06:45–06:50Z, build `71c15b3` (PR
> baocookin/pumphunt#27). Sáu file JSON của ảnh chụp được lưu trong repo ở
> [`docs/snapshot-2026-10-08/`](snapshot-2026-10-08/): `health.json`, `stats.json`, `files.json`,
> `survivor_summary.json`, `sniper_summary.json`, `graduation_summary.json`. `config.json` không lưu.
> Mọi số lấy từ đó đều ghi nguồn là `snap/<tên file>`, tức `docs/snapshot-2026-10-08/<tên file>`.
>
> **Lập trường**: dự án chỉ nghiên cứu. Không đặt lệnh thật, không phát tín hiệu cho ai, không bán dữ
> liệu. Tài liệu này không phải lời khuyên giao dịch. Lý do pháp lý: Nghị định 284/2026/NĐ-CP (xem mục 3.6).

**Ký hiệu dùng trong file**

| Nhãn | Nghĩa |
|---|---|
| **[ĐKT]** | Phán quyết theo luật đã đăng ký trước, trên mẫu kiểm định. Đây là bằng chứng. |
| **[ĐKT-tạm]** | Số tạm của một giả thuyết đã đăng ký trước nhưng chưa đủ n. Không phải bằng chứng. |
| **[TD]** | Thăm dò: chọn sau khi xem dữ liệu, trong mẫu, hoặc trên dữ liệu lịch sử. Chỉ gợi ý. |
| **[SL]** | Suy luận hoặc ước tính của người tổng hợp/agent, không phải số do nguồn tính sẵn. |
| **[NG]** | Tài liệu hoặc dữ liệu bên ngoài. `[S]` = chỉ thấy qua đoạn trích tìm kiếm; `[V]` = số của vendor, chưa kiểm chứng. |

Số viết theo kiểu Việt Nam: dấu phẩy là thập phân, dấu chấm phân cách hàng nghìn. "KTC" là khoảng tin
cậy 95%. "Net" là lãi/lỗ sau mọi chi phí đã mô hình hoá.

---

## 1. Kết luận chính

1. Trong khoảng 06/10–08/10/2026 (cộng backfill 48 giờ) và qua 27 PR, **không tìm ra luật mua nào có kỳ
   vọng (EV) dương cho người ngoài ở tốc độ con người** trên pump.fun và PumpSwap.
2. Sau migration: giả thuyết C bị **KILL** đúng quy trình đăng ký trước [ĐKT]: n 3.093, median −3,50%
   (KTC −4,00% … −3,19%), mean −27,14%, thắng 9,86%. C* (cùng luật, chỉ mẫu kiểm định) cũng KILL: n 754,
   median −6,50%.
3. Lọc "pool còn giao dịch được" (C2) lại làm kết quả tệ hơn: median −47,41% trên 226/300 vé
   (INSUFFICIENT), và về số học PASS đã không thể xảy ra [SL]. Mọi kiểu vào sau migration đã đo đều có
   mean âm, từ −9,5% đến −73% [TD].
4. Trên bonding curve, trong các điểm vào lúc token vừa ra đời (ngay sau dev / khoảng 1 giây / 10–60
   giây), chỉ vị trí ngay sau dev có EV dương (+12,0%), tức chỗ của creator và bundle; người ngoài vào sau
   khoảng 1 giây được −7,9% [TD]. (Pha cuối curve G/GS là trường hợp riêng, xem mục 5.) Forward: 79/79 ô
   thăm dò âm. S đang WAIT: n 645/2.000, mean −2,72% (KTC −7,26% … +1,82%) [ĐKT-tạm].
5. G/GS (mua khi curve chạm 60 SOL thật): sau khi sửa lỗi survivor bias, kỳ vọng lịch sử của nhóm curve
   chậm chỉ còn +6,0% (KTC +1,9 … +10,1), và về khoảng 0 nếu trượt thêm 3 SOL [TD]. Forward mới có vé
   thất bại (G 12/300, GS 7/300), nên chưa đo được giá thoát thật.
6. Bot "rây": loại bẫy thì làm được, còn tìm tập "đáng mua" thì không. Mọi phần còn lại sau lọc đều có
   mean âm hoặc KTC chứa 0. Thứ có giá trị là **quyền phủ quyết dùng riêng** (phanh FOMO). Chain active
   (cổng 11,66 SOL + SH-DEV-1 hoặc N-MMAAS-WAVE-STREAM) bắt 16/32 bẫy trên holdout và không giết coin thắng
   nào, nhưng holdout đã bị xem nên đây chỉ là thăm dò [TD].
7. Người thắng đều đặn là creator/bundle ở slot tạo và các bên thu phí (pump.fun, terminal, Jito,
   validator). Người mua sau cùng đóng vai thanh khoản cho họ thoát hàng.
8. **Còn mở khi tắt server**: phán quyết S, G, GS, C2; luật đặc trưng C3+ và S2 chưa đăng ký; lần chấm
   forward W1/W2 của sổ filter (dự kiến 15/10 và 22/10); sổ bóng luật mua B1 chưa bao giờ chạy; giả thuyết
   D (copy ví chậm) chưa bao giờ được kiểm. Tất cả dừng ở WAIT hoặc "chưa kiểm".
9. Muốn tiếp tục thì phải tải dữ liệu trên volume về trước khi xoá (khoảng 678 MB; ưu tiên `holders-*` và
   `sniper-*`), và census phải chạy liên tục cho các tuần forward (mục 6).

---

## 2. Bảng tóm tắt các giả thuyết đăng ký trước

| Giả thuyết | Đăng ký | Luật (rút gọn) | n (cần) | Số chính | Phán quyết | Nguồn |
|---|---|---|---|---|---|---|
| **C** | Từ đầu dự án (commit a7f7996, 06/10 00:04Z) | Mua mọi graduate quote SOL ở T+30 phút, giữ 1 giờ, 1 SOL; net theo khớp lệnh thật (fills v2) từ 06/10 | 3.093 (≥ 300) | median −3,50% (KTC −4,00 … −3,19), mean −27,14%, thắng 9,86%, top 2% chiếm 77,9% lãi, rug 20,3% | **KILL** [ĐKT] (vi phạm cả hai điều kiện KILL) | snap/survivor_summary.json → prereg C |
| C (thước đo nến cũ) | như trên | Đóng nến 5 phút, trừ 3,5% round-trip | 3.209 | median −4,09%, mean −13,33%, thắng 11,2%, top 2% chiếm 74,3% | KILL (chỉ để đối chiếu) | snap/survivor_summary.json → cells.d30_h60 |
| **C\*** | PR #16, 06/10 14:39Z | C, chỉ migration từ 06/10 16:00Z | 754 | median −6,50% (KTC −14,72 … −3,68), mean −32,60%, thắng 9,28%, rug 25,2% | **KILL** [ĐKT] | snap/survivor_summary.json → prereg C* |
| **C2** | PR #16, 06/10 14:39Z (trước mốc mẫu 16:00Z) | C + pool có ≥ 10 SOL thật và ≥ 1 swap trong 60 s trước T+30 | 226/300 (eligible 754) | median −47,41% (KTC −60,82 … −36,13), mean −33,28%, thắng 26,55%, rug 30,97%, top 2% chiếm 44,1% | **INSUFFICIENT** [ĐKT-tạm]; PASS đã bất khả [SL] | snap/survivor_summary.json → prereg C2 |
| C3+ (luật đặc trưng) | Quy trình ở PR #16 | ≤ 3 luật × ≤ 3 đặc trưng; khám phá tới 20/10 16:00Z | — | `RULES = []` | Chưa đăng ký luật nào | bot/app/prereg.py |
| **S** | PR #20, trước 07/10 03:00Z | Vé 0,5 SOL ở cuối slot tạo+2; thoát khi chạm 2×, 0,5× hoặc sau 60 s; mẫu băm 2%, classic quote SOL | 645/2.000 | mean −2,72% (KTC −7,26 … +1,82), median −2,87%, top 1% chiếm 39,4%; độ vững k1 −2,48%, k4 −2,69% | **WAIT** [ĐKT-tạm] | snap/sniper_summary.json → prereg |
| S2 (luật đặc trưng lúc vào) | Quy trình ở PR #20/#21 | Thăm dò tới 21/10 03:00Z, ≤ 3 luật × ≤ 3 đặc trưng | — | Chưa có ứng viên | Chưa đăng ký | docs/SNIPER.md mục 7 |
| **G** | PR #22, 06/10 23:37Z (mẫu từ 07/10 03:00Z) | Curve lần đầu ≥ 60 SOL thật → mua 0,5 SOL trễ 1 slot; bán vào PumpSwap 3 s sau migration; thất bại thì bán sau 2 giờ | 12/300 | mean −81,78% (KTC −95,77 … −67,79), thắng 0%; cả 12 vé đều là curve thất bại | **WAIT** [ĐKT-tạm] | snap/graduation_summary.json → prereg |
| **GS** | PR #23, 07/10 00:51Z | G + trigger ≥ 60 s sau lệnh tạo; chấm đúng một lần trên 300 vé đầu | 7/300 | mean −75,88% (KTC −99,55 … −52,21), thắng 0%; cả 7 vé đều thất bại | **WAIT** [ĐKT-tạm] | snap/graduation_summary.json → prereg_gs |
| Phép kiểm năm luật (cờ F1–F14, tổ hợp A–E) | Ngưỡng cố định trước khi tính, ghi trong `PREREG.txt` (lưu ở `docs/snapshot-2026-10-08/sieve-five-laws/`) | Phần còn lại sau lọc phải có KTC loại 0 và cả hai nửa thời gian dương | 0–548 tuỳ tổ hợp | Không tổ hợp nào đạt (ví dụ A ở phút 2: −4,7% [−5,4; −4,1]) | Âm hoặc chưa chứng minh [TD] | docs/SIEVE.md mục 2 |
| **Sieve R1 – ACTIVE** | PR #27, 08/10 06:38Z; forward từ 07/10 23:03:22Z | GATE_E (SOL thật lúc vào ≥ 11,66) ∧ (SH-DEV-1 ∨ N-MMAAS-WAVE-STREAM) | Forward chưa chấm | Holdout (đã bị xem): 16/32 bẫy bắt, 0/8 thắng bị giết, +4,80 SOL [TD] | Chưa kiểm | docs/SIEVE_FILTERS.md, docs/PREREG-SIEVE-R1.md |
| **Sieve R1 – 5 shadow** | PR #27 | SH-SG-1, N-MMAAS-SPLDIST, N-MMAAS-WAVE strict, N-WM-EXIT2-v2b, CLD-ORPHAN-v1 | Forward chưa chấm | Trong mẫu: v2b p 0,087; ORPHAN p 0,11 [TD] | Chưa kiểm | như trên |
| Luật mua B1 (sổ bóng v1) | Chỉ là đề xuất trong docs/SIEVE.md (PR #26); PREREG-V1 chưa viết | Phút 5, ≥ 5 SOL, top-10 < 20%, dev < 3%; vào T+45 s, thoát sau 30 phút | — | Nguồn gốc post-hoc: n 13, +29% (KTC −9 … +73) [TD] | Chưa bao giờ chạy | docs/SIEVE.md mục 5 |

---

## 3. Các hướng nghiên cứu

### 3.0 Vòng 1–2 và pivot (docs/RESEARCH.md mục 0)

Vòng 1 chọn chiến lược scalp momentum trên curve (Early-Momentum Scalp). **Vòng 2 [NG]** (6 agent: 4 nghiên cứu,
1 fact-check, 1 red team; xong lúc 05/10 23:29Z theo chat, ghi vào RESEARCH.md ở commit c684b81 ngày 06/10) bác
nó và đổi hướng dự án:

1. Backtest "$4.000/ngày" mà v1 dựa vào chỉ có 1 giờ dữ liệu, chọn tốt nhất trong lưới 270 cấu hình, độ trễ khớp
   0, đăng dưới tag vendor (tin cậy 1/5). Paper bot chạy thật: thắng 24%, PF 0,7. Python + PumpPortal mất 1,5–3 s
   từ event tới khớp; một bot đo chi phí all-in 9,5%. Người mua organic vào 2–25 slot sau trade đầu: +3,9% gộp →
   −2,7% net; 72/72 biến thể momentum âm; 45–51% tx chạm curve thất bại.
2. Graduation được chế tạo: dev mua > 5 SOL thì 8% tốt nghiệp, 0 SOL thì 0,34%; bộ lọc "dev ≤ 3 SOL" của v1 lọc
   ngược chiều.
3. Retail: khoảng 6% trader có lãi, median −$120; 93/100 ví PnL cao nhất là bot.
4. Phí 2024 toàn hệ: Raydium 56%, bot/terminal 24%, Jito 11%, pump.fun 8%.
5. "Bán verdict rug/bundle" không phải chỗ trống: Axiom Pulse, Padre, GMGN, BullX Neo, RugCheck, Bubblemaps,
   SolanaTracker đều đã hiện bundle/sniper/insider/dev; gRPC rẻ nhất tử tế $199/tháng (Shyft).
6. Marino et al.: đặc trưng thật duy nhất là tỷ lệ trader qua UI pump.fun và tốc độ gom vSOL, chưa có kiểm ngoài
   mẫu.
7. API pump.fun không backfill quá khoảng 24 giờ, nên dữ liệu sạch có slot dài hơn 24 giờ là thứ khan hiếm.

Kết quả: repo chuyển thành bộ ghi dữ liệu on-chain có slot cộng harness kiểm định C (xem mục 3.6 "Phản biện memo
ban đầu" cho xếp hạng các hướng).

### 3.1 Hạ tầng và dữ liệu

#### Kiến trúc

- Một image Docker duy nhất. Stage `node:22-alpine` build dashboard Next.js thành file tĩnh
  (`output: "export"`). Stage `python:3.13-slim` chạy `uvicorn app.api:app` ở cổng 8080. FastAPI phục vụ cả
  `/api/*` lẫn dashboard ở `/`, cùng origin nên không cần CORS. Build SHA được đóng dấu vào image
  (`ARG BUILD_SHA`) và hiện ở `/api/health`.
- Container thứ hai là `redis:7-alpine` trong cùng pod; app nói chuyện qua `localhost:6379`.
- Recorder chạy trong cùng process với API: lifespan của FastAPI tạo task `Recorder.run` khi
  `PH_RUN_RECORDER=true`.
- `Recorder.run` gom các vòng lặp có supervisor. Vòng nào lỗi thì log, đếm vào `task_errors` và khởi động
  lại sau 5 s. Watchdog chạy 30 s một lần, huỷ vòng nào im quá hạn rồi chạy lại, ghi `stalled`.

| Vòng | Việc | Chu kỳ / ngưỡng im |
|---|---|---|
| chain | `logsSubscribe` (scope migrations) | nối lại khi im > 600 s |
| status | heartbeat | 5 s; stall 120 s |
| poller | `getSignaturesForAddress(withdraw_authority)`, nguồn migration chính | 30 s; stall 600 s |
| portal | PumpPortal (kênh miễn phí) | nối lại khi im > 120 s |
| harvester | GeckoTerminal + fills + đặc trưng | 240 s; stall 1.800 s |
| snapshots | snapshot holder T+30/T+60 | stall 300 s |
| sniper | census + đọc curve | 60 s; stall 900 s |

#### Nguồn dữ liệu

- **Helius RPC**, gói Developer: $49/tháng, 10 triệu credit, 50 rps. Dùng `logsSubscribe`,
  `getSignaturesForAddress`, `getTransaction`, `getTransactionsForAddress` (phương thức riêng của Helius,
  10 credit/100 tx), và `getTokenLargestAccounts`/`getMultipleAccounts`/supply cho holder. Live: `rpc_rps=15`,
  phạt 2 s sau mỗi 429, concurrency 4. Bộ lọc `tokenTransfer` của Helius chỉ chạy ở commitment `finalized`
  và chỉ được dùng sau khi so cạnh nhau với trang không lọc.
- **PumpPortal**: chỉ kênh miễn phí `subscribeNewToken` và `subscribeMigration`, một kết nối duy nhất
  (PumpPortal ban client mở nhiều kết nối). Chỉ dùng để đo độ phủ và làm nguồn migration dự phòng, không
  dùng để đếm. Đo ngày 06/10: chỉ relay khoảng 35/67 migration mỗi giờ, khoảng 3% message ghép sai mint
  vào signature; relay khoảng 29k lệnh tạo/ngày và ghi sai địa chỉ bonding curve của launch mayhem.
- **GeckoTerminal**: API công khai, miễn phí. Lấy OHLCV của pool PumpSwap trong 24 giờ đầu. Từ IP của
  Bunny chỉ được khoảng 5–6 call/phút (IP dùng chung), kém xa mức 30/phút trong tài liệu, nên dùng nến 5
  phút. Bộ điều tốc tự thích ứng: giảm 30% sau mỗi 429, tăng 10% sau 20 call sạch, sàn 3/phút.
- **Ngoài server**: dataset công khai `loopholetape/pumpfun-launches` trên Hugging Face (parquet, ngày
  decoder đầy đủ từ 27/09/2026), dùng cho thăm dò lịch sử trong `research/*.py`. Đây không phải mẫu kiểm
  định.

#### Dataset trên volume `/data` lúc chụp cuối

Tổng cộng 17 file, 677.932.217 byte (khoảng 678 MB). Nguồn: snap/files.json.

| File | Byte | Ghi chú |
|---|---:|---|
| chain-2026-10-06.jsonl | 28.233 | event pump.fun decode từ websocket (rất nhỏ vì scope migrations) |
| chain-2026-10-07.jsonl | 36.327 | |
| chain-2026-10-08.jsonl | 11.871 | đang ghi |
| holders-2026-10-06.jsonl.gz | 706.952 | snapshot holder T+30/T+60, **không dựng lại được** |
| holders-2026-10-07.jsonl.gz | 1.552.741 | |
| holders-2026-10-08.jsonl | 725.315 | đang ghi |
| migrations.jsonl | 3.058.095 | một dòng mỗi lần thấy graduation (portal, rpc-confirmed, chain) |
| portal-2026-10-06.jsonl | 24.239.611 | mọi message PumpPortal |
| portal-2026-10-07.jsonl | 31.869.644 | |
| portal-2026-10-08.jsonl | 7.705.695 | đang ghi |
| sniper-2026-10-06.jsonl.gz | 144.473 | census: một dòng mỗi launch trong mẫu, có mọi trade của curve trong 2 giờ |
| sniper-2026-10-07.jsonl | 28.619.767 | **chưa nén** (mtime 22:33:10Z) |
| sniper-2026-10-08.jsonl | 10.905.445 | đang ghi (mtime 06:49:43Z) |
| survivor.jsonl | 117.850.142 | một dòng mỗi lần harvest (có thể nhiều dòng/mint; phân tích dùng dòng mới nhất) |
| swaps-2026-10-06.jsonl | 195.230.093 | **chưa nén** (mtime 21:12:12Z); mọi swap PumpSwap đã tải, đủ để chạy lại mô phỏng offline |
| swaps-2026-10-07.jsonl.gz | 77.918.911 | |
| swaps-2026-10-08.jsonl | 177.328.902 | đang ghi |

- Hai file lẽ ra được gzip khi sang ngày nhưng chưa được nén: `swaps-2026-10-06.jsonl` và
  `sniper-2026-10-07.jsonl` (`swaps-*`, `holders-*`, `sniper-*` ghi với `compress_rotated=True`; `chain-*` và
  `portal-*` theo thiết kế không bao giờ được nén, `bot/app/recorder.py` dòng 74–75). Theo code
  (`bot/app/jsonl.py`), file của ngày cũ chỉ được gzip khi cùng một process ghi qua mốc nửa đêm UTC. Một lần
  restart trước nửa đêm (chẳng hạn do deploy) khiến file đó không bao giờ được nén. Mtime ủng hộ giải thích
  này: `sniper-2026-10-07.jsonl` ghi lần cuối 22:33:10Z, ngay sau merge PR #25 (22:31Z);
  `swaps-2026-10-06.jsonl` ghi lần cuối 21:12:12Z, ngay sau merge PR #20 (21:10Z). Đây là suy luận từ mtime,
  chưa đối chiếu log [SL]. Theo comment trong code, file swap nén được khoảng 5 lần.
- File theo ngày được đặt tên theo ngày UTC lúc **ghi**, không theo ngày launch (`bot/app/jsonl.py`). Một dòng
  census được ghi 2 giờ 5 phút sau launch, hoặc muộn hơn nếu chạm trần credit, nên launch của ngày X nằm ở file
  X và X+1. Dòng bị trễ do chạm trần credit vẫn nằm trong hàng đợi và sang file ngày sau, không bị bỏ khỏi mẫu
  (`bot/app/sniper.py`, `harvest_once`). Khi gộp offline phải đọc mọi file rồi lọc theo `t0`.
- Số dòng theo các summary: survivor 3.377 mint (3.233 có nến, 3.093 có fills v2); sniper 2.953 launch
  (2.056 classic, 897 mayhem, 57 tốt nghiệp, 0 đứt chuỗi, 0 bị cắt); registry Redis 4.925 migration.

#### Ngân sách credit Helius

| Hạng mục | Trần/ngày | Đơn giá chính |
|---|---:|---|
| Research reads (fills, lịch sử curve, holder, nguồn tiền) `PH_FILLS_DAILY_CREDITS` | 235.000 | khoảng 218 credit cho mỗi migration quote SOL (pool C2 bận khoảng 450); cửa sổ replay tối đa 15.000 tx (≤ 1.500 credit, đủ cho khoảng 93% cửa sổ); snapshot holder 3; lịch sử curve 20–60; nguồn tiền 10/ví chưa cache, tối đa 8 ví, cache 30 ngày |
| Sniper census `PH_SNIPER_DAILY_CREDITS` | 65.000 | 1 credit/trang 1.000 chữ ký; lệnh tạo 1; curve 10/100 tx, trần 5.000 tx (500 credit); curve bận khoảng 140, curve yên khoảng 11 |
| Recorder (poller + confirm) | không có trần riêng | khoảng 5.000/ngày |

- Tổng trần 300.000/ngày, khoảng 9 triệu/tháng, nằm trong 10 triệu/tháng của gói Developer. Lần backfill
  48 giờ đầu tiên ước khoảng 3,2k credit (comment trong `bot/app/config.py`, chưa đo) [SL].
- Với 1.250–1.300 migration/ngày, trần 235k chỉ đủ cho khoảng 1.050 dòng/ngày, nên hàng chờ harvest tăng
  thêm khoảng 200 dòng mỗi ngày.
- Lịch sử trần fills/sniper mỗi ngày qua các PR: #10 250k → #11 200k → #13 270k → #17 300k (từ đây tổng
  300k) → #20 280k + 20k → #21 270k + 30k → #22 210k + 90k (census 2% → 5%) → #25 235k + 65k.
- **Credit thực tế**: ảnh chụp cuối chỉ có bộ đếm của ngày 08/10 tới khoảng 06:50Z (fills 209.808/235.000;
  sniper 19.532/65.000; transport RPC khoảng 5.230 kể từ restart 06:39Z; snap/stats.json). Tổng cả dự án không
  được ghi ở đâu. Cận trên khoảng 0,85 triệu credit: tối đa 300k trần + khoảng 5k recorder cho mỗi ngày 06/10
  và 07/10, cộng khoảng 235k đã dùng ngày 08/10; tức dưới 10% của 10 triệu/tháng [SL]. Trước khi huỷ gói, hãy
  chụp lại trang Usage của Helius và hoá đơn Bunny (Magic Containers tính compute riêng, file này chưa ghi
  [SL]), rồi điền số thật vào đây. Gói Developer nâng cấp 06/10/2026 11:04Z, nên nếu tính theo tháng thì kỳ
  gia hạn kế tiếp khoảng 06/11/2026 [SL, kiểm trên dashboard Helius].

#### API

- Đọc: `/api/health`, `/api/stats`, `/api/migrations?limit=N` (≤ 1.000), `/api/survivor/summary`,
  `/api/survivor/explore`, `/api/survivor/rows?limit=N` (≤ 5.000), `/api/sniper/summary` (cache 60 s),
  `/api/sniper/explore`, `/api/sniper/rows?limit=N` (≤ 5.000), `/api/graduation/summary` (cache 120 s),
  `/api/config` (đã loại key và URL RPC), `/api/files`.
- Xuất: `/api/export/file/<tên>` (tên phải khớp regex của file dữ liệu, ngoài ra trả 404),
  `/api/export/survivor.csv` (một hàng mỗi token), `/api/export/survivor.jsonl`,
  `/api/export/migrations.jsonl` (registry Redis, tới 1.000.000 dòng).
- `/api/debug/tx/<signature>` gọi RPC thật, mỗi lần tốn 1 credit. **API không có xác thực.**

#### Redis và JSONL: cái nào bền

- File JSONL trên `/data` là dữ liệu bền. Redis chỉ là view để truy vấn và là nơi giữ hàng đợi.
- Mọi summary (survivor, sniper, graduation, explore) và các export `survivor.*`, `migrations.jsonl`,
  `sniper/rows` đều tính từ Redis, không đọc file.
- **Không có đường code nào nạp lại JSONL vào Redis khi khởi động** (`read_jsonl` chỉ được dùng trong
  `analyze.py`). Mất Redis thì dashboard trống dù file vẫn còn.
- Chỉ có trong Redis: hàng đợi harvest, hàng đợi snapshot holder, hàng đợi sniper, cache nguồn tiền 30
  ngày, bộ đếm credit theo ngày, cursor của poller và census, các cờ `initial_backfill_done` và
  `fills_requeued_v2`, bộ đếm theo giờ.
- Về nguyên tắc có thể tính lại summary offline từ file bằng các hàm thuần (`survivor.summarize`,
  `prereg.evaluate`, `sniper.simulate_row` + `summarize`, `graduation.summarize`), nhưng việc này **chưa
  từng được chạy thử**.

#### Deploy

- Merge vào `main` sẽ chạy workflow "Build and Deploy to Magic Containers": build
  `ghcr.io/baocookin/pumphunt:<sha>` và `:latest`, rồi gọi `BunnyWay/actions/container-update-image` với
  biến repo `APP_ID`, secret `BUNNYNET_API_KEY`, container `pumphunt`. Có `workflow_dispatch` để deploy tay.
  Package GHCR phải để Public vì Bunny kéo image không dùng credential.
- App trên Bunny: container `pumphunt` (cổng 8080 qua endpoint CDN, volume `/data` 10 GB, env
  `PH_REDIS_URL=redis://localhost:6379`, `PH_DATA_DIR=/data`, `PH_CHAIN_SCOPE=migrations`,
  `PH_SOLANA_WS_URL` = websocket Helius **kèm key, không bao giờ để trong repo**) và container `redis`.
  Tài khoản trial chỉ được 1 volume/app. `bunny.json` chỉ là bản mô tả tham khảo.
- Nên bật health probe vào `/api/health`: endpoint trả 503 khi status cũ hơn 120 s, hoặc khi chưa có status
  sau 300 s chạy.
- Dashboard công khai: https://mc-5hwosgxjn6.bunny.run (link này chết khi tắt server).

#### Bộ đếm live lúc chụp cuối

Nguồn: snap/health.json và snap/stats.json.

- Build `71c15b36f8f26a702d489e73b1732b795c904294` (PR #27). Process khởi động lúc 06:39:34Z (deploy tự
  động sau merge), uptime 636,8 s. Health ok, `status_age_s` 1,7, `chain_scope=migrations`, `task_errors`
  rỗng.
- Đếm 24 giờ: 1.321 migration xác nhận on-chain, PumpPortal thấy 1.195 (90,5%). Census đếm 55.827 lệnh
  tạo, PumpPortal 48.205 (86,3%). Tổng registry 4.925 migration. Tỷ lệ phần trăm do người tổng hợp tính
  [SL].
- Theo giờ (23 giờ đủ, từ 07/10 07Z): migration on-chain tổng 1.290, thấp nhất 34/giờ (07/10 10Z), cao
  nhất 80/giờ (07/10 21Z), trung bình 56,1/giờ. Lệnh tạo theo census: 1.489–3.247/giờ, trung bình 2.368,7.
  Giờ 08/10 06Z (chưa trọn): 31 migration, 1.346 lệnh tạo.
- Harvester: `due` 248, `pending` 1.626, credit hôm nay 209.808/235.000, `fills_paused=false`, `gtfa=true`,
  `token_filter=true` (đã kiểm lại sau restart). Gecko: 46 call, 5 lần 429, `rpm_now` 3,7.
- Sniper: credit hôm nay 19.532/65.000, 188 launch trong hàng đợi, `census_gaps` 0, `errors` 0. Snapshot
  holder: đã chụp 8, trễ 0, lỗi 0, 45 đang chờ.
- RPC: transport 489 call, 0 lần 429, ước khoảng 5.230 credit kể từ restart; withdraw_authority tĩnh,
  instruction migrate là `migrate_v2`.

#### Kiểm thử, CI, chi phí

- `bot/tests` có 154 hàm test (anchor, curve, explore, features, fills, graduation, infra, prereg,
  recorder, rpc, sniper, store, survivor, swaps; có fixture tx thật). Body PR #25 ghi 165 test, có lẽ vì
  pytest đếm cả các ca tham số hoá. CI (`.github/workflows/ci.yml`) chạy `ruff check`,
  `ruff format --check` và `pytest -q` trên mọi push/PR, có Redis thật làm service.
- Chi phí vận hành: Helius Developer $49/tháng; volume Bunny $0,10/GB/tháng (cấp 10 GB, dùng khoảng 0,68
  GB); GeckoTerminal và kênh free của PumpPortal không mất tiền.

#### Các lỗi hạ tầng đã gặp (mỗi lỗi từng làm sai hoặc mất dữ liệu)

| PR | Lỗi | Ảnh hưởng | Sửa |
|---|---|---|---|
| #1 | `withdraw_authority` đoán sai trong config | `logsSubscribe` không nhận gì trên production | Xác nhận bằng `getTransaction`, học authority thật từ account của instruction |
| #3 | 46% tx nạp authority qua lookup table | websocket không thấy; sổ cũ chỉ phủ khoảng 22% | Poller `getSignaturesForAddress` 30 s/lần thành nguồn chính (đủ 143/143) |
| #4 | Backfill bắn 294 `getTransaction` cùng lúc | 205/294 bị 429 và không thử lại; 30 tx của bot thua đua bị đếm là migration | Điều tốc toàn cục, thử lại, tx thua đua tính là no-op |
| #5 | Mainnet đã có tx version 1 | RPC trả null cho khoảng 47/236 fetch | Gửi `maxSupportedTransactionVersion=255` |
| #6 | Ô 24 giờ được điền bằng nến cuối kéo dài | Pool 2 giờ tuổi báo lãi 24 giờ (bias) | Tham số `now`, ô chưa tới hạn để trống |
| #7–#8 | Gecko trả 429 cho 42/92 call từ IP Bunny (PR #7); đo thêm từ IP khác chỉ 11/40 call được nhận ở 25/phút (PR #8) | Thiếu nến | Gộp 30 pool/call, limiter thích ứng, nến 5 phút |
| #12 | PumpPortal rớt socket lúc 11:33Z ngày 06/10 | Poller và harvester chết im, API vẫn trả lời, dashboard trông bình thường | Supervisor cho mọi vòng, sau đó thêm watchdog (#16) |
| #14 | `tokenTransfer` bị từ chối ở `confirmed` | Bộ lọc bị tắt ngay lần đầu | Đọc có lọc ở `finalized` |
| #19 | `tokenTransfer` bỏ sót 1 swap trên 209.836 (lệnh qua aggregator, tx v1) | Gần như không đáng kể | Mỗi chỗ đứt phía token được đọc lại không lọc (khoảng 10 credit) |

### 3.2 Sau migration: giả thuyết C, C2 và đặc trưng

#### Động lực và định nghĩa

- Lý do chọn C [NG]: trong 15.548 graduate (tháng 5–9/2026), 43,8% còn ≥ $5k thanh khoản sau 30 phút và
  19,7% sau 24 giờ. Thanh khoản median rơi 57% từ phút 5 tới phút 30 rồi gần như đứng yên. Lúc đó chưa có
  backtest công khai nào cho điểm vào T+30. Red team chấm C 4/10 vì sợ "survivor" chỉ là bundler chưa xả.
  **Dữ liệu sau đó xác nhận nỗi sợ này.**
- Luật C, đăng ký từ đầu: mua ở T+30 phút sau migration, giữ 1 giờ, 1 SOL. Cần n ≥ 300. KILL nếu median
  net ≤ −1,25% **hoặc** 2% token tốt nhất chiếm ≥ 50% tổng lãi. PASS nếu median > +2% **và** tỷ lệ thắng ≥
  45%. Các trường hợp còn lại là INCONCLUSIVE.
- Ngày 06/10 (PR #10) đổi thước đo, giữ nguyên tiêu chí. Trước: đóng nến tại T+d và T+d+h, trừ 3,5%
  round-trip cố định. Sau: mô phỏng vị thế trên reserve thật của pool PumpSwap. Lý do: pool có virtual
  quote reserve. Ví dụ 17,6 SOL ảo cạnh 0,3 SOL thật thì lệnh 1 SOL trượt khoảng 5% mỗi chiều, nên giả định
  3,5% round-trip là quá lạc quan. Trên 70 token đầu có fills, khớp trên reserve thật cho median −14,4%
  (lệnh 1 SOL, thắng 2,9%); cùng lúc, thước đo nến trừ 3,5% trên 185 token cho −4,6% ("gần hoà") [TD, chat
  06/10 12:17Z và 12:26Z].

#### Cơ chế PumpSwap phải mô hình đúng (đo trên mainnet)

- Giá tính trên E = Q + V, trong đó Q là SOL thật trong vault và V là virtual quote reserve (khoảng 17,5 SOL
  ở pool mới). Nhưng lệnh bán không bao giờ nhận quá Q (lỗi 6063). Pool bị rút hết SOL thật vẫn báo giá mà
  không ai thoát được. Mọi lệnh bán mô phỏng bị chặn ở Q.
- Ba biến thể lệnh mua giải mã khác nhau (`buy`, `buy_exact_quote_in`, `buy_exact_quote_in_v2`). Công thức
  chung: SOL vào curve = `quote_amount_in_with_lp_fee − lp_fee`. Đọc sai thì mỗi lệnh exact-in làm SOL của
  pool lệch khoảng 1,2% giá trị lệnh, và sai số cộng dồn. Ở một pool lớn, 40/53 lệnh mua là exact-in.
- Có những khoản phí bị rút ra ngoài swap. Thiếu bước áp các khoản này thì replay lạc quan giả khoảng 1% ở
  pool 50 SOL. Bộ đếm `chain_breaks` (phía token, tức thiếu swap) được tách khỏi `quote_gaps` (phía SOL,
  tức phí bị rút).
- 95/100 tx thành công chạm một pool bận là bot MEV chỉ đọc giá, không swap. Vì vậy "tx cuối trước T" vô
  nghĩa: một pool khoảng 3 swap/s từng bị ghi "idle 242 s". Fills v2 quét lùi từ mỗi mốc tới khi gặp swap
  thật.
- Số tx trong cửa sổ T+25 → T+121 phút (40 pool): median 13, p75 389, p90 7.041, lớn nhất > 31.000. Chi phí
  dồn vào khoảng 10–15% pool sôi động, cũng là nhóm duy nhất có thể giao dịch.

#### Ba mô hình khớp lệnh

- **ghost** (bi quan): thị trường "quên" lệnh của mình; khi bán, SOL mình nạp không có trong pool.
- **persist** (lạc quan): tác động lệnh mua của mình cộng vào trạng thái lúc ra, không ai phản ứng.
- **replay** (ước lượng chính): chèn lệnh mua vào chuỗi swap thật, chạy lại từng swap sau đó với đúng lượng
  đầu vào thật trên pool giả định, áp cả các khoản rút phí, rồi bán ở mốc ra.
- Chung cho cả ba: phí pool thật hai chiều, 0,001 SOL/tx mỗi chiều, trễ 3 s từ quyết định tới khớp, cỡ lệnh
  0,5/1/2/5 SOL.

Ở ô chính d30_h60, 1 SOL (snap/survivor_summary.json → fill_models):

| Mô hình | n | Median | Thắng | p10 | p90 |
|---|---:|---:|---:|---:|---:|
| ghost | 3.093 | −61,25% | 9,05% | −99,64% | −0,90% |
| replay | 2.966 | −3,29% | 9,31% | −98,00% | −0,46% |
| persist | 3.042 | −3,07% | 10,59% | −82,54% | +0,68% |

Replay phủ 95,9% số dòng. Ghost cực bi quan ở pool mỏng vì lệnh bán bị chặn ở SOL thật, không tính 1 SOL
mình vừa nạp. **Chỉ hai ô d30_h60 và d60_h60 được replay.** Mọi ô khác dùng ghost nên median rất âm (ví dụ
d0_h60 −95,85%) chủ yếu do mô hình, không được đem so với ô chính.

#### Kết quả cuối [ĐKT]

- **C KILL** và **C\* KILL**, **C2 INSUFFICIENT**: xem số ở mục 2.
- Hai ô replay, 1 SOL: d30_h60 (ô đăng ký) median −3,50% (mean −27,14%); d60_h60 (không đăng ký trước)
  median −2,71% (mean −20,77%, thắng 9,0%, top 2% chiếm 81,4%) [TD].
- Theo cỡ lệnh ở d30_h60: 0,5 SOL −3,59% (mean −25,96%); 1 SOL −3,50% (−27,14%); 2 SOL −3,51% (−28,42%);
  5 SOL −4,01% (−30,51%). Lệnh càng lớn mean càng tệ (chi phí thanh khoản). Không ô nào trong 4 cỡ × 15 ô có
  median dương [TD].
- Lưới theo nến, đã trừ 3,5% (snap → cells) [TD]: cả 15 ô đều có median và mean âm, thắng 5,0–11,8%, top 2%
  chiếm 68,5–94,4% lãi. Giữ càng lâu càng tệ; vào càng sớm sau migration càng tệ.

| Vào sau migration | n | Giữ 1 giờ | Giữ 6 giờ | Giữ 24 giờ |
|---|---:|---:|---:|---:|
| 0 phút | 635 | −87,49% | −94,18% | −95,79% |
| 5 phút | 3.186 | −57,24% | −79,91% | −89,10% |
| 15 phút | 3.207 | −7,01% | −21,52% | −46,33% |
| 30 phút | 3.209 | −4,09% | −6,94% | −17,55% |
| 60 phút | 3.227 | −3,50% | −4,64% | −8,10% |

- Chia tầng ở ô chính, chọn sau khi xem dữ liệu nên chỉ gợi ý [TD]:

| Tầng | n | Median | Thắng | p90 |
|---|---:|---:|---:|---:|
| SOL thật lúc vào < 1 | 1.331 | −2,69% | 0,45% | −2,64% |
| 1–5 SOL | 612 | −2,82% | 2,45% | −2,66% |
| 5–20 SOL | 281 | −10,92% | 9,61% | −1,30% |
| ≥ 20 SOL | 869 | −45,96% | 29,57% | +32,22% |
| Im lúc vào < 1 phút | 1.243 | −25,75% | 22,37% | +14,49% |
| Im 1–10 phút | 874 | −2,92% | 2,17% | −2,66% |
| Im ≥ 10 phút | 976 | −2,67% | 0,82% | −2,64% |

  Pool chết dưới replay chỉ mất phí khứ hồi (khoảng 2,7%). Pool lớn và đông có đuôi phải dày hơn nhưng
  median tệ nhất, vì phần lớn là pool vừa được bơm rồi xả. Không tầng nào có median dương.
- Harvest: `alive_24h_rate` 73,9%. Định nghĩa này lỏng (có volume giờ 6–24 và có giá ở T+24h), khác với
  con số "19,7% còn ≥ $5k thanh khoản sau 24 giờ".

#### C2: vì sao lọc làm tệ hơn

- Định nghĩa (đăng ký 06/10 14:39Z, trước mốc mẫu 16:00Z): tại đúng T+30, trước độ trễ 3 s, pool có ≥ 10
  SOL thật trong vault **và** có ít nhất một swap trong 60 s trước đó. Ngưỡng chọn theo cơ chế (lệnh 1 SOL
  ≤ 1/10 SOL thật; pool còn giao dịch), không theo kết quả.
- Dự báo lúc đăng ký [TD]: C trên 98 dòng fills v2 có median −3,2%, thắng 7%, KTC [−10,9%; −2,7%]. Tầng ≥
  20 SOL thật có median −53,6% (n 24). Tài liệu đã viết trước: "C2 có thể cũng bị KILL; kết quả đó vẫn có
  giá trị nếu được kiểm định đúng quy trình."
- Kết quả cuối đi đúng chiều đó: median −47,41%. Pool lớn hoặc đông lúc vào là pool vừa bị bơm rồi xả.
- Suy luận [SL, không phải phán quyết]: 60/226 dòng có lãi, nên 166 dòng ≤ 0. Kể cả khi 74 dòng còn thiếu
  đều có lãi, dòng thứ 150 và 151 (xếp tăng dần) vẫn ≤ 0, nên median ≤ 0. Vì vậy PASS là bất khả ở n 300;
  kết cục chỉ có thể là KILL hoặc INCONCLUSIVE, và với KTC hiện tại thì gần như chắc là KILL.
- Về nguyên tắc C2 có thể hoàn tất offline sau này, vì tư cách thành viên và fills chỉ cần lịch sử swap
  (đọc lại được từ chain qua RPC archival, tốn credit). Snapshot holder thì không đọc lại được. Chưa thử
  [SL].

#### Thăm dò luật đặc trưng trước cửa sổ (307 pool kiểu C2, migration 4–5/10) [TD]

Ô T+30, giữ 1 giờ, 1 SOL, khớp lệnh thật (docs/RESEARCH.md; PR #21):

| Nhóm | n | Median | Mean | Thắng | Mất ≥ 90% |
|---|---:|---:|---:|---:|---:|
| Toàn bộ C2 | 307 | −41,7% | −32,4% | 29% | 26% |
| Token tự tốt nghiệp (dev mua ≥ 80 SOL ngay trong lệnh tạo) | 123 | −1,4% | −45% | 34% | 47% |
| Token do người khác lấp curve | 184 | −42,5% | −24% | 26% | 12% |
| Giá T+30 bằng 0,7–1,15× giá migration + mua ròng ≥ 1 SOL trong 5 phút | 52 | +2,8% (KTC +1,6 … +5,4) | −5,6% | 75% | 13% |

- Token tự tốt nghiệp: sau migration dev giữ khoảng 79% cung, nên có thể rút cạn pool bất cứ lúc nào.
  Median của nhóm này là −0,6% ở nửa đầu mẫu và −98,7% ở nửa sau. Trong nhóm "giá giữ + mua ròng", mọi ca
  về 0 đều là token tự tốt nghiệp; bỏ chúng đi thì chỉ còn 11 token.
- Quan sát production ngày 06/10 [TD]: trong 42 token đầu có lịch sử curve, 16 (38%) tốt nghiệp trong 5 s
  sau khi tạo, 13 trong số đó do dev mua ≥ 80 SOL ngay trong lệnh tạo (curve chỉ có 2 giao dịch). Lúc T+30,
  pool nhóm này còn median 0,5 SOL thật. Nhiều khả năng đây là cày ưu đãi graduation sau BOOST, giải thích
  khoảng 1.200 graduation/ngày và nhóm pool < 1 SOL.
- Không nhóm nào có mean dương ổn định.

#### Bài học "median che đuôi rug" và cam kết quy trình (PR #21)

1. Tiêu chí của C, C2 và luật đặc trưng vẫn dựa trên median, nhưng mọi bảng báo thêm mean và `rug_share`
   (tỷ lệ mất ≥ 90%).
2. Một luật chỉ được đăng ký nếu trên cửa sổ thăm dò mean của nó dương ở **cả hai nửa thời gian**.
3. Nếu một luật PASS theo median nhưng mean trên mẫu kiểm định ≤ 0, kết quả phải ghi là "PASS theo trung
   vị, EV không dương", không được gọi là chiến lược có lãi.

#### Luật đặc trưng C3+ (đăng ký quy trình, không có luật nào)

- Chỉ được dùng thông tin công khai trước T+30: trạng thái pool, order flow 5 phút, snapshot holder T+30,
  lịch sử bonding curve, nguồn tiền của ví. Danh sách đặc trưng nằm ở `C_FEATURES` trong `bot/app/explore.py`.
- Khám phá trên quần thể C2, migration trong [06/10 16:00Z, 20/10 16:00Z). Tối đa 3 luật, mỗi luật ≤ 3
  đặc trưng. Đăng ký bằng một commit thêm vào `RULES` với `since` là giờ tròn kế tiếp. Kiểm một lần khi n ≥
  300, tiêu chí như C, cộng điều kiện PASS: cận dưới KTC median > 0.
- Kế hoạch: chọn luật khi có ≥ 600 dòng C2 kèm snapshot holder (dự kiến khoảng 10/10), chọn trên 2/3 đầu và
  kiểm trên 1/3 sau. Hai hướng định thử: loại token tự tốt nghiệp; tỷ trọng ví dev và ví bundle trong snapshot
  holder T+30.
- Trạng thái cuối: `RULES = []`. Mốc 600 dòng chưa bao giờ đạt (mới 226 dòng C2). Bảng thăm dò cửa sổ
  (`/api/survivor/explore`) không có trong ảnh chụp cuối.

#### Mọi kiểu vào khác sau migration [TD]

- T+5 đến T+60 phút, giữ 1, 6 hoặc 24 giờ: mean từ −9,5% đến −73% (1.066 token ngày 4–5/10). Pool còn ≥ 40
  SOL thật và vừa có giao dịch ở T+60, giữ 24 giờ: −44%. Không thấy "sóng thứ hai".
- Ăn theo lệnh mua lại của BOOST (mua 3 s sau migration, bán ở T+5 phút): mean −5,7% (KTC −10,0 … −1,4),
  725 token, median −0,6%, thắng 49%. Tách theo loại (chỉ có trong chat): token tự tốt nghiệp n 370 có median
  +8,8% và thắng 61% nhưng mean −4,3%; token organic n 355 có median −18,9%. Cơ chế: người nắm token từ curve
  xả vào lệnh mua của BOOST.
- Từ nghiên cứu rây: pool kiểu C2 sau 24 giờ có mean −67,8%, 82% là bẫy. Cờ nguồn tiền (ví mới, cụm cùng
  nguồn, liên kết dev) gần như vô dụng ở mốc 1 giờ; phần còn lại sau lọc cờ funding (n 238) có mean −33,2%
  (KTC −41 … −24).

#### Fills v1 (đã bị thay) [TD]

186 token đã harvest, 112 có khớp lệnh (1 SOL, T+30, giữ 1 giờ). 20% migration được nạp < 1 SOL thật và
lỗ khoảng 99%. Pool còn giao dịch có median −7,8%; 5/36 tăng vượt phí khứ hồi 2,7%. Mô hình bi quan cho
median −12,4%, lạc quan −2,8%; cả hai đều KILL. Toàn bộ đã được tính lại bằng fills v2.

#### Đặc trưng tại thời điểm quyết định (PR #15, #16)

- Snapshot holder chụp trực tiếp ở T+30 và T+60 (20 tài khoản lớn nhất + chủ + tổng cung, 3 credit). Bỏ
  nếu trễ > 300 s, bỏ pool migration < 1 SOL. **Không dựng lại được về sau.**
- Lịch sử bonding curve lúc harvest (100 tx đầu + đếm tx, khoảng 20–60 credit): thời gian tới tốt nghiệp,
  dev mua, ví mua cùng slot tạo, người mua 60 s đầu, dev bán sớm.
- Nguồn tiền: giao dịch đầu tiên của dev, ví bundle, top holder (10 credit/ví, cache 30 ngày, chỉ pool có
  ≥ 5 SOL thật).
- Event pump.fun xuất hiện hai lần trong mỗi tx (log và self-CPI); không khử trùng lặp thì số bị nhân đôi.
  Đặc trưng được đo đúng tại T+30, không phải lúc khớp 3 s sau (sửa look-ahead ở PR #16).
- Ví dụ định tính [TD]: một token cả vòng đời curve chỉ có 9 giao dịch, 4 ví mua khoảng 79 SOL ngay trong
  slot tạo, 4/5 ví được nạp từ cùng một ví, pool rơi 98,6% trong giờ đầu. Token "tự nhiên" mất 8–160 phút để
  tốt nghiệp, ví dev và người mua sớm đã tồn tại 6–430 ngày.

#### Giả thuyết D

D (copy ví "chậm" đã lọc bot; nguồn [NG] Luo et al. WWW'26, +14%/lệnh trong mẫu; red team chấm 3/10) là
một trong hai hướng "chưa bị falsify" ở vòng 2 nhưng **chưa bao giờ được kiểm định** trong dự án. Cùng bài
đó: người copy chỉ còn khoảng +3% mỗi coin sau ma sát; đây là backtest lịch sử, chưa thử với đối thủ biết
thích nghi; ví bị copy nhìn thấy copier để bán vào họ [NG] (docs/SNIPER.md mục 2, docs/RESEARCH.md mục 0).

### 3.3 Bonding curve: S, G, GS

#### Cơ chế (docs/SNIPER.md mục 1)

- Curve là AMM hằng số tích trên reserve ảo 30 SOL / 1,073 tỷ token; 793,1 triệu token bán trên curve.
  Hoàn tất ở khoảng 85,005 SOL thật; giá lúc đó khoảng 14,7× giá đầu, vốn hoá khoảng 410 SOL.
- Sau X SOL vào, giá = ((30 + X)/30)² × giá đầu (1 SOL +6,8%, 5 SOL +36%, 10 SOL +78%).
- Phí 1,25% mỗi chiều (0,95% protocol + 0,30% creator). Không thấy cơ chế chống sniper. Slot khoảng 0,25 s
  từ khoảng 18/9/2026, đo được trung bình 0,272 s.
- 22% lệnh tạo nằm trong Jito bundle của dev (112 launch). Mayhem (từ 11/2025) chiếm 26–28% launch và chỉ
  tốt nghiệp 0,02%.
- BOOST (từ 21/7/2026): lúc migration khoảng 17,58 SOL vào vault, pool nhận reserve ảo tương đương nên giá
  không đổi; authority của pump.fun dùng số đó mua dần token trong khoảng 5 phút rồi đốt. Tỷ lệ tốt nghiệp
  tăng từ 0,26% (giữa 6/2026) lên 2,5–4,7% [NG]. Pool tháng 9 (5.473 pool đầy): tới phút 30 đã có 58,5% pool
  mất ≥ 90% [NG].

#### Bằng chứng đã công bố [NG]

Pine Analytics: ví do creator nạp tiền mua trong block tạo có lãi ở 87% trường hợp, khoảng 1 SOL mỗi
launch. MELT: ví phối hợp nắm trung bình 36,5% cung. Mongardini & Mei: 82,89% token lời > 100% có tăng
trưởng nhân tạo. CCS'26: wash trade ≥ 17% giao dịch. Kamat: AUROC 0,859 trong mẫu → 0,464 trên 14 ngày sau.
jmenzler (tự báo cáo) đưa 7 SOL lên khoảng 1.000 SOL trong 2–4/2024, nhưng lợi thế đó chết từ cuối 4/2024. Bot
giấy của Kamat (190 lệnh) lãi +0,039 SOL, bỏ 3 lệnh tốt nhất là lỗ. Dune (1/2025): 0,41% trong 13,55 triệu ví
lãi trên $10k; ngày 9/6/2025, 93/100 ví lãi nhất là bot. Con số "73% ví có lãi" của CoinGecko là lãi đã chốt,
không lọc bot (docs/SNIPER.md mục 2).
**Không tìm thấy nghiên cứu nào cho thấy sniper bên ngoài có lãi ngoài mẫu sau chi phí.**

#### Lịch sử S (loopholetape, 77.043 launch classic 27–29/9) [TD]

Vé 0,5 SOL, phí 1,25%/chiều + 0,002 SOL. Các số âm là cận trên cho người ngoài, vì giả định bán đúng mức
chốt:

| Vị trí vào | Chốt 1,5× | 2× | 3× | 5× | 10× | Giữ tới tốt nghiệp |
|---|---:|---:|---:|---:|---:|---:|
| Ngay sau dev | +5,6% | +6,1% | +5,5% | +5,5% | +8,8% | **+12,0%** (KTC +10,9 … +13,2) |
| Khoảng 1 giây | −6,8% | **−7,9%** (KTC −8,1 … −7,7) | −9,0% | −9,5% | −8,9% | −8,5% |
| 10–60 giây | −2,7% | −5,5% | −7,8% | −8,4% | −8,1% | −8,0% |

- Kết quả ổn định qua 3 ngày. Median luôn âm.
- 13 bộ lọc đơn giản (vào khoảng 1 s, chốt 2×; chọn trên 27–28/9, kiểm trên 29/9) đều âm ở cả hai phần dữ
  liệu. Nhóm "trông có triển vọng" lại âm nhất: dev mua 3–10 SOL −22,6%/−24,8%; dev ≥ 10 SOL −28,8%/−14,0%;
  creator từng có token tốt nghiệp −18,5%/−19,0%. Nhóm dev không mua là ít âm nhất: −2,7%/−3,1%.
- Đuôi phân phối: vé khoảng 1 s chạm ≥ 10× ở 0,3%. Chạm 100× khoảng 0,17% (khoảng 1/600) và chỉ ở vị trí tốt
  nhất; đó là đỉnh nến, không phải giá bán được. Theo toán vé số trong chat, cần khoảng 1/113 vé trúng 100×
  mới hoà vốn [SL].

#### Thị trường slot 0 (on-chain 06/10, 112 launch) [TD]

Người ngoài mua được trong slot 0 ở 32% launch và trả median 1,35× giá đầu. Tx chạm mint mới thất bại 38%
ở slot 0, 58% ở +1, 68% ở +2, 77% ở +3. 79% người mua sớm bán trong khoảng 55 s ở median 0,96×. 54% launch
không có người mua ngoài nào ở slot 0–3. Chi phí thêm: bot/terminal 0,7–1%/chiều [V]; với vé 0,1 SOL thì
riêng tip + phí ưu tiên đã chiếm 3–7% mỗi chiều. Dự án không đo được độ trễ thật của mình.

#### Census forward

Census mọi lệnh tạo qua danh sách chữ ký của mint authority pump.fun, 60 s một lần. Giữ mẫu theo sha256(chữ
ký tạo) mod 10.000: < 200 (2%, mẫu S), mở rộng lên < 500 (5%) từ khi đăng ký G. Hai giờ + 5 phút sau launch
thì đọc mọi tx thành công của curve trong 2 giờ (trần 5.000 tx). Mô phỏng vé ở cuối slot tạo+k, k ∈ {0, 1,
2, 4, 8, 20, 40}, với 11 luật thoát, `SIM_VERSION = 1`. Từ PR #25, ngừng đọc sau một trang ngắn: trên 2.017
lượt đọc, trang ngắn luôn là trang cuối; 2% lượt đọc vẫn được kiểm tra tiếp.

#### Giả thuyết S [ĐKT-tạm]

- Luật (đăng ký trước 07/10 03:00Z): mẫu gồm lệnh tạo từ mốc đó, mẫu băm 2%, quote SOL, không mayhem, curve
  chưa hoàn tất ở slot vào. Vé 0,5 SOL ở cuối slot tạo+2. Thoát khi giá trị ≥ 2×, ≤ 0,5× hoặc sau 60 s; lệnh
  bán khớp cuối slot kế tiếp. Chi phí 1,25%/chiều + 0,002 SOL/vòng; tx lỗi không tính (có lợi cho S).
- Tiêu chí khi n ≥ 2.000: KILL nếu cận trên KTC < 0 hoặc 1% vé tốt nhất chiếm ≥ 50% lãi. PASS nếu cận dưới
  > 0 **và** EV > 0 ở slot +1 và +4.
- Số tạm 08/10 (k2_p): n 645, mean −2,72% (KTC −7,26 … +1,82), median −2,87% (đúng bằng mức phí), thắng
  11,8%, p_2x 2,33%, top 1% chiếm 39,4%, unresolved 0. Độ vững: k1 −2,48%, k4 −2,69%. **WAIT.**
- Diễn biến trong chat (số tạm): 17:45Z ngày 07/10 n 285, mean −2,8%; 22:10Z n 428, mean −4,5% (KTC −7,2 …
  −1,7). Mean dao động trong khoảng −2,7% đến −4,5% khi n tăng (n 285: −2,8%; n 428: −4,5%; n 645: −2,72%).

#### Lưới thăm dò forward (mẫu 5%, gồm cả dòng trước mốc) [TD]

- Classic (2.056 launch): **79/79 ô có mean âm**, 64 ô có cận trên KTC < 0, không ô nào có cận dưới > 0. Ô
  tốt nhất k0_p −1,69%, tệ nhất k40_hold −6,12%. k2_p trên n 2.024: −2,55% (KTC −5,32 … +0,22), median
  −2,87%, top 1% chiếm 51,8%. Theo cỡ vé: 0,1 SOL −4,25%, 1 SOL −2,21%.

| Luật thoát | k=0 | 1 | 2 | 4 | 8 | 20 | 40 |
|---|---:|---:|---:|---:|---:|---:|---:|
| p (2×/0,5×/60 s) | −1,69 | −2,61 | −2,55 | −2,24 | −1,85 | −1,81 | −2,50 |
| hold | −4,90 | −5,76 | −5,83 | −5,34 | −5,05 | −5,28 | −6,12 |
| tp2 | −3,73 | −4,50 | −4,45 | −4,15 | −4,07 | −4,36 | −4,62 |

- Mayhem (897 launch, ngoài mẫu S): 13/79 ô có mean ≥ 0 nhưng không ô nào có cận dưới KTC > 0. Median rất
  âm (k2_p −51,2%).
- Vé xổ số: 2.003 vé, chạm 10× ở 0,30% (6 vé), chạm 100× 0 vé; 21 vé tốt nghiệp còn chờ pool. Vé giữ từ
  slot +2 (đỉnh trên curve, n 2.024): chạm 2× 5,29%, 5× 1,73%, 10× 0,49%.

#### S2

Luật đặc trưng lúc vào (giá vào/giá đầu, SOL thật, dev mua, ví và SOL ở slot 0, số người mua trước, dev đã
bán chưa, cờ lệnh tạo). Thăm dò tới 21/10 03:00Z, chọn khi có ≥ 1.500 vé classic (dự kiến khoảng 9/10), luật
phải có mean dương ở cả hai nửa. **Chưa có ứng viên nào**, vì trong lịch sử không nhóm nào dương. Bảng
`/api/sniper/explore` không có trong ảnh chụp cuối.

#### Giả thuyết G và GS

- **Luật G** (đăng ký 06/10 23:37Z, mẫu từ 07/10 03:00Z): classic quote SOL, mẫu băm 5%. Khi giao dịch đầu
  tiên đưa curve lên ≥ 60 SOL thật thì mua 0,5 SOL ở cuối slot kế tiếp. Nếu curve hoàn tất trước đó thì ghi
  "jump", không có vé. Thoát: nếu tốt nghiệp thì bán toàn bộ vào PumpSwap theo trạng thái 3 s sau migration;
  nếu không tốt nghiệp trong 2 giờ thì bán ở trạng thái cuối của curve. Tiêu chí khi n ≥ 300: KILL nếu cận
  trên KTC < 0 hoặc top 1% chiếm ≥ 50% lãi; PASS nếu cận dưới > 0 **và** mean > 0 ở cả 50 và 70 SOL. Vé
  tốt nghiệp chưa có dòng survivor thì chờ, không tính là thua.
- **Luật GS** (đăng ký 07/10 00:51Z): như G, thêm một điều kiện: giao dịch kích hoạt xảy ra ≥ 60 s sau lệnh
  tạo. Chấm đúng một lần trên 300 vé đầu theo thời điểm tạo, và chỉ khi không còn vé nào chờ exit. Kỳ vọng
  KTC khoảng ±7% với 300 vé, nên nhiều khả năng ra INCONCLUSIVE. Thu khoảng 20 vé/ngày.
- Thăm dò trước đăng ký [TD]: P(tốt nghiệp | chạm X) là 59%/73%/84% ở 50/60/70 SOL. Giá 3 s sau migration
  so với giá tốt nghiệp: median 1,006×, mean 1,04×, 11% dưới 0,8×. Giá tốt nghiệp / giá ở 60 SOL = (115/90)² =
  1,63×. EV vào đúng 60 SOL khoảng +23,4% đến +23,8% (bảng SNIPER.md mục 8 từ PR #22 ghi +23,8%, chú thích ¹
  của PR #24 ghi +23,4%; xem Phụ lục A).
- **Sửa survivor bias (PR #24)** [TD]: dòng "trễ 3 SOL" cũ chỉ giữ curve có đỉnh ≥ X+3, tức bỏ những curve
  chạm X rồi không lên nữa, mà các curve đó đều thất bại.

| Phép đo | Trước khi sửa | Sau khi sửa |
|---|---:|---:|
| G trễ 3 SOL, 60 SOL | +20,6% | +15,5% |
| G trễ 3 SOL, 50 SOL | +29,9% | +19,7% |
| G trễ 3 SOL, 70 SOL | +10,9% | +7,1% |
| G trễ 3 SOL, 80 SOL | +1,9% | −0,6% |
| GS (chạm 60 SOL sau giây 60, trễ 1 SOL) | +8,6% (n 1.189) | **+6,0%** (KTC +1,9 … +10,1; n 1.221) |
| G vào đúng 60 SOL | +23,8% (bảng PR #22) | +23,4% (PR #24: không bị ảnh hưởng bởi lỗi này) |

- Nhóm tốc độ (1.815 curve chạm 60 SOL, lịch sử) [TD]: 529 curve hoàn tất trong 60 s đầu (343 curve trong 2
  s, là bundle, người ngoài không vào được) cho +61,8%/vé. 65 curve đã ≥ 60 SOL ở giây 60 nhưng chưa hoàn tất
  cho −38,5% (KTC −56,1 … −20,9). 1.221 curve chạm 60 SOL sau giây 60 cho +6,0%, hai nửa +3,8%/+8,3%. Nếu cả
  nhóm đầu là jump thì kỳ vọng của G chỉ khoảng +4% đến +6%.
- Độ nhạy của nhóm chậm [TD]: vào đúng 60 SOL +8,4%; trễ 1 SOL +6,0%; trễ 3 SOL +1,5% (KTC −2,4 … +5,4);
  trễ 3 SOL kèm giá thoát 1,02× thì −0,4%. Đặc trưng lúc kích hoạt chỉ xê dịch mean trong biên nhiễu.
- Số tạm forward [ĐKT-tạm]: G n 12, mean −81,78%; GS n 7, mean −75,88%. Agent kiểm trên bản sao census cục
  bộ (tới khoảng 01:11Z ngày 08/10): **toàn bộ là curve thất bại**. 17 vé G tốt nghiệp (GS: 10) còn chờ dòng
  survivor để có giá thoát. Như vậy số tạm chỉ đo "curve thất bại rơi về đâu", chưa đo G.
- Số tạm chi tiết (snap/graduation_summary.json) [ĐKT-tạm]: G n 12, median −88,92%, rug_share 33,33%, mean độ
  vững ở 50 SOL −79,86% và ở 70 SOL −91,56%. GS n 7, median −88,92%, rug_share 28,57%, độ vững 50 SOL −74,47%,
  70 SOL −91,48%.
- Bảng forward theo mức (mọi dòng classic, gồm cả trước mốc; snap/graduation_summary.json → levels) [TD]:
  - 60 SOL: 71 curve chạm, 23 tốt nghiệp, 15 thất bại, 33 jump (46%; 33/46 trong nhóm fast, 0 trong nhóm
    slow), 19 chờ exit; P(tốt nghiệp | có vé) 60,5%. Mean t3s n 19 là −54,7%, cũng lệch về phía thất bại.
    Thoát t5m (bán 5 phút sau migration) n 19 mean −61,86%.
  - 50 SOL: 83 chạm, 24 tốt nghiệp, 27 thất bại, 32 jump, 20 chờ exit, P(tốt nghiệp | có vé) 47,06%; t3s n 31
    mean −57,55% (KTC −78,91 … −36,19).
  - 70 SOL: 63 chạm, 23 tốt nghiệp, 7 thất bại, 33 jump, 19 chờ exit, P 76,67%; t3s n 11 mean −47,73% (KTC
    −80,62 … −14,84).
- Trượt giá thật lúc vào, nhóm slow ở 60 SOL [TD, agent tự đo trên bản sao census cục bộ, mọi dòng classic gồm
  cả trước mốc, launch tới 07/10 23:05Z; chưa ghi vào SNIPER.md]: n 23, median 1,05 SOL, mean 3,01 SOL vượt
  mức (riêng mẫu kiểm định: n 17, mean 3,55). Theo bảng độ nhạy, trượt khoảng 3 SOL tương ứng kỳ vọng khoảng
  +1,5% hoặc thấp hơn cho GS.
- Điểm hoà vốn [SL]: vé tốt nghiệp vào ở 61 SOL lời khoảng +55,6% (thoát 1,0×); vé thất bại forward mất
  trung bình 81,8%; hoà vốn cần P(tốt nghiệp | vé) khoảng 60%, trong khi forward đo được 60,5% (23/38). Nghĩa
  là G nằm sát hoà vốn ngay cả trước khi biết giá thoát thật.
- Caveat thiết kế của G [SL]: code G đọc mọi vé đã có kết quả, không cố định n. Vé thất bại có kết quả sau 2
  giờ, còn vé tốt nghiệp phải chờ dòng survivor ≥ 25 giờ cộng hàng chờ harvest. Lúc n chạm 300, mẫu G sẽ
  thừa vé thất bại và mean bị kéo xuống. GS đã tránh lỗi này. Luật G không được sửa; chỉ nên ghi caveat khi
  diễn giải, hoặc đọc G tại một mốc launch mà mọi exit đã biết.
- Đặc trưng tại trigger của G (buyers, breadth_300, sell_share_300, net_sol_300, insider_ovh, top1,
  overhang_cheap, wash_cycles, dev_sold) đã được ghi từ commit c8b479d (vào main qua PR #25) nhưng chưa bao
  giờ được thăm dò hay đưa vào summary.

#### Ý nghĩa

S bị KILL nghĩa là snipe từ bên ngoài, ở tốc độ của một bot tốt, có EV âm. PASS chỉ có nghĩa là đáng đo
tiếp ở quy mô lớn hơn. Vị trí có lãi thuộc về người tạo token (bundle trong lệnh tạo); dự án không đi theo
hướng đó vì đó là tạo token để bán cho người đến sau. Mọi EV mô phỏng là cận trên cho người ngoài: mô phỏng
giả định dòng lệnh của người khác giữ nguyên và không tính tx lỗi của chính mình.

### 3.4 Bot "rây": năm luật, red team, đặc tả v1 (docs/SIEVE.md, PR #26)

Bốn agent nghiên cứu (bẫy, đám đông nhận tín hiệu, tính khả thi, dữ liệu) và một agent red team, 07–08/10.
Mọi số tự đo là **thăm dò**.

#### Năm luật gốc của chủ bot

1. Bất đối xứng: loại đá, không tìm vàng; thà im lặng cả ngày.
2. Mỗi tín hiệu là câu hỏi "ai bán cho tao, sao họ ngu hơn tao?".
3. Tin dòng tiền, không tin mặt tiền (chart vẽ được, PnL giả được; funding graph, độ tập trung cung, thời
   điểm lệnh được coi là "không giả được").
4. Tốc độ của rây, không phải của súng: tín hiệu trong 2–10 phút đầu, trước đám alert 30–120 s, chạy trên
   Helius $49.
5. Mọi lọc phải đo được; filter 7 ngày không bắt gì thì cắt.

**Phán quyết red team: không luật nào bị bỏ, cả năm luật đều phải sửa.** Luật 1, 2 và 5 đo sai thứ cần đo.
Ý hay nhất là kỷ luật "ai là người thua" của luật 2.

#### Dữ liệu và định nghĩa

- Census 5%: 1.498 launch classic (06/10 20:53Z → 07/10 20:27Z), 39 tốt nghiệp. loopholetape: 72.563 launch
  classic 27–29/9, quyết định ở giây 10–60. Migration: 307 pool kiểu C2.
- Thời điểm quyết định D = 2/5/10 phút, n = 503/207/91. Vé 0,5 SOL, phí 1,25%/chiều + 0,002 SOL.
- **Bẫy** = lỗ ≥ 50% khi bán sau 30 phút (ghi trước khi tính kết quả).
- Cơ học curve: giá ∝ (30 + x)². Lỗ tối đa trên curve = 1 − (30/(30 + x))², tức −26% ở 5 SOL, −44% ở 10 SOL,
  −75% ở 30 SOL. Chỉ lỗ được 50% khi vào từ khoảng 12,4 SOL trở lên, nên **mức curve là biến gây nhiễu cho
  mọi bộ lọc**. Từ 10 SOL lên tới tốt nghiệp là (115/40)², khoảng 8,3 lần.

#### Kết quả chính [TD]

- Tỷ lệ nền ở D = 2 phút: bẫy 7,6%, mean −9,9% (bán sau 30 phút). Theo tầng: < 1 SOL −3,7% (0 bẫy, chỉ mất
  phí); 1–5 SOL −15,2%; 5–13 SOL −30,6%; 13–30 SOL −27,9% (75% bẫy); 30–86 SOL +22,0% (n 16, tỷ lệ bẫy 44%;
  trong đó 7 coin tốt nghiệp, chính là vùng G/GS). Tầng ≥ 5 SOL: bẫy 39–45%, mean −21% đến −37%.
- Từng cờ:
  - F1 (dev giữ ≥ 3%): một trong những cờ thật nhất; trong tầng có lực vẫn 48% bẫy khi có cờ so với 36% khi
    không.
  - F8 (wash): sạch nhất, 4/4 cờ trong tầng có lực là bẫy và không loại coin thắng nào, nhưng n chỉ 14.
  - F3 (top-10 ≥ 20%): loại 34/38 bẫy nhưng cũng loại 6/7 coin thắng lớn; lift 47 lần phần lớn là do cơ học.
  - F9 (dev đã bán): bật ở 65% coin, vô tác dụng.
  - F12 (spike): 70% là bẫy, tức đuổi theo cú bơm vừa xảy ra.
  - Cờ nguồn tiền gần như vô dụng sau 1 giờ.
- **Câu hỏi then chốt: không tổ hợp đăng ký trước nào để lại phần còn lại có lời.**

| Thời điểm / tổ hợp | n | Mean | KTC |
|---|---:|---:|---|
| 2 phút, A (lõi luật 3) | 89 | −4,7% (0 bẫy, 0% thắng, toàn bụi) | −5,4 … −4,1 |
| 2 phút, B/C/E | 0–2 | "im lặng cả ngày" | |
| 2 phút, D (momentum) | 57 | −13,3% | −35 … +12 |
| 5 phút, A | 25 | +3,9% | −6 … +22 |
| 5 phút, D | 29 | −27,9% | −51 … −1 |
| loopholetape 10–60 s, lõi luật 3, tầng có lực | 548 | −16,5% | −27,5 … −4,1 |
| Migration T+30, giữ 1 giờ, cờ funding | 238 | −33,2% | −41 … −24 |

- Luật chọn sau khi xem dữ liệu ở phút 5 (có lực, top-10 < 20%, dev < 3%): n 13, +29% (KTC −9 … +73). Luật này
  dựa trên 3–4 vé tốt nghiệp, âm ở phút 2 và 10, nên khả năng cao là nhiễu. Khoảng 200 ô đã được xem mà không
  hiệu chỉnh kiểm định bội. Đây chính là nguồn gốc của luật mua B1.
- Luật 4 trên dữ liệu: vào trễ 30–120 s không làm đổi mean (cú tăng đã nằm trong giá). 79% lần tốt nghiệp xong
  trong 60 s đầu, 87% trong 120 s, nên phần lớn coin thắng đã xong trước khi cửa sổ 2–10 phút mở ra.
- Luật 2 trên dữ liệu: 58–65% SOL bán ra sau khi mình vào đến từ ví mua **sau** mình; insider chỉ 1–4%.
  Danh tính người bán không phân biệt được bẫy. Lợi thế, nếu có, lấy từ khoản lỗ của đám đông đến sau; chia sẻ
  tín hiệu thì người theo trở thành chính đám đông đó.
- Luật 3: mọi thứ đều giả được, chỉ khác chi phí (volume/holder/PnL/chart gần như miễn phí; SOL ròng tốn khoảng
  2,5% phí; chia cung ra 17–21 ví là qua mặt được; nạp qua sàn vừa tạo liên kết giả vừa che liên kết thật).
- Luật 5: thước đo sai. Ở quy mô toàn luồng, cờ có ích bắt 20–700 bẫy/ngày nên quy tắc 7 ngày không bao giờ
  kích hoạt; cờ duy nhất bắt 0 bẫy là cờ "curve mỏng", vốn loại đúng nhóm chắc chắn lỗ phí, nên sẽ bị cắt nhầm.
  Thay bằng đo bằng tiền, ≥ 200 cờ forward, người duyệt, có version.

#### 11 luật còn thiếu (đã thêm)

0 định nghĩa sự thật; 6 EV là thước đo duy nhất của MUA; 7 lối thoát cố định, không ôm qua migration;
8 phí và bụi (coin < 5 SOL không bao giờ được nhắn); 9 đủ dữ liệu mới phán (khớp reserve, độ phủ ≥ 90%);
10 đối thủ thích nghi (version gắn với chương trình pump.fun, giữ kín bộ lọc); 11 mỗi lần một giả thuyết đăng
ký trước; 12 vé nhỏ, trần lỗ; 13 người vận hành (bot là phanh FOMO); 14 riêng tư và pháp lý (chỉ dùng riêng,
không chia sẻ/bán tín hiệu, không nhận Callout Rewards, hỏi luật sư trước khi chia sẻ); 15 công tắc tắt: 60
ngày không có luật MUA đạt chuẩn thì bot vĩnh viễn chỉ cảnh báo (tính từ 08/10 thì khoảng 07/12/2026).

#### Đặc tả v1 (chưa xây)

- Bot riêng tư, ba nhãn: **[TRÁNH]**, **[THIẾU DỮ LIỆU]**, **[KHÔNG THẤY CỜ]** (kèm câu "ĐÂY KHÔNG PHẢI TÍN
  HIỆU MUA"). Không bao giờ in "MUA" cho tới khi sổ bóng đạt GO.
- Tầng 0 (miễn phí): loại mayhem, loại quote ≠ SOL, kiểm độ phủ, TRÁNH curve tự tốt nghiệp/bundle lấp curve ≥
  20 SOL. Cổng F0: 5 ≤ SOL thật < 70, ≥ 5 giao dịch và ≥ 3 ví mua trong 120 s. Tầng 1 (miễn phí, ngưỡng đóng
  băng): **đã nghỉ hưu ngày 08/10** vì trên holdout nó gắn cờ 59/61 dòng qua cổng. Tầng 2 (trả phí, ≤ 300
  coin/ngày): holder ẩn, cụm nguồn tiền.
- Sổ bóng 14 ngày cho luật mua B1. GO cần tất cả: n ≥ 400; mean ở T+45 s ≥ +5% với cận dưới KTC > 0; cả hai
  nửa 7 ngày dương; không phụ thuộc đuôi; vào ở T+90 s vẫn dương. **Mọi trường hợp lưng chừng đều tính là
  KILL.** SIEVE.md dự đoán B1 nhiều khả năng bị KILL.
- Kill: B1 ≤ 0 hoặc lưng chừng thì bỏ vĩnh viễn; pump.fun đổi chương trình thì treo; độ phủ < 90% thì dừng mọi
  output; thí điểm mất 3/10 SOL thì dừng; có ý định chia sẻ/bán tín hiệu thì dừng và hỏi luật sư.
- Chi phí thêm $0–10/tháng, trần 30k credit/ngày. Không dùng máy quét trả phí bên thứ ba (không cái nào công
  bố độ chính xác trên pump.fun).
- Phần thí điểm thật (vé 0,25 SOL, tối đa 5 lệnh/ngày, ngân sách 10 SOL) và nhãn [MUA THỬ] trong SIEVE.md mục 5
  chỉ là đặc tả, chưa bao giờ được duyệt hay chạy. Chúng mâu thuẫn với lập trường chỉ nghiên cứu và với rủi ro
  NĐ 284/2026, và với luật ràng buộc sau đó của PR #27 (không bao giờ in "MUA", xem Phụ lục A), nên không làm.

#### Kiểm chứng các khẳng định

- "86 nghìn ví mất 675K SOL": **không tìm thấy nguồn** sau khoảng 7 lần tìm. Gần nhất có nguồn: LIBRA, hơn
  86% của 15.430 ví lỗ khoảng $251M (Nansen), nên nhiều khả năng "86" là phần trăm chứ không phải số ví.
- Funding/supply/timing "không giả được": sai (chỉ là đắt để giả). "Đi trước đám đông 30–120 s là đủ": chưa
  kiểm chứng, dữ liệu đi ngược. "Chạy được trên Helius $49": đúng một phần (chỉ khi lọc theo tầng).
- Tỷ lệ nền "98–99% là bẫy" phụ thuộc định nghĩa: Solidus 99% [S]; arXiv 2603.24625 76%; census của dự án
  7,6–13% ở coin còn giao dịch, 39–45% ở tầng ≥ 5 SOL.

#### Trạng thái thực

Luật mua B1, PREREG-V1 và bot v1 **chưa bao giờ được viết hay chạy**. Nhánh này được nối tiếp bằng sổ
filter sống (mục 3.5). `PREREG.txt` (ngưỡng F1–F14, L1–L9, M1–M6) và các file kết quả của mục 2 SIEVE.md đã lưu vào repo ở
`docs/snapshot-2026-10-08/sieve-five-laws/`. Riêng các script thăm dò thì chỉ nằm trong thư mục tạm của phiên, và sẽ mất.

### 3.5 Sổ filter sống và vòng vá 1 (docs/SIEVE_FILTERS.md, docs/PREREG-SIEVE-R1.md, PR #27)

#### Triết lý thành quy trình

Câu của chủ bot: "không bắt bẫy chưa từng tồn tại; crew tiến hoá theo tuần; chuỗi lọc là sinh vật". Câu
này thành bốn thứ:

1. **Luật đếm**: một kiểu bẫy chỉ thành ứng viên khi có ≥ 3 mint bẫy, của ≥ 2 creator, trong ≥ 2 ngày (vòng
   sáng lập dùng ≥ 2/3 khối thời gian thay cho ngày).
2. **Vòng đời có version**: theo dõi → shadow → active ("cờ (chưa kiểm)") → TRÁNH. Không sửa ngưỡng tại chỗ;
   mỗi bản vá là một id mới.
3. **Lịch tuần cố định.**
4. **Ba vai tách biệt**: người phân tích (trợ lý AI), red team, và chủ bot là người duyệt duy nhất. Bot không
   tự sửa mình.

#### Kho sáng lập (khoảng 26 giờ) [TD, trong mẫu]

- Journal: ứng viên ở D = 120/300/600 s qua cổng F0. Bẫy = net 30 phút ≤ −50%; thắng = net 30 phút ≥ +100%.
- Kho: 206 dòng (launch tạo 06/10 20:53Z → 07/10 23:03Z), 127 mint, 82 dòng bẫy (55 mint), 16 dòng thắng (11
  mint), 137 dòng qua GATE_E. Explore (trước 07/10 15:15Z): 111 dòng. Holdout: 95 dòng, 32 bẫy (22 mint), 8
  thắng (5 mint).
- Khối thời gian: B1 (trước 07/10 06:00Z, 49 dòng), B2 (06:00–15:15Z, 62 dòng), B3 (15:15–23:03Z, 95 dòng).
  Lưu ý: "B1" ở đây là khối thời gian, khác với luật mua B1 ở mục 3.4.
- **Holdout đã bị xem, nên mọi số ở đây chỉ còn là thăm dò.** Dữ liệu sạch chỉ có từ sau 07/10 23:03Z.

#### Vòng 0: 19 filter → 2 active

Năm lăng kính (mài cờ v1, cách bẫy xả, sổ creator, trí nhớ ví, dấu vết MMaaS/bundle) cho ra 19 filter. Mỗi
họ filter có một verifier tự viết lại code từ định nghĩa chữ, rồi chấm trên holdout, rồi red team kiểm.

| Filter | Holdout cờ/bẫy/thắng | p | Quyết định |
|---|---|---:|---|
| N-MMAAS-WAVE-STREAM (≥ 4 ví mua cùng slot, cỡ lệch ≤ 2%) | 12/10/0 | 0,0027 (q 0,071) | **active**; filter duy nhất còn ý nghĩa sau BH |
| SH-DEV-1 (dev + creator giữ ≥ 3%) | 12/11/0 | 0,028 | **active** |
| SH-SG-1, WAVE strict, SPLDIST | 18/10/0; 4/4/0; 10/6/0 | 0,042; 0,030; 0,10 | shadow |
| SH-FLIP-1 | 10/3/0 | 0,48 (explore 0,021) | nghỉ hưu: sập ngoài mẫu |
| SH-TOP10-1, SH-TIN-1, N-WM-BL3 | 35/18/3; 19/7/3; 10/3/3 | 0,36; 0,78; 0,95 | nghỉ hưu (BL3: giữ danh sách ví) |
| S1_spike | 12/5/2 | 0,71 | REJECT, chỉ làm ngữ cảnh |
| N-WM-TDINV | 60/21/8 | 0,90 | nghỉ hưu: gắn cờ cả 5/5 mint thắng |
| N-WM-EXIT2 | 33/14/1 | 0,13 | bác (proxy "coin đông ví") → sửa thành EXIT2-v2 |
| N-WM-XIN | 46/20/2 | 0,075 | đứng ở mức info (cũng là proxy "coin đông ví") → info |
| N-ANAT-FADE, N-LTE-FACTORY | 13/11/1; 12/9/1 | 0,21; 0,35 | bác: proxy tầng 13–30 SOL |
| SH-WASH-1 | 14/9/1 | 0,33 | bác: gần động lượng → info |

Bài học: filter đơn giản, có cấu trúc (dev ôm hàng, sóng cùng cỡ, bundle ở slot tạo) đứng được; filter
"thông minh" (flippers, top-10, transfer-in, trí nhớ ví) sập ngoài mẫu.

#### Các chuỗi trên holdout [TD]

| Chuỗi | Bẫy bắt | Thắng bị giết | SOL tiết kiệm |
|---|---:|---:|---:|
| Không phủ quyết (phần qua mean −12,2%/vé) | 0/32 | 0/8 | 0 |
| Cổng trần (chặn mọi coin ≥ 11,73 SOL) | 32/32 | 7/8 | +1,73 |
| v1 có cổng | 31/32 | 6/8 | +3,70 (ngang cổng trần → nghỉ hưu) |
| Agent chọn trên chính holdout | 28/32 | 1/8 | +8,76 (đẹp giả) |
| Cùng quy trình nhưng chọn trên explore | 25/32 | 3/8 | +5,85 (ước lượng trung thực) |
| **Active trung thực: cổng + DEV ∨ WAVE-STREAM** | **16/32** | **0/8** | **+4,80** |

Ngay cả với chuỗi tốt nhất, phần được qua có mean +0,114/vé nhưng KTC theo mint là −0,23 … +0,50, chứa 0:
**không có tín hiệu mua**. Chuỗi chọn trên holdout trông tốt hơn khoảng 50% so với khi chọn trung thực.

#### Red team nhận xét cả quy trình

1. Holdout đã bị tiêu.
2. Luật PROMOTE cũ quá lỏng: một filter ngẫu nhiên cùng số cờ cũng đạt 17–66% số lần; khoảng 7,7/26 filter
   "đạt" chỉ do may rủi; sau BH chỉ còn WAVE-STREAM.
3. Đơn vị bằng chứng là mint: holdout chỉ có 22 mint bẫy và 5 mint thắng; hơn thua giữa các chuỗi chủ yếu do
   3–4 mint thắng được tha.
4. Nhãn mong manh: vào ở T+90 s thì chỉ 21/32 bẫy holdout còn là bẫy.
5. Luồng sống khác census: mất ngẫu nhiên 5% lệnh nhỏ làm EXIT2 bật thêm 248 cờ, 30 trên coin thắng.
6. Proxy trá hình (EXIT2/XIN, FADE/FACTORY, WASH).
7. Ví hạ tầng `ARu4n5mF` (có mặt ở 6,1% launch classic, bán 1,33 lần số đã mua) một mình tạo 8/33 cờ EXIT2.
   Quy trình cấm loại tay ví sau khi thấy kết quả.
8. Không có nhìn trước: cắt lệnh ở dslot không đổi cờ nào trên 576 dòng.
9. Tiền đề "crew tiến hoá theo tuần" chưa kiểm được vì mới có 26 giờ.

#### Vòng vá 1

Active trung thực còn lọt 40 dòng bẫy của 31 mint. Coin thắng duy nhất bị giết là `ukjpAvka@120` (+255%,
qua DEV: dev mua 5,86 SOL lúc tạo, giữ 17,5% nhưng không xả).

| Kiểu bẫy | Mint lọt | Ghi chú |
|---|---:|---|
| Đám đông xả dây chuyền | 11 | Curve đông (104–453 ví), chuỗi cắt lỗ bằng nút preset; **không có dấu hiệu trước D** |
| Thoát đồng loạt nhiều ví | 8 | Farm lớn 4 (chỉ B3 → theo dõi) và crew nhỏ 4 (đạt luật đếm) |
| Sụp muộn sau sóng 2 | 7 | 22/28 vé từng lời ≥ 30% (median +84%) rồi mới sụp → lỗi của giờ thoát |
| Vòng kín rút cạn | 6 | Không có tiền mới, holder tự bán dần về 0 |
| Rút cạn sát cổng | 6 | Chỉ là mép cổng (11,7–14,7 SOL), không phải cơ chế crew |
| Thoát nhiều chữ ký | 4 | Chỉ B3 → theo dõi |
| Lẻ: insider qua ví transfer, cá voi xả một lệnh, bán bậc thang | 1–2 mỗi kiểu | theo dõi |

10 đề xuất vá → **2 shadow mới**:

- **CLD-ORPHAN-v1**: kho 12/10/0, thêm 9 mint bẫy, p 0,11, MH 2,90. Phản bác mạnh nhất: "0 coin thắng" nằm
  trên lưỡi dao (3 coin thắng cách ngưỡng < 1%); mất 5% lệnh nhỏ thì 6/10 lần bật cờ trên một coin thắng.
  Vẫn đăng ký vì đây là đề xuất duy nhất chạm tới kiểu vòng kín, và shadow thì không chặn gì.
- **N-WM-EXIT2-v2b** (dùng luật phân loại ví WTYPE-v1): kho 35/24/1, thêm 12 mint bẫy, p 0,087, MH 1,42.
  Phản bác: trong mẫu không tách được khỏi placebo "curve đã sụt từ đỉnh" (p trong tầng 0,12).
- 5 đề xuất về info hoặc theo dõi (EXIT2-v2a, P1-SWARM-SCRIPTED, P2-SWARM-VET, CC-TOPDIST, LC-XFERSUP).
  Nghỉ hưu: CC-CHEAPLOAD, LC-REPUMP, CLD-REACTFLOAT, và POSTHOC-CC-FRAGILE-v0 (chọn sau khi đã thấy kết quả
  nên không bao giờ được chấm).

Bài học của vòng vá:

1. Đám đông xả không phải hàng rẻ bị xả: ở dòng bẫy, hàng của người còn lời chỉ bằng 2,6% lượng cần bán để
   kéo vé xuống −50% (44% ở dòng không bẫy, 70% ở coin thắng).
2. Farm script nhận ra được, nhưng kết cục có hai đầu: trong 16 mint farm, 12 xả trong 1 slot, 4 tốt nghiệp.
   Chỉ dùng làm nhãn thông tin.
3. Sụp muộn là lỗi của giờ thoát. Luật thoát/cảnh báo khi đang giữ vé là một giả thuyết riêng, chưa đăng ký.
4. Vòng kín khó tách khỏi curve nhỏ, yên tĩnh sát cổng.
5. WTYPE-v1 xếp được `ARu4n5mF` là ví gom hàng mà không cần nêu tên; có 28 ví exit công nghiệp.
6. Kiểm đủ lệnh (`check_chain`) dùng được: 0/1.698 launch hỏng, bắt 1.055/1.055 lần rút ngẫu nhiên một lệnh.
   Nhưng nếu luồng sống mất 5% lệnh nhỏ thì khoảng 30% launch có lỗ hổng và 85/95 dòng holdout không qua được;
   phải đọc bù 21–51 credit mỗi launch hoặc ghi "THIẾU DỮ LIỆU". Chỉ WAVE-STREAM gần như không bị ảnh hưởng.

Dấu hiệu crew né (yếu, Fisher p = 0,07): tỷ phần farm trong mint bẫy tăng 1/12 → 5/21 → 7/22 qua ba khối;
ở B3 dev chỉ giữ 1,9–2,75%, sát dưới ngưỡng 3%; sóng cùng cỡ chính xác giảm 5/12 → 4/21 → 2/22. Nhưng dải dev
1,5–3% cũng tăng ở mint không bẫy, nên có thể chỉ là nhiễu.

#### Sổ đăng ký lúc tắt server

- **ACTIVE** = GATE_E (SOL thật lúc vào ≥ 11,66; dưới mức này vé 0,5 SOL không thể lỗ 50%) ∧ (SH-DEV-1 ∨
  N-MMAAS-WAVE-STREAM). Trên kho: chặn 51 dòng (42 bẫy, 1 thắng), tức 26/55 mint bẫy và 1/11 mint thắng; để
  qua 155 dòng với mean −10,8%/vé.
- **SHADOW (5/8 chỗ)**: SH-SG-1, N-MMAAS-SPLDIST, N-MMAAS-WAVE strict, N-WM-EXIT2-v2b, CLD-ORPHAN-v1. ACTIVE +
  5 shadow chặn 93 dòng (70 bẫy, 4 thắng; 46/55 mint bẫy) và để qua 113 dòng với mean −1,7%/vé (trong mẫu, nhiều
  khả năng quá lạc quan). Vẫn không có tín hiệu mua.
- INFO, theo dõi, nghỉ hưu: danh sách đầy đủ ở docs/SIEVE_FILTERS.md mục 4 và docs/PREREG-SIEVE-R1.md mục 7–8.
- 9/55 mint bẫy không bị gì bắt (3 farm lớn ở B3, 4 đám đông xả, 1 sụp muộn, 1 vòng kín).

#### Kế hoạch forward và quy trình tuần (đăng ký trước)

- Dữ liệu: launch classic có t0 > 1791414202 (sau 07/10 23:03:22Z) trong census 5%.
- **W1**: t0 ∈ (07/10 23:03Z, 14/10 23:03Z]; chấm khoảng 15/10 02:00Z; chỉ đếm và kiểm điều kiện huỷ.
- **W2**: tới 21/10 23:03Z; chấm khoảng 22/10 02:00Z; quyết định thăng/huỷ đầu tiên trên W1 + W2, BH trên 5
  shadow.
- Khối lượng dự kiến mỗi ngày (±30–50%): khoảng 1.560 launch, 189 dòng journal, 126 dòng qua cổng, khoảng 50
  mint bẫy và 10 mint thắng.
- Phép thử sắc nhất: tối đa 1 mint thắng bị giết trên mỗi 10 mint bẫy bị bắt.
- Điều kiện ràng buộc chưa ghi ở trên: (1) Trước khi bất kỳ filter dựa danh tiếng nào (EXIT2-v2b) lên active,
  phải chạy một tuần trên luồng đầy đủ để đo tỷ lệ cờ thật, vì luồng live lớn gấp 10–20 lần census 5%. Ngưỡng
  danh tiếng tính trên mỗi 1.000 launch. (2) Sau 4 tuần, shadow nào không được thăng mà cũng không bị huỷ thì
  xuống INFO. (3) Bot v1 cần toàn bộ luồng PumpPortal cộng đọc bù (dự kiến 130–260 coin khớp B1/ngày). Dự án
  chưa bao giờ có luồng đầy đủ: scope `full` tốn 5–15 GB/ngày và cần RPC trả phí (docs/SIEVE_FILTERS.md mục 6,
  docs/PREREG-SIEVE-R1.md mục 5, research/sieve/README.md quy tắc 5, docs/SIEVE.md mục 5, README "Phạm vi ghi").
- Luật thăng shadow → active (PREREG, ràng buộc): sau ≥ 2 tuần forward, cần ≥ 20 cờ band từ ≥ 8 mint bẫy và ≥ 3
  creator; p hoán vị gom mint < 0,05 sau BH; MH OR > 1 ở từng tuần và ≥ 1,5 khi gộp; thắng mọi placebo; ≤ 1/10
  luật coin thắng; thêm ≥ 3 mint bẫy so với ACTIVE với SOL tiết kiệm biên có cận dưới KTC > 0. Active → TRÁNH
  cần ≥ 200 cờ forward.
- Quy trình tuần: khoá tuần → chấm một lần bằng code đóng băng → hồ sơ bẫy lọt (`archetype.py`) → đề xuất (tối
  đa 2/tuần, tối đa 8 shadow) → red team → chủ bot duyệt → commit khối PREREG mới. Có canary, đầu dò cận ngưỡng
  và đầu dò né riêng cho từng filter.
- Không bao giờ: chỉnh ngưỡng trên tuần đang chấm; gọi một tập là holdout khi đã có người xem; vá đúng bẫy vừa
  lọt rồi chấm trên chính tuần đó; loại ví sau khi thấy kết quả; để bot tự sửa mình; in chữ "MUA" hay chia sẻ tín
  hiệu; mô tả cơ chế crew quá mức cần để phát hiện.

#### Mã chấm đóng băng

`research/sieve/` (`filters.py` với REGISTRY và FROZEN, `journal.py`, `score.py`, `archetype.py`), chỉ dùng
thư viện chuẩn Python 3.11, chạy bằng `python3 -I`, tất định. Hash sha256 (16 ký tự đầu) lúc đăng ký:
`filters.py 890d76e5a608f09e`, `journal.py 48441b097aa3fdbe`, `score.py ce7cd03d2e0f075a`,
`archetype.py 96262e1b05c07b07`. Kiểm lại ngày 08/10: khớp, `filters.py --check` in "frozen check: OK". Gói
tái tạo kết quả scratch với 0 lệch trên 1.037 dòng; `archetype.py` khớp 82/82 dòng bẫy.

#### Phụ thuộc vào census: tắt server là dừng

Bài kiểm forward cần census chạy liên tục, **cùng tỷ lệ mẫu 5% và cùng code**. Các file census từ 06/10 phải
còn, vì kho danh tiếng của EXIT2-v2b là kho tích luỹ (W2 phải đọc pool + W1 + W2). Dữ liệu forward lúc chụp cuối
chỉ gồm các launch tạo trong khoảng 07/10 23:03:22Z → khoảng 08/10 04:44Z (khoảng 5,7 giờ launch), vì mỗi launch
được đọc 2 giờ 5 phút sau khi tạo (`sniper_window_s` 7.200 + `sniper_delay_s` 300; lần đọc cuối 06:49:43Z,
snap/stats.json → `last_harvest_ts`) [SL]. 188 launch tạo sau mốc đó còn trong hàng đợi Redis và sẽ mất khi tắt.
Lúc đăng ký (PR #27), file census ngày 08/10 mới có 9 dòng forward; chưa ai đọc kết quả. Tắt server thì W1/W2
không chấm được; sổ đăng ký giữ nguyên trạng thái "chưa kiểm".

### 3.6 Nghiên cứu chỉ có trong chat

Phần này lấy từ lịch sử trò chuyện (05/10 22:50Z → 08/10 06:49Z). Phần lớn chưa có trong `docs/`. Số liệu
tạm được ghi kèm thời điểm.

#### Phương án kiếm tiền mới trên pump.fun (07/10 22:53Z, tra web) [NG]

Kết luận: các cách "mới" năm 2026 chủ yếu là chương trình khuyến khích của chính nền tảng, không phải lợi thế
giao dịch.

| Cách | Số liệu tìm được | Đánh giá |
|---|---|---|
| Callout Rewards (từ 13/08/2026) | Top 50 người gọi nhận gần $700k; người đứng đầu $47.500 cho 215 lần gọi; 80% token được gọi có vốn hoá < $100k | Được trả tiền để kéo người theo vào token tí hon. **Không làm.** Nguồn mâu thuẫn về hình thức thưởng (USDC, PUMP, hay không có) |
| Phí creator | 0,30%/giao dịch trên curve, 0,95% ở vốn hoá 420–1.470 SOL; chỉ khoảng 0,01% creator kiếm > $10k | Xác suất thành công rất thấp; với token median, phí creator chỉ khoảng 0,01 SOL |
| Holder Rewards (từ 12/09/2026) | Tổng $6,1 triệu cho khoảng 198 nghìn ví, khoảng $31/ví | Quá nhỏ so với rủi ro giá |
| LP PumpSwap | 0,02% (dưới 420 SOL) hoặc 0,20% | Gần như chắc lỗ vì giá giảm sau migration [SL, chưa đo] |
| GO (chợ bounty) | Khoản trả cao nhất đã hoàn tất chỉ $487–686 | Nhỏ |
| Pump Fund | 12 × $250k ở định giá $10 triệu | Đã đóng |
| Token PUMP | Nền tảng đã chi khoảng $350 triệu mua lại; giá từng −81% so với đỉnh | Là cược, không phải thu nhập |
| Referral terminal 30/10/5% | Chỉ thấy trên trang bán mã mời | Chưa kiểm chứng; hướng kéo người VN vào bot lấy referral đã bị rút vì NĐ 284 |

Hướng hợp lý hơn là bán dịch vụ/dữ liệu (kiểu bộ dữ liệu loopholetape), nhưng **chưa kiểm xem có ai chịu trả
tiền**. Lưu ý: dữ liệu của dự án chứa địa chỉ ví. Thu thập hoặc bán dữ liệu tài khoản trái phép bị phạt 150–200
triệu VND theo NĐ 284/2026, nên không bán hay chia sẻ dữ liệu có thông tin ví trước khi hỏi luật sư (README mục
Pháp lý). Verdict rug/bundle cũng đã có miễn phí trên các terminal lớn (RESEARCH.md mục 0). Đây không phải đề
xuất kinh doanh.

#### Mua Helius có phí tiền không (07/10 22:57Z)

- Không phí. Helius mua được câu trả lời bằng số đo thật. Lúc đó (số tạm): C n 2.054, mean −23,6% → KILL; mọi
  kiểu vào sau migration −9,5% đến −73%; S −4,5%; ăn theo BOOST −5,7%; mức +21% của G phần lớn là bundle không vào
  được. Nếu đã cho bot giao dịch thật theo bất kỳ hướng nào trong số đó, khoản lỗ gần như chắc lớn hơn tiền Helius
  nhiều lần.
- Ba lựa chọn đã đưa ra: (1) dừng và xuất dữ liệu; (2) chạy tới khi có phán quyết rồi dừng (lúc đó được khuyên);
  (3) chuyển sang hướng không cần Helius. Tắt server ngày 08/10 trên thực tế là lựa chọn 1.
- Bối cảnh: gói Developer $49 được khuyên lúc 06/10 10:54Z (cần dữ liệu từng swap thay cho nến), và được nâng cấp
  lúc 11:04Z. Đã cân nhắc nhưng không mua: Helius Business $499 (LaserStream), shred stream $1.000/tháng, CoinGecko trả phí (nhu cầu
  chỉ khoảng 1.200 call/ngày), Bitquery, PumpPortal trả phí, nhóm KOL, terminal.

#### Bot tín hiệu và pháp lý NĐ 284/2026 (07/10 22:59Z)

- Về tiền, bot tín hiệu giống bot giao dịch: chưa có tín hiệu "nên mua" nào lời trung bình. Người bấm tay chậm hơn
  bot rất nhiều; các thời điểm đủ chậm cho người (sau migration, phút 5–60) đều âm. Chia sẻ tín hiệu là mô hình
  KOL/Callout: người gọi kiếm tiền, người theo gánh lỗ. Đề xuất thay bằng bot "đừng mua" (cảnh báo), sau đó thành
  docs/SIEVE.md.
- Pháp lý (theo tin tức, **chưa đọc văn bản gốc, không phải tư vấn pháp lý**):
  - NĐ 284/2026/NĐ-CP ban hành 16/7/2026, hiệu lực 1/9/2026.
  - Cá nhân giao dịch tài sản mã hoá không qua tổ chức được Bộ Tài chính cấp phép: 30–50 triệu VND.
  - Thu thập/bán dữ liệu tài khoản trái phép: 150–200 triệu VND.
  - Mức tối đa: 100 triệu VND (cá nhân), 200 triệu VND (tổ chức).
  - Quảng cáo/tiếp thị tài sản mã hoá không phép: 180–200 triệu VND với tổ chức.
  - Không tìm thấy điều khoản riêng về "tín hiệu". Phát tín hiệu công khai **có thể** bị coi là quảng cáo/tiếp thị
    không phép.
  - **Mâu thuẫn chưa giải quyết**: chat 05–06/10 nói mức 30–50 triệu áp dụng từ 1/9/2026; VnFinance (theo bảng
    kiểm chứng của SIEVE.md) nói mức này chỉ áp dụng 6 tháng sau khi có đơn vị đầu tiên được cấp phép.
  - Bối cảnh (06/10 21:56Z): Bộ Tài chính nhận hồ sơ từ 20/1/2026; có 5 hồ sơ (VIXEX, CTCP Tài sản số Việt Nam,
    CAEX/VPBank, SCEX, TCEX/Techcombank); mới TCEX qua vòng 1; "sớm nhất quý III". Gần như chưa có tiền lệ phạt cá
    nhân, nên đây là "rủi ro mềm". Nhưng mọi kiểu creator bundle lừa người mua (ví ẩn, volume giả, xả lên người đến
    sau) là lừa đảo chiếm đoạt tài sản (Điều 174 BLHS), không phụ thuộc luật crypto; dự án từ chối giúp việc đó.
  - Hệ quả: không chạy bot live; bot chỉ dùng riêng; không bán dữ liệu ví; hỏi luật sư trước khi chia sẻ bất cứ
    thứ gì.

#### Nghiên cứu luật bằng nhiều agent

- **v1** (06/10 23:10Z): 9 agent (4 góc × tìm kiếm + red team, cộng 1 tổng hợp). Chạy hai lần, cả hai bị container
  khởi động lại giết; 0 agent xong, phần lớn WebFetch bị proxy chặn. Đã cứu được 71 tóm tắt tìm kiếm vào một file
  tạm (khoảng 214 KB, không có trong repo). Một số dữ kiện cứu được, chỉ là đoạn trích, chưa kiểm chứng [S]:
  - Bài "The 17.6 SOL Ghost": khoảng 230 curve cũ hoàn tất trong 24 giờ sau BOOST, lãi thực tế +2 đến +4 SOL.
  - Graduation rate sau BOOST khoảng 6,7% vào một ngày đỉnh.
  - Một ví chiếm 17% mọi giao dịch bonding curve trong 27/8–2/9.
  - Tháng 4/2026: 6.379 token tốt nghiệp, 1.513 trong < 60 s.
- Song song với v1, phân tích riêng tìm ra và đăng ký G (PR #22), sau đó GS.
- **v2** (07/10 00:30Z → 01:07Z, dừng vì hết limit): 2/4 agent tìm kiếm xong, 0 red team, không có shortlist. Có 8
  ứng viên chưa kiểm định và chưa đăng ký: G50-RETAIL, W30, G60-LOWOVH, TOPDIP, SC (stale-curve completion), BS
  (sau ví "BOOST seller"), OV, WX.
- Kiểm nhanh liên quan [TD]: curve chạm ≥ 60 SOL mà không hoàn tất trong 2 giờ thì chỉ 12,4% tốt nghiệp về sau
  (563 → 70); nghĩa là chờ người khác lấp nốt curve bị bỏ dở thì phần lớn về gần 0. Thăm dò G theo đặc trưng (trong
  mẫu, chưa đăng ký): mức 50 SOL slow + dev_share < 0,0309 cho +13,2% (KTC +5,1 … +21,4; n 528); mức 60 SOL slow +
  insider_share < 0,218 cho +11,1% (KTC +4,0 … +18,2; n 391). Các số "all" +20–27% bị thổi phồng bởi curve jump
  không vào được.

#### Kiểm tra dữ liệu và backlog credit

- 07/10 17:45Z: census ghi đủ 98,6% số lệnh tạo so với PumpPortal, 0 đứt chuỗi trên 1.615 launch. Fills đã dùng
  212k/210k nên harvester dừng tới 00:00Z, trễ khoảng 10 giờ, due 594.
- 07/10 22:10Z: due tăng 594 → 897 (khoảng +70/giờ), pending 2.275. G có 22 vé kiểm định, ước tạm −7,6% ±27,7% (định
  giá vé tốt nghiệp đúng bằng giá tốt nghiệp 1,00×, không chính thức). 19/28 curve chạm 60 SOL trong phút đầu là
  jump; có vé vào ở 67–83 SOL (lệch lớn nhất +23,26 SOL).
- Chi phí harvest theo loại [TD]: migration tốt nghiệp khoảng 85 SOL (n 1.209) trung bình 200,7 credit, chiếm 91%
  tổng; trong đó pool có ≥ 10 SOL thật lúc T+30 trung bình 450,8 credit. Theo thành phần mỗi dòng quote SOL: curve
  21,7; states 28,0; window 82,0; flow 5,2.
- PR #25: census dừng sau trang ngắn (curve yên còn 11 credit thay vì 21), trần census 65k, fills 235k. Chỉ thu
  hẹp backlog chứ không chặn được (vẫn thiếu khoảng 200 dòng/ngày). Hướng giảm chi phí mỗi dòng 10–15% (lấy trạng
  thái T+30/T+60 từ cửa sổ replay đã tải) được khuyên nhưng chưa làm.
- 08/10 01:00Z: shortcut chạy đúng, trung bình 23 credit/lượt trên 294 lượt, due giảm 923 → 836.

#### Các phân tích khác

- **Binance futures** (06/10 23:55Z): phí rẻ hơn nhiều (maker 0,02%/taker 0,05% so với 1,25%) nhưng không dễ lời
  hơn. Carry BTC chỉ khoảng +6,4%/năm (26/9/2026). Binance chưa được cấp phép ở VN nên cùng rủi ro NĐ 284. Đã đề
  nghị bộ nghiên cứu F1 (carry) và F2 (trend-following khung ngày), chỉ dùng dữ liệu công khai, không giao dịch
  thật. Chưa làm.
- **"Data nghiêng về chiến lược nào"** (06/10 19:41Z, 788 token): không chiến lược mua nào được ủng hộ; pool kiểu C2
  có median −41,8%; các dấu hiệu "trông tốt" lại tệ hơn. Kết luận: luật đáng thử nhiều khả năng là luật LOẠI BỎ.
- **Giải thích KILL của C** (06/10 19:32Z, 303 token): bỏ vào 303 SOL thì mất 81,7 SOL (−27%); lệnh điển hình
  −3,9%; 2% token tốt nhất chiếm 61% tổng lãi.
- **Tổng kết bot giao dịch** (06/10 21:59Z): mọi chiến lược bot bên ngoài làm được đều có EV âm sau chi phí; người
  lời đều đặn là bên thu phí; bot chỉ thực thi được lợi thế có sẵn.
- **Phản biện memo ban đầu** (chat 05/10 23:24Z và 23:29Z; một phần kết quả fact-check và điểm red team C 4/10,
  D 3/10 có trong RESEARCH.md mục 0): khoảng 8/13 con số của memo là cũ, sai nguồn hoặc không tồn tại. Xếp hạng
  cuối (chỉ có trong chat): F-dataset 6 > C 4 > D 3 > E 3 > B 2 > A 1. Định nghĩa các hướng, theo bản red team
  trong chat (05/10 23:26Z): A = scalp momentum trên curve (chiến lược v1 Early-Momentum Scalp, đã bị falsify);
  B = bán verdict rug/bundle/dev ở block 0 (tin 23:29Z gọi là "bán dữ liệu hành vi ví"); C = survivor entry sau
  migration; D = copy ví chậm; E = xây audience Việt Nam rồi kéo vào bot Trojan/GMGN để ăn referral (đã rút vì
  NĐ 284); F = rời memecoin, cụ thể là bán bộ dữ liệu sạch có slot kéo dài > 24 giờ cùng harness kiểm định
  ("F-dataset"), hoặc làm công cụ cho các đơn vị đang xin cấp phép ở Việt Nam.
- Các đề nghị chưa được nhận: đo lãi/lỗ creator trên census (không tốn credit); mô phỏng chốt lời/cắt lỗ cho pool C2
  trên swap đã lưu.

---

## 4. Bài học phương pháp

1. **Survivor bias.** Chính tiền đề của C là survivor: pool "còn sống" sau 30 phút hoá ra là pool vừa bơm/đang xả,
   hoặc pool do dev tự tốt nghiệp nắm khoảng 79% cung. Trong G, mẫu mô phỏng cũ bỏ mất các curve chạm điều kiện
   vào rồi chết (+20,6% → +15,5%; +8,6% → +6,0% khi đưa đủ 32 curve thất bại vào). Quy tắc: tập mẫu phải gồm
   **mọi** trường hợp chạm điều kiện vào, kể cả những ca chết ngay sau đó.
2. **Median che đuôi rug.** Nhóm C2 "giá giữ + mua ròng" có median +2,8% và thắng 75%, nhưng mean −5,6% và 13% về
   0. Từ đó mọi bảng báo mean và rug_share; luật phải có mean dương ở cả hai nửa mới được đăng ký.
3. **Holdout bị tiêu.** Khi đã xem holdout thì nó chỉ còn là dữ liệu thăm dò. Chuỗi lọc chọn trên chính holdout
   trông tốt hơn khoảng 50% so với chọn trung thực (+8,76 so với +5,85 SOL). Chỉ dữ liệu sau một mốc đã commit mới
   sạch.
4. **Kiểm định bội.** Khoảng 200 ô được xem mà không hiệu chỉnh trong phép kiểm năm luật; luật PROMOTE cũ để một
   filter ngẫu nhiên đạt 17–66% số lần; khoảng 7,7/26 filter "đạt" chỉ do may; sau BH chỉ còn một filter. Dùng p
   hoán vị theo mint + BH + placebo khớp số cờ.
5. **Proxy trá hình.** Nhiều filter thực chất chỉ đo một biến rẻ hơn: EXIT2/XIN = "coin đông ví"; FADE/FACTORY =
   "đang ở tầng 13–30 SOL"; WASH ≈ động lượng; lift 47 lần của top-10 phần lớn do cơ học curve. Phải thắng các
   placebo rẻ ("curve vừa giảm", "đang ở tầng X") và kiểm trong tầng (Mantel-Haenszel).
6. **Mint là đơn vị bằng chứng**, không phải dòng. Holdout 95 dòng nhưng chỉ có 22 mint bẫy và 5 mint thắng; hơn
   thua giữa các chuỗi do 3–4 mint quyết định.
7. **Mất lệnh trên luồng sống.** Mất ngẫu nhiên 5% lệnh nhỏ làm EXIT2 bật thêm 248 cờ ma và làm 85/95 dòng holdout
   hỏng khi đòi đủ lệnh. Filter kiểu "bán nhiều hơn mua" phải chạy trên dữ liệu đã kiểm chuỗi reserve.
8. **Đo bằng khớp lệnh thật, không bằng nến.** Virtual reserve, trần bán ở SOL thật, ba biến thể lệnh mua, phí bị
   rút ngoài swap, tx MEV không swap: thiếu bất kỳ cái nào thì số sai có hệ thống. Chi phí cố định 3,5% là quá lạc
   quan.
9. **Đừng so ô khác mô hình.** Chỉ hai ô được replay; các ô ghost khác âm chủ yếu do mô hình.
10. **Chống nhìn trước.** Ô chưa tới hạn phải để trống (`now`, PR #6); đặc trưng đo tại T+30 chứ không phải 3 s sau
    (PR #16); filter chỉ đọc lệnh có slot ≤ dslot; luôn chạy `--lookahead-test`.
11. **Số tạm có thể lệch có hệ thống.** Khi kết quả thắng/thua đến với độ trễ khác nhau (G: thất bại sau 2 giờ, tốt
    nghiệp sau ≥ 25 giờ), mẫu "mọi vé đã có kết quả" thừa ca thất bại. Cố định mẫu theo thời điểm vào và chờ hết
    exit (như GS).
12. **EV lịch sử phồng vì vị trí không vào được.** Curve hoàn tất trong 60 s đầu (+61,8%) và "jump" thuộc về bundle;
    người ngoài không có vé ở đó.
13. **Ví hạ tầng và router** có mặt khắp nơi và có thể một mình tạo phần lớn số cờ. Chỉ được loại bằng luật phân loại
    ví đăng ký trước, không loại tay sau khi thấy kết quả.
14. **Con số bên ngoài phải kiểm nguồn.** Khoảng 8/13 số trong memo ban đầu cũ/sai; "86k ví mất 675K SOL" không có
    nguồn; ghi rõ [S]/[V].
15. **Kiểm độ phủ bằng nguồn độc lập.** Trước PR #3 sổ migration chỉ phủ khoảng 22% mà không ai biết; 429 không thử
    lại và tx version 1 trả null đều làm mất dữ liệu im lặng.
16. **Vận hành**: vòng lặp có thể chết im trong khi API vẫn trả lời (PR #12), nên cần supervisor, watchdog và health
    503. Redis chỉ là view: mất Redis là mất dashboard. Restart trước nửa đêm làm file không được nén.
17. **Credit quyết định tiến độ kiểm định.** Harvest dòng mới trước để bảo vệ mẫu kiểm định; khi ngân sách không đủ,
    backlog làm phán quyết trễ nhiều ngày.
18. **Đổi thước đo nhưng giữ tiêu chí.** C đổi từ nến sang fills mà giữ nguyên ngưỡng KILL/PASS; mẫu kiểm định chỉ
    gồm dòng `fills_version ≥ 2`. Không đổi ô, cỡ lệnh, chi phí hay ngưỡng sau khi thấy mẫu.

---

## 5. Dòng thời gian (UTC)

Repo có 78 commit và 27 PR, tất cả đã merge. Commit đầu e3530eb lúc 05/10 23:56Z; merge cuối là PR #27
(71c15b3) lúc 08/10 06:38:13Z.

| Mốc | Thời điểm (UTC) | Nội dung |
|---|---|---|
| Push thẳng lên main | 05/10 23:56Z → 06/10 khoảng 03:52Z | e3530eb khởi tạo. a7f7996 (00:04Z): bỏ paper trader curve-momentum (đã bị falsify), chuyển sang bộ ghi on-chain + harness kiểm định C; **đăng ký tiêu chí C**. c684b81 (00:06Z): docs/RESEARCH.md, vòng 1 chọn Early-Momentum Scalp; vòng 2 (6 agent) falsify nó (−2,7% net, 72/72 biến thể âm, 45–51% tx lỗi). bf72235 (00:44Z): deploy một image lên Bunny, scope migrations. d37f49f (03:09Z): đóng dấu build SHA, deploy tay. 17b64bf (03:46Z): xác nhận migration từ event CPI. |
| baocookin/pumphunt#1 | 06/10 02:18Z | Xác nhận migration bằng `getTransaction`, học `withdraw_authority` thật |
| baocookin/pumphunt#2 | 06/10 08:25Z | Xác nhận cả từ websocket, đếm mỗi mint một lần, nối lại socket bị im |
| baocookin/pumphunt#3 | 06/10 09:12Z | Poller thành nguồn chính (on-chain khoảng 67/giờ so với PumpPortal khoảng 35/giờ; sổ cũ chỉ phủ khoảng 22%) |
| baocookin/pumphunt#4 | 06/10 09:24Z | 205/294 fetch mất vì 429; 30 tx thua đua bị đếm nhầm → điều tốc, thử lại, no-op |
| baocookin/pumphunt#5 | 06/10 09:32Z | Tx version 1 bị trả null → `maxSupportedTransactionVersion=255` |
| baocookin/pumphunt#6 | 06/10 09:56Z | Guard `now` (sửa bias ô 24 giờ), backfill 48 giờ (đổ vào 2.151 migration), export |
| baocookin/pumphunt#7, #8 | 06/10 10:19Z, 10:40Z | Gecko 429 → gộp 30 pool/call, limiter thích ứng, nến 5 phút |
| baocookin/pumphunt#9 | 06/10 10:58Z | Tuỳ chọn key và base URL của gói CoinGecko trả phí; `/api/config` không lộ key |
| (ngoài repo) | 06/10 11:04Z | Nâng Helius lên gói Developer |
| baocookin/pumphunt#10 | 06/10 11:24Z | **Đổi thước đo sang khớp lệnh thật trên reserve PumpSwap**; ô chính 1 SOL T+30 → 1 giờ; fills 250k/ngày |
| baocookin/pumphunt#11 | 06/10 11:42Z | Cắt chi phí fills (khoảng 400 credit/pool sẽ thành khoảng 14 triệu/tháng); fills 200k |
| baocookin/pumphunt#12 | 06/10 12:03Z | Sự cố 11:33Z: poller/harvester chết im → supervisor |
| baocookin/pumphunt#13 | 06/10 14:06Z | **Fills v2**: sửa giải mã lệnh mua exact-in, quét lùi qua tx MEV, cửa sổ ≤ 15.000 tx, replay, rút phí ngoài swap; tính lại mọi dòng; fills 270k |
| baocookin/pumphunt#14 | 06/10 14:16Z | `tokenTransfer` chỉ chạy ở `finalized` |
| baocookin/pumphunt#15 | 06/10 14:29Z | Ghi nhận C KILL trên toàn quần thể; thu snapshot holder, lịch sử curve, nguồn tiền |
| baocookin/pumphunt#16 | 06/10 14:39:46Z | **Đăng ký C2, C\*, quy trình C3+** (mẫu từ 16:00Z); sửa look-ahead 3 s; watchdog |
| baocookin/pumphunt#17 | 06/10 14:42Z | Harvest dòng mới trước; tổng ngân sách 300k/ngày |
| baocookin/pumphunt#18 | 06/10 15:04Z | Ghi chú lúc đăng ký C2 (C n 98, median −3,2%; 16/42 token tốt nghiệp ≤ 5 s); `/api/export/file/<tên>` |
| baocookin/pumphunt#19 | 06/10 16:14Z | Đọc lại swap bị `tokenTransfer` bỏ sót (1/209.836) |
| baocookin/pumphunt#20 | 06/10 21:10Z | **Census launch + đăng ký S** (mẫu 2%, từ 07/10 03:00Z); lịch sử +12,0% / −7,9%; `/api/config` thôi trả URL RPC |
| baocookin/pumphunt#21 | 06/10 23:02Z | Median che đuôi rug → báo mean và rug_share; cam kết quy trình |
| baocookin/pumphunt#22 | 06/10 23:37Z | **Đăng ký G**; census lên 5%; sniper 90k, fills 210k |
| baocookin/pumphunt#23 | 07/10 00:51Z | **Đăng ký GS**; hạ kỳ vọng G xuống +5 … +12%; ăn theo BOOST −5,7% |
| baocookin/pumphunt#24 | 07/10 01:01Z | **Sửa survivor bias** (GS +8,6% → +6,0%; G trễ 3 SOL +20,6% → +15,5%) |
| baocookin/pumphunt#25 | 07/10 22:31Z | Census dừng sau trang ngắn; census 65k, fills 235k; kèm đặc trưng trigger của G (c8b479d) |
| baocookin/pumphunt#26 | 08/10 00:18Z | docs/SIEVE.md: năm luật, red team, đặc tả v1 (chỉ tài liệu) |
| baocookin/pumphunt#27 | 08/10 06:38Z | Sổ filter sống, vòng vá 1, **đăng ký PREREG-SIEVE-R1**, mã chấm đóng băng `research/sieve/` |
| Ảnh chụp cuối | 08/10 khoảng 06:45–06:50Z | Build 71c15b3 chạy từ 06:39:34Z; C/C\* KILL; C2 INSUFFICIENT; S/G/GS WAIT; sieve chưa chấm forward |

---

## 6. Việc còn dở khi tắt server và cách chạy lại

### 6.1 Trạng thái các giả thuyết và ngày phán quyết nếu chạy tiếp

| Giả thuyết | Lúc tắt | Ngày dự kiến nếu chạy tiếp | Ghi chú |
|---|---|---|---|
| C, C\* | KILL | — | Đã xong |
| C2 | INSUFFICIENT, 226/300 | Phụ thuộc backlog harvest | PASS đã bất khả [SL] |
| C3+ | Chưa có luật | Chọn khoảng 10/10; cửa sổ khám phá tới 20/10 16:00Z | Snapshot holder không bổ sung được về sau |
| S | WAIT, 645/2.000 | Khoảng 10–11/10 [SL] | Nhiều khả năng KILL theo chat [SL] |
| S2 | Chưa có luật | Chọn khoảng 9/10; thăm dò tới 21/10 03:00Z | |
| G | WAIT, 12/300 | Đọc được khoảng 16–17/10 [SL] | Ghi caveat lệch về phía thất bại |
| GS | WAIT, 7/300 | Khoảng 22/10, đọc được khoảng 23–24/10 khi hết exit [SL] | Nhiều khả năng INCONCLUSIVE |
| Sieve W1 | Chưa chấm | 15/10 02:00Z | Cần census liên tục |
| Sieve W2 | Chưa chấm | 22/10 02:00Z (quyết định thăng/huỷ đầu tiên) | |
| Luật mua B1 | Chưa bao giờ chạy | — | Cần viết PREREG-V1 và code sổ bóng |
| D | Chưa kiểm | — | |
| Công tắc tắt 60 ngày (SIEVE.md mục 4 luật 15, mục 7) | Đang đếm từ 08/10 | khoảng 07/12/2026 | Nếu tới lúc đó chưa có luật MUA nào đạt GO thì theo luật của chính dự án, bot vĩnh viễn chỉ cảnh báo và ngừng tìm tín hiệu mua trên curve. Chạy lại sau ngày này thì luật vẫn áp dụng [SL] |
| Luật thoát/cảnh báo khi đang giữ vé (đám đông xả dây chuyền, sụp muộn) | Chưa đăng ký | — | Hai kiểu bẫy lớn nhất không phủ quyết được trước D (docs/SIEVE_FILTERS.md mục 9.3) |
| Nghiên cứu cổng (rút cạn sát cổng 11,66–17,4 SOL) | Chưa làm | — | "Một nghiên cứu về cổng, không phải filter" (docs/SIEVE_FILTERS.md mục 5) |
| 8 ứng viên của nghiên cứu luật v2 (G50-RETAIL, W30, G60-LOWOVH, TOPDIP, SC, BS, OV, WX) | Chưa kiểm, chưa đăng ký | — | Mục 3.6 |
| Đặc trưng tại trigger của G (c8b479d) | Đã ghi, chưa thăm dò | — | Mục 3.3 |
| Đối chiếu số migration với Dune `pumpdotfun_solana.pump_call_migrate` | Chưa bao giờ làm | — | README dòng 117 yêu cầu làm trước khi tin số liệu [SL: không thấy kết quả ở đâu] |
| F1 carry / F2 trend Binance; lãi lỗ creator trên census; TP/SL cho pool C2 trên swap đã lưu | Chỉ là đề nghị | — | Mục 3.6 |

Nếu chạy lại sau 20/10 16:00Z (C3+) hoặc 21/10 03:00Z (S2), cửa sổ thăm dò đã đóng mà chưa có luật nào. Mọi luật
mới phải đăng ký mới, với `since` sau commit; dữ liệu cũ chỉ được dùng để thăm dò [SL theo docs/PREREG.md].

### 6.2 Công việc dở sẽ mất (chỉ nằm trong hàng đợi Redis)

- 1.626 migration chờ harvest (248 đã tới hạn), chưa có nến và fills.
- 45 snapshot holder đang chờ: **mất vĩnh viễn**, không dựng lại được.
- 188 launch trong mẫu sniper chưa được đọc.
- Cache nguồn tiền, cursor của poller/census, bộ đếm credit, bộ đếm theo giờ.

### 6.3 Dữ liệu phải tải về TRƯỚC khi tắt

Thứ tự ưu tiên: `holders-*` (không dựng lại được) → `sniper-*` (census; cần cho S/G/GS và sổ filter) →
`swaps-*` và `survivor.jsonl` (tốn credit nhất để dựng lại) → phần còn lại. Không cần bí mật nào. Để ở thư mục
riêng, ngoài repo, và đọc bằng `python3 -I`. **Không commit dữ liệu vào repo.**

```bash
BASE=https://mc-5hwosgxjn6.bunny.run
OUT=~/pumphunt-final; mkdir -p "$OUT"/files "$OUT"/redis "$OUT"/json && cd "$OUT"

# 1. Danh sách file trên volume (tên có thể khác bảng ở mục 3.1 nếu server chạy qua nửa đêm)
curl -sf "$BASE/api/files" -o json/files.json
python3 -I -c 'import json,re,sys
ok=re.compile(r"^[a-z]+(-\d{4}-\d{2}-\d{2})?\.jsonl(\.gz)?$")   # chỉ nhận tên file dữ liệu hợp lệ
names=[f["name"] for f in json.load(open(sys.argv[1]))["files"] if ok.match(f["name"])]
rank=lambda n:0 if n.startswith("holders-") else 1 if n.startswith("sniper-") else 2
print("\n".join(sorted(names, key=rank)))' json/files.json > names.txt

# 2. Mọi file dữ liệu (≈678 MB lúc chụp cuối)
while read -r f; do curl -sf -o "files/$f" "$BASE/api/export/file/$f" || echo "LỖI $f"; done < names.txt

# 3. View chỉ có trong Redis
curl -sf -o redis/survivor.csv               "$BASE/api/export/survivor.csv"
curl -sf -o redis/survivor.jsonl             "$BASE/api/export/survivor.jsonl"
curl -sf -o redis/migrations-registry.jsonl  "$BASE/api/export/migrations.jsonl"   # khác file migrations.jsonl
curl -sf -o redis/sniper-rows.json           "$BASE/api/sniper/rows?limit=5000"     # 2.953 dòng lúc chụp
curl -sf -o redis/survivor-rows.json         "$BASE/api/survivor/rows?limit=5000"
curl -sf -o redis/migrations-1000.json       "$BASE/api/migrations?limit=1000"

# 4. Mọi summary, kể cả hai bảng explore (chưa có trong ảnh chụp cuối)
for p in health stats config files survivor/summary survivor/explore sniper/summary sniper/explore graduation/summary; do
  curl -sf -o "json/$(echo "$p" | tr / -).json" "$BASE/api/$p" || echo "LỖI $p"
done
```

`/api/config` đã ẩn key, nhưng vẫn không nên đăng công khai.

**Không mở kết quả các dòng forward** (launch có t0 > 1791414202 trong `sniper-*`, và các vé S/G/GS sau 07/10
03:00Z) khi kiểm bản tải. Chỉ kiểm số byte và gzip. Với sổ filter, xem kết quả forward trước lần chấm là điều cấm
(research/sieve/README.md quy tắc 3; docs/PREREG-SIEVE-R1.md mục 1 và 11). Với S/G/GS, luật đã cố định nên xem số tạm
không đổi phán quyết, nhưng tránh mở để khỏi bị cám dỗ chọn luật mới trên chính các vé đó [SL]. Muốn dùng phần W1
dở dang (khoảng 5,7 giờ launch) thì phải commit một khối PREREG mới trước, nói rõ tuần bị cắt và lý do. Nếu không,
phần đó chỉ được coi là thăm dò.

### 6.4 Kiểm tra bản tải

```bash
cd ~/pumphunt-final
# so số byte với files.json tải cùng lúc (file đang ghi có thể lớn thêm một chút)
python3 -I -c 'import json,os
for f in json.load(open("json/files.json"))["files"]:
    p="files/"+f["name"]; print(f["name"], f["bytes"], os.path.getsize(p) if os.path.exists(p) else "THIẾU")'
for f in files/*.gz; do gzip -t "$f" || echo "HỎNG $f"; done
gzip -9 files/swaps-2026-10-06.jsonl files/sniper-2026-10-07.jsonl   # hai file lẽ ra đã được nén
gzip -9 files/portal-*.jsonl   # tuỳ chọn: portal-* (khoảng 64 MB) theo thiết kế không bao giờ được nén
```

- Các file đang ghi (ngày 08/10, `survivor.jsonl`, `migrations.jsonl`) có thể bị cắt dở dòng cuối: bỏ dòng cuối
  nếu `json.loads` lỗi, hoặc tải chúng sau cùng.
- Cách đóng băng dữ liệu mà không tốn credit (theo code, **chưa thử**): redeploy với `PH_RUN_RECORDER=false`; API
  vẫn phục vụ file và view Redis nhưng recorder không chạy.

**Nhật ký tải dữ liệu (điền khi tải xong)**

- Ngày giờ tải (UTC): …
- Nơi lưu (ổ/máy/cloud): …
- Tổng byte: … (so với 677.932.217 lúc chụp)
- Đã chạy `cd ~/pumphunt-final && sha256sum files/* redis/* json/* > SHA256SUMS` và lưu SHA256SUMS cùng chỗ: [ ]
- 6 JSON của ảnh chụp cuối đã lưu trong repo (`docs/snapshot-2026-10-08/`): [x]
- Đã xoá app/volume Bunny: [ ] ngày …
- Đã huỷ/hạ Helius và xoay key: [ ] ngày …

### 6.5 Thứ chỉ nằm ở thư mục tạm của phiên (sẽ mất)

- ~~Các file JSON của ảnh chụp cuối~~: đã lưu vào repo ở `docs/snapshot-2026-10-08/`.
- Bản sao census cục bộ (06 và 07 đầy đủ, 08 dở dang tới khoảng 01:11Z).
- Script thăm dò của SIEVE.md mục 2. `PREREG.txt` (ngưỡng F1–F14, L1–L9, M1–M6) và các file kết quả `*_out.txt` thì đã lưu vào repo, ở `docs/snapshot-2026-10-08/sieve-five-laws/`.
- 71 tóm tắt tìm kiếm của nghiên cứu luật v1, và journal của các agent v2.

Nếu muốn giữ những thứ này thì phải chép ra trước khi phiên kết thúc; file này không chứa nội dung gốc của
chúng.

### 6.6 Cách chạy lại

1. **App Bunny còn**: bật lại/redeploy trên dash.bunny.net, hoặc chạy `workflow_dispatch` của workflow deploy (cần
   `APP_ID` và `BUNNYNET_API_KEY` còn hiệu lực).
2. **App đã xoá**: tạo lại theo README bước 3–4 từ image `ghcr.io/baocookin/pumphunt:latest` (image vẫn nằm trên
   GHCR, package phải Public). Cổng 8080, volume `/data`, env `PH_REDIS_URL`, `PH_DATA_DIR=/data`,
   `PH_CHAIN_SCOPE=migrations`, `PH_SOLANA_WS_URL` (websocket Helius có key, đặt trong Bunny, không đặt trong
   repo). Cập nhật biến repo `APP_ID`. Bật health probe `/api/health`.
3. **Chạy local**: `cp .env.example .env` rồi `docker compose up --build`, mở http://localhost:8080. Phân tích
   offline: `cd bot && python -m app.analyze data/survivor.jsonl --cost_bps 500`.
4. Với Redis mới: poller quét 48 giờ migration một lần (ước khoảng 3,2k credit theo comment trong
   `bot/app/config.py`, chưa đo [SL]); census chỉ đọc trang mới nhất, không backfill (khi Redis còn cursor thì một
   lần restart liệt kê lại tối đa 30 trang, khoảng 12 giờ); dòng survivor đầu tiên có sau 25 giờ.
   **Chép file cũ lại vào `/data` không khôi phục được dashboard**, vì không có đường nạp lại vào Redis. Số cũ phải
   tính offline từ file (hàm thuần, chưa chạy thử).
5. Credit: gói Helius Developer ($49, 10 triệu/tháng); trần 235k + 65k/ngày (khoảng 9 triệu/tháng) cộng recorder
   khoảng 5k/ngày. Muốn hết backlog thì cần thêm khoảng 1,5 triệu credit/tháng hoặc giảm chi phí mỗi dòng 10–15%.
6. Điều kiện riêng cho từng giả thuyết khi chạy lại [SL, trừ chỗ ghi khác]:
   - **S/G/GS**: giữ nguyên code, `PREREG_S_TS`/`PREREG_G_TS` và băm mẫu. Các vé đã có chỉ còn trong file
     `sniper-*`, nên phải gộp offline. Khoảng trống lúc server tắt chỉ làm thiếu vé, nhưng cần ghi rõ khi báo cáo.
   - **Vé G/GS tốt nghiệp** cần dòng survivor (nến Gecko + swap) để có giá thoát. Swap đọc lại được qua RPC (tốn
     credit); snapshot holder thì không.
   - **Sổ filter (W1/W2)**: theo tài liệu, census phải liên tục, cùng tỷ lệ 5% và cùng code. Có khoảng trống thì kho
     danh tiếng tích luỹ của v2b bị hổng, nên nhiều khả năng cần một khối PREREG mới với mốc tuần mới. Đây là suy
     luận, tài liệu chưa ghi.
   - **C2**: có thể hoàn tất offline nếu đọc lại lịch sử swap của các migration còn thiếu.
7. Lưu ý cấu hình: cấu hình live khớp mặc định trong `bot/app/config.py`. README đã cũ ở nhiều chỗ: bảng thành phần ghi
   `PH_SNIPER_SAMPLE_PER_10K=200` (live và `.env.example` là 500), và ghi điều tốc `PH_RPC_RPS` 5/s (live là 15;
   `.env.example` cũng ghi 5, mức của gói free). Các chỗ cũ khác: (a) sơ đồ kiến trúc và bảng Harvester trong
   README ghi nến GeckoTerminal 1 phút, thực tế là 5 phút từ PR #7–#8; (b) mục "Chi phí ước tính" của README nói
   Helius free là đủ, thực tế fills và census cần gói Developer $49; (c) README mục G ghi "P(tốt nghiệp | chạm 60
   SOL) 73%, EV +21–24%", là số trước khi sửa survivor bias (xem mục 3.3); (d) docs/RESEARCH.md mục 4
   (`python -m app.backtest`, chiến lược Early-Momentum Scalp) và mục 6 (chạy paper, grid backtest, `LiveBroker`)
   đã bị bỏ khi pivot; không còn `bot/app/backtest.py`.
8. API không có xác thực, và `/api/debug/tx/<sig>` tiêu credit thật: cần lưu ý nếu chạy lại công khai.

### 6.7 Dọn hạ tầng sau khi tắt

- Quyết định xoá app và volume Bunny (chỉ sau khi đã tải và kiểm dữ liệu).
- Huỷ hoặc hạ gói Helius Developer, và xoay hoặc huỷ API key.
- Nếu xoá app thì `APP_ID` và `BUNNYNET_API_KEY` trên repo hết tác dụng; workflow deploy sẽ lỗi ở lần push lên
  `main` kế tiếp. Có thể tắt workflow đó.
- Image trên GHCR và repo vẫn còn.

### 6.8 Kiểm trước khi chạy lại (sau nhiều tháng)

pump.fun có thể đã đổi chương trình, phí, BOOST hay địa chỉ; Helius hay PumpPortal có thể đã đổi API. Không kiểm
thì decoder, giả định của census và mọi phiên bản filter đóng băng có thể hỏng mà không báo lỗi.

1. IDL pump.fun và PumpSwap còn khớp với `bot/app/anchor.py`: chạy `pytest -q` với fixture tx thật, rồi decode vài
   tx mới qua `/api/debug/tx/<sig>` (mỗi lần tốn 1 credit).
2. `withdraw_authority` còn là địa chỉ trong `bot/app/config.py` (`migration_authority`), instruction migrate vẫn
   là `migrate_v2`. Lúc tắt: `authority_static=true`, `migrate_ix=migrate_v2` (snap/stats.json).
3. Mint authority trong `bot/app/sniper.py` (`MINT_AUTHORITY`) vẫn được mọi lệnh tạo nhắc tới (đo cũ: 190/190 tx
   thành công là lệnh tạo, docs/SNIPER.md mục 6); nếu không thì census không còn đầy đủ.
4. Tham số curve (30 SOL / 1,073 tỷ token ảo, hoàn tất khoảng 85 SOL), phí 1,25%/chiều, BOOST khoảng 17,58 SOL,
   cờ mayhem, virtual reserve của PumpSwap. Có thay đổi thì làm theo tinh thần docs/SIEVE.md mục 7: treo kết luận
   cũ, chỉ dùng dữ liệu sau thay đổi.
5. Helius còn `getTransactionsForAddress` và bộ lọc `tokenTransfer` (lúc tắt: `gtfa=true`, `token_filter=true`).
   Không còn `getTransactionsForAddress` thì fills lùi về chỉ mục chữ ký + `getTransaction` (tối đa 150 tx/pool,
   tốn hơn hẳn) và census ngừng đọc curve (`harvest_once` trả 0 khi `gtfa` là False).
6. PumpPortal còn kênh miễn phí; GeckoTerminal còn trả nến 5 phút.
7. `python3 -I research/sieve/filters.py --check` phải in "frozen check: OK", và hash 4 file khớp mục 3.5.
8. Chạy lại `docs/PREREG-SIEVE-R1.md` thì phải cùng code census, cùng mẫu băm 5% (`PH_SNIPER_SAMPLE_PER_10K=500`).

---

## 7. Bản đồ tài liệu và code trong repo

| Đường dẫn | Nội dung |
|---|---|
| `README.md` | Tổng quan, kiến trúc, bảng thành phần, đo thực tế, xuất dữ liệu, chạy local, deploy Bunny (bước 3–4), chi phí, pháp lý. Lưu ý các chỗ cũ ở mục 6.6 bước 7. |
| `docs/TONG-KET-NGHIEN-CUU.md` | File này |
| `docs/snapshot-2026-10-08/` | 6 JSON của ảnh chụp cuối, cùng `sieve-five-laws/` (PREREG.txt và kết quả của phép kiểm năm luật) |
| `docs/RESEARCH.md` | Vòng nghiên cứu 1–2 và pivot, động lực của C, sửa phương pháp sang fills, cơ chế PumpSwap, đăng ký C2, thăm dò luật đặc trưng, cam kết quy trình, tóm tắt G/GS. **Chưa có số cuối của C/C\*/C2 trên fills v2** (chỉ có ở file này) |
| `docs/PREREG.md` | Đăng ký trước C, C\*, C2, quy trình luật C3+, các điều cấm |
| `docs/SNIPER.md` | Cơ chế curve, BOOST, mayhem, bằng chứng công bố, lịch sử S, slot 0, chi phí snipe, census, luật S/S2, G, GS |
| `docs/SIEVE.md` | Bot rây: năm luật, kiểm trên dữ liệu, red team, 11 luật thiếu, đặc tả v1, GO/NO-GO, kill, kiểm chứng khẳng định, nguồn |
| `docs/SIEVE_FILTERS.md` | Sổ filter sống: vòng 0, vòng vá 1, kiểu bẫy, sổ đăng ký, kế hoạch forward, quy trình tuần |
| `docs/PREREG-SIEVE-R1.md` | Khối đăng ký **ràng buộc** của sổ filter: tuần W1/W2, thống kê, placebo, định nghĩa v2b/ORPHAN/WTYPE-v1, luật thăng/giáng/huỷ, điều cấm |
| `bot/app/api.py` | FastAPI: mọi endpoint đọc/xuất, lifespan chạy recorder |
| `bot/app/recorder.py` | Các vòng lặp, supervisor, watchdog, poller, harvester |
| `bot/app/config.py` | Mọi tham số và ngân sách credit (kèm comment lý do) |
| `bot/app/anchor.py`, `events.py` | Decode event pump.fun từ IDL; kiểu dữ liệu message PumpPortal |
| `bot/app/chain_feed.py`, `feed.py`, `rpc.py` | Websocket on-chain, PumpPortal, đọc/xác nhận migration qua RPC |
| `bot/app/gecko.py` | Client GeckoTerminal có điều tốc thích ứng |
| `bot/app/pumpswap.py`, `swaps.py`, `fills.py` | Decode swap PumpSwap, tải swap qua Helius, ba mô hình khớp lệnh |
| `bot/app/survivor.py`, `prereg.py`, `explore.py`, `analyze.py` | Metric và verdict của C; giả thuyết C/C\*/C2/RULES; bảng thăm dò; CLI offline |
| `bot/app/holders.py`, `curve_history.py`, `funding.py` | Đặc trưng tại thời điểm quyết định |
| `bot/app/curve.py` | Toán bonding curve (hàm thuần) |
| `bot/app/sniper.py`, `graduation.py` | Census, mô phỏng S; tính G/GS |
| `bot/app/store.py`, `jsonl.py` | Redis/in-memory store; ghi JSONL xoay theo ngày và gzip |
| `bot/tests/` | 154 hàm test, có fixture tx thật |
| `research/sniper_launches.py` | Tái lập SNIPER.md mục 3 (cần duckdb + parquet loopholetape) |
| `research/graduation_speed.py` | Tái lập SNIPER.md mục 8–9; tham số `[level] [slip] [exit_factor]` |
| `research/sieve/` | Mã chấm đóng băng (`filters.py`, `journal.py`, `score.py`, `archetype.py`) và README (lệnh tải census, lệnh hằng tuần, quy tắc không được phá) |
| `web/app/page.tsx` | Dashboard một trang (Next.js 15, React 19), poll API mỗi 5 s |
| `Dockerfile`, `docker-compose.yml`, `bunny.json`, `.env.example` | Image, chạy local, mô tả app Bunny, biến môi trường mẫu |
| `.github/workflows/ci.yml`, `deploy.yml` | CI (ruff + pytest với Redis); build GHCR và deploy Bunny |

---

## Phụ lục A. Các chỗ số liệu lệch nhau giữa nguồn

| Chỗ lệch | Chi tiết | Cách hiểu |
|---|---|---|
| Lệnh tạo 24 giờ theo census | 55.827 (stats.json) và 55.809 (sniper_summary.json) | Hai endpoint đọc ở hai thời điểm khác nhau |
| Credit sniper hôm nay | 19.532 (stats.json) và 19.530 (sniper_summary.json, 06:48Z) | Như trên |
| Độ phủ PumpPortal | Ngày 06/10: khoảng 35/67 migration/giờ và khoảng 29k/57k lệnh tạo/ngày. Lúc chụp cuối: 90,5% migration, 86,3% lệnh tạo | Đo ở thời điểm khác nhau; chưa rõ vì sao độ phủ tăng |
| EV G vào đúng 60 SOL | +23,8% (bảng SNIPER.md) và +23,4% (chú thích) | Bảng SNIPER.md mục 8 (từ PR #22) ghi +23,8%; chú thích ¹ (PR #24) ghi dòng này "không bị ảnh hưởng (+23,4%)"; nguồn không giải thích chênh 0,4 điểm |
| Nhóm C2 "giá giữ" | `explore.py` docstring: median +0,6%, mean −9,7%. RESEARCH.md: median +2,8%, mean −5,6% | Hai định nghĩa nhóm khác nhau (docstring không có điều kiện mua ròng). Cùng kết luận |
| p của SH-DEV-1 | 0,028 (holdout) và 0,050, MH 3,45 (toàn kho, tái lập với N 2000) | Hai tập dữ liệu khác nhau |
| Điều kiện thăng hạng sieve | SIEVE_FILTERS mục 7: "≥ 20 cờ ở tầng ≥ 13 SOL". PREREG-SIEVE-R1 mục 5: "≥ 20 cờ band (≥ 11,66)" từ ≥ 8 mint bẫy và ≥ 3 creator. Luật giáng active → shadow cũng viết khác nhau | PREREG-SIEVE-R1 là bản ràng buộc |
| Tầng của P2-SWARM-VET-v1 | INFO (PREREG mục 7) và theo dõi (SIEVE_FILTERS mục 4) | PREREG là bản ràng buộc |
| Thời điểm áp dụng mức phạt 30–50 triệu của NĐ 284 | Từ 1/9/2026 (chat 05–06/10) hoặc 6 tháng sau khi có đơn vị đầu tiên được cấp phép (VnFinance) | Chưa đọc văn bản gốc; hỏi luật sư |
| Callout Rewards trả bằng gì | USDC (Invezz, CoinEx), PUMP (Bittime), không có thưởng (AInvest) | Nguồn mâu thuẫn |
| Số test | 154 hàm `def test_` và 165 test trong body PR #25 | Có lẽ pytest đếm cả ca tham số hoá |
| Kết quả C theo thời gian | 06/10 19:32Z: n 303, median −3,9%. 07/10 17:45Z: n 2.054, mean −23,6%. Cuối: n 3.093, median −3,50%, mean −27,14% | Các số trước là số tạm; số cuối là phán quyết |
| S theo thời gian | 07/10 22:10Z: n 428, mean −4,5% (KTC −7,2 … −1,7). Cuối: n 645, mean −2,72% (KTC −7,26 … +1,82) | Số tạm; cận trên KTC từng < 0 rồi lại > 0 |
| Thời điểm PR #25 | Merge 22:31:54Z (git log); bản 0c26f86 chạy trên production khoảng 22:33Z (chat) | Không mâu thuẫn: một mốc là merge, một mốc là deploy |
| In chữ "MUA" | SIEVE.md mục 5: được in [MUA THỬ] sau khi sổ bóng đạt GO. SIEVE_FILTERS mục 7.9 và research/sieve/README quy tắc 7 (cùng PR #27 với PREREG-SIEVE-R1): không bao giờ in "MUA", không chia sẻ tín hiệu | Bản sau (PR #27) và lập trường chỉ nghiên cứu được áp dụng |
