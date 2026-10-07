"""Runtime configuration (env vars / .env, prefix PH_)."""

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="PH_", extra="ignore")

    # --- infra ---
    build_sha: str = "dev"  # set by the Docker build; shown in /api/health and the dashboard
    redis_url: str | None = "redis://localhost:6379"
    data_dir: str = "data"
    # Static export of the Next.js dashboard, served at "/" when the directory exists.
    static_dir: str | None = None
    run_recorder: bool = True
    run_harvester: bool = True

    # Primary feed: any Solana RPC websocket. Public endpoint works but rate-limits;
    # a free Helius key (wss://mainnet.helius-rpc.com/?api-key=...) is the sane default.
    solana_ws_url: str = "wss://api.mainnet-beta.solana.com"
    # HTTP endpoint for getTransaction; derived from the websocket URL when unset.
    solana_http_url: str | None = None
    chain_commitment: str = "confirmed"
    # Reconnect when a websocket stays silent this long (dead sockets that still answer pings).
    chain_stale_s: float = 600
    pumpportal_stale_s: float = 120
    # "migrations": subscribe only to transactions mentioning pump.fun's withdraw/migration
    #   authority (~1k tx/day, a few MB/day — fits any free RPC tier).
    # "full": also subscribe to the whole pump.fun program (every create/trade,
    #   5-15 GB/day of stream — needs a paid RPC plan and a big volume).
    chain_scope: Literal["migrations", "full"] = "migrations"
    # Initial guess; the IDL does not fix this address, so the recorder learns the real one
    # from confirmed migrate transactions and re-subscribes if it differs.
    migration_authority: str = "39azUYFWPz3VHgKCf3VChUwbpURdCHRxjWVowf5jUJjg"
    # In "full" scope, trades are logged as compact rows unless this is on.
    record_raw_trades: bool = False
    # Confirm every PumpPortal migration with getTransaction (slot + pool from chain, 1 credit each).
    rpc_confirm: bool = True
    # Primary source: poll getSignaturesForAddress(authority) and confirm every successful new tx.
    # ~100 tx/h on the authority, a third of them failed migrate races that cost nothing.
    rpc_poll: bool = True
    poll_s: float = 30
    backfill_s: float = 6 * 3600  # how far back every process start walks
    # The very first start of a deployment walks further, once, so the harvester has days of
    # graduations to work on immediately instead of waiting 25h for the first row. ~1 credit per
    # successful tx (about 3.2k for 48h). Set to 0 to disable.
    initial_backfill_s: float = 48 * 3600
    rpc_concurrency: int = 4  # parallel getTransaction calls
    # Global request pace. Helius free tier allows 10/s, Developer 50/s; a 429 backs every caller off.
    rpc_rps: float = 15
    rpc_429_penalty_s: float = 2  # every caller backs off this long after a 429
    # Highest transaction version to accept from getTransaction. v1 txs exist on mainnet (2026);
    # 0 made the RPC return null for them. Any u8 is accepted, so ask for everything.
    rpc_max_tx_version: int = 255
    retry_max_attempts: int = 6  # a tx whose fetch failed is retried on later polls this many times
    retry_batch: int = 50  # failed fetches re-queued per poll

    # Secondary feed (coverage check + migration fallback). Free channels, no API key needed.
    pumpportal_enabled: bool = True
    pumpportal_ws_url: str = "wss://pumpportal.fun/api/data"
    pumpportal_api_key: str | None = None

    # --- harvester: post-migration candles from GeckoTerminal (free, ~30 req/min) ---
    # Free public GeckoTerminal API (no key). With a CoinGecko plan use the on-chain base URL
    # and key instead: https://pro-api.coingecko.com/api/v3/onchain + x-cg-pro-api-key
    # (Demo key: https://api.coingecko.com/api/v3/onchain + x-cg-demo-api-key), and raise gecko_rpm.
    gecko_base_url: str = "https://api.geckoterminal.com/api/v2"
    gecko_api_key: str | None = None
    gecko_api_key_header: str = "x-cg-pro-api-key"
    gecko_rpm: int = 20  # ceiling; the limiter adapts downward on 429s (the egress IP may be shared)
    gecko_candle_minutes: int = 5  # one call per 24h window; every tested delay/horizon is a multiple of 5
    harvest_after_s: float = 25 * 3600  # wait until the 24h window is fully observable
    # ~3 Gecko calls per row at gecko_rpm -> about 8 rows/min; the batch just bounds one cycle.
    harvest_interval_s: float = 240
    harvest_batch: int = 40

    # --- executable fills: swap-level simulation on PumpSwap reserves (needs RPC credits) ---
    fills_enabled: bool = True
    # Cells whose whole [entry, exit] window is fetched so every swap can be replayed with our
    # position in the pool (the primary estimate). Other cells use entry/exit states only and
    # report the ghost (pessimistic) and persist (optimistic) bounds.
    fills_replay_cells: list[str] = ["d30_h60", "d60_h60"]
    fills_flow_s: int = 300  # order-flow features cover this span before each replayed entry
    # Transactions per pool, not swaps: MEV bots that only read the price outnumber trades ~20:1
    # on busy pools. 40 random pools held median 13, p90 7,041, max > 31,000 transactions in
    # the replay window; 15,000 completes ~93% of windows at <= 1,500 credits (0.1 per tx).
    fills_replay_max_tx: int = 15_000
    fills_flow_max_tx: int = 3_000  # 5-minute flow window when the replay window was too big
    fills_scan_pages: int = 3  # 100-transaction pages scanned back from a decision time for a swap
    fills_token_filter: bool = True  # try Helius' tokenTransfer filter; used only once verified
    fills_max_pages: int = 40  # signature pages (1,000 each), only without getTransactionsForAddress
    # RPC credits all research reads (fills, curve history, holders, funding) may spend per UTC
    # day; the harvester pauses until the next day once reached. Measured on 07/10/2026: ~218
    # credits per SOL-quoted migration (busy C2 pools ~450), 1,250-1,300 migrations a day, so the
    # cap binds every day and the backlog grows. With the census's 65k this is 300k/day at most,
    # ~9M/month, inside the Developer plan's 10M with room for the recorder itself (~5k/day).
    fills_daily_credits: int = 235_000
    fill_sizes_sol: list[float] = [0.5, 1, 2, 5]
    fill_tx_fee_sol: float = 0.001  # base + priority fee per transaction, two per round trip
    fill_latency_s: float = 3  # decision to landed transaction

    # --- decision-time features (RPC credits, metered with the fills) ---
    # Live: the token's largest holders at each decision time (3 credits). Nothing else can
    # rebuild them later. Skipped for pools whose migration put < 1 SOL in (not tradeable).
    holder_snapshots: bool = True
    holder_snapshot_delays_min: list[int] = [30, 60]
    holder_snapshot_max_late_s: float = 300  # a snapshot taken later than this is not a decision-time one
    holder_snapshot_poll_s: float = 5
    # At harvest: how the bonding curve filled (its oldest 100 transactions + a count, ~20-60 credits)
    features_curve: bool = True
    features_curve_count_cap: int = 5_000
    # At harvest: the oldest transaction (first funder) of the creator, the creation-slot bundle and
    # the largest holders (the curve's earliest buyers when no snapshot exists), 10 credits per
    # wallet not in the 30-day cache; only for pools holding at least
    # `features_funding_min_real_sol` real SOL at the first decision time.
    features_funding_wallets: int = 8
    features_funding_min_real_sol: float = 5
    features_funding_ttl_days: int = 30

    # --- sniper sample (hypothesis S, docs/SNIPER.md) ---
    # A census of launches from the mint authority's signatures (1 credit per poll), a share of
    # them kept by a hash of the create signature, each read once its window has passed: its
    # create (1 credit) and, for a SOL curve, every curve transaction in the window (10 credits per
    # 100). 57-76k launches a day; 2% is ~1,100-1,500 launches. A busy curve costs ~140 credits
    # (1,200 transactions, measured), a quiet one 11.
    sniper_enabled: bool = True
    # 5% since hypothesis G (curves that reach 50-70 SOL are ~3% of launches); S tests its
    # registered 2%, the same hash's lower part
    sniper_sample_per_10k: int = 500
    # of the graduations a sniper can enter (dev buy < 85 SOL), 92% happen within 1 h, 95% within 2 h
    sniper_window_s: int = 7_200
    sniper_delay_s: int = 300  # read this long after the window closed (finalized, indexed)
    sniper_max_tx: int = 5_000  # transactions read per curve at most (500 credits)
    # stop a curve read after a page shorter than asked (it has always been the last one), except
    # on an audit sample (independent hash) that reads on and counts short_then_more
    sniper_stop_on_short_page: bool = True
    sniper_page_audit_per_10k: int = 200
    # ~79k/day while every read paid an empty last page; ~56k/day without it (5% sample)
    sniper_daily_credits: int = 65_000
    sniper_census_max_pages: int = 30  # after a restart: up to ~12 h of launches listed again
    sniper_poll_s: float = 60
    sniper_batch: int = 20

    # --- survivor-entry hypothesis (C) ---
    entry_delays_min: list[int] = [0, 5, 15, 30, 60]
    horizons_min: list[int] = [60, 360, 1440]
    # Fixed round-trip cost: 1.25% x2 curve/PumpSwap-tier fees + priority/Jito + slippage.
    # Research range 3.0-3.5%; one live bot measured 9.5% all-in on fresh tokens.
    cost_bps_round_trip: int = 350


settings = Settings()
