# pumphunt

**Không phải bot mua token.** Đây là bộ ghi dữ liệu on‑chain pump.fun có slot + harness nghiên cứu để trả lời một câu hỏi cụ thể, với tiêu chí giết được đăng ký trước:

> **Giả thuyết C — "survivor entry":** mua token *đã graduate* tại T+30 phút sau migration (sau khi thanh khoản đã rơi ~57% và ổn định), giữ 1h, có dương EV sau chi phí không?

Vì sao lại là câu hỏi này, và vì sao v1 (scalp momentum trên curve) bị bỏ: [`docs/RESEARCH.md`](docs/RESEARCH.md). Tóm tắt: 6 agent nghiên cứu/phản biện độc lập + fact‑check kết luận mua token mới trên curve là âm EV có cấu trúc (−2.7% net cho người vào sau 2–25 slot; 72/72 biến thể momentum âm; 45–51% tx fail), mô hình dự đoán graduation không generalize (AUROC 0.86 → 0.46 sau 14 ngày), và **Nghị định 284/2026** (hiệu lực 1/9/2026) phạt cá nhân VN giao dịch qua nhà cung cấp chưa cấp phép. Thứ khan hiếm có bằng chứng là *dữ liệu sạch có slot kéo dài >24h* — nên repo này ghi dữ liệu trước, trade sau (nếu có).

## Kiến trúc

```
Solana RPC logsSubscribe (pump.fun program) ──► anchor.py decode ──► recorder ──► Redis + JSONL
PumpPortal (free: newToken, migration)      ──► coverage counter ─┘      │
                                                                         ▼ (T+25h)
                        GeckoTerminal 1‑min OHLCV ◄── harvester ◄── migrations
                                                                         │
                                       survivor.py metrics ──► analyze.py / API ──► web/
```

| Thành phần | File | Vai trò |
|---|---|---|
| Decoder | `bot/app/anchor.py` | Decode `CreateEvent / TradeEvent / CompleteEvent / CompletePumpAmmMigrationEvent` từ log `Program data:`; discriminator + layout lấy từ IDL chính thức. Giữ raw base64 để decode lại sau. |
| Chain feed | `bot/app/chain_feed.py` | `logsSubscribe` mentions program pump.fun, có **slot**, reconnect. Public RPC chạy được; Helius free tốt hơn. |
| Portal feed | `bot/app/feed.py` | Chỉ kênh miễn phí (`subscribeNewToken`, `subscribeMigration`) để đo **coverage** so với chain. |
| Recorder | `bot/app/recorder.py` | Đếm theo giờ, registry migration (mint, pool, slot), JSONL thô cho mọi message. |
| Harvester | `bot/app/gecko.py`, `recorder.py` | Sau 25h, kéo nến 1 phút 24h đầu của pool PumpSwap (địa chỉ pool có sẵn trong event migrate). |
| Metrics | `bot/app/survivor.py` | Return net theo (delay vào × thời gian giữ), max drawdown, volume buckets, lottery detector, **verdict đăng ký trước**. |
| CLI | `bot/app/analyze.py` | Bảng kết quả từ `survivor.jsonl`, `--cost_bps` để stress chi phí. |
| API | `bot/app/api.py` | `/stats /migrations /survivor/summary /survivor/rows /config`. |
| Dashboard | `web/` | Next.js, poll API 5s. |
| Curve math | `bot/app/curve.py` | Giữ lại cho mô phỏng fill trên curve (có test). |

## Chạy

```bash
cp .env.example .env     # đặt PH_SOLANA_WS_URL = Helius free key nếu có
docker compose up --build
# API http://localhost:8080  ·  dashboard http://localhost:3000  ·  dữ liệu trong volume botdata (/data)
```

Không Docker:

```bash
cd bot && pip install -r requirements-dev.txt
PH_REDIS_URL= uvicorn app.api:app --port 8080      # in‑memory store
cd ../web && npm install && npm run dev
```

Kiểm tra: `cd bot && ruff check . && pytest -q`.

## Tiêu chí giết (đăng ký trước, ô T+30m → 1h, net 3.5% round‑trip)

| Kết quả | Điều kiện |
|---|---|
| INSUFFICIENT | n < 300 |
| KILL | median net ≤ −1.25% **hoặc** top 2% tên chiếm ≥ 50% tổng lãi (hình vé số) |
| PASS | median net > +2% **và** win rate ≥ 45% |
| INCONCLUSIVE | còn lại |

Chạy `python -m app.analyze data/survivor.jsonl --cost_bps 500` để xem kết quả đổ vỡ ở mức chi phí nào. Verdict không được chỉnh sau khi thấy dữ liệu.

## Dữ liệu sinh ra (`/data`)

* `raw_chain.jsonl` — mọi `logsNotification` (slot, signature, logs) — tái decode được.
* `raw_portal.jsonl` — mọi message PumpPortal.
* `migrations.jsonl` — một dòng/graduation: mint, pool, slot, ts, SOL vào pool.
* `survivor.jsonl` — một dòng/token đã harvest: cells return, mdd, volume, reserve.

Đây là tài sản chính của repo. Đối chiếu đếm create hàng giờ với Dune (`pumpdotfun_solana.pump_call_create`) trước khi tin bất kỳ con số nào.

## Pháp lý (Việt Nam)

Nghị định 284/2026/NĐ‑CP (16/7/2026, hiệu lực 1/9/2026): cá nhân giao dịch tài sản mã hóa không qua tổ chức được Bộ Tài chính cấp phép bị phạt 30–50 triệu VND; thu thập/bán dữ liệu tài khoản trái phép 150–200 triệu. Repo này **chỉ ghi dữ liệu công khai on‑chain và không đặt lệnh**. Hỏi luật sư trước khi (a) giao dịch thật từ VN hoặc (b) bán dữ liệu có thông tin ví.

## Deploy (Bunny Magic Containers)

`.github/workflows/deploy.yml` build 2 image lên GHCR rồi cập nhật tag trên app. Cần `BUNNYNET_API_KEY`, `APP_ID`, `DASHBOARD_API_URL`; sửa `REPLACE_OWNER` trong `bunny.json`. Volume `/data` nên ≥4 GB (raw chain stream ~1–2 GB/ngày ở 40k launch/ngày).
