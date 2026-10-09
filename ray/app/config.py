"""Runtime configuration: environment variables (prefix RAY_), a few read from the old PH_ names.

The Bunny app of the research recorder already holds the Helius websocket URL with its key
(PH_SOLANA_WS_URL) and the data directory (PH_DATA_DIR); the scorer reuses them when its own
variables are not set, so a redeploy into the same app needs no new secret except RAY_PASSWORD.
With no RPC URL at all it reads the public Solana RPC, which also serves getTransactionsForAddress
(checked 09/10/2026), more slowly.
"""

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .rpc import http_url_from_ws

PUBLIC_RPC = "https://api.mainnet-beta.solana.com"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="RAY_", extra="ignore")

    build_sha: str = "dev"  # stamped by the Docker build; shown in /api/health
    # HTTP Basic password for the dashboard and the API (any user name). Unset: they answer 503.
    password: str | None = None
    # HTTPS RPC URL serving getTransactionsForAddress (Helius, with its key). Unset: PH_SOLANA_WS_URL
    # turned into https, else the public Solana RPC.
    rpc_url: str | None = Field(None, validation_alias=AliasChoices("RAY_RPC_URL", "PH_SOLANA_HTTP_URL"))
    legacy_ws_url: str | None = Field(None, validation_alias=AliasChoices("PH_SOLANA_WS_URL"))
    data_dir: str = Field("data", validation_alias=AliasChoices("RAY_DATA_DIR", "PH_DATA_DIR"))
    run_engine: bool = True

    # Request starts per second; unset: 10 on a private RPC, 2.5 on the public one (it answers 429
    # from about 3 a second).
    rpc_rps: float | None = None
    rpc_429_penalty_s: float = 2.0
    # Credits per UTC day. Scoring reads stop here; the census and the reserve reads may go 25% over.
    # 300k a day fits Helius Developer's 10M a month; Ray used ~240k on its first full-rate day.
    daily_credits: int = 300_000

    # Launch census: the mint authority's history, read every `census_s` (10 credits per 100 creates).
    census_s: float = 60.0
    census_backfill_s: float = 660.0  # on start, launches this old are listed again
    # Live reserves: every live curve is read in batches of 100 (1 credit per batch); curves with at
    # least `hot_min_sol` real SOL (or younger than `hot_age_s`) every `hot_poll_s`, the rest every
    # `cold_poll_s`. The poll loop wakes every `poll_tick_s`.
    poll_tick_s: float = 5.0
    hot_poll_s: float = 5.0
    cold_poll_s: float = 30.0
    hot_min_sol: float = 2.0
    hot_age_s: float = 45.0

    # Decision times after the create, in seconds: the sieve's validated ones.
    checkpoints_s: list[int] = [120, 300, 600]
    # A checkpoint is decided only within this many seconds after it (later is a missed checkpoint).
    checkpoint_late_s: float = 45.0
    # Curves below this many real SOL are scored too (no veto applies there: a 0.5 SOL ticket cannot
    # lose 50%); off by default, it would read the history of ~1,000 more launches a day.
    score_below_gate: bool = False
    # Curve transactions read per launch at most (~600 credits): busy curves carry 3,500+ in their
    # first 400 s, mostly not trades; a cut history leaves the filters that need every trade unscored.
    history_max_tx: int = 6_000
    workers: int = 4  # parallel candidate scorings (most of their time is waiting for the index)
    # Re-read the history after each of these waits until it replays to the decision read (the
    # index trails the accounts by 15-30 s on the public RPC, less on Helius).
    sync_waits_s: list[float] = [3.0, 5.0, 8.0, 10.0, 14.0]

    ondemand_per_hour: int = 60  # scores asked by mint (dashboard, Telegram)
    # Outcome journal: every full score's ticket valued 30 minutes after its entry (checked this often).
    outcome_tick_s: float = 5.0
    # How often the live rule (which filters may decide, the risk shown) is recomputed from the journal.
    rules_refresh_s: float = 600.0
    # Keep the trades of every launch scored at a decision time (rows-*.jsonl.gz, ~20 MB a day), so a
    # new filter can be run on past weeks without reading the chain again.
    archive_rows: bool = True
    keep_scores: int = 3_000  # scores kept in memory for the dashboard

    # Optional private Telegram bot: answers /score <mint> in this one chat, and can push verdicts.
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    telegram_push: list[str] = []  # verdict codes to push, e.g. ["TRANH", "KHONG_THAY_CO"]
    public_url: str | None = None  # dashboard link put in Telegram messages

    def http_url(self) -> str:
        return self.rpc_url or http_url_from_ws(self.legacy_ws_url) or PUBLIC_RPC

    def rpc_kind(self) -> str:
        """What the status shows instead of the URL (which may carry a key)."""
        url = self.http_url()
        if url == PUBLIC_RPC:
            return "public"
        return "helius" if "helius" in url else "private"

    def rps(self) -> float:
        return self.rpc_rps or (2.5 if self.rpc_kind() == "public" else 10.0)


settings = Settings()
