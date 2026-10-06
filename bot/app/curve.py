"""pump.fun bonding-curve math.

The curve is a constant-product AMM over *virtual* reserves:
    v_sol * v_tokens = k
A token starts with ~30 virtual SOL and ~1.073B virtual tokens (1B real supply,
~793M of which are sellable on the curve). The trading fee (1.25 % at the time
of writing) is taken from the SOL side on both buys and sells.

Everything here is pure functions so it can be unit-tested and reused by the
paper broker and the backtester.
"""

from dataclasses import dataclass

TOTAL_SUPPLY = 1_000_000_000
INITIAL_V_SOL = 30.0
INITIAL_V_TOKENS = 1_073_000_000.0
# Curve completes (migrates to PumpSwap) once ~85 real SOL has been collected,
# i.e. v_sol ≈ 115. We use it only to compute "progress %" for display/filters.
GRADUATION_V_SOL = 115.0


@dataclass(frozen=True)
class CurveState:
    v_sol: float
    v_tokens: float

    @property
    def price(self) -> float:
        """SOL per token."""
        return self.v_sol / self.v_tokens

    @property
    def market_cap_sol(self) -> float:
        return self.price * TOTAL_SUPPLY

    @property
    def progress_pct(self) -> float:
        done = (self.v_sol - INITIAL_V_SOL) / (GRADUATION_V_SOL - INITIAL_V_SOL)
        return max(0.0, min(100.0, done * 100))


def _fee(sol: float, fee_bps: int) -> float:
    return sol * fee_bps / 10_000


def buy(state: CurveState, sol_in: float, fee_bps: int) -> tuple[float, CurveState]:
    """Spend `sol_in` SOL (fee included). Returns (tokens_out, new_state)."""
    if sol_in <= 0:
        raise ValueError("sol_in must be > 0")
    effective = sol_in - _fee(sol_in, fee_bps)
    k = state.v_sol * state.v_tokens
    new_v_sol = state.v_sol + effective
    new_v_tokens = k / new_v_sol
    tokens_out = state.v_tokens - new_v_tokens
    return tokens_out, CurveState(new_v_sol, new_v_tokens)


def sell(state: CurveState, tokens_in: float, fee_bps: int) -> tuple[float, CurveState]:
    """Sell `tokens_in` tokens. Returns (sol_out_after_fee, new_state)."""
    if tokens_in <= 0:
        raise ValueError("tokens_in must be > 0")
    k = state.v_sol * state.v_tokens
    new_v_tokens = state.v_tokens + tokens_in
    new_v_sol = k / new_v_tokens
    gross = state.v_sol - new_v_sol
    return gross - _fee(gross, fee_bps), CurveState(new_v_sol, new_v_tokens)


def exit_value(state: CurveState, tokens: float, fee_bps: int) -> float:
    """What we'd actually receive if we dumped `tokens` right now (price impact + fee)."""
    if tokens <= 0:
        return 0.0
    sol_out, _ = sell(state, tokens, fee_bps)
    return sol_out
