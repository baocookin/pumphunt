"""Runtime configuration (env vars / .env, prefix PH_)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="PH_", extra="ignore")

    # --- infra ---
    redis_url: str | None = "redis://localhost:6379"
    data_dir: str = "data"
    run_recorder: bool = True
    run_harvester: bool = True

    # Primary feed: any Solana RPC websocket. Public endpoint works but rate-limits;
    # a free Helius key (wss://mainnet.helius-rpc.com/?api-key=...) is the sane default.
    solana_ws_url: str = "wss://api.mainnet-beta.solana.com"
    chain_commitment: str = "confirmed"

    # Secondary feed (coverage check only). Free channels, no API key needed.
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
