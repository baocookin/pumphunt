"""Executable fills on PumpSwap, simulated from real pool states.

The candle-based metrics ask "what did the price do". These ask "what would a position of
S SOL have returned, executed on-chain": the pool's reserves at the moment of entry decide
how many tokens S buys, the reserves at exit decide how much SOL those tokens sell for, and
the pool's own fee schedule applies on both legs. Latency is modelled by executing against
the state `latency_s` after the decision time.

Curve (verified to the lamport against mainnet swaps, see tests), with E = Q + V the pool's
effective quote reserves (Q real SOL in the vault, V the signed virtual quote reserves):
    buy : base_out  = B * q / (E + q),   q = SOL into the curve, fees added on top
    sell: quote_out = E * b / (B + b),   fees taken out of quote_out
A sell never pays more than the real vault holds: V is pricing-only (PumpSwap error 6063
InsufficientRealQuoteReserves), so a pool drained of real SOL but carrying virtual reserves
quotes a price nobody can exit at. Every sell here is capped at Q.

Three execution models, reported side by side:
  ghost   : the market forgets our trade, the exit is priced on the real exit state.
            Pessimistic: our own SOL is not in the pool when we sell.
  persist : our trade's effect on the pool is added to the real exit state.
            Optimistic: nobody else reacts to or trades against our position.
  replay  : our buy is inserted into the real sequence of swaps, every later swap is
            re-executed with its real input amount against the modified pool, and we sell at
            exit. Needs every swap between entry and exit; the primary estimate when available.
"""

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Any

from .pumpswap import Swap

BPS = 10_000
LAMPORTS = 1_000_000_000
ZERO_KEY = "11111111111111111111111111111111"


def size_key(size: float) -> str:
    """Stable dict key for a position size: 1 and 1.0 are both "1"."""
    return f"{float(size):g}"


