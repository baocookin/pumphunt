"""Runtime configuration (env vars / .env, prefix PH_)."""

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="PH_", extra="ignore")

    # --- infra ---
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

    # Secondary feed (coverage check + migration fallback). Free channels, no API key needed.
    pumpportal_enabled: bool = True
    pumpportal_ws_url: str = "wss://pumpportal.fun/api/data"
    pumpportal_api_key: str | None = None

    # --- harvester: post-migration candles from GeckoTerminal (free, ~30 req/min) ---
    gecko_base_url: str = "https://api.geckoterminal.com/api/v2"
    gecko_rpm: int = 25
    harvest_after_s: float = 25 * 3600  # wait until the 24h window is fully observable
    harvest_interval_s: float = 300
    harvest_batch: int = 20

    # --- survivor-entry hypothesis (C) ---
    entry_delays_min: list[int] = [0, 5, 15, 30, 60]
    horizons_min: list[int] = [60, 360, 1440]
    # Fixed round-trip cost: 1.25% x2 curve/PumpSwap-tier fees + priority/Jito + slippage.
    # Research range 3.0-3.5%; one live bot measured 9.5% all-in on fresh tokens.
    cost_bps_round_trip: int = 350


settings = Settings()
