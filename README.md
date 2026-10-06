# pumphunt

**Không phải bot mua token.** Đây là bộ ghi dữ liệu on‑chain pump.fun có slot + harness nghiên cứu để trả lời một câu hỏi cụ thể, với tiêu chí giết được đăng ký trước:

> **Giả thuyết C — "survivor entry":** mua token *đã graduate* tại T+30 phút sau migration (sau khi thanh khoản đã rơi ~57% và ổn định), giữ 1h, có dương EV sau chi phí không?

Vì sao lại là câu hỏi này, và vì sao v1 (scalp momentum trên curve) bị bỏ: [`docs/RESEARCH.md`](docs/RESEARCH.md). Tóm tắt: 6 agent nghiên cứu/phản biện độc lập + fact‑check kết luận mua token mới trên curve là âm EV có cấu trúc (−2.7% net cho người vào sau 2–25 slot; 72/72 biến thể momentum âm; 45–51% tx fail), mô hình dự đoán graduation không generalize (AUROC 0.86 → 0.46 sau 14 ngày), và **Nghị định 284/2026** (hiệu lực 1/9/2026) phạt cá nhân VN giao dịch qua nhà cung cấp chưa cấp phép. Thứ khan hiếm có bằng chứng là *dữ liệu sạch có slot kéo dài >24h* — nên repo này ghi dữ liệu trước, trade sau (nếu có).

## Kiến trúc

```
Solana RPC logsSubscribe ──► anchor.py decode ──► recorder ──► Redis + JSONL (/data)
  (migration authority; cả program nếu scope=full)                   │
PumpPortal (free: newToken, migration) ──► coverage + fallback ──────┤
                                                                     ▼ (T+25h)
                      GeckoTerminal 1‑min OHLCV ◄── harvester ◄── migrations
                                                                     │
                       survivor.py metrics ──► /api/* ──► dashboard (Next.js static, cùng origin)
```

Một container `pumphunt` (FastAPI phục vụ cả API lẫn dashboard đã build tĩnh) + một container `redis`. Không CORS, không cần biết URL public trước khi build.

