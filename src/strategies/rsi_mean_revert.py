import pandas as pd

from ..indicators import rsi
from .base import Decision, Strategy


class RSIMeanRevert(Strategy):
    """Long when RSI exits oversold, short when RSI exits overbought."""

    name = "rsi_mean_revert"

    def __init__(self, period: int = 14, oversold: float = 30, overbought: float = 70):
        if not 0 < oversold < overbought < 100:
            raise ValueError("require 0 < oversold < overbought < 100")
        self.period = period
        self.oversold = oversold
        self.overbought = overbought

    def warmup(self) -> int:
        return self.period + 5

    def signal(self, df: pd.DataFrame) -> Decision:
        if len(df) < self.warmup():
            return Decision("flat", "not enough history")

        values = rsi(df["close"], self.period)
        prev = values.iloc[-2]
        curr = values.iloc[-1]

        if pd.isna(prev) or pd.isna(curr):
            return Decision("flat", "indicator not ready")

        if prev <= self.oversold and curr > self.oversold:
            return Decision("long", f"rsi rebound from oversold at {df.index[-1]}")
        if prev >= self.overbought and curr < self.overbought:
            return Decision("short", f"rsi drop from overbought at {df.index[-1]}")

        return Decision("flat", "rsi neutral")
