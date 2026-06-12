import pandas as pd

from ..strategy import latest_signal
from .base import Decision, Strategy


class SMACrossover(Strategy):
    """Long on fast SMA crossing above slow, short on the opposite cross."""

    name = "sma_crossover"

    def __init__(self, fast: int = 20, slow: int = 50):
        if fast >= slow:
            raise ValueError("fast must be < slow")
        self.fast = fast
        self.slow = slow

    def warmup(self) -> int:
        return self.slow + 2

    def signal(self, df: pd.DataFrame) -> Decision:
        d = latest_signal(df, self.fast, self.slow)
        return Decision(d.signal, d.reason)