| Thành phần | File | Vai trò |
|---|---|---|
| Decoder | `bot/app/anchor.py` | Decode `CreateEvent / TradeEvent / CompleteEvent / CompletePumpAmmMigrationEvent` từ log `Program data:`; discriminator + layout lấy từ IDL chính thức. Giữ raw base64 để decode lại sau. |
| Chain feed | `bot/app/chain_feed.py` | `logsSubscribe` một subscription/địa chỉ, có **slot**, reconnect. |
| Portal feed | `bot/app/feed.py` | Kênh miễn phí (`subscribeNewToken`, `subscribeMigration`): đếm coverage + nguồn migration dự phòng. Kênh `subscribeMigration` gộp cả bonk.fun/Raydium LaunchLab; recorder lọc theo trường `pool`, chỉ ghi pump.fun (`portal_migrate_other` đếm phần còn lại). Cả hai websocket tự nối lại khi im lặng quá `PH_PUMPPORTAL_STALE_S` (120s) / `PH_CHAIN_STALE_S` (600s), vì socket chết vẫn trả lời ping. |
| Poller | `bot/app/recorder.py` | **Nguồn chính.** Mỗi 30s gọi `getSignaturesForAddress(withdraw_authority)` (1 credit) từ cursor lưu trong Redis; tx lỗi (≈1/3, bot đua migrate) bỏ qua miễn phí, tx mới chưa đường nào claim thì `getTransaction`. Khác `logsSubscribe`, index này liệt kê cả tx nạp authority qua lookup table (đo: 143/143). Khởi động lạnh hoặc mất cursor thì quét lại `PH_BACKFILL_S` (6h). |
| RPC confirm | `bot/app/rpc.py` | Mỗi tx migrate mà poller liệt kê, websocket thấy (log bị Solana cắt ở 10KB nên không decode được) hoặc PumpPortal báo → `getTransaction(signature)` (1 credit, dedup theo signature) → lấy **pool + slot** từ bản sao event qua self‑CPI, hoặc từ account của instruction `migrate`/`migrate_v2`; đọc `withdraw_authority` thật và tự re‑subscribe nếu địa chỉ đoán sai. |
| Recorder | `bot/app/recorder.py` | Đếm theo giờ, registry migration (mint, pool, slot), JSONL xoay theo ngày. |
| Harvester | `bot/app/gecko.py`, `recorder.py` | Sau 25h, kéo nến 1 phút 24h đầu của pool PumpSwap; dòng tới hạn được xử lý **mới nhất trước** (mẫu kiểm định và snapshot đang chờ không phải xếp sau tồn đọng tính lại, tồn đọng chạy bằng phần ngân sách credit còn lại); tự tra pool theo mint nếu chỉ thấy qua PumpPortal. Gecko 429 dai dẳng thì ném lỗi để thử lại chu kỳ sau (không ghi nhầm thành `no_data`); `no_data` có lý do `no_pool` / `no_candles`; ô nào vượt quá "bây giờ" thì để trống. Lần khởi động đầu tiên của một deployment, poller quét `PH_INITIAL_BACKFILL_S` (48h) một lần để harvester có việc ngay. |
| Fills (khớp lệnh thật) | `bot/app/pumpswap.py`, `fills.py`, `swaps.py` | Với mỗi pool SOL: (1) một **cửa sổ đầy đủ** mọi swap quanh các ô phát lại `PH_FILLS_REPLAY_CELLS` (mặc định T+30→T+90 và T+60→T+120, thêm 5 phút trước mỗi lần vào) qua `getTransactionsForAddress` của Helius (0,1 credit/tx; trang đầu 100 tx, quá một trang thì đếm chữ ký trước rồi mới tải, trần `PH_FILLS_REPLAY_MAX_TX`=15.000 tx); (2) nếu cửa sổ quá trần, cửa sổ 5 phút trước mỗi lần vào (`PH_FILLS_FLOW_MAX_TX`) cho order flow; (3) trạng thái pool tại mọi mốc vào/ra khác bằng **quét lùi** từ mốc đó tới khi gặp swap thật (`PH_FILLS_SCAN_PAGES` trang × 100 tx), vì giao dịch cuối trước một mốc thường là bot MEV đọc giá chứ không swap. Mô phỏng mua `PH_FILL_SIZES_SOL` SOL (trạng thái sau `PH_FILL_LATENCY_S`), bán ở mốc ra, theo ba mô hình: *ghost* (bi quan), *persist* (lạc quan), *replay* (chèn lệnh của ta vào chuỗi swap thật và thực thi lại từng swap sau đó; là ước lượng chính khi có cửa sổ đầy đủ). Lệnh bán bị chặn ở SOL thật trong vault (virtual reserve chỉ để định giá). Ba biến thể lệnh mua (`buy`, `buy_exact_quote_in`, `buy_exact_quote_in_v2`) được giải mã riêng và biến động vault đọc từ số dư token của tx: tái tạo đúng từng lamport trạng thái của swap kế tiếp (test trên tx thật). Mọi swap tải về được ghi vào `swaps-YYYY-MM-DD.jsonl` (gzip khi sang ngày). Credit đếm theo ngày, dừng ở `PH_FILLS_DAILY_CREDITS`. Không có Helius thì lùi về `getSignaturesForAddress` + `getTransaction`. |
| Đặc trưng tại thời điểm quyết định | `bot/app/holders.py`, `curve_history.py`, `funding.py` | (1) **Snapshot holder đúng giờ** (T+30, T+60 sau migration; `PH_HOLDER_SNAPSHOT_DELAYS_MIN`): 20 tài khoản token lớn nhất + chủ sở hữu + tổng cung (3 credit), chụp trực tiếp vì về sau không dựng lại được; trễ quá `PH_HOLDER_SNAPSHOT_MAX_LATE_S` thì bỏ (không còn là góc nhìn lúc quyết định). Bỏ qua pool migration < 1 SOL. Tính tỷ trọng top1/5/10 ngoài pool, số ví ≥1%, và *khả năng thoát*: SOL mà top‑10 rút được nếu bán hết vào pool đúng lúc đó (so với SOL thật). (2) **Lịch sử bonding curve** lúc harvest (100 tx đầu + đếm tx, ~20–60 credit): thời gian từ tạo tới tốt nghiệp, dev mua bao nhiêu, ví mua cùng slot tạo token (bundle), người mua 60s đầu, dev bán sớm. Event pump.fun xuất hiện hai lần (log + self‑CPI) nên được khử trùng lặp. (3) **Nguồn tiền**: giao dịch đầu tiên của dev, ví bundle và top holder (10 credit/ví, cache 30 ngày; chỉ cho pool còn ≥ `PH_FEATURES_FUNDING_MIN_REAL_SOL` SOL thật): ví mới tạo, cụm ví chung người nạp, ví liên quan dev. Snapshot ghi `holders-YYYY-MM-DD.jsonl`; mọi đặc trưng vào dòng survivor và CSV (`h30_*`, `curve_*`, `fund_*`). |
| Sniper (giả thuyết S) | `bot/app/sniper.py` | **Census mọi launch on‑chain**: mỗi 60s gọi `getSignaturesForAddress` trên mint authority của pump.fun (mọi lệnh tạo đều nhắc tới nó; 1 credit), giữ 2% theo băm chữ ký lệnh tạo (`PH_SNIPER_SAMPLE_PER_10K`=200, không phụ thuộc kết quả). Hai giờ sau mỗi launch trong mẫu: đọc lệnh tạo (1 credit), và với curve quote SOL thì đọc mọi tx thành công của curve trong 2 giờ đó (`getTransactionsForAddress`, cũ nhất trước, 10 credit/100 tx, trần `PH_SNIPER_MAX_TX`), giữ mọi trade theo thứ tự chuỗi (slot, vị trí trong block) kèm reserve sau lệnh. Mô phỏng vé mua ở cuối slot tạo+k (k = 0…40) với 11 luật thoát; ghi `sniper-YYYY-MM-DD.jsonl` (đường giá thô + kết quả), Redis giữ kết quả gọn. Ngân sách riêng `PH_SNIPER_DAILY_CREDITS` (20k/ngày). Tài liệu + đăng ký trước: [`docs/SNIPER.md`](docs/SNIPER.md). |
| Xuất dữ liệu | `bot/app/api.py` | `/api/export/survivor.csv` (một hàng mỗi token, một nhóm cột mỗi ô vào×giữ), `/api/export/survivor.jsonl`, `/api/export/migrations.jsonl`; `/api/files` liệt kê file trên volume, `/api/export/file/<tên>` tải từng file (ví dụ `swaps-2026-10-06.jsonl`, `holders-2026-10-06.jsonl`). |
| Metrics | `bot/app/survivor.py` | Return net theo (delay vào × thời gian giữ), max drawdown, độ cũ của giá thoát, volume buckets, lottery detector, **verdict đăng ký trước**. |
| CLI | `bot/app/analyze.py` | Bảng kết quả từ `survivor.jsonl`, `--cost_bps` để stress chi phí. |
| API + static | `bot/app/api.py` | `/api/health /api/stats /api/migrations /api/survivor/summary /api/survivor/rows /api/sniper/summary /api/sniper/rows /api/config`; `/` = dashboard. |
| Dashboard | `web/` | Next.js `output: "export"`, poll API 5s. |
| Curve math | `bot/app/curve.py` | Giữ lại cho mô phỏng fill trên curve (có test). |

