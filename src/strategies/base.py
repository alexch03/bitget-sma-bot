from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal

import pandas as pd


Signal = Literal["long", "short", "flat"]


@dataclass
class Decision:
    signal: Signal
    reason: str


class Strategy(ABC):
    """Base class for pluggable strategies."""

    name: str = "base"

    @abstractmethod
    def signal(self, df: pd.DataFrame) -> Decision:
        """Return the signal implied by the last closed candle."""

    @abstractmethod
    def warmup(self) -> int:
        """Minimum candles required before the strategy can fire a non-flat signal."""
