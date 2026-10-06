"""Executable fills on PumpSwap, simulated from real pool states.

The candle-based metrics ask "what did the price do". These ask "what would a position of
S SOL have returned, executed on-chain": the pool's reserves at the moment of entry decide
how many tokens S buys (price impact included), the reserves at exit decide how much SOL
those tokens sell for, and the pool's own fee schedule is applied on both legs. Latency is
modelled by executing against the state `latency_s` after the decision time.

Curve (verified to the lamport against mainnet swaps, see tests):
    buy : base_out  = B * q / (Q + V + q),   q = SOL into the curve, fees added on top
    sell: quote_out = (Q + V) * b / (B + b), fees taken out of quote_out
where V is the pool's constant virtual quote reserve.
"""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Any

from .pumpswap import Swap

BPS = 10_000
LAMPORTS = 1_000_000_000


def fee(amount: int, bps: int) -> int:
    """PumpSwap rounds every fee component up."""
    return -(-amount * bps // BPS)


@dataclass(frozen=True)
class PoolState:
    base: int
    quote: int
    virtual: int
    lp_bps: int
    protocol_bps: int
    creator_bps: int
    ts: int  # when this state became current

    @property
    def fee_bps(self) -> int:
        return self.lp_bps + self.protocol_bps + self.creator_bps

    def fees_on(self, amount: int) -> tuple[int, int]:
        """(total fees, lp share) charged on `amount` of quote."""
        lp = fee(amount, self.lp_bps)
        return lp + fee(amount, self.protocol_bps) + fee(amount, self.creator_bps), lp

    @property
    def liquidity_sol(self) -> float:
        return (self.quote + self.virtual) / LAMPORTS

    @property
    def mark(self) -> float:
        """SOL per raw token unit."""
        return (self.quote + self.virtual) / self.base if self.base else 0.0


def _pre(s: Swap) -> PoolState:
    return PoolState(s.base_pre, s.quote_pre, s.virtual_quote, s.lp_bps, s.protocol_bps, s.creator_bps, s.ts)


def _post(s: Swap) -> PoolState:
    return PoolState(
        s.base_post, s.quote_post, s.virtual_quote, s.lp_bps, s.protocol_bps, s.creator_bps, s.ts
    )


def state_at(swaps: Sequence[Swap], t: float) -> PoolState | None:
    """Pool state in force at time t: after the last swap at or before t; before the first swap,
    the first swap's pre-state (which is the pool's initial state when swaps start at creation)."""
    if not swaps:
        return None
    if t < swaps[0].ts:
        return replace(_pre(swaps[0]), ts=swaps[0].ts)
    best = None
    for s in swaps:
        if s.ts <= t:
            best = s
        else:
            break
    assert best is not None
    return _post(best)


def curve_buy(state: PoolState, q: int) -> tuple[int, PoolState]:
    """Put `q` lamports into the curve (fees already set aside). Returns (tokens_out, new state)."""
    if q <= 0 or state.quote + state.virtual + q <= 0:
        return 0, state
    tokens = state.base * q // (state.quote + state.virtual + q)
    _, lp = state.fees_on(q)
    return tokens, replace(state, base=state.base - tokens, quote=state.quote + q + lp)


def buy(state: PoolState, budget_lamports: int) -> tuple[int, PoolState, int]:
    """Spend `budget_lamports` in total (curve input + fees on top). Returns (tokens_out, new state, fees)."""
    q = budget_lamports * BPS // (BPS + state.fee_bps)
    while q > 0 and q + state.fees_on(q)[0] > budget_lamports:
        q -= 1
    tokens, new = curve_buy(state, q)
    return tokens, new, budget_lamports - q


def sell(state: PoolState, tokens: int) -> tuple[int, PoolState, int]:
    """Sell `tokens`. Returns (lamports received after fees, new state, fees)."""
    if tokens <= 0 or state.base + tokens <= 0:
        return 0, state, 0
    gross = (state.quote + state.virtual) * tokens // (state.base + tokens)
    fees, lp = state.fees_on(gross)
    new = replace(state, base=state.base + tokens, quote=state.quote - gross + lp)
    return gross - fees, new, fees


def simulate_cell(
    swaps: Sequence[Swap],
    t_in: float,
    t_out: float,
    budget_lamports: int,
    tx_fee_lamports: int,
    latency_s: float,
) -> dict[str, Any] | None:
    s_in = state_at(swaps, t_in + latency_s)
    s_out = state_at(swaps, t_out + latency_s)
    if s_in is None or s_out is None:
        return None
    tokens, _, fees_in = buy(s_in, budget_lamports)
    if tokens <= 0:
        return None
    sol_out, _, fees_out = sell(s_out, tokens)
    cost = budget_lamports + 2 * tx_fee_lamports
    # mark-to-market path for drawdown: what the position would have sold for after each swap
    worst = sol_out
    for s in swaps:
        if t_in + latency_s < s.ts <= t_out + latency_s:
            v, _, _ = sell(_post(s), tokens)
            worst = min(worst, v)
    mark_in, mark_out = s_in.mark, s_out.mark
    return {
        "net": sol_out / cost - 1,  # the number that matters: SOL back per SOL risked
        "gross_mark": (mark_out / mark_in - 1) if mark_in else None,  # price move alone
        "impact_in": (budget_lamports - fees_in) / (s_in.quote + s_in.virtual),  # fraction of liquidity taken
        "liquidity_in_sol": s_in.liquidity_sol,
        "liquidity_out_sol": s_out.liquidity_sol,
        "fees_sol": (fees_in + fees_out + 2 * tx_fee_lamports) / LAMPORTS,
        "mdd": worst / cost - 1,
        "exit_stale_s": (t_out + latency_s) - s_out.ts,
    }


def compute_fills(
    swaps: Sequence[Swap],
    t0: int,
    delays_min: Sequence[int],
    horizons_min: Sequence[int],
    sizes_sol: Sequence[float],
    tx_fee_sol: float = 0.001,
    latency_s: float = 3.0,
    now: float | None = None,
) -> dict[str, Any]:
    """{cell: {size: result}} for every entry delay x horizon x position size."""
    out: dict[str, Any] = {}
    tx_fee = int(tx_fee_sol * LAMPORTS)
    for d in delays_min:
        for h in horizons_min:
            key = f"d{d}_h{h}"
            t_in = t0 + d * 60
            t_out = t_in + h * 60
            if now is not None and t_out + latency_s > now:
                out[key] = None
                continue
            out[key] = {
                str(size): simulate_cell(swaps, t_in, t_out, int(size * LAMPORTS), tx_fee, latency_s)
                for size in sizes_sol
            }
    return out