## Phạm vi ghi (`PH_CHAIN_SCOPE`)

| Scope | Subscribe | Băng thông | Dùng khi |
|---|---|---|---|
| `migrations` (mặc định) | tx có nhắc tới `withdraw_authority` của pump.fun (~1,000 tx/ngày). IDL không cố định địa chỉ này nên bot **tự học** từ tx migrate đã xác nhận qua RPC; `PH_MIGRATION_AUTHORITY` chỉ là giá trị khởi đầu | **vài MB/ngày** | Helius free (1M credit/tháng, 20 credit/MB), Bunny |
| `full` | thêm toàn bộ program pump.fun (mọi create/trade) | **5–15 GB/ngày** | chỉ khi có RPC trả phí + volume lớn; trade ghi dạng compact (`PH_RECORD_RAW_TRADES=true` để ghi đủ) |

Giả thuyết C chỉ cần migration, nên mặc định là đủ. Số "token tạo mới" ở scope `migrations` lấy từ PumpPortal.

## Chạy local

```bash
cp .env.example .env     # dán Helius free key vào PH_SOLANA_WS_URL; đổi PORT nếu 8080 bận
docker compose up --build
# http://localhost:8080  (dashboard + /api)   ·  dữ liệu trong volume botdata (/data)
```

Không Docker (dev):

