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
    fills_full_window_min: int = 120  # every swap in this window after migration is fetched
    fills_max_swaps: int = 400  # cap on transactions fetched per pool inside that window
    fills_max_pages: int = 25  # signature pages (1000 each) per pool
    fills_daily_credits: int = 250_000  # RPC credits the harvester may spend per UTC day
    fill_sizes_sol: list[float] = [0.5, 1, 2, 5]
    fill_tx_fee_sol: float = 0.001  # base + priority fee per transaction, two per round trip
    fill_latency_s: float = 3  # decision to landed transaction

    # --- survivor-entry hypothesis (C) ---
    entry_delays_min: list[int] = [0, 5, 15, 30, 60]
    horizons_min: list[int] = [60, 360, 1440]
    # Fixed round-trip cost: 1.25% x2 curve/PumpSwap-tier fees + priority/Jito + slippage.
    # Research range 3.0-3.5%; one live bot measured 9.5% all-in on fresh tokens.
    cost_bps_round_trip: int = 350


settings = Settings()