def fee(amount: int, bps: int) -> int:
    """PumpSwap rounds every fee component up."""
    return -(-amount * bps // BPS)


@dataclass(frozen=True)
class PoolState:
    base: int
    quote: int  # real SOL in the quote vault (lamports)
    virtual: int  # signed virtual quote reserves: pricing only, never paid out
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
    def effective(self) -> int:
        """Quote reserves the price is computed on; never negative per the program's guarantee."""
        return max(0, self.quote + self.virtual)

    @property
    def liquidity_sol(self) -> float:
        return self.effective / LAMPORTS

    @property
    def real_sol(self) -> float:
        return self.quote / LAMPORTS

    @property
    def mark(self) -> float:
        """SOL per raw token unit."""
        return self.effective / self.base if self.base else 0.0


def _pre(s: Swap) -> PoolState:
    return PoolState(s.base_pre, s.quote_pre, s.virtual_quote, s.lp_bps, s.protocol_bps, s.creator_bps, s.ts)


def _post(s: Swap) -> PoolState:
    return PoolState(
        s.base_post, s.quote_post, s.virtual_quote, s.lp_bps, s.protocol_bps, s.creator_bps, s.ts
    )


def state_at(swaps: Sequence[Swap], t: float) -> PoolState | None:
    """Pool state in force at time t: after the last swap at or before t; before the first swap,
    the first swap's pre-state (the pool's initial state when swaps start at creation)."""
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


def decision_state(swaps: Sequence[Swap], t: float) -> dict[str, Any] | None:
    """The pool as a trader saw it at the decision time t (no execution latency): real and
    virtual SOL, effective liquidity, mark price and seconds since the last swap."""
    st = state_at(swaps, t)
    if st is None:
        return None
    traded = [s.ts for s in swaps if s.ts <= t]
    return {
        "real_sol": st.real_sol,
        "virtual_sol": st.virtual / LAMPORTS,
        "liquidity_sol": st.liquidity_sol,
        "mark": st.mark,
        "last_trade_age_s": (t - max(traded)) if traded else None,
    }


def curve_buy(state: PoolState, q: int) -> tuple[int, PoolState]:
    """Put `q` lamports into the curve (fees already set aside). Returns (tokens_out, new state)."""
    eff = state.effective
    if q <= 0 or eff + q <= 0 or state.base <= 0:
        return 0, state
    tokens = state.base * q // (eff + q)
    _, lp = state.fees_on(q)
    return tokens, replace(state, base=state.base - tokens, quote=state.quote + q + lp)


def buy(state: PoolState, budget_lamports: int) -> tuple[int, PoolState, int]:
    """Spend `budget_lamports` in total (curve input + fees on top). Returns (tokens_out, new state, fees)."""
    q = budget_lamports * BPS // (BPS + state.fee_bps)
    while q > 0 and q + state.fees_on(q)[0] > budget_lamports:
        q -= 1
    tokens, new = curve_buy(state, q)
    return tokens, new, budget_lamports - q


def sell_ex(state: PoolState, tokens: int) -> tuple[int, PoolState, int, bool]:
    """Sell `tokens`. Returns (lamports received after fees, new state, fees, capped): `capped`
    when the curve asked for more SOL than the real vault holds and the payout was cut to it."""
    if tokens <= 0 or state.base + tokens <= 0:
        return 0, state, 0, False
    gross = state.effective * tokens // (state.base + tokens)
    capped = gross > state.quote
    if capped:
        gross = max(0, state.quote)
    fees, lp = state.fees_on(gross)
    new = replace(state, base=state.base + tokens, quote=state.quote - gross + lp)
    return gross - fees, new, fees, capped


def sell(state: PoolState, tokens: int) -> tuple[int, PoolState, int]:
    """Sell `tokens`. Returns (lamports received after fees, new state, fees)."""
    received, new, fees, _ = sell_ex(state, tokens)
    return received, new, fees


def apply_swap(state: PoolState, s: Swap) -> PoolState:
    """Re-execute a real swap against a (counterfactual) pool: same curve input for a buy, same
    tokens in for a sell, the swap's own fee schedule and virtual reserves. Instructions route
    fees differently (one keeps most of them in the vault); whatever the real swap left in the
    vault beyond the classic rule is left in the counterfactual vault too. On the real
    pre-state this reproduces the real post-state exactly (see tests)."""
    st = replace(
        state,
        virtual=s.virtual_quote,
        lp_bps=s.lp_bps,
        protocol_bps=s.protocol_bps,
        creator_bps=s.creator_bps,
    )
    if s.side == "buy":
        # exact-in buys price their tokens on one lamport less than they put in (measured)
        q = s.quote_amount - (1 if s.ix_name.startswith("buy_exact_quote_in") else 0)
        _, new = curve_buy(st, q)
        # a buy's vault change depends only on its input, not on the pool
        return replace(new, quote=st.quote + (s.quote_post - s.quote_pre), ts=s.ts)
    _, new, _, _ = sell_ex(st, s.base_amount)
    extra = (s.quote_post - s.quote_pre) - (s.lp_fee - s.quote_amount)
    return replace(new, quote=new.quote + extra, ts=s.ts)


def simulate_cell(
    swaps: Sequence[Swap],
    t_in: float,
    t_out: float,
    budget_lamports: int,
    tx_fee_lamports: int,
    latency_s: float,
    replay_swaps: Sequence[Swap] | None = None,
) -> dict[str, Any] | None:
    """One position: buy `budget_lamports` at t_in, sell everything at t_out.

    `swaps` holds at least the swaps that fix the pool state at entry and exit. `replay_swaps`,
    when given, must hold every swap between entry and exit; it enables the replay model."""
    t_a, t_b = t_in + latency_s, t_out + latency_s
    s_in = state_at(swaps, t_a)
    s_out = state_at(swaps, t_b)
    if s_in is None or s_out is None:
        return None
    tokens, post_in, fees_in = buy(s_in, budget_lamports)
    if tokens <= 0:
        return None
    cost = budget_lamports + 2 * tx_fee_lamports

    # ghost: the real exit state, our SOL not in it
    g_recv, _, g_fees, g_cap = sell_ex(s_out, tokens)
    g_worst = g_recv
    for s in swaps:
        if t_a < s.ts <= t_b:
            v, _, _, _ = sell_ex(_post(s), tokens)
            g_worst = min(g_worst, v)

    # persist: our buy's change to the pool carried to the real exit state
    p_recv = None
    if s_out.base - tokens > 0:
        delta_quote = post_in.quote - s_in.quote
        p_state = replace(s_out, base=s_out.base - tokens, quote=s_out.quote + delta_quote)
        p_recv, _, _, _ = sell_ex(p_state, tokens)

    # replay: our buy inserted into the real sequence. Reserves that moved between two real
    # swaps without a swap (fees swept out of the vault, transfers in) move ours the same way.
    r = None
    if replay_swaps is not None:
        st = post_in
        real_base, real_quote = s_in.base, s_in.quote
        worst = None
        n = 0
        for s in replay_swaps:
            if t_a < s.ts <= t_b:
                st = replace(
                    st, base=st.base + s.base_pre - real_base, quote=st.quote + s.quote_pre - real_quote
                )
                st = apply_swap(st, s)
                real_base, real_quote = s.base_post, s.quote_post
                n += 1
                v, _, _, _ = sell_ex(st, tokens)
                worst = v if worst is None else min(worst, v)
        r_recv, _, r_fees, r_cap = sell_ex(st, tokens)
        worst = r_recv if worst is None else min(worst, r_recv)
        r = {"recv": r_recv, "fees": r_fees, "capped": r_cap, "worst": worst, "n": n}

    if r is not None:
        recv, fees_out, capped, worst, model = r["recv"], r["fees"], r["capped"], r["worst"], "replay"
    else:
        recv, fees_out, capped, worst, model = g_recv, g_fees, g_cap, g_worst, "ghost"
    mark_in, mark_out = s_in.mark, s_out.mark
    return {
        "net": recv / cost - 1,  # primary: SOL back per SOL risked under `model`
        "model": model,
        "net_ghost": g_recv / cost - 1,
        "net_persist": (p_recv / cost - 1) if p_recv is not None else None,
        "net_replay": (r["recv"] / cost - 1) if r is not None else None,
        "replayed_swaps": r["n"] if r is not None else None,
        "gross_mark": (mark_out / mark_in - 1) if mark_in else None,  # the market's own move
        "impact_in": (budget_lamports - fees_in) / s_in.effective if s_in.effective else None,
        "liquidity_in_sol": s_in.liquidity_sol,
        "real_in_sol": s_in.real_sol,
        "base_in": s_in.base,  # with the line above: the pool at entry, before our buy
        "pool_fees_bps": [s_in.lp_bps, s_in.protocol_bps, s_in.creator_bps],
        "virtual_in_sol": s_in.virtual / LAMPORTS,
        "real_out_sol": s_out.real_sol,
        "liquidity_out_sol": s_out.liquidity_sol,
        "last_trade_age_in_s": t_a - s_in.ts,
        "exit_capped": capped,
        "fees_sol": (fees_in + fees_out + 2 * tx_fee_lamports) / LAMPORTS,
        "mdd": worst / cost - 1,
        "exit_stale_s": t_b - s_out.ts,
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
    replay_swaps: Sequence[Swap] | None = None,
    replay_range: tuple[float, float] | None = None,
) -> dict[str, Any]:
    """{cell: {size: result}} for every entry delay x horizon x position size.

    A cell is replayed when [entry, exit] (latency included) lies inside `replay_range`, the
    time span over which `replay_swaps` is known to hold every swap of the pool."""
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
            rs = None
            if replay_swaps is not None and replay_range is not None:
                lo, hi = replay_range
                if lo <= t_in + latency_s and t_out + latency_s <= hi:
                    rs = replay_swaps
            out[key] = {
                size_key(size): simulate_cell(
                    swaps, t_in, t_out, int(size * LAMPORTS), tx_fee, latency_s, replay_swaps=rs
                )
                for size in sizes_sol
            }
    return out


def flow_features(swaps: Sequence[Swap], t_end: float, span_s: float = 300) -> dict[str, Any]:
    """What the pool's order flow looked like in the `span_s` seconds before a decision at `t_end`.
    Needs every swap of that span (a complete window), otherwise the counts undercount."""
    sel = [s for s in swaps if t_end - span_s < s.ts <= t_end]
    buys = [s for s in sel if s.side == "buy"]
    sells = [s for s in sel if s.side == "sell"]
    creator = next((s.coin_creator for s in swaps if s.coin_creator and s.coin_creator != ZERO_KEY), None)
    by_seller: Counter[str] = Counter()
    for s in sells:
        by_seller[s.user] += s.quote_amount
    sold = sum(by_seller.values())
    last = max((s.ts for s in swaps if s.ts <= t_end), default=None)
    buy_sol = sum(s.quote_amount for s in buys) / LAMPORTS
    sell_sol = sold / LAMPORTS
    return {
        "span_s": span_s,
        "swaps": len(sel),
        "buys": len(buys),
        "sells": len(sells),
        "traders": len({s.user for s in sel}),
        "buyers": len({s.user for s in buys}),
        "buy_sol": buy_sol,
        "sell_sol": sell_sol,
        "net_sol": buy_sol - sell_sol,
        "top_seller_share": (max(by_seller.values()) / sold) if sold else 0.0,
        "creator": creator,
        "creator_sell_sol": (
            sum(s.quote_amount for s in sells if creator and s.user == creator) / LAMPORTS if creator else 0.0
        ),
        "last_trade_age_s": (t_end - last) if last is not None else None,
    }
