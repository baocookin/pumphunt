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
| Portal feed | `bot/app/feed.py` | Kênh miễn phí (`subscribeNewToken`, `subscribeMigration`): đếm coverage + nguồn migration dự phòng. |
| RPC confirm | `bot/app/rpc.py` | Mỗi migration PumpPortal báo → `getTransaction(signature)` (1 credit) → decode event lấy **pool + slot** từ chain, đọc `withdraw_authority` thật từ instruction `migrate`/`migrate_v2` và tự re‑subscribe feed nếu địa chỉ đoán sai. |
| Recorder | `bot/app/recorder.py` | Đếm theo giờ, registry migration (mint, pool, slot), JSONL xoay theo ngày. |
| Harvester | `bot/app/gecko.py`, `recorder.py` | Sau 25h, kéo nến 1 phút 24h đầu của pool PumpSwap; tự tra pool theo mint nếu chỉ thấy qua PumpPortal. |
| Metrics | `bot/app/survivor.py` | Return net theo (delay vào × thời gian giữ), max drawdown, độ cũ của giá thoát, volume buckets, lottery detector, **verdict đăng ký trước**. |
| CLI | `bot/app/analyze.py` | Bảng kết quả từ `survivor.jsonl`, `--cost_bps` để stress chi phí. |
| API + static | `bot/app/api.py` | `/api/health /api/stats /api/migrations /api/survivor/summary /api/survivor/rows /api/config`; `/` = dashboard. |
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

## Dữ liệu sinh ra (`/data`)

* `chain-YYYY-MM-DD.jsonl` — mọi event pump.fun decode được từ RPC (slot, signature; trade dạng compact ở scope `full`).
* `portal-YYYY-MM-DD.jsonl` — mọi message PumpPortal.
* `migrations.jsonl` — một dòng/lần thấy graduation (nguồn chain hoặc portal; dòng chain có pool).
* `survivor.jsonl` — một dòng/token đã harvest: cells return, mdd, `exit_stale_s`, volume, reserve.

Đây là tài sản chính của repo. Đối chiếu đếm migration hàng giờ (chain vs PumpPortal vs RPC‑confirm, và với Dune `pumpdotfun_solana.pump_call_migrate`) trước khi tin bất kỳ con số nào.

## Đọc trạng thái (`/api/stats` → `status`)

* `chain_feed.connected / subscribed / notifications`: WebSocket đã nối, số subscription được RPC xác nhận, số notification nhận. `notifications = 0` kéo dài trong khi `counts.portal_migrate` tăng = địa chỉ đang subscribe không nằm trong tx migrate.
* `rpc.confirmed / failed / no_event`: số migration PumpPortal được xác nhận on‑chain. `rpc.withdraw_authority` là địa chỉ thật đọc từ tx; `authority_static=false` nghĩa là nó được nạp qua address‑lookup‑table và `logsSubscribe` không thể theo dõi — khi đó đường RPC‑confirm là nguồn slot/pool chính, vẫn đủ cho giả thuyết C.
* `mentions`: danh sách địa chỉ feed đang subscribe (sau khi tự học).

## Pháp lý (Việt Nam)

Nghị định 284/2026/NĐ‑CP (16/7/2026, hiệu lực 1/9/2026): cá nhân giao dịch tài sản mã hóa không qua tổ chức được Bộ Tài chính cấp phép bị phạt 30–50 triệu VND; thu thập/bán dữ liệu tài khoản trái phép 150–200 triệu. Repo này **chỉ ghi dữ liệu công khai on‑chain và không đặt lệnh**. Hỏi luật sư trước khi (a) giao dịch thật từ VN hoặc (b) bán dữ liệu có thông tin ví.
