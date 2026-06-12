import pandas as pd

from ..indicators import bollinger_bands
from .base import Decision, Strategy


class BollingerBreakout(Strategy):
    """Long on close breaking above upper band, short on close breaking below lower band."""

    name = "bollinger"

    def __init__(self, period: int = 20, std: float = 2.0):
        if period < 2:
            raise ValueError("period must be >= 2")
        self.period = period
        self.std = std

    def warmup(self) -> int:
        return self.period + 2

    def signal(self, df: pd.DataFrame) -> Decision:
        if len(df) < self.warmup():
            return Decision("flat", "not enough history")

        _middle, upper, lower = bollinger_bands(df["close"], self.period, self.std)
        prev_close = df["close"].iloc[-2]
        curr_close = df["close"].iloc[-1]
        prev_up, curr_up = upper.iloc[-2], upper.iloc[-1]
        prev_lo, curr_lo = lower.iloc[-2], lower.iloc[-1]

        if pd.isna(prev_up) or pd.isna(curr_up) or pd.isna(prev_lo) or pd.isna(curr_lo):
            return Decision("flat", "indicator not ready")

        if prev_close <= prev_up and curr_close > curr_up:
            return Decision("long", f"breakout above upper band at {df.index[-1]}")
        if prev_close >= prev_lo and curr_close < curr_lo:
            return Decision("short", f"breakout below lower band at {df.index[-1]}")

        return Decision("flat", "no breakout")
