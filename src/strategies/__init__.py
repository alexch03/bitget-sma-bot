from .base import Decision, Signal, Strategy
from .bollinger import BollingerBreakout
from .rsi_mean_revert import RSIMeanRevert
from .sma_crossover import SMACrossover


STRATEGIES = {
    "sma_crossover": SMACrossover,
    "bollinger": BollingerBreakout,
    "rsi_mean_revert": RSIMeanRevert,
}


def make_strategy(name: str, **kwargs) -> Strategy:
    """Instantiate a strategy from the registry by name."""
    if name not in STRATEGIES:
        raise ValueError(f"unknown strategy: {name!r}. Available: {list(STRATEGIES)}")
    return STRATEGIES[name](**kwargs)


__all__ = [
    "Decision",
    "Signal",
    "Strategy",
    "SMACrossover",
    "BollingerBreakout",
    "RSIMeanRevert",
    "STRATEGIES",
    "make_strategy",
]
