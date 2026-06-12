from dataclasses import dataclass
from typing import Literal

import pandas as pd

from .indicators import add_smas


Signal = Literal["long", "short", "flat"]


@dataclass
class Decision:
    signal: Signal
    reason: str


def latest_signal(df: pd.DataFrame, fast: int, slow: int) -> Decision:
    """Return the signal implied by the last closed candle.

    Rule:
      - long when fast SMA crosses above slow SMA
      - short when fast SMA crosses below slow SMA
      - flat otherwise
    """
    if len(df) < slow + 2:
        return Decision("flat", "not enough history")

    enriched = add_smas(df, fast, slow)
    prev = enriched.iloc[-2]
    curr = enriched.iloc[-1]

    fast_col, slow_col = f"sma_{fast}", f"sma_{slow}"

    prev_diff = prev[fast_col] - prev[slow_col]
    curr_diff = curr[fast_col] - curr[slow_col]

    if pd.isna(prev_diff) or pd.isna(curr_diff):
        return Decision("flat", "indicator not ready")

    if prev_diff <= 0 < curr_diff:
        return Decision("long", f"fast crossed above slow at {curr.name}")
    if prev_diff >= 0 > curr_diff:
        return Decision("short", f"fast crossed below slow at {curr.name}")

    return Decision("flat", "no cross")


def position_size(balance_usdt: float, price: float, risk_pct: float) -> float:
    """Very simple sizing: notional = balance * risk_pct, amount = notional / price."""
    notional = balance_usdt * (risk_pct / 100.0)
    return notional / max(price, 1e-9)