```bash
cd bot && pip install -r requirements-dev.txt
PH_REDIS_URL= uvicorn app.api:app --port 8080                 # in‑memory store
cd ../web && npm install && NEXT_PUBLIC_API_URL=http://localhost:8080 npm run dev   # :3000
# hoặc build tĩnh rồi để FastAPI phục vụ: cd web && npm run build  → bot tự tìm ../web/out
```

Kiểm tra: `cd bot && ruff check . && pytest -q`.

## Deploy lên Bunny Magic Containers

Cấu trúc mô phỏng đúng [template của Bunny](https://github.com/jamie-at-bunny/mc-template-fastapi-with-redis) (app + redis, cùng pod, nói chuyện qua `localhost`).

1. **Push lên `main`** → workflow build image `ghcr.io/<owner>/pumphunt:<sha>` và `:latest`.
2. **Đặt package GHCR thành Public**: GitHub profile → Packages → `pumphunt` → Package settings → Change visibility → Public. (Bunny kéo image không có credential.)
3. **Tạo app trên [dash.bunny.net](https://dash.bunny.net) → Magic Containers → Create App**:
   - Container `pumphunt` (tên này phải khớp `container:` trong `deploy.yml`): Registry *GitHub Container Registry*, image `ghcr.io/<owner>/pumphunt:latest`; **Endpoint** port `8080`; **Persistent Volume** mount `/data` (10 GB là dư cho scope `migrations`); env:
     - `PH_REDIS_URL=redis://localhost:6379`
     - `PH_DATA_DIR=/data`
     - `PH_CHAIN_SCOPE=migrations`
     - `PH_SOLANA_WS_URL=wss://mainnet.helius-rpc.com/?api-key=…` (free key)
   - Container `redis`: Registry *Docker Hub*, image `redis:7-alpine`; volume `/data` (tùy chọn — tài khoản trial chỉ được 1 volume/app, khi đó bỏ volume của redis; JSONL mới là dữ liệu bền, Redis chỉ là cache).
   - Confirm & deploy → nhận URL `https://mc-xxx.bunny.run` (dashboard ở `/`, API ở `/api/...`).
4. **Bật CD**: repo Settings → Variables `APP_ID` (id app trên Bunny), Secrets `BUNNYNET_API_KEY`. Từ đó mỗi push lên `main` tự cập nhật image qua `BunnyWay/actions/container-update-image`.

`bunny.json` chỉ là bản mô tả tham khảo cho các giá trị trên.

Chi phí ước tính: volume $0.10/GB/tháng; Helius free đủ cho scope `migrations` (≈ 20 credit/MB × vài MB/ngày ≪ 1M/tháng). Scope `full` sẽ đốt hết free tier trong vài ngày — đừng bật trên Bunny nếu chưa có plan trả phí.

## Tiêu chí giết (đăng ký trước, ô T+30m → 1h, net 3.5% round‑trip)

| Kết quả | Điều kiện |
|---|---|
| INSUFFICIENT | n < 300 |
| KILL | median net ≤ −1.25% **hoặc** top 2% tên chiếm ≥ 50% tổng lãi (hình vé số) |
| PASS | median net > +2% **và** win rate ≥ 45% |
| INCONCLUSIVE | còn lại |

Chạy `python -m app.analyze data/survivor.jsonl --cost_bps 500` để xem kết quả đổ vỡ ở mức chi phí nào. Verdict không được chỉnh sau khi thấy dữ liệu.

**Sniper (giả thuyết S, đăng ký 07/10/2026):** vé 0,5 SOL mua ở cuối slot tạo+2, chốt x2 / cắt 50% / bán sau 60 giây, trên launch classic quote SOL từ `2026‑10‑07 03:00 UTC`; KILL nếu cận trên KTC 95% của EV < 0, PASS nếu cận dưới > 0 và EV vẫn dương khi vào ở slot +1 và +4; cần n ≥ 2.000. Đo lịch sử trên 77k launch (9/2026): vào ngay sau dev EV +12%, vào ~1 giây sau EV −8% — lợi thế thuộc về vị trí của người tạo token. Toàn văn: [`docs/SNIPER.md`](docs/SNIPER.md).

Verdict chính hiện là ô khớp lệnh thật 1 SOL. Từ 06/10/2026 có thêm **C2** (chỉ pool giao dịch được lúc quyết định: ≥ 10 SOL thật và có swap trong 60 giây trước T+30), kiểm định *chỉ* trên migration sau `2026‑10‑06 16:00 UTC`, cùng quy trình khám phá → kiểm định cho các luật dựa trên đặc trưng. Toàn văn: [`docs/PREREG.md`](docs/PREREG.md).

## Dữ liệu sinh ra (`/data`)

* `chain-YYYY-MM-DD.jsonl` — mọi event pump.fun decode được từ RPC (slot, signature; trade dạng compact ở scope `full`).
* `portal-YYYY-MM-DD.jsonl` — mọi message PumpPortal.
* `migrations.jsonl` — một dòng/lần thấy graduation (nguồn chain hoặc portal; dòng chain có pool).
* `survivor.jsonl` — một dòng/token đã harvest: cells return, mdd, `exit_stale_s`, volume, reserve, fills, order flow, đặc trưng holder/curve/nguồn tiền.
* `swaps-YYYY-MM-DD.jsonl(.gz)` — mọi swap PumpSwap harvester đã tải cho từng pool (đủ để chạy lại mô phỏng offline).
* `holders-YYYY-MM-DD.jsonl(.gz)` — snapshot holder chụp đúng giờ quyết định.
* `sniper-YYYY-MM-DD.jsonl(.gz)` — mỗi launch trong mẫu sniper một dòng: lệnh tạo (mint, curve, dev, quote, mayhem, reserve ban đầu), mọi trade của curve trong 2 giờ đầu theo thứ tự chuỗi (`slot, tx, ev, ts, user, buy, sol, tokens, v_sol, v_tokens, ix`), lúc hoàn tất, kiểm tra chuỗi reserve, và kết quả mô phỏng (`sim`).

Đây là tài sản chính của repo. Đối chiếu đếm migration hàng giờ (chain vs PumpPortal vs RPC‑confirm, và với Dune `pumpdotfun_solana.pump_call_migrate`) trước khi tin bất kỳ con số nào.

## Đọc trạng thái (`/api/stats` → `status`)

* `chain_feed.connected / subscribed / notifications`: WebSocket đã nối, số subscription được RPC xác nhận, số notification nhận. `notifications = 0` kéo dài trong khi `counts.portal_migrate` tăng = địa chỉ đang subscribe không nằm trong tx migrate.
* `rpc.confirmed / failed / no_event`: số migration được xác nhận on‑chain qua `getTransaction`, kích hoạt bởi websocket (`rpc.triggered.chain`) hoặc PumpPortal (`rpc.triggered.portal`); `rpc.via` cho biết event đọc từ log, từ bản sao self‑CPI, hay từ account của instruction. `rpc.withdraw_authority` là địa chỉ thật đọc từ tx; `authority_static=false` nghĩa là tx đó nạp nó qua address‑lookup‑table và `logsSubscribe` không thấy. Vì người ký luôn là key tĩnh, recorder đếm `rpc.migrate_users` và tự subscribe thêm ví ký ≥80% trong ≥10 migration đã xác nhận.
* `mentions`: danh sách địa chỉ feed đang subscribe (sau khi tự học).
* `loops`: số giây kể từ lần cuối mỗi vòng lặp báo còn tiến triển. Vòng nào im quá hạn (poller 10 phút, harvester 30 phút, snapshot 5 phút, status 2 phút) bị watchdog huỷ và chạy lại; lần đó ghi vào `task_errors` là "stalled". Nếu cả recorder dừng vì lỗi, API khởi động lại nó sau 10 giây.
* `/api/health` trả **503** khi status không được cập nhật quá 2 phút (hoặc chưa từng có sau 5 phút chạy). Bật health probe của Bunny vào `/api/health` để container tự khởi động lại khi đó.

## Pháp lý (Việt Nam)

Nghị định 284/2026/NĐ‑CP (16/7/2026, hiệu lực 1/9/2026): cá nhân giao dịch tài sản mã hóa không qua tổ chức được Bộ Tài chính cấp phép bị phạt 30–50 triệu VND; thu thập/bán dữ liệu tài khoản trái phép 150–200 triệu. Repo này **chỉ ghi dữ liệu công khai on‑chain và không đặt lệnh**. Hỏi luật sư trước khi (a) giao dịch thật từ VN hoặc (b) bán dữ liệu có thông tin ví.

## Đo thực tế (06/10/2026, 145 tx migrate từ RPC công khai)

* On‑chain có ≈ **67 migration pump.fun / giờ**; PumpPortal chỉ relay ≈ 35/giờ và ≈3% message ghép sai mint vào signature. Không được dùng PumpPortal làm nguồn đếm.
* Authority ký ≈100 tx/giờ, 1/3 thất bại (nhiều bot đua gọi `migrate`, permissionless: 53 ví ký khác nhau, ví lớn nhất 32%). Không có keeper cố định để subscribe.
* `migrate_v2` chiếm 94%; ở 46% tx authority được nạp qua lookup table nên `logsSubscribe` không thấy. `getSignaturesForAddress` liệt kê đủ 100% → poller là nguồn chính.
* Event `CompletePumpAmmMigrationEvent`: trong log 31%, chỉ qua self‑CPI 66%, chỉ còn account của instruction 3% (bản `migrate` cũ, log bị cắt). Decoder cần cả ba đường.
* Pool PumpSwap có **virtual quote reserve** (ví dụ 17.6 SOL ảo bên cạnh 0.3 SOL thật): giá và trượt giá tính trên Q+V, nên thanh khoản hiệu dụng sau khi bị rút có thể chỉ ~18 SOL, lệnh 1 SOL trượt ~5% mỗi chiều. Giả định 3.5% round‑trip là lạc quan; đó là lý do có fills.
* Một số curve quote bằng stablecoin (`sol_amount` ≈ 0.02): lọc theo `quote_mint` khi phân tích.
* Bot thua cuộc đua migrate vẫn có tx *thành công*: log "Bonding curve already migrated", không CPI, không event. Chỉ tx có CPI sang PumpSwap mới là migration (đếm riêng ở `rpc.noop`).
* Mainnet đã có **transaction version 1**; `getTransaction` với `maxSupportedTransactionVersion: 0` trả null cho chúng (≈20% tx của authority), trông như "not found" trên mọi RPC. Recorder gửi `PH_RPC_MAX_TX_VERSION` (255). Cấu trúc JSON v1 giống v0 (thêm `transactionConfig`, `stackHeight`).
* GeckoTerminal từ IP egress của Bunny chỉ chấp nhận ~5–6 call/phút (IP dùng chung), kém xa 30/phút trong tài liệu. Harvester dùng nến 5 phút (cả cửa sổ 24h trong một call; mọi mốc vào/giữ đều là bội của 5 phút), gộp thông tin pool 30 cái một call, và bộ điều tốc tự thích ứng (giảm 30% mỗi 429, tăng 10% sau 20 call sạch, sàn 3/phút, trần `PH_GECKO_RPM`).
* Helius free trả 429 khi bắn hơn ~10 req/s: client điều tốc toàn cục `PH_RPC_RPS` (5/s), bị 429 thì mọi caller lùi `PH_RPC_429_PENALTY_S`; fetch hỏng được xếp hàng thử lại ở các vòng poll sau (`PH_RETRY_MAX_ATTEMPTS`), và mỗi lần khởi động poller quét lại cả cửa sổ `PH_BACKFILL_S` (dòng đã có pool không fetch lại).

